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
from random import randint

from ws61850.endpoint.endpoint import WebSocketEndpoint
from ws61850.iec61850.data_model.example_ieds import build_model1
from ws61850.iec61850.server.control_handling import (
    ControlHandlerResult,
    ControlServiceStatusKind,
)
from ws61850.iec61850.server.iec61850_server import IEC61850Server
from ws61850.iec61850.server.service_error import ServiceStatusKind


async def toggle_custom_value(iec61150_server, obj_ref):
    while True:
        value = randint(1, 5)
        await iec61150_server.update_value(obj_ref, value)
        print(f"Value of {obj_ref} changed to {value}")
        await asyncio.sleep(5)


async def toggle_quality_value(iec61150_server, obj_ref):
    while True:
        random_operate_Block = bool(randint(0, 1))
        value = {
            "validity": "good",
            "source": "process",
            "test": False,
            "operatorBlock": random_operate_Block,
        }
        await iec61150_server.update_value(obj_ref, value)
        print(f"Value of {obj_ref} changed to {value}")
        await asyncio.sleep(5)


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


async def main():
    ep_wsClient_1 = WebSocketEndpoint()
    iec61850_server_1 = IEC61850Server(build_model1(), "cp1")
    iec61850_server_1.set_control_handler(control_handler_for_float, None)
    ep_wsClient_1.add_iec61850_server(iec61850_server_1)

    task1 = asyncio.create_task(ep_wsClient_1.start("active", "localhost", 8765, "cp1"))

    await asyncio.gather(task1)


if __name__ == "__main__":
    asyncio.run(main())
