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
import pathlib
import random
import sys

from ws61850.endpoint.active_endpoint import ActiveEndpoint
from ws61850.iec61850.data_model import IedModelLoader
from ws61850.iec61850.server.iec61850_server import IEC61850Server

_MODEL_PATH = pathlib.Path(__file__).parent.parent.parent.parent / "testing" / "ieds" / "ied_model1.json"

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    stream=sys.stdout,
)


async def toggle_custom_value(iec61850_server, obj_ref):
    while True:
        value = random.randint(1, 5)
        await iec61850_server.update_value(obj_ref, value)
        logger.info("Value of %s changed to %s", obj_ref, value)
        await asyncio.sleep(5)


async def toggle_float_value(iec61850_server, obj_ref):
    while True:
        value = random.uniform(5.5, 10.0)
        await iec61850_server.update_value(obj_ref, value)
        logger.info("Value of %s changed to %.4f", obj_ref, value)
        await asyncio.sleep(0.1)


async def main():
    endpoint = ActiveEndpoint()

    iec61850_server = IEC61850Server(IedModelLoader.from_file(_MODEL_PATH), "cp1")
    report_task = asyncio.create_task(iec61850_server.periodic_report_start())
    toggle_task = asyncio.create_task(toggle_float_value(iec61850_server, "LD0/MMXU1.TotW.mag.f"))
    endpoint.add_iec61850_server(iec61850_server)

    logger.info("Connecting to localhost:8765 cp=cp1")
    await asyncio.gather(endpoint.start("localhost", 8765, "cp1"), report_task, toggle_task)


if __name__ == "__main__":
    asyncio.run(main())
