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

_MODEL_PATH = Path(__file__).resolve().parents[3] / "testing" / "ieds" / "ied_model1.json"

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    stream=sys.stdout,
)


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

    parser.add_argument(
        "--start",
        type=int,
        default="1",
        help="the number of support PoCC (default: '1').",
    )
    parser.add_argument(
        "--stop",
        type=int,
        default="50",
        help="the number of support PoCC (default: '50').",
    )
    parser.add_argument(
        "--delay",
        type=int,
        default="2",
        help="the delay to start next (default: '2').",
    )
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
    parser.add_argument(
        "--report",
        type=bool,
        default=False,
        help="report enabled (default: 'False').",
    )
    return parser.parse_args()


async def create_ws_clients(cp, task_list, args):
    endpoint = ActiveEndpoint()
    iec61850_server = IEC61850Server(IedModelLoader.from_file(_MODEL_PATH), cp)
    endpoint.add_iec61850_server(iec61850_server)

    controller_task = asyncio.create_task(endpoint.start(args.host, args.port, cp))
    task_list.append(controller_task)

    if args.report:
        report_task = asyncio.create_task(iec61850_server.periodic_report_start())
        task_list.append(report_task)


async def run_clients(tasks):
    await asyncio.gather(*tasks)


async def main():
    args = parse_args()
    task_list = []

    for pocc_num in range(args.start, args.stop + 1):
        pocc_id = f"EAN{pocc_num:03}"
        logger.info("Registering IEC61850 Controller on WS-Client with ID: %s", pocc_id)
        await create_ws_clients(pocc_id, task_list, args)
        if args.delay > 0:
            await asyncio.sleep(args.delay)

    await run_clients(task_list)


if __name__ == "__main__":
    asyncio.run(main())
