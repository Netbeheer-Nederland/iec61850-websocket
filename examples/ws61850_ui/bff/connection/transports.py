import asyncio
from typing import Any

from bff.connection.profile import ConnectionProfile
from bff.connection.security import SecurityContext
from ws61850.endpoint.endpoint import WebSocketEndpoint


class WsClientTransport:
    role = "ws_client"

    async def start(
        self,
        endpoint: WebSocketEndpoint,
        profile: ConnectionProfile,
        security: SecurityContext,
    ) -> None:
        await endpoint.start(
            "active",
            profile.host,
            profile.port,
            profile.cp,
            access_token=security.access_token,
        )

    async def stop(self, endpoint: WebSocketEndpoint, cp: str) -> None:
        ws_info = next((item for item in endpoint.websocket_info_list if item.cp == cp), None)
        if ws_info and not getattr(ws_info.websocket, "closed", False):
            await ws_info.websocket.close()


class WsServerTransport:
    role = "ws_server"

    async def start(
        self,
        endpoint: WebSocketEndpoint,
        profile: ConnectionProfile,
        security: SecurityContext,
    ) -> None:
        await endpoint.start("passive", profile.host, profile.port)

    async def wait_until_listening(self, endpoint: WebSocketEndpoint, start_task: asyncio.Task[Any] | None) -> None:
        if start_task is None:
            return
        while True:
            if start_task.done():
                await start_task
                return
            if getattr(endpoint, "server", None) is not None:
                return
            await asyncio.sleep(0.05)

    async def stop(self, endpoint: WebSocketEndpoint, cp: str) -> None:
        await endpoint.stop_passive()
