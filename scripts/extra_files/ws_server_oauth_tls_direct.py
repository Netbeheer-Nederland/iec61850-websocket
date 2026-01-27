#from time import sleep

from Endpoint.endpoint import *
import asyncio
from IEC61850.server.IEC61850Server import *
from Examples.ieds.high_level_model import ied as ied1
from src.TLSConfig.TLSConfiguration import *

project_root = ""
for path in sys.path:
    if path.endswith("certs"):
        project_root = path
        break
kc_cert_path = os.path.join(project_root, 'keycloak.crt')

project_root = ""
for path in sys.path:
    if path.endswith("certs"):
        project_root = path
        break
cert_path = os.path.join(project_root, 'server_FT9.crt')
key_path = os.path.join(project_root, 'server_FT9.key')

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
    # websocket server
    #ws_id = "ws_server"
    #ws_secret = "K4Nrd14seXG52J3xpnIqfMyILTJJu3VI"
    #url = "https://192.168.100.15:8443/realms/master/protocol/openid-connect/token/introspect"
    # introspect example
    # access_token_validation = introspect_token(ws_id, ws_secret, url, access_token["access_token_raw"])
    # if access_token_validation:
    #    print("introspection succeeded")
    # else:
    #    print("introspection failed")
    tls_config = TLSConfiguration(cert_path, key_path, True)
    tls_config.set_min_and_max_version(min_version=ssl.TLSVersion.TLSv1_2, max_version=ssl.TLSVersion.TLSv1_2)

    ep_wsServer = WebSocketEndpoint(is_direct=True, tls_config=tls_config,
                                    oauth_enable=True, cert_endpoint="https://192.168.100.15:8443/realms/master/protocol/openid-connect/certs",
                                    token_issuer="https://192.168.100.15:8443/realms/master", kc_cert=kc_cert_path)

    iec61850_server = IEC61850Server(ied1, "cp1")
    iec61850_server.set_control_handler(control_handler_for_float, None)

    ep_wsServer.add_iec61850_server(iec61850_server)

    server_task = asyncio.create_task(
        ep_wsServer.start("passive", "192.168.100.40", 8765)
    )

    await server_task

if __name__ == "__main__":
    asyncio.run(main())


