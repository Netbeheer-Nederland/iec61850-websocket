import asyncio
from collections.abc import Callable
from typing import Any

from ws61850.endpoint.endpoint import WebSocketEndpoint, WebSocketInfo
from ws61850.iec61850.client.iec61850_client import IEC61850Client
from ws61850.iec61850.server.iec61850_server import IEC61850Server


class IecClientBinding:
    def __init__(self, client_cls: type[IEC61850Client], cp: str) -> None:
        self.client = client_cls(cp)

    @property
    def role(self) -> str:
        return "iec_client"

    def attach(self, endpoint: WebSocketEndpoint) -> None:
        endpoint.add_iec61850_client(self.client)
        self.client.send_msg_callback = endpoint.send_msg_callback

    def get_application(self) -> IEC61850Client:
        return self.client

    async def wait_for_ready(self, start_task: asyncio.Task[Any] | None) -> bool:
        if start_task is None:
            return False
        ready_task = asyncio.create_task(self.client.ready_event.wait())
        try:
            done, _pending = await asyncio.wait({start_task, ready_task}, return_when=asyncio.FIRST_COMPLETED)
            if ready_task in done and self.client.is_connected:
                return True
            if start_task in done:
                await start_task
            return self.client.is_connected
        finally:
            if not ready_task.done():
                ready_task.cancel()
                await asyncio.gather(ready_task, return_exceptions=True)

    def status(
        self,
        endpoint: WebSocketEndpoint | None,
        loop: asyncio.AbstractEventLoop | None,
        manual_disconnect: bool,
        transport_role: str,
    ) -> dict[str, Any]:
        if manual_disconnect or not endpoint or not loop:
            return {"state": "not-connected", "detail": {}}

        state = "listening" if transport_role == "ws_server" and getattr(endpoint, "server", None) is not None else "not-connected"
        detail: dict[str, Any] = {}
        ws_info = endpoint.get_websocket_info(self.client)

        if self.client.is_connected:
            state = "connected"
        elif ws_info is not None:
            state = "connecting"
        elif transport_role == "ws_client":
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

    def ensure_connection(
        self,
        endpoint: WebSocketEndpoint | None,
        loop: asyncio.AbstractEventLoop | None,
        timeout: int,
    ) -> tuple[IEC61850Client, WebSocketEndpoint, WebSocketInfo, asyncio.AbstractEventLoop]:
        if not endpoint or not loop:
            raise RuntimeError("not-connected")
        if not self.client.is_connected:
            wait_fut = asyncio.run_coroutine_threadsafe(self.client.ready_event.wait(), loop)
            try:
                wait_fut.result(timeout=timeout)
            except Exception:
                pass
        if not self.client.is_connected:
            raise RuntimeError("not-connected")
        ws_info = endpoint.get_websocket_info(self.client)
        if ws_info is None:
            raise RuntimeError("no-websocket-info")
        return self.client, endpoint, ws_info, loop

    def disconnect_message(self, transport_role: str) -> str:
        return "Passive server stopped" if transport_role == "ws_server" else "Disconnected from server"

    def mark_disconnected(self) -> None:
        self.client.is_connected = False
        if hasattr(self.client, "disconnect_event"):
            self.client.disconnect_event.set()


class IecServerBinding:
    def __init__(self, server: IEC61850Server) -> None:
        self.server = server

    @property
    def role(self) -> str:
        return "iec_server"

    def attach(self, endpoint: WebSocketEndpoint) -> None:
        endpoint.add_iec61850_server(self.server)
        self.server.send_msg_callback = endpoint.send_msg_callback
        self.server.recv_msg_callback = endpoint.recv_msg_callback

    def get_application(self) -> IEC61850Server:
        return self.server

    async def wait_for_ready(self, start_task: asyncio.Task[Any] | None) -> bool:
        if start_task is None:
            return False
        await asyncio.sleep(0)
        return not start_task.done()

    def status(
        self,
        endpoint: WebSocketEndpoint | None,
        loop: asyncio.AbstractEventLoop | None,
        manual_disconnect: bool,
        transport_role: str,
    ) -> dict[str, Any]:
        if manual_disconnect or not endpoint or not loop:
            return {"state": "not-connected", "detail": {}}
        ws_info = next((item for item in endpoint.websocket_info_list if item.cp == self.server.cp), None)
        if ws_info and not getattr(ws_info.websocket, "closed", False):
            return {
                "state": "connected" if self.server.ready_event.is_set() else "connecting",
                "detail": {
                    "invokeId": ws_info.invoke_id,
                    "associateId": ws_info.associate_id,
                    "cp": self.server.cp,
                },
            }
        return {"state": "connecting", "detail": {"cp": self.server.cp}}

    def ensure_connection(
        self,
        endpoint: WebSocketEndpoint | None,
        loop: asyncio.AbstractEventLoop | None,
        timeout: int,
    ) -> tuple[Any, WebSocketEndpoint, WebSocketInfo, asyncio.AbstractEventLoop]:
        raise RuntimeError("iec-server-does-not-support-client-invoke")

    def disconnect_message(self, transport_role: str) -> str:
        return "Passive server stopped" if transport_role == "ws_server" else "Disconnected from peer"

    def mark_disconnected(self) -> None:
        return None


ApplicationBinding = IecClientBinding | IecServerBinding
ServerFactory = Callable[[str], IEC61850Server]
