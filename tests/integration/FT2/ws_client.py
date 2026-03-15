import asyncio

from ws61850.endpoint.endpoint import WebSocketEndpoint
from ws61850.iec61850.client.iec61850_client import IEC61850Client

maxMessageSize_server = 65000


async def connect_with_retry(endpoint, mode, host, port, cp, protocol=None, max_retries=10, delay=3):
    # Connect repeatedly until successful or mx_retries reached
    attempt = 0
    while True:
        try:
            print(f"Attempting to connect to {host}:{port} (attempt {attempt + 1})...")
            await endpoint.start(mode, host, port, cp, protocol=protocol)
            # break #Exit loop if connected
            return endpoint.client_list[0]  # return newly connected client
        except (ConnectionRefusedError, OSError) as e:
            attempt += 1
            print(f"Connection failed : {e}")
            if max_retries and attempt >= max_retries:
                print(" Max retries reached. Giving up.")
                return None
            print(f"Retrying in {delay} seconds...")
            await asyncio.sleep(delay)
        except Exception as e:
            attempt += 1
            print(f"Attempt {attempt}: Unexpected error: {e}")
            if attempt >= max_retries:
                return None
            print(f"Retrying in {delay} seconds...")
            await asyncio.sleep(delay)


async def main():
    # websocket server
    ep_wsClient_1 = WebSocketEndpoint(is_direct=True, try_reconnect=False)
    iec61850_client_1 = IEC61850Client("cp1")
    ep_wsClient_1.add_iec61850_client(iec61850_client_1)

    await connect_with_retry(ep_wsClient_1, mode='active', host='localhost', port=8765, cp='cp1')


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Client stopped by user")
