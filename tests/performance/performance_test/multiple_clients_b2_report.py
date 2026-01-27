from Examples.ieds.high_level_model import ied as ied1
from Examples.ieds.ied_model_2 import ied as ied2
from Endpoint.endpoint import *
import asyncio
from IEC61850.server.IEC61850Server import *
from IEC61850.server.control_handling import *
from IEC61850.server.service_error import *
from TLSConfig.TLSConfiguration import *
import sys
import copy  # Added for deep copy

maxMessageSize = 65000

deep_copied_ieds = [copy.deepcopy(ied1) for _ in range(500)]

async def create_ws_clients(cp, task_list, i):
    ied_instance = deep_copied_ieds[i - 501]  # Create a unique IED instance for each server
    ep_wsClient_1 = WebSocketEndpoint()
    iec61850_server_1 = IEC61850Server(ied_instance, cp)
    ep_wsClient_1.add_iec61850_server(iec61850_server_1)
    report_task_1 = asyncio.create_task(iec61850_server_1.periodic_report_start())


    task1 = asyncio.create_task(ep_wsClient_1.start("active","192.168.100.5", 8765, cp))
    task_list.append(task1)
    task_list.append(report_task_1)

async def run_clients(tasks):
    await asyncio.gather(*tasks)

async def main():
    task_list = []
    for i in range(500, 1001):
        await create_ws_clients("cp" + str(i), task_list, i)
        await asyncio.sleep(0.005)

    await run_clients(task_list)


if __name__ == "__main__":
    asyncio.run(main())
