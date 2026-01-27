from Examples.ieds.high_level_model import ied as ied1
from Examples.ieds.ied_model_2 import ied as ied2
from Endpoint.endpoint import *
import asyncio
from IEC61850.server.IEC61850Server import *
from IEC61850.server.control_handling import *
from IEC61850.server.service_error import *
import random



maxMessageSize = 65000

async def toggle_custom_value(iec61150_server, obj_ref):
    while True:
        value = randint(1, 5)
        await iec61150_server.update_value(obj_ref, value)
        print(f"Value of {obj_ref} changed to {value}")
        await asyncio.sleep(5)

async def toggle_float_value(iec61150_server, obj_ref):
    while True:
        value = random.uniform(5.5, 10.0)
        await iec61150_server.update_value(obj_ref, value)
        print(f"Value of {obj_ref} changed to {value}")
        await asyncio.sleep(0.1)


async def main():
    ep_wsClient_1 = WebSocketEndpoint()
    iec61850_server_1 = IEC61850Server(ied1, "cp1")
    report_task_1 = asyncio.create_task(iec61850_server_1.periodic_report_start())
    toggle_task_1 = asyncio.create_task(toggle_float_value(iec61850_server_1, "LD0/MMXU1.TotW.mag.f"))

    ep_wsClient_1.add_iec61850_server(iec61850_server_1)

    task1 = asyncio.create_task(ep_wsClient_1.start("active","localhost", 8765, "cp1"))

    await asyncio.gather(task1, report_task_1, toggle_task_1)

if __name__ == "__main__":
    asyncio.run(main())