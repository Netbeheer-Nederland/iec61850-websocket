from ws61850.endpoint.endpoint import *
from ws61850.iec61850.client.iec61850_client import *


async def test_protocol_rejection(endpoint, mode, host, port, cp, protocol):
    try:
        await endpoint.start(mode, host, port, cp, protocol=protocol)

    except Exception as e:
        print(f"Caught exception type: {type(e).__name__}")
        print(f"Error Message: {e}")


async def main():
    # websocket server
    ep_wsClient_1 = WebSocketEndpoint(is_direct=True)
    iec61850_client_1 = IEC61850Client("cp1")
    ep_wsClient_1.add_iec61850_client(iec61850_client_1)
    protocol = ["iec61850-tpaa-ber-v1"]

    await test_protocol_rejection(ep_wsClient_1, mode='active', host='localhost', port=8765, cp='cp1',
                                  protocol=protocol)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTest stopped by user.")
