from time import sleep

from Endpoint.endpoint import *
import asyncio
from IEC61850.client.IEC61850Client import *

maxMessageSize_server = 65000

def callback_called(result, param):
    print("callback called: ", result)

async def main():
    # websocket server
    ep_wsServer = WebSocketEndpoint()

    iec61850_client = IEC61850Client("cp1")
    ep_wsServer.add_iec61850_client(iec61850_client)


    server_task = asyncio.create_task(
        ep_wsServer.start("passive", "localhost", 8765)
    )

    await ep_wsServer.client_list[0].ready_event.wait()
    if ep_wsServer.client_list[0].is_connected is True:
        websocket_info = ep_wsServer.get_websocket_info(ep_wsServer.client_list[0])
        if websocket_info is not None:
            try:
                server_list = await ep_wsServer.client_list[0].get_server_directory(websocket_info, None, None)
                for ld_index, ld_inst in enumerate(server_list):
                    is_last_ld = ld_index == len(server_list) - 1
                    ld_prefix = "└── " if is_last_ld else "├── "
                    print(f"{ld_prefix}{ld_inst}")

                    ln_refs = await ep_wsServer.client_list[0].get_logical_device_directory(ld_inst, websocket_info, None, None)
                    for ln_index, ln_inst in enumerate(ln_refs):
                        is_last_ln = ln_index == len(ln_refs) - 1
                        ln_prefix = "    └── " if is_last_ld else "│   └── " if is_last_ln else (
                            "    ├── " if is_last_ld else "│   ├── ")
                        print(f"{ln_prefix}{ln_inst}")

                        ln_directory_urcb = await ep_wsServer.client_list[0].get_logical_node_directory(ld_inst, ln_inst,
                                                                                                      "urcb",
                                                                                                      websocket_info,
                                                                                                      None,
                                                                                                      None)
                        for urcb_index, urcb_inst in enumerate(ln_directory_urcb):
                            urcb_prefix = (
                                "        └── [URCB] "
                            )

                            print(f"{urcb_prefix}{urcb_inst}")

                        ln_directory_brcb = await ep_wsServer.client_list[0].get_logical_node_directory(ld_inst,
                                                                                                        ln_inst,
                                                                                                        "brcb",
                                                                                                        websocket_info,
                                                                                                        None,
                                                                                                        None)
                        for brcb_index, brcb_inst in enumerate(ln_directory_brcb):
                            brcb_prefix = (
                                "        └── [BRCB] "
                            )

                            print(f"{brcb_prefix}{brcb_inst}")

                        ln_directory_ds = await ep_wsServer.client_list[0].get_logical_node_directory(ld_inst, ln_inst,
                                                                                                      "dataset",
                                                                                                      websocket_info,
                                                                                                      None,
                                                                                                      None)
                        for ds_index, ds_inst in enumerate(ln_directory_ds):
                            ds_prefix = (
                                "        └── [DS] "
                            )

                            print(f"{ds_prefix}{ds_inst}")
                            ds_items = await ep_wsServer.client_list[0].get_dataset_directory(ld_inst, ln_inst, ds_inst,
                                                                                             websocket_info,
                                                                                             None, None)
                            for item_index, item_inst in enumerate(ds_items):
                                item_text = item_inst["ref"] + f"[{item_inst['fc']}]"
                                item_prefix = (
                                    "            └── "
                                )
                                print(f"{item_prefix}{item_text}")

                        ln_directory_do = await ep_wsServer.client_list[0].get_logical_node_directory(ld_inst, ln_inst,
                                                                                                      "dataObject",
                                                                                                      websocket_info,
                                                                                                      None,
                                                                                                      None)
                        for do_index, do_inst in enumerate(ln_directory_do):
                            is_last_do = do_index == len(ln_directory_do) - 1
                            do_prefix = (
                                "        └── " if is_last_do else
                                "        ├── "
                            )
                            print(f"{do_prefix}{do_inst}")

                            da_def = await ep_wsServer.client_list[0].get_data_definition(ld_inst + "/" + ln_inst + "." + do_inst,
                                                                                      websocket_info,
                                                                                      None, None)

                            sdos = retrieve_sdos(da_def)
                            for sdo_index, sdo_inst in enumerate(sdos):
                                print_node(sdo_index, sdo_inst, len(sdos))
                                retrieve_attributes_sdo(da_def, sdo_inst)

                            da_list = retrieve_das(da_def)
                            if (len(da_list)) != 0:
                                print_direct_da(da_list)

                print("running the negative test cases:")
                ln_refs = await ep_wsServer.client_list[0].get_logical_device_directory("wrong_ld_name", websocket_info, None,
                                                                                        None)
                print(ln_refs)

                ln_directory_ds = await ep_wsServer.client_list[0].get_logical_node_directory("LD0","wrong_ln",
                                                                                              "dataset",
                                                                                              websocket_info,
                                                                                              None,
                                                                                              None)
                print(ln_directory_ds)



            except Exception as e:
                print("handler not called:", e)

    else:
        print("did not enter first if ")

    await server_task

if __name__ == "__main__":
    asyncio.run(main())
