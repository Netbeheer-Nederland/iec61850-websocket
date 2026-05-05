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

from ws61850.endpoint.active_endpoint import ActiveEndpoint
from ws61850.iec61850.client.iec61850_client import IEC61850Client

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    stream=sys.stdout,
)


async def main():
    endpoint = ActiveEndpoint(is_direct=True, try_reconnect=False)

    iec61850_client = IEC61850Client("cp1")
    endpoint.add_iec61850_client(iec61850_client)

    logger.info("Connecting to localhost:8765 cp=cp1")
    await endpoint.start("localhost", 8765, "cp1")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Client stopped by user")
