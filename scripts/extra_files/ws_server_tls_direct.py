from time import sleep
from Examples.ieds.high_level_model import ied as ied1

from Endpoint.endpoint import *
import asyncio
from IEC61850.client.IEC61850Client import *
import sys

from TLSConfig.TLSConfiguration import *
from IEC61850.server.IEC61850Server import *


project_root = ""
for path in sys.path:
    if path.endswith("certs"):
        project_root = path
        break
cert_path = os.path.join(project_root, 'server_FT9.crt')
key_path = os.path.join(project_root, 'server_FT9.key')
maxMessageSize_server = 65000

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

def callback_called(result, param):
    print("callback called: ", result)


async def main():

    tls_config = TLSConfiguration(cert_path, key_path, True)
    tls_config.set_min_and_max_version(min_version=ssl.TLSVersion.TLSv1_2, max_version=ssl.TLSVersion.TLSv1_2)

    ep_wsServer = WebSocketEndpoint(is_direct=True, tls_config=tls_config)
    iec61850_server = IEC61850Server(ied1, "cp1")
    iec61850_server.set_control_handler(control_handler_for_float, None)

    ep_wsServer.add_iec61850_server(iec61850_server)


    server_task = asyncio.create_task(
        ep_wsServer.start("passive", "192.168.100.40", 8765)
    )


    await server_task

if __name__ == "__main__":
    asyncio.run(main())
