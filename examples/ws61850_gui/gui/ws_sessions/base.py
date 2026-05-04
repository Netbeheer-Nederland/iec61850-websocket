from __future__ import annotations

import asyncio
import logging
import os
import ssl
import tempfile
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Optional

import jwt

from gui.state import RuntimeState
from ws61850.asn1.encode_decode import encode_tpaa_message
from ws61850.endpoint.endpoint import WebSocketEndpoint, WebSocketInfo
from ws61850.iec61850.client.iec61850_client import IEC61850Client
from ws61850.iec61850.client.request_handling import create_token_refresh
from ws61850.security.oauth import get_access_token
from ws61850.security.tls import TLSConfiguration

if TYPE_CHECKING:
    from gui.connection_manager import ConnectionManager

logger = logging.getLogger(__name__)


class BaseWebSocketSession(ABC):
    def __init__(
        self,
        manager: "ConnectionManager",
        state: RuntimeState,
        url: str,
        port: int,
        cp: Any,
        is_direct: bool = False,
        security: Optional[dict[str, Any]] = None,
    ) -> None:
        self.manager = manager
        self.state = state
        self.url = url
        self.port = port
        self.cp = cp
        self.is_direct = is_direct
        self.security = security
        self.endpoint: Any = None
        self.client: Any = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.start_task: Optional[asyncio.Task[Any]] = None
        self.refresh_task: Optional[asyncio.Task[Any]] = None

    @property
    @abstractmethod
    def mode(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def run(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def status(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def disconnect(self) -> str:
        raise NotImplementedError

    def _initialize_runtime(self, endpoint: Any, client: Any, loop: asyncio.AbstractEventLoop) -> None:
        invoke_lock = asyncio.Lock()
        self.endpoint = endpoint
        self.client = client
        self.loop = loop
        with self.state.state_lock:
            self.state.endpoint = endpoint
            self.state.client = client
            self.state.loop = loop
            self.state.invoke_lock = invoke_lock
            self.state.mode = self.mode
            self.state.is_direct = self.is_direct
        logger.info("session runtime initialized mode=%s cp=%s", self.mode, self.cp)

    def _set_endpoint_task(self, task: asyncio.Task[Any]) -> None:
        self.start_task = task
        with self.state.state_lock:
            self.state.endpoint_task = task

    def _set_refresh_task(self, task: asyncio.Task[Any]) -> None:
        self.refresh_task = task
        with self.state.state_lock:
            self.state.token_refresh_task = task

    def _is_cancelled(self) -> bool:
        with self.state.state_lock:
            return self.state.cancel_connect or self.state.manual_disconnect

    def _set_status(self, status: str) -> None:
        with self.state.state_lock:
            self.state.status = status

    async def _build_endpoint_and_client(
        self,
    ) -> tuple[Any, Any, Optional[str], bool, Optional[str], Optional[str], Optional[str], Optional[str]]:
        tls_config, oauth_config = await self._prepare_security()
        access_token = oauth_config["access_token"] if oauth_config else None
        token_refresh_enabled = oauth_config["token_refresh_enabled"] if oauth_config else False
        token_request_url = oauth_config["token_request_url"] if oauth_config else None
        client_id = oauth_config["client_id"] if oauth_config else None
        client_secret = oauth_config["client_secret"] if oauth_config else None
        keycloak_cert_path = oauth_config["kc_cert"] if oauth_config else None
        endpoint = self.manager.endpoint_cls(
            is_direct=self.is_direct,
            tls_config=tls_config,
            oauth_enable=oauth_config["oauth_enable"] if oauth_config else None,
            cert_endpoint=oauth_config["certificate_url"] if oauth_config else None,
            token_issuer=oauth_config["token_issuer"] if oauth_config else None,
            kc_cert=keycloak_cert_path,
        )
        client = self.manager.client_cls(self.cp)
        endpoint.add_iec61850_client(client)
        endpoint.send_msg_callback = lambda msg, ts: self.manager.log_message("send", msg, ts)
        endpoint.recv_msg_callback = lambda msg, ts: self.manager.log_message("recv", msg, ts)
        client.send_msg_callback = endpoint.send_msg_callback
        return (
            endpoint,
            client,
            access_token,
            token_refresh_enabled,
            token_request_url,
            client_id,
            client_secret,
            keycloak_cert_path,
        )

    async def _prepare_security(self) -> tuple[Optional[TLSConfiguration], Optional[dict[str, Any]]]:
        if not self.security:
            logger.debug("no security configuration provided mode=%s", self.mode)
            return None, None

        tls_config = None
        oauth_config = {
            "oauth_enable": self.security.get("enableOAuth"),
            "certificate_url": None,
            "token_issuer": None,
            "kc_cert": None,
            "access_token": None,
            "token_refresh_enabled": bool(self.security.get("enableTokenRefresh")),
            "token_request_url": self.security.get("oauthUrl"),
            "client_id": self.security.get("oauthClientId"),
            "client_secret": self.security.get("oauthClientSecret"),
        }

        if self.security.get("enableTLS"):
            logger.info("preparing TLS configuration mode=%s", self.mode)
            if self.mode == "active":
                cert_path = self._write_security_file("ws_server_ca_", ".pem", self.security.get("tlsCACert", ""))
                tls_config = TLSConfiguration(is_ws_server=False, cert_path=cert_path, key_path=None)
            else:
                cert_path = self._write_security_file("ws_server_cert_", ".pem", self.security.get("certificate", ""))
                key_path = self._write_security_file("ws_server_key_", ".pem", self.security.get("privateKey", ""))
                tls_config = TLSConfiguration(is_ws_server=True, cert_path=cert_path, key_path=key_path)
                if self.security.get("tlsVersion") == "1.2":
                    tls_config.set_min_and_max_version(
                        min_version=ssl.TLSVersion.TLSv1_2,
                        max_version=ssl.TLSVersion.TLSv1_2,
                    )
                else:
                    tls_config.set_min_and_max_version(
                        min_version=ssl.TLSVersion.TLSv1_3,
                        max_version=ssl.TLSVersion.TLSv1_3,
                    )
                tls_config.ssl_context.keylog_filename = os.path.join(tempfile.gettempdir(), "ws61850_gui_tlskeys.log")

        if self.security.get("enableOAuth"):
            logger.info("preparing OAuth configuration mode=%s", self.mode)
            kc_cert_path = self._write_security_file("kc_root_ca_", ".pem", self.security.get("oauthCACert", ""))
            oauth_config["kc_cert"] = kc_cert_path
            if self.mode == "active":
                oauth_config["access_token"] = await get_access_token(
                    oauth_config["token_request_url"],
                    oauth_config["client_id"],
                    oauth_config["client_secret"],
                    kc_cert_path,
                    None,
                )
            else:
                oauth_config["certificate_url"] = self.security.get("oauthCertEndpoint")
                oauth_config["token_issuer"] = self.security.get("oauthIssuer")

        return tls_config, oauth_config

    def _write_security_file(self, prefix: str, suffix: str, content: str) -> Optional[str]:
        if not content:
            return None
        with tempfile.NamedTemporaryFile("w", delete=False, prefix=prefix, suffix=suffix) as handle:
            handle.write(content)
            path = handle.name
        with self.state.state_lock:
            self.state.security_files.append(path)
        logger.debug("wrote temporary security file path=%s", path)
        return path

    async def _refresh_token_if_needed(
        self,
        url: str,
        client_id: str,
        client_secret: str,
        token: str,
        websocket_endpoint: WebSocketEndpoint,
        client_cert: Any,
        keycloak_cert: Optional[str],
    ) -> None:
        while True:
            websocket_info = next(
                (ws_info for ws_info in websocket_endpoint.websocket_info_list if ws_info.cp == self.cp),
                None,
            )
            if websocket_info is not None:
                decoded = jwt.decode(token, options={"verify_signature": False})
                if decoded["exp"] - time.time() < 3:
                    logger.info("refreshing OAuth token cp=%s", self.cp)
                    token = await get_access_token(url, client_id, client_secret, keycloak_cert, client_cert)
                    refresh_token_message = create_token_refresh(websocket_info.associate_id, token)
                    encoded_message = encode_tpaa_message(refresh_token_message)
                    await websocket_info.websocket.send(encoded_message)
            await asyncio.sleep(1)

    async def _close_if_needed(self) -> None:
        if self.endpoint is None or self.client is None:
            return
        ws_info = self.endpoint.get_websocket_info(self.client)
        if ws_info and hasattr(ws_info, "websocket") and not getattr(ws_info.websocket, "closed", False):
            logger.info("closing websocket cp=%s", self.cp)
            await ws_info.websocket.close()

    def _cancel_endpoint_task(self) -> None:
        if self.start_task is not None and not self.start_task.done():
            logger.debug("cancelling endpoint task mode=%s cp=%s", self.mode, self.cp)
            self.start_task.cancel()

    def _cleanup_runtime(self, cleanup_files: bool) -> None:
        self.manager._clear_connection_refs(self, cleanup_files=cleanup_files)

    def ensure_connection(
        self, timeout: int = 10
    ) -> tuple[Any, WebSocketEndpoint, WebSocketInfo, asyncio.AbstractEventLoop]:
        client = self.client
        endpoint = self.endpoint
        loop = self.loop
        if not client or not endpoint or not loop:
            logger.debug("ensure_connection failed: missing client/endpoint/loop")
            raise RuntimeError("not-connected")
        if not client.is_connected:
            logger.debug("ensure_connection waiting for ready_event cp=%s timeout=%s", client.cp, timeout)
            wait_fut = asyncio.run_coroutine_threadsafe(client.ready_event.wait(), loop)
            try:
                wait_fut.result(timeout=timeout)
            except Exception:
                logger.debug("ensure_connection ready_event wait timed out or failed cp=%s", client.cp)
        if not client.is_connected:
            logger.debug("ensure_connection failed: client not connected cp=%s", client.cp)
            raise RuntimeError("not-connected")
        ws_info = endpoint.get_websocket_info(client)
        if ws_info is None:
            logger.debug("ensure_connection failed: no websocket info cp=%s", client.cp)
            raise RuntimeError("no-websocket-info")
        return client, endpoint, ws_info, loop
