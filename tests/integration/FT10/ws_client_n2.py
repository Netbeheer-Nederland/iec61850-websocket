from os import access

import asn1.encode_decode
from Examples.ieds.high_level_model import ied as ied1
from Examples.ieds.ied_model_2 import ied as ied2
from Endpoint.endpoint import *
import asyncio
from IEC61850.server.IEC61850Server import *
from oauth.oauth_functions import *
import jwt

maxMessageSize = 65000
project_root = ""
for path in sys.path:
    if path.endswith("certs"):
        project_root = path
        break
cert_path = os.path.join(project_root, 'keycloak.crt')

async def main():
    token_request_url = "https://192.168.100.15:8443/realms/master/protocol/openid-connect/token"

    client_secret_1 = "jK4S3MnitPLBU92HqncgyvlifDA1ByD6"
    client_id_1 = "ws_client_1"
    access_token_1 = await get_access_token(token_request_url, client_id_1, client_secret_1, cert_path,None)

    ep_wsClient_1 = WebSocketEndpoint(oauth_enable=True, try_reconnect=False)
    iec61850_server_1 = IEC61850Server(ied1, "cp1")
    ep_wsClient_1.add_iec61850_server(iec61850_server_1)

    task1 = asyncio.create_task(ep_wsClient_1.start("active","localhost", 8765, "cp1", access_token_1))
    await asyncio.gather(task1)

if __name__ == "__main__":
    asyncio.run(main())