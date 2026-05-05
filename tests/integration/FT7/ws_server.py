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

trgOp = {"dchg": False, "qchg": False, "dupd": False, "integrity": True, "gi": False}

urcb = IEC61850Client.ClientReportControlBlock("LD0/LLN0.rcbActualValues", False)
urcb.trgOps = trgOp
urcb.intgPd = 1000

urcb_2 = IEC61850Client.ClientReportControlBlock("LD0/LLN0.rcbActualValues", False)
urcb_2.rptEna = True


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
                set_urcb_res = await client.set_URCB_values(urcb, websocket_info, None, None)
                logger.info("set_URCB_values (integrity): %s", set_urcb_res)

                set_urcb_res = await client.set_URCB_values(urcb_2, websocket_info, None, None)
                logger.info("set_URCB_values (rptEna): %s", set_urcb_res)

            except Exception as e:
                logger.exception("Service call failed: %s", e)
    else:
        logger.warning("Client did not connect")

    await server_task


if __name__ == "__main__":
    asyncio.run(main())
