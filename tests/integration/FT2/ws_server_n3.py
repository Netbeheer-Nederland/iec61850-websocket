import asyncio

from testing.ieds.high_level_model import make_ied_model1
from ws61850.endpoint.endpoint import *
from ws61850.iec61850.server.iec61850_server import IEC61850Server

maxMessageSize = 65000


async def main():
    protocol = ["iec61850-tpaa-jer-v1", "iec61850-tpaa-ber-v1"]
    # websocket client
    ep_wsServer = WebSocketEndpoint(is_direct=True)
    iec61850_server = IEC61850Server(make_ied_model1(), "cp1")
    ep_wsServer.add_iec61850_server(iec61850_server)

    server_task = asyncio.create_task(
        ep_wsServer.start("passive", "localhost", 8765, protocol=protocol)
    )

    # await server_task
    await asyncio.gather(server_task)


async def cancel_existing_tasks():
    # Cancel all tasks except the current one
    current = asyncio.current_task()
    for task in asyncio.all_tasks():
        if task is not current:
            task.cancel()
    # Give cancelled tasks time to finish
    await asyncio.sleep(1)


async def main_wrapper():
    await cancel_existing_tasks()
    await main()  # your main function


if __name__ == "__main__":
    asyncio.run(main_wrapper())
