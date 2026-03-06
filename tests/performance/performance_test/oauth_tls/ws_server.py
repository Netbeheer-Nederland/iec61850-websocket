import asyncio
import sys
from time import sleep

from Endpoint.endpoint import *
from IEC61850.client.IEC61850Client import *
from TLSConfig.TLSConfiguration import *

cert_path = ""
for path in sys.path:
    if path.endswith("certs"):
        cert_path = path
        break
key_path = os.path.join(cert_path, "server_perf.key")
server_cert_path = os.path.join(cert_path, "server_perf.crt")
maxMessageSize_server = 65000


optFlds = {
    "seqNum": False,
    "timeStamp": True,
    "dataSet": True,
    "bufOvfl": True,
    "configRef": False,
    "entryID": True,
    "dataRef": False,
    "reasonCode": False,
}

trgOp = {"dchg": False, "qchg": False, "dupd": False, "integrity": True, "gi": False}

brcb = IEC61850Client.ClientReportControlBlock("LD0/LLN0.rcbMinMaxAvg", True)
brcb.rptEna = True
brcb.confRev = 5
brcb.opt_flds = optFlds
brcb.bufTm = 1000
brcb.sqNum = 42
brcb.trgOps = trgOp
brcb.intgPd = 2000
brcb.gi = True
brcb.purgeBuf = False
brcb.entryId = b"\x01\x02\x03\x04\x05\x06\x07\x08"
brcb.timeOfEntry = get_now_time()
brcb.resvTms = 5

urcb = IEC61850Client.ClientReportControlBlock("LD0/LLN0.rcbSetpoints", True)
urcb.rptEna = True
urcb.confRev = 5
urcb.opt_flds = optFlds
urcb.bufTm = 1000
urcb.sqNum = 88
urcb.trgOps = trgOp
urcb.intgPd = 5000
urcb.gi = True
urcb.entryId = b"\x01\x02\x03\x04\x05\x06\x07\x08"
urcb.timeOfEntry = get_now_time()
urcb.resv = True


def callback_called(result, param):
    print("callback called: ", result)


data_attribute_value = {
    "name": "Oper",
    "data": (
        "structure",
        {
            "data": [
                ("structure", {"name": "f", "data": [("float32", 10.5)]}),
                (
                    "structure",
                    {
                        "name": "origin",
                        "data": [
                            ("enumerated", "bayControl"),
                            ("octetString", b"ORIGIN_ID_1234567890"),
                        ],
                    },
                ),
                ("int8u", 2),
                (
                    "timeStamp",
                    {
                        "secondSinceEpoch": 1757588367,
                        "fractionOfSecond": 8120140,
                        "timeQuality": {
                            "leapSecondsKown": False,
                            "clockFailure": False,
                            "clockNotSynchronized": False,
                            "timeAccuracy": 3,
                        },
                    },
                ),
                ("boolean", False),
                ("check", {"synchroCheck": False, "interlockCheck": True}),
            ]
        },
    ),
}

data_WMaxSetPct = [
    {
        "name": "setMag",
        "data": ("structure", {"name": "f", "data": [("float32", 19.666)]}),
    }
]

oper_val = {
    "ref": "LD0/DWMX1.WMaxSpt",
    "ctlVal": ("structure", {"data": [("structure", {"data": [("float32", 666.43)]})]}),
    "origin": {"orCat": "stationControl", "orIdent": b"ORIGIN_ID_1234567890"},
    "ctlNum": 10,
    "t": {
        "secondSinceEpoch": 1757588367,
        "fractionOfSecond": 8120140,
        "timeQuality": {
            "leapSecondsKown": False,
            "clockFailure": False,
            "clockNotSynchronized": False,
            "timeAccuracy": 3,
        },
    },
    "test": True,
    "check": {"synchroCheck": False, "interlockCheck": False},
}


async def add_iec61850_client_requests(iec61850_client, ep_wsServer):
    await iec61850_client.ready_event.wait()
    if iec61850_client.is_connected is True:
        websocket_info = ep_wsServer.get_websocket_info(iec61850_client)
        if websocket_info is not None:
            try:
                server_list = await iec61850_client.get_server_directory(websocket_info, None, None)
                ld_directory = await iec61850_client.get_logical_device_directory("LD0", websocket_info, None, None)
                ln_directory_ds = await iec61850_client.get_logical_node_directory(
                    "LD0", "LLN0", "dataset", websocket_info, None, None
                )
                ln_directory_do = await iec61850_client.get_logical_node_directory(
                    "LD0", "LLN0", "dataObject", websocket_info, None, None
                )
                ds_directory = await iec61850_client.get_dataset_directory(
                    "LD0", "LLN0", "DataSetMinMaxAvg", websocket_info, None, None
                )
                set_urcb_res = await iec61850_client.set_URCB_values(urcb, websocket_info, None, None)
                da_def = await iec61850_client.get_data_definition("LD0/DWMX1.WMaxSptPct", websocket_info, None, None)

                set_da_res = await iec61850_client.set_data_values(
                    "LD0/DWMX1.WMaxSpt.Oper",
                    "co",
                    [data_attribute_value],
                    websocket_info,
                    None,
                    None,
                )
                da_val = await iec61850_client.get_data_values(
                    "LD0/DWMX1.WMaxSpt.Oper", "co", True, websocket_info, None, None
                )

            except Exception as e:
                print("handler not called:", e)


async def add_iec61850_clients(ep_wsServer, cp):
    iec61850_client = IEC61850Client(cp)
    ep_wsServer.add_iec61850_client(iec61850_client)


project_root = ""
for path in sys.path:
    if path.endswith("certs"):
        project_root = path
        break
kc_cert_path = os.path.join(project_root, "keycloak.crt")


async def main():
    # TLS config for server
    try:
        tls_config_server = TLSConfiguration(cert_path=server_cert_path, key_path=key_path, is_ws_server=True)
        ssl_context = tls_config_server.ssl_context
        tls_config_server.ssl_context.keylog_filename = os.path.join("tlskeys.log")
    except FileNotFoundError:
        print(
            "CRITICAL ERROR: Server certificate or key not found. Ensure 'server.crt' and 'server.key' exist in the 'certs' directory."
        )
        return
    except Exception as e:
        print(f"CRITICAL ERROR: Failed to load server TLS configuration: {e}")
        return

    ep_wsServer = WebSocketEndpoint(
        oauth_enable=True,
        tls_config=tls_config_server,
        cert_endpoint="https://192.168.100.15:8443/realms/master/protocol/openid-connect/certs",
        token_issuer="https://192.168.100.15:8443/realms/master",
        kc_cert=kc_cert_path,
    )

    for i in range(0, 1001):
        await add_iec61850_clients(ep_wsServer, "cp" + str(i))

    server_task = asyncio.create_task(ep_wsServer.start("passive", "localhost", 8765))

    await asyncio.sleep(2)

    request_tasks = []
    for client in ep_wsServer.client_list:
        task = asyncio.create_task(add_iec61850_client_requests(client, ep_wsServer))
        request_tasks.append(task)

    await asyncio.gather(*request_tasks)

    await server_task


if __name__ == "__main__":
    asyncio.run(main())
