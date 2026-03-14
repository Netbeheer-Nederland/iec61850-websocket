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

from ws61850.endpoint.endpoint import WebSocketEndpoint
from ws61850.iec61850.client.iec61850_client import IEC61850Client

maxMessageSize_server = 65000

oper_val = {
    "ref": "LD0/DWMX1.WMaxSpt",
    "ctlVal": ("float32", 26.43),
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
oper_val_setMag = {
    "ref": "DWMX1.WMaxSet.setMag",
    "ctlVal": ("structure", {"data": [("float32", 11.86)]}),
    "origin": {"orCat": "stationControl", "orIdent": b"ORIGIN_ID_333"},
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

setMag_val = [{"name": "setMag", "data": ("structure", {"data": [("float32", 67.39)]})}]


async def main():
    # websocket server
    ep_wsServer = WebSocketEndpoint()

    iec61850_client = IEC61850Client("cp1")
    ep_wsServer.add_iec61850_client(iec61850_client)

    server_task = asyncio.create_task(ep_wsServer.start("passive", "localhost", 8765))

    await ep_wsServer.client_list[0].ready_event.wait()
    if ep_wsServer.client_list[0].is_connected is True:
        websocket_info = ep_wsServer.get_websocket_info(ep_wsServer.client_list[0])
        if websocket_info is not None:
            try:
                ###mxVal
                da_val = await ep_wsServer.client_list[0].get_data_values(
                    "LD0/DWMX1.WMaxSpt", "mx", True, websocket_info, None, None
                )
                print(da_val)
                select_result = await ep_wsServer.client_list[0].select("LD0/DWMX1.WMaxSpt", websocket_info, None, None)
                print(select_result)
                operate_result = await ep_wsServer.client_list[0].operate(oper_val, websocket_info, None, None)
                print(operate_result)

                da_val = await ep_wsServer.client_list[0].get_data_values(
                    "LD0/DWMX1.WMaxSpt", "mx", True, websocket_info, None, None
                )
                print(da_val)

                ####setMag

                da_val = await ep_wsServer.client_list[0].get_data_values(
                    "LD0/DWMX1.WMaxSet", "sp", True, websocket_info, None, None
                )
                print(da_val)

                set_val_res = await ep_wsServer.client_list[0].set_data_values(
                    "LD0/DWMX1.WMaxSet.setMag",
                    "sp",
                    setMag_val,
                    websocket_info,
                    None,
                    None,
                )
                print(set_val_res)

                da_val = await ep_wsServer.client_list[0].get_data_values(
                    "LD0/DWMX1.WMaxSet", "sp", True, websocket_info, None, None
                )
                print(da_val)

            except Exception as e:
                print("handler not called:", e)

    else:
        print("did not enter first if ")

    await server_task


if __name__ == "__main__":
    asyncio.run(main())
