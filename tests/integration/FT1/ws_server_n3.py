from time import sleep

from Endpoint.endpoint import *
import asyncio
from IEC61850.client.IEC61850Client import *

maxMessageSize_server = 65000

async def main():

    protocol=["iec61850-tpaa-jer-v1", "iec61850-tpaa-ber-v1"]
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