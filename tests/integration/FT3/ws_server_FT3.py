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

from ws61850.endpoint.passive_endpoint import PassiveEndpoint
from ws61850.iec61850.client.iec61850_client import IEC61850Client
from ws61850.iec61850.server.request_handling import (
    print_direct_da,
    print_node,
    retrieve_attributes_sdo,
    retrieve_das,
    retrieve_sdos,
)

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    stream=sys.stdout,
)


async def main():
    endpoint = PassiveEndpoint()

    client = IEC61850Client("cp1")
    endpoint.add_iec61850_client(client)

    server_task = asyncio.create_task(endpoint.start("localhost", 8765))

    await client.ready_event.wait()
    if client.is_connected is True:
        websocket_info = endpoint.get_websocket_info(client)
        if websocket_info is not None:
            try:
                server_list = await client.get_server_directory(websocket_info, None, None)
                for ld_index, ld_inst in enumerate(server_list):
                    is_last_ld = ld_index == len(server_list) - 1
                    ld_prefix = "└── " if is_last_ld else "├── "
                    print(f"{ld_prefix}{ld_inst}")

                    ln_refs = await client.get_logical_device_directory(ld_inst, websocket_info, None, None)
                    for ln_index, ln_inst in enumerate(ln_refs):
                        is_last_ln = ln_index == len(ln_refs) - 1
                        ln_prefix = (
                            "    └── "
                            if is_last_ld
                            else "│   └── " if is_last_ln else ("    ├── " if is_last_ld else "│   ├── ")
                        )
                        print(f"{ln_prefix}{ln_inst}")

                        ln_directory_urcb = await client.get_logical_node_directory(
                            ld_inst, ln_inst, "urcb", websocket_info, None, None
                        )
                        for urcb_inst in ln_directory_urcb:
                            print(f"        └── [URCB] {urcb_inst}")

                        ln_directory_brcb = await client.get_logical_node_directory(
                            ld_inst, ln_inst, "brcb", websocket_info, None, None
                        )
                        for brcb_inst in ln_directory_brcb:
                            print(f"        └── [BRCB] {brcb_inst}")

                        ln_directory_ds = await client.get_logical_node_directory(
                            ld_inst, ln_inst, "dataset", websocket_info, None, None
                        )
                        for ds_inst in ln_directory_ds:
                            print(f"        └── [DS] {ds_inst}")
                            ds_items = await client.get_dataset_directory(
                                ld_inst, ln_inst, ds_inst, websocket_info, None, None
                            )
                            for item_inst in ds_items:
                                item_text = item_inst["ref"] + f"[{item_inst['fc']}]"
                                print(f"            └── {item_text}")

                        ln_directory_do = await client.get_logical_node_directory(
                            ld_inst, ln_inst, "dataObject", websocket_info, None, None
                        )
                        for do_index, do_inst in enumerate(ln_directory_do):
                            is_last_do = do_index == len(ln_directory_do) - 1
                            do_prefix = "        └── " if is_last_do else "        ├── "
                            print(f"{do_prefix}{do_inst}")

                            da_def = await client.get_data_definition(
                                ld_inst + "/" + ln_inst + "." + do_inst, websocket_info, None, None
                            )

                            sdos = retrieve_sdos(da_def)
                            for sdo_index, sdo_inst in enumerate(sdos):
                                print_node(sdo_index, sdo_inst, len(sdos))
                                retrieve_attributes_sdo(da_def, sdo_inst)

                            da_list = retrieve_das(da_def)
                            if len(da_list) != 0:
                                print_direct_da(da_list)

                logger.info("Running negative test cases:")
                ln_refs = await client.get_logical_device_directory("wrong_ld_name", websocket_info, None, None)
                logger.info("wrong LD result: %s", ln_refs)

                ln_directory_ds = await client.get_logical_node_directory(
                    "LD0", "wrong_ln", "dataset", websocket_info, None, None
                )
                logger.info("wrong LN result: %s", ln_directory_ds)

            except Exception as e:
                logger.exception("Service call failed: %s", e)
    else:
        logger.warning("Client did not connect")

    await server_task


if __name__ == "__main__":
    asyncio.run(main())
