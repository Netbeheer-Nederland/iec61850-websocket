import asyncio
from random import randint


from ws61850.endpoint.endpoint import WebSocketEndpoint
from ws61850.iec61850.data_model.example_ieds import build_model1, build_model2
from ws61850.iec61850.server.iec61850_server import IEC61850Server

maxMessageSize = 65000


async def toggle_custom_value(iec61150_server, obj_ref):
    while True:
        value = randint(1, 5)
        await iec61150_server.update_value(obj_ref, value)
        print(f"Value of {obj_ref} changed to {value}")
        await asyncio.sleep(5)


def received_msg_callback(msg, timestamp):
    print(f"(received message): {timestamp}: {msg}")


def send_msg_callback(msg, timestamp):
    print(f"(sent message): {timestamp}: {msg}")


async def main():
    # websocket client
    ep_wsServer = WebSocketEndpoint(is_direct=True)
    ep_wsServer.recv_msg_callback = received_msg_callback
    ep_wsServer.send_msg_callback = send_msg_callback
    iec61850_server = IEC61850Server(build_model1(), "cp1")
    report_task_1 = asyncio.create_task(iec61850_server.periodic_report_start())
    ep_wsServer.add_iec61850_server(iec61850_server)

    iec61850_server = IEC61850Server(build_model2(), "cp2")
    toggle_task_2 = asyncio.create_task(toggle_custom_value(iec61850_server, "LD0/DGEN1.DEROpSt.stVal"))

    ep_wsServer.add_iec61850_server(iec61850_server)

    server_task = asyncio.create_task(ep_wsServer.start("passive", "localhost", 8765))

    # await server_task
    await asyncio.gather(server_task, report_task_1, toggle_task_2)


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

# if __name__ == "__main__":
#
#     for task in asyncio.all_tasks():
#         if task is not asyncio.current_task():
#             task.cancel()
#
#     asyncio.sleep(1)
#
#     asyncio.run(main())
