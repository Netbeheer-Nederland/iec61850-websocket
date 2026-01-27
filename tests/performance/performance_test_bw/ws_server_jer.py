from time import sleep

from Endpoint.endpoint import *
import asyncio
from IEC61850.client.IEC61850Client import *
import sys
import traceback

from TLSConfig.TLSConfiguration import *

maxMessageSize_server = 65000

trgOp_urcb = {"dchg": False, "qchg": False, "dupd": False, "integrity": True, "gi": False}
urcb = IEC61850Client.ClientReportControlBlock("LD0/LLN0.rcbSetpoints", False)
urcb.rptEna = True
urcb.trgOps = trgOp_urcb
urcb.intgPd = 1000


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
                            "data": [("enumerated", 1), ("octetString", b"ORIGIN_ID_1234567890")]
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

oper_val= {
            "ref": "LD0/DWMX1.WMaxSpt.mxVal", "ctlVal":('structure', {'data': [('structure', {'data': [('float32', 666.43)]})]}),
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

    ep_wsServer = WebSocketEndpoint()

    iec61850_client = IEC61850Client("cp1")
    ep_wsServer.add_iec61850_client(iec61850_client)

    iec61850_client = IEC61850Client("cp2")
    ep_wsServer.add_iec61850_client(iec61850_client)

    server_task = asyncio.create_task(
        ep_wsServer.start("passive", "localhost", 8765, protocol=["iec61850-tpaa-jer-v1"])
    )

    await ep_wsServer.client_list[0].ready_event.wait()
    if ep_wsServer.client_list[0].is_connected is True:
        websocket_info = ep_wsServer.get_websocket_info(ep_wsServer.client_list[0])
        if websocket_info is not None:
            try:
                server_list = await ep_wsServer.client_list[0].get_server_directory(websocket_info, callback_called, None)
                ld_directory = await ep_wsServer.client_list[0].get_logical_device_directory("LD0", websocket_info, callback_called, None)
                ln_directory_do = await ep_wsServer.client_list[0].get_logical_node_directory("LD0", "LLN0", "dataObject",
                                                                            websocket_info, callback_called, None)
                ds_directory = await ep_wsServer.client_list[0].get_dataset_directory("LD0", "LLN0", "DataSetMinMaxAvg",
                                                                       websocket_info, callback_called, None)
                da_def = await ep_wsServer.client_list[0].get_data_definition("LD0/DWMX1.WMaxSptPct", websocket_info, callback_called, None)
                da_dir = await ep_wsServer.client_list[0].get_data_directory("LD0/MMXU1.A",
                                                                             websocket_info, callback_called, None)
                set_da_res = await ep_wsServer.client_list[0].set_data_values("LD0/DWMX1.WMaxSpt.Oper", "co", [data_attribute_value],
                                                               websocket_info, callback_called, None)
                ####Select######
                await ep_wsServer.client_list[0].select("LD0/DWMX1.WMaxSpt", websocket_info, callback_called, None)

                ####Operate#####
                await ep_wsServer.client_list[0].operate(oper_val, websocket_info, callback_called, None)
                await ep_wsServer.client_list[0].get_data_values("LD0/DWMX1.WMaxSpt.Oper", "co", True, websocket_info,
                                                                callback_called, None)



                set_urcb_res = await ep_wsServer.client_list[0].set_URCB_values(urcb, websocket_info, callback_called,
                                                                                None)

            except Exception as e:
                print("handler not called:", e)
                traceback.print_exc()

    else:
        print("did not enter first if ")

    await server_task

if __name__ == "__main__":
    asyncio.run(main())