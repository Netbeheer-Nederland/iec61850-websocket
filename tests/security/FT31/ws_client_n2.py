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

from testing.certs.paths import CERT_DIR
from testing.ieds.high_level_model import make_ied_model1
from ws61850.endpoint.endpoint import WebSocketEndpoint
from ws61850.iec61850.server.iec61850_server import IEC61850Server
from ws61850.security.oauth import get_access_token

logger = logging.getLogger(__name__)

cafile = CERT_DIR / "ca.pem"


async def main():
    logger.info("Start Client")
    token_request_url = "https://localhost:8443/realms/iec61850-test/protocol/openid-connect/token"

    client_id = "ws-client"
    client_secret = "K4Nrd14seXG52J3xpnIqfMyILTJJu3VI"
    access_token_1 = await get_access_token(token_request_url, client_id, client_secret, cafile)

    ep_ws_client = WebSocketEndpoint(oauth_enable=True, try_reconnect=False)
    iec61850_server_1 = IEC61850Server(make_ied_model1(), "cp1")
    ep_ws_client.add_iec61850_server(iec61850_server_1)

    task1 = asyncio.create_task(ep_ws_client.start("active", "localhost", 8765, "cp1", access_token_1))
    await asyncio.gather(task1)


if __name__ == "__main__":
    asyncio.run(main())
