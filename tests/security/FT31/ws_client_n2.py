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
from pathlib import Path

from testing.certs.paths import CERT_DIR
from ws61850.endpoint.active_endpoint import ActiveEndpoint
from ws61850.iec61850.data_model import IedModelLoader
from ws61850.iec61850.server.iec61850_server import IEC61850Server
from ws61850.security.oauth import get_access_token

_MODEL_PATH = Path(__file__).parent.parent.parent.parent / "testing" / "ieds" / "ied_model1.json"

logger = logging.getLogger(__name__)

cafile = CERT_DIR / "ca.pem"


async def main():
    logger.info("Start Client")
    token_request_url = "https://localhost:8443/realms/iec61850-test/protocol/openid-connect/token"

    client_id = "ws-client"
    client_secret = "K4Nrd14seXG52J3xpnIqfMyILTJJu3VI"
    access_token = await get_access_token(token_request_url, client_id, client_secret, cafile)

    endpoint = ActiveEndpoint(oauth_enable=True, try_reconnect=False)

    iec61850_server = IEC61850Server(IedModelLoader.from_file(_MODEL_PATH), "cp1")
    endpoint.add_iec61850_server(iec61850_server)

    task = asyncio.create_task(endpoint.start("localhost", 8765, "cp1", access_token=access_token))
    await asyncio.gather(task)


if __name__ == "__main__":
    asyncio.run(main())
