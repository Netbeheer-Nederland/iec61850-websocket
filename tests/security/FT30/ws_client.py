import asyncio
import sys
from pathlib import Path

from ws61850.endpoint.endpoint import WebSocketEndpoint
from ws61850.iec61850.server.control_handling import (
    ControlHandlerResult,
    ControlServiceStatusKind,
)
from ws61850.iec61850.server.iec61850_server import IEC61850Server
from ws61850.iec61850.server.service_error import ServiceStatusKind
from ws61850.security.tls import TLSConfiguration

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from testing.certs.paths import CERT_DIR  # noqa: E402
from testing.ieds.high_level_model import make_ied_model1  # noqa: E402

max_message_size = 65000

cafile = CERT_DIR / "ca.pem"


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
    print(f"{cafile}")
    tls_config = TLSConfiguration(cafile, None, False)
    ep_ws_client = WebSocketEndpoint(tls_config=tls_config)
    iec61850_server_1 = IEC61850Server(make_ied_model1(), "cp1")
    iec61850_server_1.set_control_handler(control_handler_for_float, None)
    report_task_1 = asyncio.create_task(iec61850_server_1.periodic_report_start())
    ep_ws_client.add_iec61850_server(iec61850_server_1)

    task1 = asyncio.create_task(ep_ws_client.start("active", "localhost", 8765, "cp1"))

    await asyncio.gather(task1, report_task_1)


if __name__ == "__main__":
    asyncio.run(main())
