import ast
import asyncio
import re

from ws61850.endpoint.endpoint import WebSocketEndpoint
from ws61850.iec61850.client.iec61850_client import IEC61850Client
from ws61850.iec61850.data_model.helper import get_now_time

maxMessageSize_server = 65000


def callback_called(result, param):
    print("callback called: ", result)


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
    # print("func_name: ", func_name)
    # print("args: ", args)
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


async def async_input(prompt: str = ""):
    return await asyncio.to_thread(input, prompt)


async def main():
    ctl_num = 0

    # websocket server
    ep_wsServer = WebSocketEndpoint()

    iec61850_client = IEC61850Client("cp1")
    ep_wsServer.add_iec61850_client(iec61850_client)

    iec61850_client = IEC61850Client("cp2")
    ep_wsServer.add_iec61850_client(iec61850_client)

    server_task = asyncio.create_task(ep_wsServer.start("passive", "localhost", 8765))

    await ep_wsServer.client_list[0].ready_event.wait()
    if ep_wsServer.client_list[0].is_connected is True:
        websocket_info = ep_wsServer.get_websocket_info(ep_wsServer.client_list[0])
        if websocket_info is not None:
            while True:
                try:
                    # input_command = input("Please enter the command: ")
                    input_command = await async_input("Please enter the command: ")

                    # print("the input is: ", input_command)
                    function_name, args = extract_function_name_and_arguments(input_command)
                    if function_name == "get_server_directory":
                        server_list = await ep_wsServer.client_list[0].get_server_directory(websocket_info, None, None)
                        print("server directory: ", server_list)
                    elif function_name == "get_logical_device_directory":
                        ln_refs = await ep_wsServer.client_list[0].get_logical_device_directory(
                            args[0], websocket_info, None, None
                        )
                        print("LN list: ", ln_refs)
                    elif function_name == "get_logical_node_directory":
                        ln_directory_items = await ep_wsServer.client_list[0].get_logical_node_directory(
                            args[0], args[1], args[2], websocket_info, None, None
                        )
                        print("LN directory: ", ln_directory_items)
                    elif function_name == "get_data_definition":
                        da_def = await ep_wsServer.client_list[0].get_data_definition(
                            args[0], websocket_info, None, None
                        )
                        print(da_def)
                    elif function_name == "get_data_values":
                        data_val = await ep_wsServer.client_list[0].get_data_values(
                            args[0], args[1], args[2], websocket_info, None, None
                        )
                        print("data value: ", data_val)
                    elif function_name == "select":
                        select_result = await ep_wsServer.client_list[0].select(args[0], websocket_info, None, None)
                        print(select_result)

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
                        operate_res = await ep_wsServer.client_list[0].operate(values, websocket_info, None, None)
                        print("operate result: ", operate_res)

                    elif function_name == "set_data_values":
                        value = [{"data": (args[2], args[3])}]
                        set_data_val_result = await ep_wsServer.client_list[0].set_data_values(
                            args[0], args[1], value, websocket_info, None, None
                        )
                        print("set data values result: ", set_data_val_result)
                    elif function_name == "get_dataset_directory":
                        ds_directory = await ep_wsServer.client_list[0].get_dataset_directory(
                            args[0], args[1], args[2], websocket_info, None, None
                        )
                        print("dataset directory: ", ds_directory)
                    elif function_name == "get_BRCB_values":
                        brcb_val = await ep_wsServer.client_list[0].get_BRCB_values(args[0], websocket_info, None, None)
                        print("brcb value: ", brcb_val)

                    elif function_name == "get_URCB_values":
                        urcb_val = await ep_wsServer.client_list[0].get_URCB_values(args[0], websocket_info, None, None)
                        print(urcb_val)

                    elif function_name == "get_dataset_values":
                        ds_values = await ep_wsServer.client_list[0].get_dataset_values(
                            args[0], args[1], args[2], websocket_info, None, None
                        )
                        print("dataset values: ", ds_values)
                    elif function_name == "set_BRCB_values":
                        func, args, kwargs = parse_command(input_command)

                        # print("func_name:", func)
                        # print("args:", args)
                        # print("kwargs:", kwargs)

                        brcb = IEC61850Client.ClientReportControlBlock(args[0], True)
                        # key, value = args[1].split("=", 1)
                        key, value = next(iter(kwargs.items()))
                        for attr in dir(brcb):
                            if attr.lower() == key.lower():
                                # only evaluate if it's a string
                                if isinstance(value, str):
                                    try:
                                        value = ast.literal_eval(value)
                                    except Exception:
                                        pass  # leave as string if not a literal
                                setattr(brcb, attr, value)
                                break
                        else:
                            print(f"Warning: No matching attribute found for {key}")

                        set_brcb_res = await ep_wsServer.client_list[0].set_BRCB_values(
                            brcb, websocket_info, None, None
                        )
                        print("set brcb result: ", set_brcb_res)

                    elif function_name == "set_URCB_values":
                        func, args, kwargs = parse_command(input_command)

                        urcb = IEC61850Client.ClientReportControlBlock(args[0], False)
                        # key, value = args[1].split("=", 1)
                        key, value = next(iter(kwargs.items()))
                        for attr in dir(urcb):
                            if attr.lower() == key.lower():
                                # only evaluate if it's a string
                                if isinstance(value, str):
                                    try:
                                        value = ast.literal_eval(value)
                                    except Exception:
                                        pass  # leave as string if not a literal
                                setattr(urcb, attr, value)
                                break
                        else:
                            print(f"Warning: No matching attribute found for {key}")

                        set_urcb_res = await ep_wsServer.client_list[0].set_URCB_values(
                            urcb, websocket_info, None, None
                        )
                        print("set urcb result: ", set_urcb_res)

                    else:
                        print("Incorrect command, please try again!")

                except Exception as e:
                    print("error in processing the request:", e)

    else:
        print("did not enter first if ")

    await server_task


if __name__ == "__main__":
    asyncio.run(main())
