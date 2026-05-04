from __future__ import annotations

import asyncio
import logging
from typing import Any

from gui.ws_sessions.base import BaseWebSocketSession

logger = logging.getLogger(__name__)


class ActiveClientSession(BaseWebSocketSession):
    @property
    def mode(self) -> str:
        return "active"

    async def run(self) -> None:
        logger.info("active session starting cp=%s", self.cp)
        try:
            loop = asyncio.get_running_loop()
            (
                endpoint,
                client,
                access_token,
                token_refresh_enabled,
                token_request_url,
                client_id,
                client_secret,
                keycloak_cert_path,
            ) = await self._build_endpoint_and_client()
            self._initialize_runtime(endpoint, client, loop)

            self._set_endpoint_task(
                asyncio.create_task(endpoint.start("active", self.url, self.port, self.cp, access_token=access_token))
            )
            logger.info("active websocket endpoint task created cp=%s", self.cp)

            if token_refresh_enabled:
                logger.info("token refresh enabled cp=%s", self.cp)
                self._set_refresh_task(
                    asyncio.create_task(
                        self._refresh_token_if_needed(
                            token_request_url,
                            client_id,
                            client_secret,
                            access_token,
                            endpoint,
                            None,
                            keycloak_cert_path,
                        )
                    )
                )

            connected = await self._wait_for_ready_event()
            if not connected:
                logger.warning("active websocket endpoint did not reach connected state cp=%s", self.cp)
                if self.start_task is not None:
                    await self.start_task
                return

            if self._is_cancelled():
                logger.info("active session cancelled during startup cp=%s", self.cp)
                await self._close_if_needed()
                self.manager.log_action_end(self.state.connect_aid, False, "connect-cancelled")
                self._cleanup_runtime(cleanup_files=True)
                return

            self._set_status("connected")
            self.manager.log_action_end(self.state.connect_aid, True)
            logger.info("active session connected cp=%s", self.cp)
            if self.start_task is not None:
                await self.start_task
            logger.info("active session endpoint exited cp=%s", self.cp)
            self._cleanup_runtime(cleanup_files=True)
        except asyncio.CancelledError:
            logger.info("active session cancelled cp=%s", self.cp)
            self.manager.log_action_end(self.state.connect_aid, True, extra_detail={"stopped": True})
            self._cleanup_runtime(cleanup_files=True)
        except Exception as exc:
            logger.exception("active session failed cp=%s", self.cp)
            self._set_status("error")
            self.manager.log_action_end(self.state.connect_aid, False, str(exc))
            self._cleanup_runtime(cleanup_files=True)
            raise
        finally:
            if self.refresh_task is not None:
                logger.debug("cancelling token refresh task cp=%s", self.cp)
                self.refresh_task.cancel()
                await asyncio.gather(self.refresh_task, return_exceptions=True)

    async def _wait_for_ready_event(self) -> bool:
        if self.client is None or self.start_task is None:
            return False
        logger.debug("waiting for active ready_event cp=%s", self.cp)
        ready_task = asyncio.create_task(self.client.ready_event.wait())
        try:
            done, _pending = await asyncio.wait({self.start_task, ready_task}, return_when=asyncio.FIRST_COMPLETED)
            if ready_task in done and self.client.is_connected:
                logger.debug("active ready_event set cp=%s", self.cp)
                return True
            if self.start_task in done:
                logger.debug("active start task finished before ready_event cp=%s", self.cp)
                await self.start_task
            return self.client.is_connected
        finally:
            if not ready_task.done():
                ready_task.cancel()
                await asyncio.gather(ready_task, return_exceptions=True)

    def status(self) -> dict[str, Any]:
        if self.state.manual_disconnect:
            return {"state": "not-connected", "detail": {}}
        if not self.client or not self.endpoint or not self.loop:
            return {"state": "not-connected", "detail": {}}

        state = "not-connected"
        detail: dict[str, Any] = {}
        ws_info = self.endpoint.get_websocket_info(self.client)

        if self.client.is_connected:
            state = "connected"
        elif ws_info is not None:
            state = "connecting"
        else:
            state = "starting"
        if ws_info and getattr(ws_info.websocket, "closed", False):
            state = "not-connected"

        if ws_info:
            detail = {
                "invokeId": ws_info.invoke_id,
                "associateId": ws_info.associate_id,
                "cp": self.client.cp,
            }
        return {"state": state, "detail": detail}

    def disconnect(self) -> str:
        if not self.client or not self.endpoint or not self.loop:
            logger.info("active disconnect requested with no active connection")
            return "no-active-connection"
        logger.info("active disconnect requested cp=%s", self.cp)

        with self.state.state_lock:
            self.state.manual_disconnect = True
            self.state.cancel_connect = True

        ws_info = self.endpoint.get_websocket_info(self.client)
        if ws_info and not getattr(ws_info.websocket, "closed", False):

            async def _close_ws() -> None:
                await ws_info.websocket.close()

            asyncio.run_coroutine_threadsafe(_close_ws(), self.loop).result(timeout=10)
        self.client.is_connected = False
        self.manager.log_action("Disconnected from server", "warn")
        self._cancel_endpoint_task()
        self._cleanup_runtime(cleanup_files=True)
        logger.info("active disconnect completed cp=%s", self.cp)
        return "disconnected"
