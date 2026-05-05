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
import random
import sys
import time
from pathlib import Path

from ws61850.endpoint.active_endpoint import ActiveEndpoint
from ws61850.iec61850.data_model import IedModelLoader
from ws61850.iec61850.server.iec61850_server import IEC61850Server
from ws61850.security.oauth import get_access_token
from ws61850.security.tls import TLSConfiguration

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from testing.certs.paths import CERT_DIR  # noqa: E402
from testing.tasks.refresh_token_if_needed import refresh_token_if_needed  # noqa: E402
from testing.tasks.runner import run_tasks  # noqa: E402
from testing.utils.credentials_store import load_credentials  # noqa: E402

_MODEL_PATH = _project_root / "testing" / "ieds" / "ied_model1.json"

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    stream=sys.stdout,
)

cafile = CERT_DIR / "ca.pem"
CREDENTIALS_FILE = "data/client_credentials.json"


def resolve_credentials_path(credentials_file_path: str) -> Path:
    path = Path(credentials_file_path)
    if path.is_absolute():
        return path
    project_root = Path(__file__).resolve().parent
    return (project_root / path).resolve()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="WebSocketClient + IEC61850-Controller")
    default_host = os.getenv("WS_SERVER_HOST", "localhost")
    port = os.getenv("WS_SERVER_PORT", "8765")
    if port is None:
        default_port = 8765
    else:
        try:
            default_port = int(port)
        except ValueError:
            parser.error("WS_SERVER_PORT must be an integer")

    parser.add_argument("--start", type=int, default="1", help="start PoCC index (default: 1).")
    parser.add_argument("--stop", type=int, default="50", help="stop PoCC index (default: 50).")
    parser.add_argument("--delay", type=int, default="2", help="delay between clients in seconds (default: 2).")
    parser.add_argument(
        "--host",
        type=str,
        default=default_host,
        help="hostname for the websocket server (env: WS_SERVER_HOST, default: 'localhost').",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=default_port,
        help="port for the websocket server (env: WS_SERVER_PORT, default: 8765).",
    )
    parser.add_argument("--report", type=bool, default=True, help="report enabled (default: True).")
    return parser.parse_args()


async def toggle_float_value(iec61850_server, obj_ref):
    while True:
        value = random.uniform(5.5, 10.0)
        await iec61850_server.update_value(obj_ref, value)
        await asyncio.sleep(1)


BASE = os.environ.get("KEYCLOAK_URL", "https://localhost:8443")
TARGET_REALM = os.environ.get("IEC61850_REALM", "iec61850-test")
token_endpoint = f"{BASE}/realms/{TARGET_REALM}/protocol/openid-connect/token"


async def start_client_process(client_config, i, args):
    client_id = client_config["client_id"]
    client_secret = client_config["client_secret"]
    access_token = await get_access_token(token_endpoint, client_id, client_secret, cafile)
    logger.info("Access-Token: %s", access_token)

    tls_config = TLSConfiguration(cafile, None, False)
    endpoint = ActiveEndpoint(oauth_enable=True, tls_config=tls_config)

    pocc_id = client_config["pocc_id"]
    iec61850_server = IEC61850Server(IedModelLoader.from_file(_MODEL_PATH), pocc_id)
    endpoint.add_iec61850_server(iec61850_server)

    task_list = []
    controller_task = asyncio.create_task(
        endpoint.start(args.host, args.port, pocc_id, access_token=access_token)
    )
    task_list.append(controller_task)

    if args.report:
        report_task = asyncio.create_task(iec61850_server.periodic_report_start())
        task_list.append(report_task)

    refresh_task = asyncio.create_task(
        refresh_token_if_needed(
            token_endpoint,
            client_config["client_id"],
            client_config["client_secret"],
            client_config["pocc_id"],
            access_token,
            endpoint,
            cafile,
        )
    )
    task_list.append(refresh_task)

    logger.info("[%s] Starting WSS connection...", pocc_id)
    await run_tasks(task_list)


async def run_multi_clients():
    args = parse_args()

    credentials_path = resolve_credentials_path(CREDENTIALS_FILE)
    credentials = load_credentials(credentials_path)
    total = args.stop - args.start + 1
    logger.info("Starting concurrent execution of %s clients...", total)

    startup_tasks = []
    for i, config in enumerate(credentials):
        if args.start - 1 > i >= args.stop:
            break
        routine = start_client_process(config, i, args)
        task = asyncio.create_task(routine, name=f"Task-{config['pocc_id']}")
        startup_tasks.append(task)
        await asyncio.sleep(args.delay)

    await run_tasks(startup_tasks)


if __name__ == "__main__":
    try:
        asyncio.run(run_multi_clients())
    except KeyboardInterrupt:
        logger.info("Dynamic Client Runner stopped by user (Ctrl+C).")
    except Exception:
        logger.exception("Critical error in main runner")
