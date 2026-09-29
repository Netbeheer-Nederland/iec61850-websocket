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
import pathlib
import sys

from ws61850.endpoint.active_endpoint import ActiveEndpoint
from ws61850.iec61850.data_model import IedModelLoader
from ws61850.iec61850.server.control_handling import (
    ControlHandlerResult,
    ControlServiceStatusKind,
)
from ws61850.iec61850.server.iec61850_server import IEC61850Server
from ws61850.iec61850.server.service_error import ServiceStatusKind

_MODEL_PATH = pathlib.Path(__file__).parent.parent.parent.parent / "testing" / "ieds" / "ied_model1.json"

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    stream=sys.stdout,
)


def control_handler_for_float(obj_ref, ctlVal_value, parameter):
    if ctlVal_value is not None:
        if ctlVal_value["type"].startswith("float"):
            if ctlVal_value["value"] < 50:
                return ControlHandlerResult.OK, None
            else:
                return ControlHandlerResult.FAILED, ControlServiceStatusKind.invalidPosition
    else:
        return None, ServiceStatusKind.instanceNotAvailable
    return None, None


async def main():
    endpoint = ActiveEndpoint()

    iec61850_server = IEC61850Server(IedModelLoader.from_file(_MODEL_PATH), "cp1")
    iec61850_server.set_control_handler(control_handler_for_float, None)
    endpoint.add_iec61850_server(iec61850_server)

    logger.info("Connecting to localhost:8765 cp=cp1")
    await endpoint.start("localhost", 8765, "cp1")


if __name__ == "__main__":
    asyncio.run(main())
