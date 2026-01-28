# from time import sleep
import os
import sys

from ws61850.endpoint.endpoint import *
from ws61850.iec61850.client.iec61850_client import *

maxMessageSize_server = 65000

data_WMaxSetPct = [{"name": "setMag", "data": ("structure", {"name": "f", "data": [("float32", 19.48)]})}]

optFlds = {"seqNum": False, "timeStamp": True, "dataSet": True, "bufOvfl": True, "configRef": False,
           "entryID": True, "dataRef": False, "reasonCode": False}

trgOp = {"dchg": False, "qchg": False, "dupd": False, "integrity": True, "gi": False}

brcb = IEC61850Client.ClientReportControlBlock("LD0/LLN0.rcbMinMaxAvg", True)
brcb.rptEna = True

brcb.confRev = 5
brcb.optFlds = optFlds
brcb.bufTm = 1000
brcb.sqNum = 42
brcb.trgOps = trgOp
brcb.intgPd = 2000
brcb.gi = True
brcb.purgeBuf = False
brcb.entryId = b'\x01\x02\x03\x04\x05\x06\x07\x08'
brcb.timeOfEntry = get_now_time()
brcb.resvTms = 5

urcb = IEC61850Client.ClientReportControlBlock("LD0/LLN0.rcbSetpoints", True)
urcb.rptEna = True
urcb.confRev = 5000
urcb.optFlds = optFlds
urcb.bufTm = 1000
urcb.sqNum = 88
urcb.trgOps = trgOp
urcb.intgPd = 5
urcb.gi = True
urcb.entryId = b'\x01\x02\x03\x04\x05\x06\x07\x08'
urcb.timeOfEntry = get_now_time()
urcb.resv = True


def callback_called(result, param):
    print("callback called: ", result)


project_root = ""
for path in sys.path:
    if path.endswith("certs"):
        project_root = path
        break
kc_cert_path = os.path.join(project_root, 'keycloak.crt')


async def main():
    # websocket server
    # ws_id = "ws_server"
    # ws_secret = "K4Nrd14seXG52J3xpnIqfMyILTJJu3VI"
    # url = "https://192.168.100.15:8443/realms/master/protocol/openid-connect/token/introspect"
    # introspect example
    # access_token_validation = introspect_token(ws_id, ws_secret, url, access_token["access_token_raw"])
    # if access_token_validation:
    #    print("introspection succeeded")
    # else:
    #    print("introspection failed")

    ep_wsServer = WebSocketEndpoint(oauth_enable=True,
                                    cert_endpoint="https://192.168.100.15:8443/realms/master/protocol/openid-connect/certs",
                                    token_issuer="https://192.168.100.15:8443/realms/master", kc_cert=kc_cert_path)

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
                server_list = await ep_wsServer.client_list[0].get_server_directory(websocket_info, callback_called,
                                                                                    None)
                ld_directory = await ep_wsServer.client_list[0].get_logical_device_directory("LD0", websocket_info,
                                                                                             callback_called, None)
                ln_directory_ds = await ep_wsServer.client_list[0].get_logical_node_directory("LD0", "LLN0", "dataset",
                                                                                              websocket_info,
                                                                                              callback_called, None)
                ln_directory_do = await ep_wsServer.client_list[0].get_logical_node_directory("LD0", "LLN0",
                                                                                              "dataObject",
                                                                                              websocket_info,
                                                                                              callback_called, None)
                ds_directory = await ep_wsServer.client_list[0].get_dataset_directory("LD0", "LLN0", "DataSetMinMaxAvg",
                                                                                      websocket_info, callback_called,
                                                                                      None)
                da_def = await ep_wsServer.client_list[0].get_data_definition("LD0/LLN0.Mod", websocket_info,
                                                                              callback_called, None)
                da_val = await ep_wsServer.client_list[0].get_data_values("LD0/DWMX1.WMaxSetPct", "sp", True,
                                                                          websocket_info, callback_called, None)
                set_da_res = await ep_wsServer.client_list[0].set_data_values("LD0/DWMX1.WMaxSetPct", "sp",
                                                                              data_WMaxSetPct,
                                                                              websocket_info, callback_called, None)
                set_brcb_res = await ep_wsServer.client_list[0].set_BRCB_values(brcb, websocket_info, callback_called,
                                                                                None)

                print("printing the list or returned items from client 1")
                print("server_list:", server_list)
                print("ld_directory:", ld_directory)
                print("ln_directory_ds:", ln_directory_ds)
                print("ln_directory_do:", ln_directory_do)
                print("ds_directory:", ds_directory)
                print("da_def:", da_def)
                print("da_val:", da_val)
                print("set_da_res:", set_da_res)
                print("set_brcb_res:", set_brcb_res)



            except Exception as e:
                print("handler not called:", e)
        else:
            print("websocket_info is None")
    else:
        print("did not enter first if ")

    await server_task


if __name__ == "__main__":
    asyncio.run(main())
