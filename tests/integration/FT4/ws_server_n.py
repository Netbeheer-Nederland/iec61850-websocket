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
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    stream=sys.stdout,
)

oper_val_wrong_type = {
    "ref": "LD0/DWMX1.WMaxSpt",
    "ctlVal": ("int64", 16),
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
oper_val_out_of_range = {
    "ref": "LD0/DWMX1.WMaxSpt",
    "ctlVal": ("float32", 1000.44),
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
oper_val_incorrect_do = {
    "ref": "LD0/DWMX1.WMaxSetPct",
    "ctlVal": ("float32", 14.2),
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

setMag_val = [{"name": "setMag", "data": ("structure", {"data": [("float32", 67.39)]})}]
setMag_wrong = [{"name": "setMag", "data": ("structure", {"data": [("boolean", False)]})}]


async def main():
    endpoint = PassiveEndpoint()

    client = IEC61850Client("cp1")
    endpoint.add_iec61850_client(client)

    server_task = asyncio.create_task(endpoint.start("localhost", 8765))

    await client.ready_event.wait()
    if client.is_connected is True:
        websocket_info = endpoint.get_websocket_info(client)
        if websocket_info is not None:
            try:
                logger.info("Running negative test cases:")

                da_val = await client.get_data_values("LD0/DWMX1.WMaxSpt_wrong", "mx", True, websocket_info, None, None)
                logger.info("getDataValues with wrong reference: %s", da_val)

                select_result = await client.select("LD0/DWMX1.WMaxSetPct", websocket_info, None, None)
                logger.info("select result: %s", select_result)

                operate_result = await client.operate(oper_val_wrong_type, websocket_info, None, None)
                logger.info("operate with incorrect data type: %s", operate_result)

                operate_result = await client.operate(oper_val_incorrect_do, websocket_info, None, None)
                logger.info("operate with incorrect data object: %s", operate_result)

                set_val_res = await client.set_data_values(
                    "LD0/DWMX1.WMaxSet.setMag_wrong", "sp", setMag_val, websocket_info, None, None
                )
                logger.info("setDataValues for nonexistent object: %s", set_val_res)

                set_val_res = await client.set_data_values(
                    "LD0/DWMX1.WMaxSet.setMag", "sp", setMag_wrong, websocket_info, None, None
                )
                logger.info("setDataValues with incorrect type: %s", set_val_res)

                select_result = await client.select("LD0/DWMX1.WMaxSpt", websocket_info, None, None)
                logger.info("select result: %s", select_result)

                operate_result = await client.operate(oper_val_out_of_range, websocket_info, None, None)
                logger.info("operate with out-of-range data: %s", operate_result)

            except Exception as e:
                logger.exception("Service call failed: %s", e)
    else:
        logger.warning("Client did not connect")

    await server_task


if __name__ == "__main__":
    asyncio.run(main())
