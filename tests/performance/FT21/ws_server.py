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
import logging
import sys

from ws61850.endpoint.passive_endpoint import PassiveEndpoint
from ws61850.iec61850.client.iec61850_client import IEC61850Client

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    stream=sys.stdout,
)

trgOp_urcb = {
    "dchg": False,
    "qchg": False,
    "dupd": False,
    "integrity": True,
    "gi": False,
}

urcb = IEC61850Client.ClientReportControlBlock("LD0/LLN0.rcbSetpoints", False)
urcb.rptEna = True
urcb.trgOps = trgOp_urcb
urcb.intgPd = 1000


def callback_called(result, param):
    logger.info("callback called: %s", result)


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
                            ("enumerated", 1),
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
    "ref": "LD0/DWMX1.WMaxSpt.mxVal",
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


async def main():
    endpoint = PassiveEndpoint()

    client1 = IEC61850Client("cp1")
    endpoint.add_iec61850_client(client1)

    client2 = IEC61850Client("cp2")
    endpoint.add_iec61850_client(client2)

    server_task = asyncio.create_task(
        endpoint.start("localhost", 8765, protocol=["iec61850-tpaa-jer-v1"])
    )

    await client1.ready_event.wait()
    if client1.is_connected is True:
        websocket_info = endpoint.get_websocket_info(client1)
        if websocket_info is not None:
            try:
                server_list = await client1.get_server_directory(websocket_info, callback_called, None)
                ld_directory = await client1.get_logical_device_directory("LD0", websocket_info, callback_called, None)
                ln_directory_do = await client1.get_logical_node_directory(
                    "LD0", "LLN0", "dataObject", websocket_info, callback_called, None
                )
                ds_directory = await client1.get_dataset_directory(
                    "LD0", "LLN0", "DataSetMinMaxAvg", websocket_info, callback_called, None
                )
                da_def = await client1.get_data_definition("LD0/DWMX1.WMaxSptPct", websocket_info, callback_called, None)
                da_dir = await client1.get_data_directory("LD0/MMXU1.A", websocket_info, callback_called, None)
                set_da_res = await client1.set_data_values(
                    "LD0/DWMX1.WMaxSpt.Oper", "co", [data_attribute_value], websocket_info, callback_called, None
                )
                await client1.select("LD0/DWMX1.WMaxSpt", websocket_info, callback_called, None)
                await client1.operate(oper_val, websocket_info, callback_called, None)
                await client1.get_data_values("LD0/DWMX1.WMaxSpt.Oper", "co", True, websocket_info, callback_called, None)
                set_urcb_res = await client1.set_URCB_values(urcb, websocket_info, callback_called, None)

            except Exception as e:
                logger.exception("Service call failed: %s", e)
    else:
        logger.warning("Client did not connect")

    await server_task


if __name__ == "__main__":
    asyncio.run(main())
