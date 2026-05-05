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
from ws61850.iec61850.client.iec61850_client import IEC61850Client, get_now_time

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    stream=sys.stdout,
)

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
brcb.optFlds = optFlds
brcb.bufTm = 1000
brcb.sqNum = 42
brcb.trgOps = trgOp
brcb.intgPd = 2
brcb.gi = True
brcb.purgeBuf = False
brcb.entryId = b"\x01\x02\x03\x04\x05\x06\x07\x08"
brcb.timeOfEntry = get_now_time()
brcb.resvTms = 5

urcb = IEC61850Client.ClientReportControlBlock("LD0/LLN0.rcbSetpoints", False)
urcb.rptEna = True
urcb.confRev = 5
urcb.optFlds = optFlds
urcb.bufTm = 1000
urcb.sqNum = 88
urcb.trgOps = trgOp
urcb.intgPd = 5
urcb.gi = True
urcb.entryId = b"\x01\x02\x03\x04\x05\x06\x07\x08"
urcb.timeOfEntry = get_now_time()
urcb.resv = True

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

oper_val = {
    "ref": "LD0/DWMX1.WMaxSpt",
    "ctlVal": ("float32", 666.43),
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


def callback_called(result, param):
    logger.info("Callback: %s", result)


async def main():
    endpoint = PassiveEndpoint()

    client = IEC61850Client("cp1")
    endpoint.add_iec61850_client(client)

    asyncio.create_task(endpoint.start("localhost", 8765))
    logger.info("Waiting for client connections on localhost:8765")

    while True:
        await client.ready_event.wait()
        websocket_info = endpoint.get_websocket_info(client)
        if websocket_info is not None:
            try:
                urcb_list = await client.get_logical_node_directory("LD0", "LLN0", "urcb", websocket_info, callback_called, None)
                brcb_list = await client.get_logical_node_directory("LD0", "LLN0", "brcb", websocket_info, callback_called, None)
                server_list = await client.get_server_directory(websocket_info, callback_called, None)
                ld_directory = await client.get_logical_device_directory("LD0", websocket_info, callback_called, None)
                ln_directory_ds = await client.get_logical_node_directory("LD0", "LLN0", "dataset", websocket_info, callback_called, None)
                ln_directory_do = await client.get_logical_node_directory("LD0", "LLN0", "dataObject", websocket_info, callback_called, None)
                ds_directory = await client.get_dataset_directory("LD0", "LLN0", "DataSetMinMaxAvg", websocket_info, callback_called, None)
                da_def = await client.get_data_definition("LD0/DWMX1.WMaxSptPct", websocket_info, callback_called, None)

                set_da_res = await client.set_data_values("LD0/DWMX1.WMaxSpt.Oper", "co", [data_attribute_value], websocket_info, callback_called, None)
                da_val = await client.get_data_values("LD0/DWMX1.WMaxSpt.Oper", "co", True, websocket_info, callback_called, None)

                await client.select("LD0/DWMX1.WMaxSpt", websocket_info, callback_called, None)
                await client.set_data_values("LD0/DWMX1.WMaxSpt.Oper", "co", [data_attribute_value], websocket_info, callback_called, None)
                await client.operate(oper_val, websocket_info, callback_called, None)
                await client.get_data_values("LD0/DWMX1.WMaxSpt.Oper", "co", True, websocket_info, callback_called, None)

                logger.info("urcb_list: %s", urcb_list)
                logger.info("brcb_list: %s", brcb_list)
                logger.info("server_list: %s", server_list)
                logger.info("ld_directory: %s", ld_directory)
                logger.info("ln_directory_ds: %s", ln_directory_ds)
                logger.info("ln_directory_do: %s", ln_directory_do)
                logger.info("ds_directory: %s", ds_directory)
                logger.info("da_def: %s", da_def)
                logger.info("da_val: %s", da_val)
                logger.info("set_da_res: %s", set_da_res)

            except Exception as e:
                logger.exception("Service call failed: %s", e)
                continue

        while client.is_connected:
            await asyncio.sleep(0.1)


if __name__ == "__main__":
    asyncio.run(main())
