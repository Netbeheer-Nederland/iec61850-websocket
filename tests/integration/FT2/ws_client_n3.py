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


async def test_protocol_rejection(endpoint, mode, host, port, cp, protocol):
    try:
        await endpoint.start(mode, host, port, cp, protocol=protocol)

    except Exception as e:
        print(f"Caught exception type: {type(e).__name__}")
        print(f"Error Message: {e}")


async def main():
    # websocket server
    ep_wsClient_1 = WebSocketEndpoint(is_direct=True)
    iec61850_client_1 = IEC61850Client("cp1")
    ep_wsClient_1.add_iec61850_client(iec61850_client_1)
    protocol = ["wrong-protocol-v1"]

    await test_protocol_rejection(
        ep_wsClient_1, mode="active", host="localhost", port=8765, cp="cp1", protocol=protocol
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTest stopped by user.")
