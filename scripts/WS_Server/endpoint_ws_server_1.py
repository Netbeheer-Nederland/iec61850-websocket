import os

import asyncio
import sys
import traceback

from ws61850.endpoint.endpoint import WebSocketEndpoint
from ws61850.iec61850.client.iec61850_client import IEC61850Client

project_root = ""
for path in sys.path:
    if path.endswith("exploration"):
        project_root = path
        break

cert_path = os.path.join(project_root, 'certs', 'server.crt')
key_path = os.path.join(project_root, 'certs', 'server.key')

maxMessageSize_server = 65000

optFlds = {"seqNum": False, "timeStamp": True, "dataSet": True, "bufOvfl": True, "configRef": False,
           "entryID": True, "dataRef": False, "reasonCode": False}

trgOp = {"dchg": False, "qchg": False, "dupd": False, "integrity": True, "gi": False}

# brcb = IEC61850Client.ClientReportControlBlock("LD0/LLN0.rcbMinMaxAvg", True)
#
# #brcb.rptId = "Report1"
# brcb.rptEna = True
# # rcb.resv = "ReservedValue"
# #brcb.datSet = "Dataset1"
# brcb.confRev = 5
# brcb.optFlds = optFlds
# brcb.bufTm = 1000
# brcb.sqNum = 42
# brcb.trgOps = trgOp
# brcb.intgPd = 2000
# brcb.gi = True
# brcb.purgeBuf = False
# brcb.entryId = b'\x01\x02\x03\x04\x05\x06\x07\x08'
# brcb.timeOfEntry = get_now_time()
# brcb.resvTms = 5

trgOp_urcb = {"dchg": False, "qchg": False, "dupd": False, "integrity": True, "gi": False}

urcb = IEC61850Client.ClientReportControlBlock("LD0/LLN0.rcbSetpoints", False)

# urcb.rptId = "new_Report"
urcb.rptEna = True
# urcb.datSet = "new_Dataset"
# urcb.confRev = 5
# urcb.optFlds = optFlds
# urcb.bufTm = 1000
# urcb.sqNum = 88
urcb.trgOps = trgOp_urcb
urcb.intgPd = 1000


# urcb.gi = True
# urcb.entryId = b'\x01\x02\x03\x04\x05\x06\x07\x08'
# urcb.timeOfEntry = get_now_time()
# urcb.resv = True


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

oper_val = {
    "ref": "LD0/DWMX1.WMaxSpt.mxVal",
    "ctlVal": ('structure', {'data': [('structure', {'data': [('float32', 666.43)]})]}),
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
                # urcb_list = await ep_wsServer.client_list[0].get_logical_node_directory("LD0", "LLN0", "urcb",
                #                                                            websocket_info, callback_called, None)
                # brcb_list = await ep_wsServer.client_list[0].get_logical_node_directory("LD0", "LLN0", "brcb",
                #                                                            websocket_info, callback_called, None)
                ###server_list = await ep_wsServer.client_list[0].get_server_directory(websocket_info, callback_called, None)
                ###ld_directory = await ep_wsServer.client_list[0].get_logical_device_directory("LD0", websocket_info, callback_called, None)
                # ln_directory_ds = await ep_wsServer.client_list[0].get_logical_node_directory("LD0", "LLN0", "dataset",
                #                                                            websocket_info, callback_called, None)
                ###ln_directory_do = await ep_wsServer.client_list[0].get_logical_node_directory("LD0", "LLN0", "dataObject",
                ###                                                            websocket_info, callback_called, None)
                ###ds_directory = await ep_wsServer.client_list[0].get_dataset_directory("LD0", "LLN0", "DataSetMinMaxAvg",
                ####                                                       websocket_info, callback_called, None)
                ###da_def = await ep_wsServer.client_list[0].get_data_definition("LD0/DWMX1.WMaxSptPct", websocket_info, callback_called, None)
                ###da_dir = await ep_wsServer.client_list[0].get_data_directory("LD0/MMXU1.A",
                ###                                                             websocket_info, callback_called, None)
                ###set_da_res = await ep_wsServer.client_list[0].set_data_values("LD0/DWMX1.WMaxSpt.Oper", "co", [data_attribute_value],
                ###                                               websocket_info, callback_called, None)
                # da_val = await ep_wsServer.client_list[0].get_data_values("LD0/DWMX1.WMaxSpt.Oper", "co", True, websocket_info, callback_called, None)
                # await ep_wsServer.client_list[0].get_data_values("LD0/DWMX1.WMaxSetPct", "sp", True, websocket_info, callback_called, None)

                ####Select######
                ###await ep_wsServer.client_list[0].select("LD0/DWMX1.WMaxSpt", websocket_info, callback_called, None)
                # await ep_wsServer.client_list[0].select("LD0/DWMX1.WMaxSpt", websocket_info, callback_called, None)

                ####Operate#####
                # await ep_wsServer.client_list[0].set_data_values("LD0/DWMX1.WMaxSpt.Oper", "co", [data_attribute_value],
                #                                               websocket_info, callback_called, None)
                # await ep_wsServer.client_list[0].operate(oper_val, websocket_info, callback_called, None)
                ###await ep_wsServer.client_list[0].get_data_values("LD0/DWMX1.WMaxSpt.Oper", "co", True, websocket_info,
                ###                                                callback_called, None)

                # set_brcb_res = await ep_wsServer.client_list[0].set_BRCB_values(brcb, websocket_info, callback_called, None)
                set_urcb_res = await ep_wsServer.client_list[0].set_URCB_values(urcb, websocket_info, callback_called,
                                                                                None)

                print("printing the list or returned items from client 1")
                # print("urcb_list:", urcb_list)
                # print("brcb_list:", brcb_list)
                ###print("server_list:", server_list)
                ###print("ld_directory:", ld_directory)
                # print("ln_directory_ds:", ln_directory_ds)
                ###print("ln_directory_do:", ln_directory_do)
                ###print("ds_directory:", ds_directory)
                ###print("da_def:", da_def)
                ###print("da_dir:", da_dir)
                # print("da_val:", da_val)
                ###print("set_da_res:", set_da_res)
                # print("set_brcb_res:", set_brcb_res)
                print("set_urcb_res:", set_urcb_res)



            except Exception as e:
                print("handler not called:", e)
                traceback.print_exc()

    else:
        print("did not enter first if ")

    # await ep_wsServer.client_list[1].ready_event.wait()
    #
    # if ep_wsServer.client_list[1].is_connected is True:
    #     websocket_info = ep_wsServer.get_websocket_info(ep_wsServer.client_list[1])
    #     if websocket_info is not None:
    #         server_list = await ep_wsServer.client_list[1].get_server_directory(websocket_info, callback_called, None)
    #
    #         ld_directory = await ep_wsServer.client_list[1].get_logical_device_directory("LD0", websocket_info,
    #                                                                                      callback_called, None)
    #
    #         ln_directory_do = await ep_wsServer.client_list[1].get_logical_node_directory("LD0", "DWMX1", "dataObject",
    #                                                                                       websocket_info,
    #                                                                                       callback_called, None)
    #
    #         da_def = await ep_wsServer.client_list[1].get_data_definition("LD0/DWMX1.WMaxSetPct", websocket_info,
    #                                                                       callback_called, None)
    #         #set_urcb_res = await ep_wsServer.client_list[1].set_URCB_values(urcb, websocket_info, callback_called, None)
    #
    #         print("printing the list or returned items from client 2")
    #         print("server_list:", server_list)
    #         print("ld_directory:", ld_directory)
    #         print("ln_directory_do:", ln_directory_do)
    #         print("da_def:", da_def)
    #         #print("set_urcb_res:", set_urcb_res)
    #
    # else:
    #     print("did not enter second if ")

    await server_task


if __name__ == "__main__":
    asyncio.run(main())
