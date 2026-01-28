# from ws61850.endpoint.endpoint import *
import asyncio

from ws61850.endpoint.endpoint import WebSocketEndpoint
from ws61850.iec61850.client.iec61850_client import IEC61850Client

# from ws61850.iec61850.client.iec61850_client import *

maxMessageSize_server = 65000


async def main():
    protocol = ["iec61850-tpaa-jer-v1"]
    # websocket server
    ep_wsServer = WebSocketEndpoint()

    iec61850_client = IEC61850Client("cp1")
    ep_wsServer.add_iec61850_client(iec61850_client)

    server_task = asyncio.create_task(
        ep_wsServer.start("passive", "localhost", 8765, protocol=protocol)
    )

    await server_task


if __name__ == "__main__":
    asyncio.run(main())
