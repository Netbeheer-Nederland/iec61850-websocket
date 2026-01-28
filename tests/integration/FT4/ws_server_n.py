from ws61850.endpoint.endpoint import *
from ws61850.iec61850.client.iec61850_client import *

maxMessageSize_server = 65000

oper_val_wrong_type = {
    "ref": "LD0/DWMX1.WMaxSpt", "ctlVal": ('int64', 16),
    "origin": {
        "orCat": "stationControl",
        "orIdent": b'ORIGIN_ID_1234567890'
    },
    "ctlNum": 10,
    "t": {
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
oper_val_out_of_range = {
    "ref": "LD0/DWMX1.WMaxSpt", "ctlVal": ('float32', 1000.44),
    "origin": {
        "orCat": "stationControl",
        "orIdent": b'ORIGIN_ID_1234567890'
    },
    "ctlNum": 10,
    "t": {
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
oper_val_incorrect_do = {
    "ref": "LD0/DWMX1.WMaxSetPct", "ctlVal": ('float32', 14.2),
    "origin": {
        "orCat": "stationControl",
        "orIdent": b'ORIGIN_ID_1234567890'
    },
    "ctlNum": 10,
    "t": {
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

oper_val_setMag = {
    "ref": "DWMX1.WMaxSet", "ctlVal": ('float32', 11.86),
    "origin": {
        "orCat": "stationControl",
        "orIdent": b'ORIGIN_ID_333'
    },
    "ctlNum": 10,
    "t": {
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

setMag_val = [{'name': 'setMag', 'data': ('structure', {'data': [('float32', 67.39)]})}]
setMag_wrong = [{'name': 'setMag', 'data': ('structure', {'data': [('boolean', False)]})}]


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

                print("doing the negative test case: ")
                da_val = await ep_wsServer.client_list[0].get_data_values("LD0/DWMX1.WMaxSpt_wrong", "mx", True,
                                                                          websocket_info, None, None)
                print("result of getDataValues with a wrong reference", da_val)

                select_result = await ep_wsServer.client_list[0].select("LD0/DWMX1.WMaxSetPct", websocket_info, None,
                                                                        None)
                print(select_result)

                operate_result = await ep_wsServer.client_list[0].operate(oper_val_wrong_type, websocket_info, None,
                                                                          None)
                print("result for incorrect data type in operate request", operate_result)

                operate_result = await ep_wsServer.client_list[0].operate(oper_val_incorrect_do, websocket_info, None,
                                                                          None)
                print("result for incorrect data object for performing operate request", operate_result)

                set_val_res = await ep_wsServer.client_list[0].set_data_values("LD0/DWMX1.WMaxSet.setMag_wrong", "sp",
                                                                               setMag_val,
                                                                               websocket_info, None, None)

                print("result for setDataValue for a nonexistent object", set_val_res)

                set_val_res = await ep_wsServer.client_list[0].set_data_values("LD0/DWMX1.WMaxSet.setMag", "sp",
                                                                               setMag_wrong,
                                                                               websocket_info, None, None)
                #
                print("result for setDataValue for a incorrect type of value", set_val_res)
                #
                select_result = await ep_wsServer.client_list[0].select("LD0/DWMX1.WMaxSpt", websocket_info, None,
                                                                        None)
                print("select result: ", select_result)

                operate_result = await ep_wsServer.client_list[0].operate(oper_val_out_of_range, websocket_info, None,
                                                                          None)
                print("result for out of range data in operate request", operate_result)



            except Exception as e:
                print("handler not called:", e)

    else:
        print("did not enter first if ")

    await server_task


if __name__ == "__main__":
    asyncio.run(main())
