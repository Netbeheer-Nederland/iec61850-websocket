import asyncio

from testing.ieds.high_level_model import make_ied_model1
from ws61850.endpoint.endpoint import WebSocketEndpoint
from ws61850.iec61850.server.iec61850_server import IEC61850Server


async def create_ws_clients(cp, task_list):
    ep_wsClient_1 = WebSocketEndpoint()
    iec61850_server_1 = IEC61850Server(make_ied_model1(), cp)
    ep_wsClient_1.add_iec61850_server(iec61850_server_1)

    task1 = asyncio.create_task(ep_wsClient_1.start("active", "localhost", 8765, cp))
    task_list.append(task1)


async def run_clients(tasks):
    await asyncio.gather(*tasks)


async def main():
    task_list = []
    for i in range(0, 500):
        await create_ws_clients("cp" + str(i), task_list)
        await asyncio.sleep(1)

    await run_clients(task_list)


if __name__ == "__main__":
    asyncio.run(main())
