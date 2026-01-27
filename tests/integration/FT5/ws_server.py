from time import sleep

from Endpoint.endpoint import *
import asyncio
from IEC61850.client.IEC61850Client import *

maxMessageSize_server = 65000


trgOp = {"dchg": False, "qchg": True, "dupd": False, "integrity": False, "gi": True}


urcb = IEC61850Client.ClientReportControlBlock("LD0/LLN0.rcbSetpoints", True)
urcb.trgOps = trgOp


urcb_2 = IEC61850Client.ClientReportControlBlock("LD0/LLN0.rcbSetpoints", True)
urcb_2.gi = True
urcb_2.rptEna = True


def callback_called(result, param):
    print("callback called: ", result)


data_attribute_value = {
    "name": "Oper",
    "data": ("structure",
        {
            "data": [
                        ("structure",
                            {
                                "name": "f",
                                "data": [("float32", 10.5)]
                            }
                        ),
                        ("structure", {
                            "name": "origin",
                            "data": [("enumerated", "bayControl"), ("octetString", b"ORIGIN_ID_1234567890")]
                        }),
                        ("int8u", 2),
                        ("timeStamp", {
                                    "secondSinceEpoch": 1757588367,
                                    "fractionOfSecond": 8120140,
                                    "timeQuality": {
                                        "leapSecondKnown": False,
                                        "clockFailure": False,
                                        "clockNotSynchronized": False,
                                        "timeAccuracy": 3
                                    }
                                }),
                        ("boolean", False),
                        ("check",
                                {
                                    "synchroCheck": False,
                                    "interlockCheck": True
                                }
                        )
            ]
        }
    )
}

data_WMaxSetPct = [{"name": "setMag", "data": ("structure", {"name": "f", "data": [("float32", 19.666)]})}]
#"ctlVal":('structure', {'data': [('float32', 26.43)]})
oper_val= {
            "ref": "LD0/DWMX1.WMaxSpt", "ctlVal":('float32', 26.43),
            "origin": {
                    "orCat": "stationControl",
                    "orIdent": b'ORIGIN_ID_1234567890'
           },
           "ctlNum": 10,
           "t" : {
                    "secondSinceEpoch": 1757588367,
                    "fractionOfSecond": 8120140,
                    "timeQuality": {
                      "leapSecondKnown": False,
                      "clockFailure": False,
                      "clockNotSynchronized": False,
                      "timeAccuracy": 3
                  }
                },
           "test": True,
           "check": {
                        "synchroCheck": False,
                        'interlockCheck': False
                    }
           }


async def main():
    # websocket server
    ep_wsServer = WebSocketEndpoint()

    iec61850_client = IEC61850Client("cp1")
    ep_wsServer.add_iec61850_client(iec61850_client)

    server_task = asyncio.create_task(
        ep_wsServer.start("passive", "192.168.100.14", 8765)
    )

    await ep_wsServer.client_list[0].ready_event.wait()
    if ep_wsServer.client_list[0].is_connected is True:
        websocket_info = ep_wsServer.get_websocket_info(ep_wsServer.client_list[0])
        if websocket_info is not None:
            try:
                set_urcb_res = await ep_wsServer.client_list[0].set_URCB_values(urcb, websocket_info, callback_called, None)
                print("set_urcb_res:", set_urcb_res)

                set_urcb_res = await ep_wsServer.client_list[0].set_URCB_values(urcb_2, websocket_info, callback_called,
                                                                                None)
                print("set_urcb_res:", set_urcb_res)

                select_result = await ep_wsServer.client_list[0].select("LD0/DWMX1.WMaxSpt", websocket_info, None, None)
                print(select_result)
                operate_result = await ep_wsServer.client_list[0].operate(oper_val, websocket_info, None, None)
                print(operate_result)



            except Exception as e:
                print("handler not called:", e)

    else:
        print("did not enter first if ")




    await server_task

if __name__ == "__main__":
    asyncio.run(main())
