# from Examples.ieds.high_level_model import ied as ied1
# from Examples.ieds.ied_model_2 import ied as ied2
# from Endpoint.endpoint import *
import asyncio
# from IEC61850.server.IEC61850Server import *
# from IEC61850.server.control_handling import *
# from IEC61850.server.service_error import *

from testing.ieds.high_level_model import make_ied_model1
from ws61850.endpoint.endpoint import WebSocketEndpoint
from ws61850.iec61850.server.control_handling import ControlHandlerResult, ControlServiceStatusKind
from ws61850.iec61850.server.iec61850_server import IEC61850Server
from ws61850.iec61850.server.service_error import ServiceStatusKind

maxMessageSize = 65000

async def connect_with_retry(endpoint, mode, host, port, cp, protocol=None, max_retries=None, delay=5):
    """Try to connect repeatedly until success or max_retries reached."""
    attempt = 0
    while True:
        try:
            print(f"Attempting to connect to {host}:{port} (attempt {attempt + 1})...")
            await endpoint.start(mode, host, port, cp, protocol=protocol)
            #print("Connected successfully.")
            break  # Exit loop if connected
        except (ConnectionRefusedError, OSError) as e:
            attempt += 1
            print(f"Connection failed: {e}")
            if max_retries and attempt >= max_retries:
                print(" Max retries reached. Giving up.")
                return
            print(f"Retrying in {delay} seconds...")
            await asyncio.sleep(delay)
        except Exception as e:
            print(f"Unexpected error: {e}")
            await asyncio.sleep(delay)

async def main():
    protocol = ["iec61850-tpaa-ber-v1"]
    ep_wsClient_1 = WebSocketEndpoint()
    iec61850_server_1 = IEC61850Server(make_ied_model1(), "cp1")
    ep_wsClient_1.add_iec61850_server(iec61850_server_1)

    # Keep trying to connect every 5 seconds if the server is unavailable
    await connect_with_retry(ep_wsClient_1, "active", "localhost", 8765, "cp1", protocol=protocol)

if __name__ == "__main__":
    asyncio.run(main())