from __future__ import annotations

import asyncio
import logging
from typing import Any

from gui.ws_sessions.base import BaseWebSocketSession

logger = logging.getLogger(__name__)


class PassiveServerSession(BaseWebSocketSession):
    @property
    def mode(self) -> str:
        return "passive"

    async def run(self) -> None:
        logger.info("passive session starting cp=%s", self.cp)
        try:
            loop = asyncio.get_running_loop()
            endpoint, client, *_ = await self._build_endpoint_and_client()
            self._initialize_runtime(endpoint, client, loop)
            self._set_endpoint_task(asyncio.create_task(endpoint.start("passive", "0.0.0.0", self.port)))
            logger.info("passive websocket endpoint task created port=%s cp=%s", self.port, self.cp)
            await self._wait_for_server_handle()
            if not self._is_cancelled():
                self._set_status("listening")
            self.manager.log_action_end(self.state.connect_aid, True)
            logger.info("passive websocket endpoint is listening port=%s cp=%s", self.port, self.cp)
            if self.start_task is not None:
                await self.start_task
            logger.info("passive websocket endpoint exited cp=%s", self.cp)
            self._cleanup_runtime(cleanup_files=True)
        except asyncio.CancelledError:
            logger.info("passive session cancelled cp=%s", self.cp)
            self.manager.log_action_end(self.state.connect_aid, True, extra_detail={"stopped": True})
            self._cleanup_runtime(cleanup_files=True)
        except Exception as exc:
            logger.exception("passive session failed cp=%s", self.cp)
            self._set_status("error")
            self.manager.log_action_end(self.state.connect_aid, False, str(exc))
            self._cleanup_runtime(cleanup_files=True)
            raise

    async def _wait_for_server_handle(self) -> None:
        if self.start_task is None:
            return
        logger.debug("waiting for passive websocket endpoint to start cp=%s", self.cp)
        while True:
            if self.start_task.done():
                logger.debug("passive start task completed before server handle cp=%s", self.cp)
                await self.start_task
                return
            if getattr(self.endpoint, "server", None) is not None:
                logger.debug("passive websocket endpoint server handle available cp=%s", self.cp)
                return
            await asyncio.sleep(0.05)

    def status(self) -> dict[str, Any]:
        if self.state.manual_disconnect:
            return {"state": "not-connected", "detail": {}}
        if not self.client or not self.endpoint or not self.loop:
            return {"state": "not-connected", "detail": {}}

        state = "listening"
        detail: dict[str, Any] = {}
        ws_info = self.endpoint.get_websocket_info(self.client)
        if self.client.is_connected and ws_info is not None and not getattr(ws_info.websocket, "closed", False):
            state = "connected"
        if ws_info:
            detail = {
                "invokeId": ws_info.invoke_id,
                "associateId": ws_info.associate_id,
                "cp": self.client.cp,
            }
        return {"state": state, "detail": detail}

    def disconnect(self) -> str:
        if not self.client or not self.endpoint or not self.loop:
            logger.info("passive disconnect requested with no active connection")
            return "no-active-connection"
        logger.info("passive disconnect requested cp=%s", self.cp)

        with self.state.state_lock:
            self.state.manual_disconnect = True
            self.state.cancel_connect = True

        async def _stop_passive() -> None:
            await self.endpoint.stop_passive()

        asyncio.run_coroutine_threadsafe(_stop_passive(), self.loop).result(timeout=10)
        self.client.is_connected = False
        self.manager.log_action("Passive server stopped", "warn")
        self._cancel_endpoint_task()
        self._cleanup_runtime(cleanup_files=True)
        logger.info("passive disconnect completed cp=%s", self.cp)
        return "disconnected"
