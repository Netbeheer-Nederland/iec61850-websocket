
from os import access

import asn1.encode_decode
from Examples.ieds.high_level_model import ied as ied1
from Examples.ieds.ied_model_2 import ied as ied2
from Endpoint.endpoint import *
import asyncio
from IEC61850.server.IEC61850Server import *
from oauth.oauth_functions import *
import jwt
import sys
from TLSConfig.TLSConfiguration import *
maxMessageSize = 65000

project_root = ""
for path in sys.path:
    if path.endswith("certs"):
        project_root = path
        break
cert_path = os.path.join(project_root, 'keycloak.crt')

project_root = ""
for path in sys.path:
    if path.endswith("certs"):
        project_root = path
        break
tls_cert_path = os.path.join(project_root, 'root_CA1.pem')

async def refresh_token_if_needed(url, client_id, client_secret, token, websocket_endpoint, cp, client_cert, keycloack_cert):
    #jwks_url = "http://localhost:8080/realms/master/protocol/openid-connect/certs"
    while True:
        websocket_info = next((ws_info for ws_info in websocket_endpoint.websocket_info_list if ws_info.cp == cp), None)

        if websocket_info is not None:
            decoded = jwt.decode(token, options={"verify_signature": False})
            # Check if less than 3 seconds until expiration
            if decoded["exp"] - time.time() < 3:
                print(f"The access token for {cp} endpoint is expiring soon, requesting a new token...")
                token = await get_access_token(url, client_id, client_secret, keycloack_cert, client_cert)
                refresh_token_message = create_token_refresh(websocket_info.associate_id, token)
                encoded_message = asn1.encode_decode.encode_tpaa_message(refresh_token_message)

                await websocket_info.websocket.send(encoded_message)

        await asyncio.sleep(1)  # check every second


async def main():
    token_request_url = "https://192.168.100.15:8443/realms/master/protocol/openid-connect/token"

    keycloack_cert = cert_path
    ## If client authentication is needed, provide the client certificate and key paths
    #client_cert = (
    #    r"/home/raspberry/Desktop/rti2_protocol_spec/exploration/certs/new_certs/client1.crt",
    #    r"/home/raspberry/Desktop/rti2_protocol_spec/exploration/certs/new_certs/client1.key"
    #)
    tls_config = TLSConfiguration(tls_cert_path, None, False)
    client_cert = None
    client_secret_1 = "jK4S3MnitPLBU92HqncgyvlifDA1ByD6"
    client_id_1 = "ws_client_1"
    access_token_1 = await get_access_token(token_request_url, client_id_1, client_secret_1, keycloack_cert, client_cert)
    ep_wsClient_1 = WebSocketEndpoint(oauth_enable=True, tls_config=tls_config)
    iec61850_server_1 = IEC61850Server(ied1, "cp1")
    ep_wsClient_1.add_iec61850_server(iec61850_server_1)

    task1 = asyncio.create_task(ep_wsClient_1.start("active","192.168.100.14", 8765, "cp1", access_token=access_token_1))
    task_token_1 = asyncio.create_task(refresh_token_if_needed(token_request_url,client_id_1, client_secret_1, access_token_1, ep_wsClient_1, "cp1", client_cert, keycloack_cert))

    await asyncio.gather(task1, task_token_1)

if __name__ == "__main__":
    asyncio.run(main())
