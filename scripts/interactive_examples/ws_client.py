from Examples.ieds.high_level_model import ied as ied1
from Examples.ieds.ied_model_2 import ied as ied2
from Endpoint.endpoint import *
import asyncio
from IEC61850.server.IEC61850Server import *
from IEC61850.server.control_handling import *
from IEC61850.server.service_error import *



maxMessageSize = 65000

async def toggle_custom_value(iec61150_server, obj_ref):
    while True:
        value = randint(1, 5)
        await iec61150_server.update_value(obj_ref, value)
        print(f"Value of {obj_ref} changed to {value}")
        await asyncio.sleep(5)

async def toggle_quality_value(iec61150_server, obj_ref):
    while True:
        random_operate_Block = bool(randint(0, 1))
        value = {'validity': 'good', 'source': 'process', 'test': False, 'operatorBlock': random_operate_Block}
        await iec61150_server.update_value(obj_ref, value)
        print(f"Value of {obj_ref} changed to {value}")
        await asyncio.sleep(5)

def control_handler_for_float(obj_ref, ctlVal_value, parameter):
    if ctlVal_value is not None:
        if ctlVal_value["type"].startswith("float"):
            if ctlVal_value["value"] <50:
                return ControlHandlerResult.OK, None
            else:
                return ControlHandlerResult.FAILED, ControlServiceStatusKind.invalidPosition
    else:
        return None, ServiceStatusKind.instanceNotAvailable
    return None, None


async def main():
    ep_wsClient_1 = WebSocketEndpoint()
    iec61850_server_1 = IEC61850Server(ied1, "cp1")
    iec61850_server_1.set_control_handler(control_handler_for_float, None)
    ep_wsClient_1.add_iec61850_server(iec61850_server_1)

    task1 = asyncio.create_task(ep_wsClient_1.start("active","localhost", 8765, "cp1"))

    await asyncio.gather(task1)

if __name__ == "__main__":
    asyncio.run(main())