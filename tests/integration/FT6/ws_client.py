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
from random import randint

from testing.ieds.high_level_model import make_ied_model1
from ws61850.endpoint.active_endpoint import ActiveEndpoint
from ws61850.iec61850.server.iec61850_server import IEC61850Server

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    stream=sys.stdout,
)


async def toggle_custom_value(iec61850_server, obj_ref):
    while True:
        value = randint(1, 5)
        await iec61850_server.update_value(obj_ref, value)
        logger.info("Value of %s changed to %s", obj_ref, value)
        await asyncio.sleep(5)


async def main():
    endpoint = ActiveEndpoint()

    iec61850_server = IEC61850Server(make_ied_model1(), "cp1")
    toggle_task = asyncio.create_task(toggle_custom_value(iec61850_server, "LD0/DGEN1.DEROpSt.stVal"))
    endpoint.add_iec61850_server(iec61850_server)

    logger.info("Connecting to localhost:8765 cp=cp1")
    await asyncio.gather(endpoint.start("localhost", 8765, "cp1"), toggle_task)


if __name__ == "__main__":
    asyncio.run(main())
