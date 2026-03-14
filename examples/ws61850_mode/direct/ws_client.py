# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
#
# Copyright 2025 Netbeheer Nederland
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import asyncio
import time

import jwt

from ws61850 import asn1
from ws61850.endpoint.endpoint import WebSocketEndpoint
from ws61850.iec61850.client.iec61850_client import IEC61850Client
from ws61850.iec61850.client.request_handling import create_token_refresh
from ws61850.iec61850.data_model.helper import get_now_time
from ws61850.security.oauth import get_access_token

maxMessageSize_server = 65000


def received_msg_callback(msg, timestamp):
    print(f"(received message): {timestamp}: {msg}")


def send_msg_callback(msg, timestamp):
    print(f"(sent message): {timestamp}: {msg}")


data_WMaxSetPct = [
    {
        "name": "setMag",
        "data": ("structure", {"name": "f", "data": [("float32", 19.48)]}),
    }
]

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

# brcb.rptId = "Report1"
brcb.rptEna = True
# rcb.resv = "ReservedValue"
# brcb.datSet = "Dataset1"
brcb.confRev = 5
brcb.optFlds = optFlds
brcb.bufTm = 1000
brcb.sqNum = 42
brcb.trgOps = trgOp
brcb.intgPd = 2000
brcb.gi = True
brcb.purgeBuf = False
brcb.entryId = b"\x01\x02\x03\x04\x05\x06\x07\x08"
brcb.timeOfEntry = get_now_time()
brcb.resvTms = 5

urcb = IEC61850Client.ClientReportControlBlock("LD0/LLN0.rcbSetpoints", False)

# urcb.rptId = "new_Report"
urcb.rptEna = True
# urcb.datSet = "new_Dataset"
urcb.confRev = 5
urcb.optFlds = optFlds
urcb.bufTm = 1000
urcb.sqNum = 88
urcb.trgOps = trgOp
urcb.intgPd = 5000
urcb.gi = True
urcb.entryId = b"\x01\x02\x03\x04\x05\x06\x07\x08"
urcb.timeOfEntry = get_now_time()
urcb.resv = True

urcb_2 = IEC61850Client.ClientReportControlBlock("LD0/LLN0.rcbMinMaxAvg", True)
urcb_2.rptEna = False
urcb_2.trgOps = trgOp
urcb.intgPd = 2000

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


def callback_called(result, param):
    print("callback called!: ", result)


async def refresh_token_if_needed(url, client_id, client_secret, token, websocket_endpoint, cp):
    # jwks_url = "http://localhost:8080/realms/master/protocol/openid-connect/certs"
    while True:
        websocket_info = next(
            (ws_info for ws_info in websocket_endpoint.websocket_info_list if ws_info.cp == cp),
            None,
        )

        if websocket_info is not None:
            decoded = jwt.decode(token, options={"verify_signature": False})

            # Check if less than 3 seconds until expiration
            if decoded["exp"] - time.time() < 3:
                print(f"The access token for {cp} endpoint is expiring soon, requesting a new token...")
                token = get_access_token(url, client_id, client_secret)
                refresh_token_message = create_token_refresh(websocket_info.associate_id, token)
                encoded_message = asn1.encode_decode.encode_tpaa_message(refresh_token_message)

                await websocket_info.websocket.send(encoded_message)

        await asyncio.sleep(1)  # check every second


async def main():
    # websocket server
    # token_request_url = "http://localhost:8080/realms/master/protocol/openid-connect/token"
    #
    # client_secret_1 = "AaA1qTaRDLAsbdBYMXssaXsraPj8Bdp1"
    # client_id_1 = "ws_client_1"
    # access_token_1 = get_access_token(token_request_url, client_id_1, client_secret_1)

    ep_wsClient_1 = WebSocketEndpoint(is_direct=True)
    ep_wsClient_1.recv_msg_callback = received_msg_callback
    ep_wsClient_1.send_msg_callback = send_msg_callback
    iec61850_client_1 = IEC61850Client("cp1")
    ep_wsClient_1.add_iec61850_client(iec61850_client_1)

    # client_secret_2 = "38XeW4HnYQRxNZZxT3oy8SceulBVw9Pm"
    # client_id_2 = "ws_client_2"
    # access_token_2 = get_access_token(token_request_url, client_id_2, client_secret_2)

    ep_wsClient_2 = WebSocketEndpoint(is_direct=True)
    ep_wsClient_2.recv_msg_callback = received_msg_callback
    ep_wsClient_2.send_msg_callback = send_msg_callback
    iec61850_client_2 = IEC61850Client("cp2")
    ep_wsClient_2.add_iec61850_client(iec61850_client_2)

    task1 = asyncio.create_task(ep_wsClient_1.start("active", "localhost", 8765, "cp1"))
    task2 = asyncio.create_task(ep_wsClient_2.start("active", "localhost", 8765, "cp2"))

    # task_token_1 = asyncio.create_task(refresh_token_if_needed(token_request_url,client_id_1, client_secret_1, access_token_1, ep_wsClient_1, "cp1"))
    # task_token_2 = asyncio.create_task(refresh_token_if_needed(token_request_url,client_id_2, client_secret_2, access_token_2, ep_wsClient_2, "cp2"))

    # await ep_wsClient.server_list[0].ready_event.wait()

    await ep_wsClient_1.client_list[0].ready_event.wait()
    if ep_wsClient_1.client_list[0].is_connected is True:
        websocket_info = ep_wsClient_1.get_websocket_info(ep_wsClient_1.client_list[0])
        if websocket_info is not None:
            try:
                await ep_wsClient_1.client_list[0].get_server_directory(websocket_info, callback_called, None)
                await ep_wsClient_1.client_list[0].get_logical_device_directory(
                    "LD0", websocket_info, callback_called, None
                )
                await ep_wsClient_1.client_list[0].set_BRCB_values(brcb, websocket_info, callback_called, None)
                await ep_wsClient_1.client_list[0].get_data_values(
                    "LD0/MMXU1.MinWPhs",
                    "mx",
                    True,
                    websocket_info,
                    callback_called,
                    None,
                )
                await ep_wsClient_1.client_list[0].get_data_definition(
                    "LD0/MMXU1.MinWPhs", websocket_info, callback_called, None
                )
                # await ep_wsClient_1.client_list[0].set_URCB_values(urcb, websocket_info, callback_called, None)

            except Exception as e:
                print("handler not called:", e)
    else:
        print("did not enter first if ")

    await ep_wsClient_2.client_list[0].ready_event.wait()

    if ep_wsClient_2.client_list[0].is_connected is True:
        websocket_info = ep_wsClient_2.get_websocket_info(ep_wsClient_2.client_list[0])
        if websocket_info is not None:
            await ep_wsClient_2.client_list[0].get_server_directory(websocket_info, callback_called, None)
            await ep_wsClient_2.client_list[0].get_logical_device_directory(
                "LD0", websocket_info, callback_called, None
            )
            # await ep_wsServer.client_list[0].set_BRCB_values(brcb, websocket)
            await ep_wsClient_2.client_list[0].set_URCB_values(urcb, websocket_info, callback_called, None)
            await ep_wsClient_2.client_list[0].get_dataset_directory(
                "LD0", "LLN0", "DataSetMinMaxAvg", websocket_info, callback_called, None
            )
            await ep_wsClient_2.client_list[0].set_data_values(
                "LD0/DWMX1.WMaxSpt.Oper",
                "co",
                [data_attribute_value],
                websocket_info,
                callback_called,
                None,
            )
    else:
        print("did not enter second if ")
    await asyncio.gather(task1, task2)


if __name__ == "__main__":
    asyncio.run(main())
