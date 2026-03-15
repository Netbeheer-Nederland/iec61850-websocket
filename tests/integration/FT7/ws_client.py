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
import random

from testing.ieds.high_level_model import make_ied_model1
from ws61850.endpoint.endpoint import WebSocketEndpoint
from ws61850.iec61850.server.iec61850_server import IEC61850Server

maxMessageSize = 65000


async def toggle_custom_value(iec61150_server, obj_ref):
    while True:
        value = random.randint(1, 5)
        await iec61150_server.update_value(obj_ref, value)
        print(f"Value of {obj_ref} changed to {value}")
        await asyncio.sleep(5)


async def toggle_float_value(iec61150_server, obj_ref):
    while True:
        value = random.uniform(5.5, 10.0)
        await iec61150_server.update_value(obj_ref, value)
        print(f"Value of {obj_ref} changed to {value}")
        await asyncio.sleep(0.1)


async def main():
    ep_wsClient_1 = WebSocketEndpoint()
    iec61850_server_1 = IEC61850Server(make_ied_model1(), "cp1")
    report_task_1 = asyncio.create_task(iec61850_server_1.periodic_report_start())
    toggle_task_1 = asyncio.create_task(toggle_float_value(iec61850_server_1, "LD0/MMXU1.TotW.mag.f"))

    ep_wsClient_1.add_iec61850_server(iec61850_server_1)

    task1 = asyncio.create_task(ep_wsClient_1.start("active", "localhost", 8765, "cp1"))

    await asyncio.gather(task1, report_task_1, toggle_task_1)


if __name__ == "__main__":
    asyncio.run(main())
