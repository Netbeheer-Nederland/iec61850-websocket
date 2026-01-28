from ws61850.endpoint.endpoint import *
from ws61850.iec61850.client.iec61850_client import *

maxMessageSize_server = 65000

trgOp = {"dchg": True, "qchg": False, "dupd": False, "integrity": False, "gi": False}

urcb = IEC61850Client.ClientReportControlBlock("LD0/LLN0.rcbSetpoints_wrong", True)
# urcb.rptEna = True
urcb.trgOps = trgOp

urcb_2 = IEC61850Client.ClientReportControlBlock("LD0/LLN0.rcbSetpoints_wrong", True)
urcb_2.rptEna = True


async def main():
    # websocket server
    ep_wsServer = WebSocketEndpoint()

    iec61850_client = IEC61850Client("cp1")
    ep_wsServer.add_iec61850_client(iec61850_client)

    server_task = asyncio.create_task(
        ep_wsServer.start("passive", "localhost", 8765)
    )

    await ep_wsServer.client_list[0].ready_event.wait()
    if ep_wsServer.client_list[0].is_connected is True:
        websocket_info = ep_wsServer.get_websocket_info(ep_wsServer.client_list[0])
        if websocket_info is not None:
            try:
                set_urcb_res = await ep_wsServer.client_list[0].set_URCB_values(urcb, websocket_info, None,
                                                                                None)
                print("set_urcb_res:", set_urcb_res)

                set_urcb_res = await ep_wsServer.client_list[0].set_URCB_values(urcb_2, websocket_info, None,
                                                                                None)
                print("set_urcb_res:", set_urcb_res)




            except Exception as e:
                print("handler not called:", e)

    else:
        print("did not enter first if ")

    await server_task


if __name__ == "__main__":
    asyncio.run(main())
