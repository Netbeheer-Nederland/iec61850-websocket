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
import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from ws61850.endpoint.active_endpoint import ActiveEndpoint
from ws61850.iec61850.data_model import IedModelLoader
from ws61850.iec61850.server.iec61850_server import IEC61850Server

_project_root = Path(__file__).resolve().parents[3]

_MODEL_PATH = _project_root / "testing" / "ieds" / "ied_model1.json"

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    stream=sys.stdout,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="WebSocketServer")
    default_host = os.getenv("WS_SERVER_HOST", "localhost")
    port = os.getenv("WS_SERVER_PORT", "8765")
    if port is None:
        default_port = 8765
    else:
        try:
            default_port = int(port)
        except ValueError:
            parser.error("WS_SERVER_PORT must be an integer")

    parser.add_argument(
        "--host",
        type=str,
        default=default_host,
        help="hostname for the websocket server (default: 'localhost').",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=default_port,
        help="port for the websocket server (default: 8765).",
    )

    return parser.parse_args()


# A forged access token: a well-formed RS256 JWT with the FT31 realm's issuer,
# audience "account" and an expiry in 2100, but signed by no key the realm
# knows (kid "ft31-invalid-key", bogus signature). The server must reject it.
INVALID_ACCESS_TOKEN = (
    "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6ImZ0MzEtaW52YWxpZC1rZXkifQ"
    ".eyJpc3MiOiJodHRwczovL2xvY2FsaG9zdDo4NDQzL3JlYWxtcy9pZWM2MTg1MC10ZXN0IiwiYXVkIjoiYWNjb3VudCIsInN1YiI6ImZ0MzEtbjEiLCJhenAiOiJ3cy1jbGllbnQiLCJpYXQiOjE3NjcyMjU2MDAsImV4cCI6NDEwMjQ0NDgwMH0"
    ".bm90LWEtdmFsaWQtc2lnbmF0dXJlLW5vdC1hLXZhbGlkLXNpZ25hdHVyZS1ub3QtYS12YWxpZC1zaWduYXR1cmUtbm90LWEtdmFsaWQtc2lnbmF0dXJlLQ"
)


async def main():
    args = parse_args()
    logger.info("Start Client")

    access_token = INVALID_ACCESS_TOKEN
    logger.info("Using hardcoded invalid access token")

    # No reconnect: one rejected attempt is the expected outcome.
    endpoint = ActiveEndpoint(oauth_enable=True, try_reconnect=False)

    iec61850_server = IEC61850Server(IedModelLoader.from_file(_MODEL_PATH), "cp1")
    endpoint.add_iec61850_server(iec61850_server)

    task = asyncio.create_task(
        endpoint.start(args.host, args.port, "cp1", access_token=access_token)
    )
    await asyncio.gather(task)


if __name__ == "__main__":
    asyncio.run(main())
