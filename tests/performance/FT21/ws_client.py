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
from pathlib import Path

from ws61850.endpoint.active_endpoint import ActiveEndpoint
from ws61850.iec61850.server.control_handling import (
    ControlHandlerResult,
    ControlServiceStatusKind,
)
from ws61850.iec61850.server.iec61850_server import IEC61850Server
from ws61850.iec61850.server.service_error import ServiceStatusKind

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from testing.ieds.high_level_model import make_ied_model1  # noqa: E402

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    stream=sys.stdout,
)


def control_handler_for_float(obj_ref, ctlVal_value, parameter):
    if ctlVal_value is not None:
        if ctlVal_value["type"].startswith("float"):
            if ctlVal_value["value"] < 50:
                return ControlHandlerResult.OK, None
            else:
                return (
                    ControlHandlerResult.FAILED,
                    ControlServiceStatusKind.invalidPosition,
                )
    else:
        return None, ServiceStatusKind.instanceNotAvailable
    return None, None


async def schedule_abort(iec61850_server, endpoint):
    await asyncio.sleep(4)
    websocket_info = endpoint.get_websocket_info_iec61850_server(iec61850_server)
    await iec61850_server.abort_function(websocket_info)


async def schedule_release(iec61850_server, endpoint):
    await asyncio.sleep(10)
    websocket_info = endpoint.get_websocket_info_iec61850_server(iec61850_server)
    await iec61850_server.release_function(websocket_info)


async def main():
    endpoint = ActiveEndpoint()

    iec61850_server = IEC61850Server(make_ied_model1(), "cp1")
    iec61850_server.set_control_handler(control_handler_for_float, None)
    report_task = asyncio.create_task(iec61850_server.periodic_report_start())
    endpoint.add_iec61850_server(iec61850_server)

    logger.info("Connecting to localhost:8765 cp=cp1 (JER)")
    task = asyncio.create_task(
        endpoint.start("localhost", 8765, "cp1", protocol=["iec61850-tpaa-jer-v1"])
    )

    await asyncio.gather(task, report_task)


if __name__ == "__main__":
    asyncio.run(main())
