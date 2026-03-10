import asyncio

from testing.ieds.high_level_model import make_ied_model1
from ws61850.endpoint.endpoint import WebSocketEndpoint
from ws61850.iec61850.server.control_handling import (
    ControlHandlerResult,
    ControlServiceStatusKind,
)
from ws61850.iec61850.server.iec61850_server import IEC61850Server
from ws61850.iec61850.server.service_error import ServiceStatusKind


def control_handler_for_float(obj_ref, ctlVal_value, parameter):
    if ctlVal_value is not None:
        if ctlVal_value["type"].startswith("float"):
            if ctlVal_value["value"] < 50:
                return ControlHandlerResult.OK, None
            else:
                return (
                    ControlHandlerResult.FAILED,
                    ControlServiceStatusKind.invalidPosition,
                )
    else:
        return None, ServiceStatusKind.instanceNotAvailable
    return None, None


async def main():
    ep_ws_client = WebSocketEndpoint()
    iec61850_server_1 = IEC61850Server(make_ied_model1(), "cp1")
    iec61850_server_1.set_control_handler(control_handler_for_float, None)
    report_task_1 = asyncio.create_task(iec61850_server_1.periodic_report_start())
    ep_ws_client.add_iec61850_server(iec61850_server_1)

    task1 = asyncio.create_task(
        ep_ws_client.start("active", "localhost", 8765, "cp1", protocol=["iec61850-tpaa-ber-v1"])
    )

    await asyncio.gather(task1, report_task_1)


if __name__ == "__main__":
    asyncio.run(main())
