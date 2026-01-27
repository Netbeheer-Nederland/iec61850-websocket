import asyncio
import sys
import time
import os
import ssl
import random
import copy
from Endpoint.endpoint import WebSocketEndpoint
from IEC61850.client.IEC61850Client import *
from IEC61850.server.IEC61850Server import *
from TLSConfig.TLSConfiguration import TLSConfiguration
import jwt
from oauth.oauth_functions import *
import asn1.encode_decode

credentials_path = ""
for path in sys.path:
    if path.endswith("client_credentials"):
        credentials_path = path
        break
credentials_file_path = os.path.join(credentials_path, 'client_credentials_500_1.json')
CREDENTIALS_FILE = credentials_file_path

project_root = ""
for path in sys.path:
    if path.endswith("certs"):
        project_root = path
        break
cert_path = os.path.join(project_root, 'root_CA1.pem')



try:
    # Import modified functions
    from kc_client_gen import generate_clients
    from oauth_controller import authenticate_clients
except ImportError as e:
    print(
        f"Error: Could not import sibling module (kc_client_gen or oauth_controller): {e}. Check if they are in the same directory.")
    sys.exit(1)

try:
    from Examples.ieds.high_level_model import ied as ied1
    from Examples.ieds.ied_model_2 import ied as ied2
except ImportError as e:

    ied1 = {}
    ied2 = {}

max_message_size_client = 65000


def get_now_time():
    return int(time.time())


def callback_called(result, param):
    # Callback for request handling
    pass

async def toggle_float_value(iec61150_server, obj_ref):
    while True:
        value = random.uniform(5.5, 10.0)
        await iec61150_server.update_value(obj_ref, value)
        #print(f"Value of {obj_ref} changed to {value} of server intance {iec61150_server}")
        await asyncio.sleep(1)

async def add_iec61850_client_requests(iec61850_client, ep_wsClient):
    """
    Handles IEC 61850 client requests after connection.
    """
    await iec61850_client.ready_event.wait()

    if iec61850_client.is_connected is True:
        websocket_info = ep_wsClient.get_websocket_info(iec61850_client)

        if websocket_info is not None:
            print(f"[{iec61850_client.cp}] Connection established. Performing requests...")

            try:
                # Placeholder: Clients stay connected for 5 seconds to simulate activity
                await asyncio.sleep(5)

            except Exception as e:
                print(f"[{iec61850_client.cp}] Error during request handler: {e}")
        else:
            print(f"[{iec61850_client.cp}] Connection information not found after ready event.")

deep_copied_ieds = [copy.deepcopy(ied1) for _ in range(500)]
async def start_client_process(client_config, i):
    """
    Initializes and starts a single WebSocket client/IED using its configuration.
    """
    try:
        cp = client_config['cp_id']
        access_token = client_config['access_token']
        # keycloak_cert_path will point to the trust anchor for WSS verification
        keycloak_cert_path = client_config['keycloak_cert_path']

    except KeyError as e:
        print(f"CRITICAL KEY ERROR in start_client_process: Missing key {e}. Config: {client_config}")
        return

    # --- TLS Configuration for Client ---
    try:
        tls_config_client = TLSConfiguration(
            cert_path=cert_path,
            key_path=None,
            is_ws_server=False
        )
        tls_config_client.set_min_and_max_version(min_version=ssl.TLSVersion.TLSv1_2)
        ssl_context = tls_config_client.ssl_context
    except Exception as e:
        print(f"[{cp}] Failed to load TLS configuration: {e}")
        return
    # ------------------------------------

    # Initialize Endpoint and Server
    ep_wsClient = WebSocketEndpoint(oauth_enable=True, tls_config=tls_config_client)

    # Assign IED Model based on client ID number
    #ied_instance = copy.deepcopy(ied1)  # Create a unique IED instance for each server
    ied_instance = deep_copied_ieds[i]
    client_number = int(cp.replace('cp', ''))
    iec61850_server = IEC61850Server(ied_instance, cp)
    ep_wsClient.add_iec61850_server(iec61850_server)

    # Add Report task
    report_task = asyncio.create_task(iec61850_server.periodic_report_start())
    #toggle_task = asyncio.create_task(toggle_float_value(iec61850_server, "LD0/MMXU1.TotW.mag.f"))

    # Add the client object
    #iec61850_client = IEC61850Client(cp)
    #ep_wsClient.add_iec61850_client(iec61850_client)

    print(f"[{cp}] Starting WSS connection...")

    # Start WebSocket Connection - Now correctly including an empty list [] for subprotocols
    client_task = asyncio.create_task(
        ep_wsClient.start(
            "active",
            "192.168.100.5",
            8765,
            cp,
            access_token = access_token
        )
    )

    # Add Request Handling Task
    #request_task = asyncio.create_task(add_iec61850_client_requests(iec61850_client, ep_wsClient))
    #websocket_info = ep_wsClient.get_websocket_info(iec61850_client)

    token_request_url = "https://192.168.100.15:8443/realms/master/protocol/openid-connect/token"
    refresh_task = asyncio.create_task(refresh_token_if_needed(token_request_url, client_config['client_id'], client_config['client_secret'], access_token, ep_wsClient, client_config['cp_id'], cert_path, keycloak_cert_path))

    # Wait for the connection and requests to finish
    try:
        await asyncio.gather(client_task, refresh_task, report_task)
    except Exception as e:
        print(f"[{cp}] Client process failed: {e}")


async def refresh_token_if_needed(url, client_id, client_secret, token, websocket_endpoint, cp, client_cert, keycloack_cert):
    jwks_url = "https://192.168.100.15:8443/realms/master/protocol/openid-connect/certs"
    while True:
        #print("length: ", len(websocket_endpoint.websocket_info_list))
        #print("printing websocket_info_list")
        #print("cp val: ", websocket_endpoint.websocket_info_list[0].cp)
        websocket_info = next((ws_info for ws_info in websocket_endpoint.websocket_info_list if ws_info.cp == cp), None)
        #print(f"websocketInfo",len(websocket_endpoint.websocket_info_list))
        #print(f"cp websocket info: {websocket_info.cp}")
        if websocket_info is not None:
            #print("entered here 1")
            try:
                decoded = jwt.decode(token, options={"verify_signature": False})
                # Check if less than 3 seconds until expiration
                if decoded["exp"] - time.time() < 40:
                    print(f"The access token for {cp} endpoint is expiring soon, requesting a new token...")
                    token = await get_access_token(url, client_id, client_secret, keycloack_cert, client_cert)
                    refresh_token_message = create_token_refresh(websocket_info.associate_id, token)
                    encoded_message = asn1.encode_decode.encode_tpaa_message(refresh_token_message)

                    await websocket_info.websocket.send(encoded_message)
                    print(f"new token sent")
        
            except Exception as e:
                print(f"[{cp}] Failed to refresh token: {e}")
        await asyncio.sleep(1)        

async def run_multi_clients():
    start_time = time.time()

    # Calculate the end ID for logging

    print("STEP 1: Authenticating clients and retrieving live access tokens...")
    authenticated_clients_batch = await authenticate_clients(CREDENTIALS_FILE)

    if not authenticated_clients_batch:
        print("ERROR: No clients were authenticated. Exiting runner.")
        return

    print(f"Step 2 Complete: Retrieved tokens for {len(authenticated_clients_batch)} clients.")
    print("-" * 40)

    # STEP 3: RUN THIS BATCH
    print(f"STEP 3: Starting concurrent execution of {len(authenticated_clients_batch)} clients...")

    startup_tasks = []

    for i, config in enumerate(authenticated_clients_batch):
        task = asyncio.create_task(start_client_process(config, i), name=f"Task-{config['cp_id']}")
        startup_tasks.append(task)
        await asyncio.sleep(0.1)

    try:
        await asyncio.gather(*startup_tasks)
    except Exception as e:
        print(f"An unexpected exception occurred during client execution: {e}")

    end_time = time.time()
    total_time = end_time - start_time
    print("-" * 40)
    print(f"Batch 1 finished. Clients: {len(authenticated_clients_batch)}.")
    print(f"Total Runner Execution Time: {total_time:.2f} seconds.")


if __name__ == "__main__":
    try:
        asyncio.run(run_multi_clients())
    except KeyboardInterrupt:
        print("\nDynamic Client Runner (Batch 1) stopped by user (Ctrl+C).")
    except Exception as e:
        print(f"Critical error in main runner: {e}")
