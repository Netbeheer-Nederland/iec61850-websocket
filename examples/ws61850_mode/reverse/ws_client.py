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
from random import randint

from ws61850.endpoint import ActiveEndpoint
from ws61850.iec61850.data_model import IedModelLoader
from ws61850.iec61850.server.control_handling import (
    ControlHandlerResult,
    ControlServiceStatusKind,
)
from ws61850.iec61850.server.iec61850_server import IEC61850Server
from ws61850.iec61850.server.service_error import ServiceStatusKind

logger = logging.getLogger(__name__)

_MODEL_PATH = pathlib.Path(__file__).parent.parent / "ied_model1.json"


async def toggle_custom_value(iec61150_server, obj_ref):
    while True:
        value = randint(1, 5)
        await iec61150_server.update_value(obj_ref, value)
        logger.info(f"Value of {obj_ref} changed to {value}")
        await asyncio.sleep(5)


async def toggle_quality_value(iec61150_server, obj_ref):
    while True:
        random_operate_block = bool(randint(0, 1))
        value = {
            "validity": "good",
            "source": "process",
            "test": False,
            "operatorBlock": random_operate_block,
        }
        await iec61150_server.update_value(obj_ref, value)
        logger.info(f"Value of {obj_ref} changed to {value}")
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


async def schedule_abort(iec61850_server, endpoint):
    await asyncio.sleep(4)
    websocket_info = endpoint.get_websocket_info(iec61850_server)
    await iec61850_server.abort_function(websocket_info)


async def schedule_release(iec61850_server, endpoint):
    await asyncio.sleep(10)
    websocket_info = endpoint.get_websocket_info(iec61850_server)

    await iec61850_server.release_function(websocket_info)


async def main():
    ep_ws_client_1 = ActiveEndpoint()
    iec61850_server_1 = IEC61850Server(IedModelLoader.from_file(_MODEL_PATH), "cp1")
    iec61850_server_1.set_control_handler(control_handler_for_float, None)
    report_task_1 = asyncio.create_task(iec61850_server_1.periodic_report_start())
    # toggle_task_1 = asyncio.create_task(toggle_custom_value(iec61850_server_1, "LD0/DGEN1.DEROpSt.stVal"))
    # abort_task = asyncio.create_task(schedule_abort(iec61850_server_1, ep_ws_client_1))
    # release_task = asyncio.create_task(schedule_release(iec61850_server_1, ep_ws_client_1))
    ep_ws_client_1.add_iec61850_server(iec61850_server_1)

    # ep_wsClient_2 = ActiveEndpoint()
    # iec61850_server_2 = IEC61850Server(ied2, "cp2")
    # toggle_task_2 = asyncio.create_task(toggle_custom_value(iec61850_server_2, "LD0/DGEN1.DEROpSt.stVal"))
    # #toggle_task_3 = asyncio.create_task(toggle_quality_value(iec61850_server_2, "LD0/DWMX1.WMaxSptPct.q"))
    # ep_wsClient_2.add_iec61850_server(iec61850_server_2)
    #
    task1 = asyncio.create_task(
        ep_ws_client_1.start("localhost", 8765, "cp1", protocol=["iec61850-tpaa-jer-v1"])
    )
    # task2 = asyncio.create_task(ep_wsClient_2.start("active","localhost",8765, "cp2"))
    #
    # await asyncio.gather(task1, task2, report_task_1, toggle_task_2)
    # await asyncio.gather(task1)
    # ep_wsClient_2 = ActiveEndpoint()
    # iec61850_server_2 = IEC61850Server(ied2, "cp2")
    # toggle_task_2 = asyncio.create_task(toggle_custom_value(iec61850_server_2, "LD0/DGEN1.DEROpSt.stVal"))
    # #toggle_task_3 = asyncio.create_task(toggle_quality_value(iec61850_server_2, "LD0/DWMX1.WMaxSptPct.q"))
    # ep_wsClient_2.add_iec61850_server(iec61850_server_2)

    # task1 = asyncio.create_task(ep_ws_client_1.start("active","localhost", 8765, "cp1"))
    # task2 = asyncio.create_task(ep_wsClient_2.start("active","localhost",8765, "cp2"))

    await asyncio.gather(task1, report_task_1)
    # await asyncio.sleep(10)
    # await iec61850_server_1.abort_function(ep_ws_client_1.get_websocket_info(iec61850_server_1))


if __name__ == "__main__":
    asyncio.run(main())
