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
    endpoint = PassiveEndpoint()

    client = IEC61850Client("cp1")
    endpoint.add_iec61850_client(client)

    server_task = asyncio.create_task(endpoint.start("localhost", 8765))
    logger.info("Waiting for client to connect on localhost:8765")

    await client.ready_event.wait()
    if client.is_connected:
        websocket_info = endpoint.get_websocket_info(client)
        if websocket_info is not None:
            try:
                da_val = await client.get_data_values("LD0/DWMX1.WMaxSpt", "mx", True, websocket_info, None, None)
                logger.info("get_data_values WMaxSpt: %s", da_val)

                select_result = await client.select("LD0/DWMX1.WMaxSpt", websocket_info, None, None)
                logger.info("select: %s", select_result)

                operate_result = await client.operate(oper_val, websocket_info, None, None)
                logger.info("operate: %s", operate_result)

                da_val = await client.get_data_values("LD0/DWMX1.WMaxSpt", "mx", True, websocket_info, None, None)
                logger.info("get_data_values WMaxSpt after operate: %s", da_val)

                da_val = await client.get_data_values("LD0/DWMX1.WMaxSet", "sp", True, websocket_info, None, None)
                logger.info("get_data_values WMaxSet: %s", da_val)

                set_val_res = await client.set_data_values(
                    "LD0/DWMX1.WMaxSet.setMag", "sp", setMag_val, websocket_info, None, None
                )
                logger.info("set_data_values setMag: %s", set_val_res)

                da_val = await client.get_data_values("LD0/DWMX1.WMaxSet", "sp", True, websocket_info, None, None)
                logger.info("get_data_values WMaxSet after set: %s", da_val)

            except Exception as e:
                logger.exception("Service call failed: %s", e)
    else:
        logger.warning("Client did not connect")

    await server_task


if __name__ == "__main__":
    asyncio.run(main())
