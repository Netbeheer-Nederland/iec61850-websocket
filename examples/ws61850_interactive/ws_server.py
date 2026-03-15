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
import ast
import asyncio
import logging
import re
import sys

from ws61850.endpoint.endpoint import WebSocketEndpoint
from ws61850.iec61850.client.iec61850_client import IEC61850Client
from ws61850.iec61850.data_model.helper import get_now_time

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)

maxMessageSize_server = 65000


def callback_called(result, param):
    logger.info("callback called: %s", result)


def extract_function_name_and_arguments(input):
    match = re.match(r"(\w+)\((.*)\)", input)
    args = []
    func_name = None
    if match:
        func_name = match.group(1)  # "get_server_directory"
        args_str = match.group(2)  # "websocket_info, None, 42, 'hello'"

        for arg in [a.strip() for a in args_str.split(",")]:
            try:
                # Safely convert string to Python object (None, int, str, etc.)
                val = ast.literal_eval(arg)
            except Exception:
                # If it's not a literal (e.g. variable name), keep as string
                val = arg
            args.append(val)
    # logger.info("func_name: ", func_name)
    # logger.info("args: ", args)
    return func_name, args


def parse_command(command: str):
    # Example: 'set_BRCB_values("LD0/LLN0.rcbMinMaxAvg", optFlds={"seqNum": True, "timeStamp": True})'
    func_name, args_str = command.split("(", 1)
    func_name = func_name.strip()
    args_str = args_str.rstrip(")")

    if args_str.strip():
        tree = ast.parse(f"f({args_str})", mode="eval")
        call = tree.body
        args = [ast.literal_eval(arg) for arg in call.args]
        kwargs = {kw.arg: ast.literal_eval(kw.value) for kw in call.keywords}
    else:
        args, kwargs = [], {}

    return func_name, args, kwargs


async def async_input(prompt: str, disconnect_event: asyncio.Event):
    loop = asyncio.get_running_loop()
    input_future = loop.create_future()

    def on_input_ready():
        try:
            line = sys.stdin.readline()
        except Exception as exc:
            if not input_future.done():
                input_future.set_exception(exc)
            return
        if not input_future.done():
            input_future.set_result(line.rstrip("\n"))

    print(prompt, end="", flush=True)
    loop.add_reader(sys.stdin, on_input_ready)

    disconnect_task = asyncio.create_task(disconnect_event.wait())
    try:
        done, _ = await asyncio.wait(
            {input_future, disconnect_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if disconnect_task in done:
            if not input_future.done():
                input_future.cancel()
            print()
            return None
        return input_future.result()
    finally:
        loop.remove_reader(sys.stdin)
        disconnect_task.cancel()


async def main():
    ctl_num = 0

    # websocket server
    ep_wsServer = WebSocketEndpoint()

    iec61850_client = IEC61850Client("cp1")
    ep_wsServer.add_iec61850_client(iec61850_client)

    iec61850_client = IEC61850Client("cp2")
    ep_wsServer.add_iec61850_client(iec61850_client)

    server_task = asyncio.create_task(ep_wsServer.start("passive", "localhost", 8765))

    selected_client = ep_wsServer.client_list[0]
    while True:
        await selected_client.ready_event.wait()
        if not selected_client.is_connected:
            continue

        selected_client.disconnect_event.clear()
        websocket_info = ep_wsServer.get_websocket_info(selected_client)
        if websocket_info is None:
            continue

        logger.info("Client connected, console input enabled")
        while selected_client.is_connected:
            try:
                input_command = await async_input("\nPlease enter the command: ", selected_client.disconnect_event)
                if input_command is None:
                    logger.info("Client disconnected, console input disabled")
                    break

                function_name, args = extract_function_name_and_arguments(input_command)
                if function_name == "get_server_directory":
                    server_list = await selected_client.get_server_directory(websocket_info, None, None)
                    logger.info("server directory: %s", server_list)
                elif function_name == "get_logical_device_directory":
                    ln_refs = await selected_client.get_logical_device_directory(
                        args[0], websocket_info, None, None
                    )
                    logger.info("LN list: %s", ln_refs)
                elif function_name == "get_logical_node_directory":
                    ln_directory_items = await selected_client.get_logical_node_directory(
                        args[0], args[1], args[2], websocket_info, None, None
                    )
                    logger.info("LN directory: %s", ln_directory_items)
                elif function_name == "get_data_definition":
                    da_def = await selected_client.get_data_definition(args[0], websocket_info, None, None)
                    logger.info(da_def)
                elif function_name == "get_data_values":
                    data_val = await selected_client.get_data_values(args[0], args[1], args[2], websocket_info, None, None)
                    logger.info("data value: %s", data_val)
                elif function_name == "select":
                    select_result = await selected_client.select(args[0], websocket_info, None, None)
                    logger.info(select_result)
                elif function_name == "operate":
                    values = {
                        "ref": args[0],
                        "ctlVal": (
                            "structure",
                            {"data": [("structure", {"data": [(args[1], args[2])]})]},
                        ),
                        "origin": {
                            "orCat": "stationControl",
                            "orIdent": b"CONSOLE_APPLICATION_ID",
                        },
                        "ctlNum": ctl_num,
                        "t": get_now_time(),
                    }
                    ctl_num += 1
                    operate_res = await selected_client.operate(values, websocket_info, None, None)
                    logger.info("operate result: %s", operate_res)
                elif function_name == "set_data_values":
                    value = [{"data": (args[2], args[3])}]
                    set_data_val_result = await selected_client.set_data_values(
                        args[0], args[1], value, websocket_info, None, None
                    )
                    logger.info("set data values result: %s", set_data_val_result)
                elif function_name == "get_dataset_directory":
                    ds_directory = await selected_client.get_dataset_directory(
                        args[0], args[1], args[2], websocket_info, None, None
                    )
                    logger.info("dataset directory: %s", ds_directory)
                elif function_name == "get_BRCB_values":
                    brcb_val = await selected_client.get_BRCB_values(args[0], websocket_info, None, None)
                    logger.info("brcb value: %s", brcb_val)
                elif function_name == "get_URCB_values":
                    urcb_val = await selected_client.get_URCB_values(args[0], websocket_info, None, None)
                    logger.info(urcb_val)
                elif function_name == "get_dataset_values":
                    ds_values = await selected_client.get_dataset_values(
                        args[0], args[1], args[2], websocket_info, None, None
                    )
                    logger.info("dataset values: %s", ds_values)
                elif function_name == "set_BRCB_values":
                    func, args, kwargs = parse_command(input_command)

                    brcb = IEC61850Client.ClientReportControlBlock(args[0], True)
                    key, value = next(iter(kwargs.items()))
                    for attr in dir(brcb):
                        if attr.lower() == key.lower():
                            if isinstance(value, str):
                                try:
                                    value = ast.literal_eval(value)
                                except Exception:
                                    pass
                            setattr(brcb, attr, value)
                            break
                    else:
                        logger.info("Warning: No matching attribute found for %s", key)

                    set_brcb_res = await selected_client.set_BRCB_values(brcb, websocket_info, None, None)
                    logger.info("set brcb result: %s", set_brcb_res)
                elif function_name == "set_URCB_values":
                    func, args, kwargs = parse_command(input_command)

                    urcb = IEC61850Client.ClientReportControlBlock(args[0], False)
                    key, value = next(iter(kwargs.items()))
                    for attr in dir(urcb):
                        if attr.lower() == key.lower():
                            if isinstance(value, str):
                                try:
                                    value = ast.literal_eval(value)
                                except Exception:
                                    pass
                            setattr(urcb, attr, value)
                            break
                    else:
                        logger.info("Warning: No matching attribute found for %s", key)

                    set_urcb_res = await selected_client.set_URCB_values(urcb, websocket_info, None, None)
                    logger.info("set urcb result: %s", set_urcb_res)
                else:
                    logger.info("Incorrect command, please try again!")
            except Exception as e:
                logger.info("error in processing the request: %s", e)

    await server_task


if __name__ == "__main__":
    asyncio.run(main())
