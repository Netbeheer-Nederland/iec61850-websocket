import asyncio
import copy

from testing.ieds.high_level_model import make_ied_model1
from ws61850.endpoint.endpoint import WebSocketEndpoint
from ws61850.iec61850.server.iec61850_server import IEC61850Server

deep_copied_ieds = [copy.deepcopy(make_ied_model1()) for _ in range(500)]


async def create_ws_clients(cp, task_list, i):
    ied_instance = deep_copied_ieds[i]  # Create a unique IED instance for each server
    ep_wsClient_1 = WebSocketEndpoint()
    iec61850_server_1 = IEC61850Server(ied_instance, cp)
    ep_wsClient_1.add_iec61850_server(iec61850_server_1)
    report_task_1 = asyncio.create_task(iec61850_server_1.periodic_report_start())

    task1 = asyncio.create_task(ep_wsClient_1.start("active", "192.168.100.5", 8765, cp))
    task_list.append(task1)
    task_list.append(report_task_1)


async def run_clients(tasks):
    await asyncio.gather(*tasks)


async def main():
    task_list = []
    for i in range(0, 500):
        await create_ws_clients("cp" + str(i), task_list, i)
        await asyncio.sleep(0.005)

    await run_clients(task_list)


if __name__ == "__main__":
    asyncio.run(main())
