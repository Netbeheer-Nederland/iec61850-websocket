import asyncio
import logging
import time
from typing import Any

import jwt

from bff.connection.bindings import ApplicationBinding, IecClientBinding, IecServerBinding, ServerFactory
from bff.connection.profile import ConnectionProfile
from bff.connection.security import SecurityContext, SecurityFactory
from bff.connection.transports import WsClientTransport, WsServerTransport
from bff.state import RuntimeState
from ws61850.asn1.encode_decode import encode_tpaa_message
from ws61850.endpoint import ActiveEndpoint, EndpointProtocol, PassiveEndpoint
from ws61850.iec61850.client.iec61850_client import IEC61850Client
from ws61850.iec61850.client.request_handling import create_token_refresh

logger = logging.getLogger(__name__)


class ConnectionRuntime:
    def __init__(
        self,
        manager: Any,
        state: RuntimeState,
        profile: ConnectionProfile,
        target: str,
        *,
        client_cls: type[IEC61850Client],
        server_factory: ServerFactory | None,
        security_factory: SecurityFactory | None = None,
    ) -> None:
        self.manager = manager
        self.state = state
        self.profile = profile
        self.target = target
        self.client_cls = client_cls
        self.server_factory = server_factory
        self.security_factory = security_factory or SecurityFactory()
        self.transport = WsServerTransport() if profile.transport_role == "ws_server" else WsClientTransport()
        self.binding: ApplicationBinding | None = None
        self.endpoint: EndpointProtocol | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.start_task: asyncio.Task[Any] | None = None
        self.refresh_task: asyncio.Task[Any] | None = None
        self.security_context = SecurityContext()
        self.connection_watch_task: asyncio.Task[Any] | None = None

    @property
    def mode(self) -> str:
        return self.profile.endpoint_mode

    @property
    def cp(self) -> str:
        return self.profile.cp

    def _create_binding(self) -> ApplicationBinding:
        if self.profile.application_role == "iec_client":
            return IecClientBinding(self.client_cls, self.profile.cp)
        if self.server_factory is None:
            raise RuntimeError("iec-server-factory-not-configured")
        return IecServerBinding(self.server_factory(self.profile.cp))

    async def run(self) -> None:
        logger.info(
            "connection runtime starting transport_role=%s application_role=%s cp=%s",
            self.profile.transport_role,
            self.profile.application_role,
            self.profile.cp,
        )
        try:
            self.loop = asyncio.get_running_loop()
            self.security_context = await self.security_factory.build(
                self.profile.security,
                transport_role=self.profile.transport_role,
            )
            self.binding = self._create_binding()
            kwargs = dict(
                is_direct=self.profile.is_direct,
                tls_config=self.security_context.tls_config,
                oauth_enable=self.security_context.oauth_enable,
                cert_endpoint=self.security_context.certificate_url,
                token_issuer=self.security_context.token_issuer,
                kc_cert=self.security_context.kc_cert,
            )
            if self.profile.transport_role == "ws_server":
                self.endpoint = PassiveEndpoint(**kwargs)
            else:
                self.endpoint = ActiveEndpoint(**kwargs, try_reconnect=True)
            self.endpoint.send_msg_callback = lambda msg, ts: self.manager.log_message(
                "send",
                msg,
                ts,
                target=self.target,
            )
            self.endpoint.recv_msg_callback = lambda msg, ts: self.manager.log_message(
                "recv",
                msg,
                ts,
                target=self.target,
            )
            self.binding.attach(self.endpoint)
            self._initialize_state()

            self.start_task = asyncio.create_task(self.transport.start(self.endpoint, self.profile, self.security_context))
            with self.state.state_lock:
                self.state.endpoint_task = self.start_task

            if self.profile.transport_role == "ws_server" and isinstance(self.binding, IecClientBinding):
                self.connection_watch_task = asyncio.create_task(self._watch_passive_client_connection())

            if self._supports_token_refresh():
                self.refresh_task = asyncio.create_task(self._refresh_token_if_needed())
                with self.state.state_lock:
                    self.state.token_refresh_task = self.refresh_task

            await self._wait_until_ready()
            if self._is_cancelled():
                self.manager.log_action_end(self.state.connect_aid, False, "connect-cancelled", target=self.target)
                await self._disconnect_transport()
                return

            self._set_status("connected" if self.profile.transport_role == "ws_client" else "listening")
            self.manager.log_action_end(self.state.connect_aid, True, target=self.target)
            if self.start_task is not None:
                await self.start_task
            self._cleanup_runtime(cleanup_files=True)
        except asyncio.CancelledError:
            self.manager.log_action_end(self.state.connect_aid, True, extra_detail={"stopped": True}, target=self.target)
            self._cleanup_runtime(cleanup_files=True)
        except Exception as exc:
            logger.exception("connection runtime failed cp=%s", self.profile.cp)
            self._set_status("error")
            self.manager.log_action_end(self.state.connect_aid, False, str(exc), target=self.target)
            self._cleanup_runtime(cleanup_files=True)
            raise
        finally:
            if self.connection_watch_task is not None:
                self.connection_watch_task.cancel()
                await asyncio.gather(self.connection_watch_task, return_exceptions=True)
            if self.refresh_task is not None:
                self.refresh_task.cancel()
                await asyncio.gather(self.refresh_task, return_exceptions=True)

    def status(self) -> dict[str, Any]:
        binding = self.binding
        if binding is None:
            return {"state": "not-connected", "detail": {}}
        return binding.status(self.endpoint, self.loop, self.state.manual_disconnect, self.profile.transport_role)

    def ensure_connection(self, timeout: int = 10):
        binding = self.binding
        if binding is None:
            raise RuntimeError("not-connected")
        return binding.ensure_connection(self.endpoint, self.loop, timeout)

    def disconnect(self) -> str:
        if self.endpoint is None or self.loop is None or self.binding is None:
            return "no-active-connection"
        with self.state.state_lock:
            self.state.manual_disconnect = True
            self.state.cancel_connect = True
        asyncio.run_coroutine_threadsafe(self._disconnect_transport(), self.loop).result(timeout=10)
        self.binding.mark_disconnected()
        self.manager.log_action(self.binding.disconnect_message(self.profile.transport_role), "warn", target=self.target)
        self._cancel_start_task()
        self._cleanup_runtime(cleanup_files=True)
        return "disconnected"

    def _initialize_state(self) -> None:
        application = self.binding.get_application() if self.binding is not None else None
        invoke_lock = asyncio.Lock() if self.profile.application_role == "iec_client" else None
        with self.state.state_lock:
            self.state.endpoint = self.endpoint
            self.state.client = application if self.profile.application_role == "iec_client" else None
            self.state.server = application if self.profile.application_role == "iec_server" else None
            self.state.loop = self.loop
            self.state.invoke_lock = invoke_lock
            self.state.mode = self.profile.endpoint_mode
            self.state.is_direct = self.profile.is_direct
            self.state.connection_profile = self.profile
            self.state.application_role = self.profile.application_role
            self.state.security_files = list(self.security_context.temp_files)

    async def _wait_until_ready(self) -> None:
        if self.profile.transport_role == "ws_server":
            await self.transport.wait_until_listening(self.endpoint, self.start_task)
            return
        binding = self.binding
        if binding is None:
            raise RuntimeError("not-connected")
        ready = await binding.wait_for_ready(self.start_task)
        if not ready and self.start_task is not None:
            await self.start_task

    async def _disconnect_transport(self) -> None:
        if self.endpoint is None:
            return
        await self.transport.stop(self.endpoint, self.profile.cp)

    def _cancel_start_task(self) -> None:
        if self.start_task is not None and not self.start_task.done():
            self.start_task.cancel()

    def _is_cancelled(self) -> bool:
        with self.state.state_lock:
            return self.state.cancel_connect or self.state.manual_disconnect

    def _set_status(self, status: str) -> None:
        with self.state.state_lock:
            self.state.status = status

    def _cleanup_runtime(self, cleanup_files: bool) -> None:
        self.manager._clear_connection_refs(self.target, self, cleanup_files=cleanup_files)

    def _supports_token_refresh(self) -> bool:
        return (
            isinstance(self.binding, IecClientBinding)
            and self.profile.transport_role == "ws_client"
            and self.security_context.token_refresh_enabled
            and self.security_context.access_token is not None
            and self.security_context.token_request_url is not None
            and self.security_context.client_id is not None
            and self.security_context.client_secret is not None
        )

    async def _refresh_token_if_needed(self) -> None:
        assert self.endpoint is not None
        token = self.security_context.access_token
        while True:
            websocket_info = next((ws for ws in self.endpoint.websocket_info_list if ws.cp == self.profile.cp), None)
            if websocket_info is not None and token is not None:
                decoded = jwt.decode(token, options={"verify_signature": False})
                if decoded["exp"] - time.time() < 3:
                    from ws61850.security.oauth import get_access_token

                    token = await get_access_token(
                        self.security_context.token_request_url,
                        self.security_context.client_id,
                        self.security_context.client_secret,
                        self.security_context.kc_cert,
                        None,
                    )
                    refresh_token_message = create_token_refresh(websocket_info.associate_id, token)
                    encoded_message = encode_tpaa_message(refresh_token_message)
                    await websocket_info.websocket.send(encoded_message)
            await asyncio.sleep(1)

    async def _watch_passive_client_connection(self) -> None:
        assert isinstance(self.binding, IecClientBinding)
        was_connected = False
        while True:
            is_connected = bool(self.binding.client.is_connected)
            if is_connected and not was_connected:
                self.manager.log_action(
                    f"WebSocket client connected to server for cp={self.profile.cp}",
                    target=self.target,
                )
            elif was_connected and not is_connected and getattr(self.endpoint, "server", None) is not None:
                self.manager.log_action(
                    f"WebSocket client disconnected from server for cp={self.profile.cp}",
                    "warn",
                    target=self.target,
                )
            was_connected = is_connected
            await asyncio.sleep(0.2)
