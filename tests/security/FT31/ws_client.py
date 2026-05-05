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
import time
from pathlib import Path

import jwt

from ws61850.endpoint.active_endpoint import ActiveEndpoint
from ws61850.iec61850.data_model import IedModelLoader
from ws61850.iec61850.server.iec61850_server import IEC61850Server
from ws61850.security.oauth import get_access_token

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from testing.certs.paths import CERT_DIR  # noqa: E402
from testing.tasks.refresh_token_if_needed import refresh_token_if_needed  # noqa: E402

_MODEL_PATH = _project_root / "testing" / "ieds" / "ied_model1.json"

cafile = CERT_DIR / "ca.pem"

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    stream=sys.stdout,
)


BASE = "https://localhost:8443"
TARGET_REALM = "iec61850-test"
token_endpoint = f"{BASE}/realms/{TARGET_REALM}/protocol/openid-connect/token"


async def main():
    logger.info("Start Client")

    client_id = "ws-client"
    client_secret = "K4Nrd14seXG52J3xpnIqfMyILTJJu3VI"
    access_token = await get_access_token(token_endpoint, client_id, client_secret, cafile)
    logger.info("Access-Token: %s", access_token)

    endpoint = ActiveEndpoint(oauth_enable=True)

    iec61850_server = IEC61850Server(IedModelLoader.from_file(_MODEL_PATH), "cp1")
    endpoint.add_iec61850_server(iec61850_server)

    task = asyncio.create_task(endpoint.start("localhost", 8765, "cp1", access_token=access_token))
    task_token = asyncio.create_task(
        refresh_token_if_needed(token_endpoint, client_id, client_secret, "cp1", access_token, endpoint, cafile)
    )

    await asyncio.gather(task, task_token)


if __name__ == "__main__":
    asyncio.run(main())
