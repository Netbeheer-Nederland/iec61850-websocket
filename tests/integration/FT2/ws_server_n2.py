from Examples.ieds.high_level_model import ied as ied1
from Examples.ieds.ied_model_2 import ied as ied2
from Endpoint.endpoint import *
import asyncio
from IEC61850.server.IEC61850Server import *

maxMessageSize = 65000

async def main():

    try:
        protocol = ["iec61850-tpaa-jer-v1"]
        # websocket client
        ep_wsServer = WebSocketEndpoint(is_direct=True)
        iec61850_server = IEC61850Server(ied1, "cp1")
        ep_wsServer.add_iec61850_server(iec61850_server)


        server_task = asyncio.create_task(
            ep_wsServer.start("passive", "localhost", 8765, protocol=protocol)
        )

        #await server_task
        await asyncio.gather(server_task)



    except websockets.exceptions.NegotiationError as e:
        print("NegotiationError:", e)
    except Exception as e:
        print("Exception:", e)
    finally:
        print("\nProtocol rejection test complete.")


async def cancel_existing_tasks():
    # Cancel all tasks except the current one
    current = asyncio.current_task()
    for task in asyncio.all_tasks():
        if task is not current:
            task.cancel()
    # Give cancelled tasks time to finish
    await asyncio.sleep(1)



async def main_wrapper():
    await cancel_existing_tasks()
    await main()  # your main function


if __name__ == "__main__":
    asyncio.run(main_wrapper())
