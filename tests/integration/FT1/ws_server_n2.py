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

# maxMessageSize_server = 65000


async def main():
    protocol = ["iec61850-tpaa-jer-v1"]
    # websocket server
    ep_ws_server = WebSocketEndpoint()

    iec61850_client = IEC61850Client("cp1")
    ep_ws_server.add_iec61850_client(iec61850_client)

    server_task = asyncio.create_task(ep_ws_server.start("passive", "localhost", 8765, protocol=protocol))

    await server_task


if __name__ == "__main__":
    asyncio.run(main())
