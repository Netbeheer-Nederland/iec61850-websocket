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

from ws61850.endpoint.passive_endpoint import PassiveEndpoint
from ws61850.iec61850.client.iec61850_client import IEC61850Client
from ws61850.iec61850.data_model.helper import get_now_time

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    stream=sys.stdout,
)

optional_fields = {
    "seqNum": False,
    "timeStamp": True,
    "dataSet": True,
    "bufOvfl": True,
    "configRef": False,
    "entryID": True,
    "dataRef": False,
    "reasonCode": False,
}

trgOp = {"dchg": False, "qchg": False, "dupd": False, "integrity": True, "gi": False}

brcb = IEC61850Client.ClientReportControlBlock("LD0/LLN0.rcbMinMaxAvg", True)
brcb.rptEna = True
brcb.confRev = 5
brcb.opt_flds = optional_fields
brcb.bufTm = 1000
brcb.sqNum = 42
brcb.trgOps = trgOp
brcb.intgPd = 2000
brcb.gi = True
brcb.purgeBuf = False
brcb.entryId = b"\x01\x02\x03\x04\x05\x06\x07\x08"
brcb.timeOfEntry = get_now_time()
brcb.resvTms = 5

urcb = IEC61850Client.ClientReportControlBlock("LD0/LLN0.rcbSetpoints", True)
urcb.rptEna = True
urcb.confRev = 5
urcb.opt_flds = optional_fields
urcb.bufTm = 1000
urcb.sqNum = 88
urcb.trgOps = trgOp
urcb.intgPd = 5000
urcb.gi = True
urcb.entryId = b"\x01\x02\x03\x04\x05\x06\x07\x08"
urcb.timeOfEntry = get_now_time()
urcb.resv = True


def callback_called(result, param):
    logger.info("callback called: %s", result)


data_attribute_value = {
    "name": "Oper",
    "data": (
        "structure",
        {
            "data": [
                ("structure", {"name": "f", "data": [("float32", 10.5)]}),
                (
                    "structure",
                    {
                        "name": "origin",
                        "data": [
                            ("enumerated", "bayControl"),
                            ("octetString", b"ORIGIN_ID_1234567890"),
                        ],
                    },
                ),
                ("int8u", 2),
                (
                    "timeStamp",
                    {
                        "secondSinceEpoch": 1757588367,
                        "fractionOfSecond": 8120140,
                        "timeQuality": {
                            "leapSecondsKown": False,
                            "clockFailure": False,
                            "clockNotSynchronized": False,
                            "timeAccuracy": 3,
                        },
                    },
                ),
                ("boolean", False),
                ("check", {"synchroCheck": False, "interlockCheck": True}),
            ]
        },
    ),
}

data_WMaxSetPct = [
    {
        "name": "setMag",
        "data": ("structure", {"name": "f", "data": [("float32", 19.666)]}),
    }
]

oper_val = {
    "ref": "LD0/DWMX1.WMaxSpt",
    "ctlVal": ("structure", {"data": [("structure", {"data": [("float32", 666.43)]})]}),
    "origin": {"orCat": "stationControl", "orIdent": b"ORIGIN_ID_1234567890"},
    "ctlNum": 10,
    "t": {
        "secondSinceEpoch": 1757588367,
        "fractionOfSecond": 8120140,
        "timeQuality": {
            "leapSecondsKown": False,
            "clockFailure": False,
            "clockNotSynchronized": False,
            "timeAccuracy": 3,
        },
    },
    "test": True,
    "check": {"synchroCheck": False, "interlockCheck": False},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="WebSocketServer")
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
        "--pocc",
        type=int,
        default="100",
        help="the number of support PoCC (default: '100').",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=default_host,
        help="hostname for the websocket server (default: 'localhost').",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=default_port,
        help="port for the websocket server (default: 8765).",
    )

    return parser.parse_args()


async def add_iec61850_client_requests(iec61850_client, endpoint):
    await iec61850_client.ready_event.wait()
    if iec61850_client.is_connected is True:
        websocket_info = endpoint.get_websocket_info(iec61850_client)
        if websocket_info is not None:
            try:
                server_list = await iec61850_client.get_server_directory(websocket_info, callback_called, None)
                ld_directory = await iec61850_client.get_logical_device_directory(
                    "LD0", websocket_info, callback_called, None
                )
                ln_directory_ds = await iec61850_client.get_logical_node_directory(
                    "LD0", "LLN0", "dataset", websocket_info, callback_called, None
                )
                ln_directory_do = await iec61850_client.get_logical_node_directory(
                    "LD0", "LLN0", "dataObject", websocket_info, callback_called, None
                )
                ds_directory = await iec61850_client.get_dataset_directory(
                    "LD0", "LLN0", "DataSetMinMaxAvg", websocket_info, callback_called, None
                )
                set_urcb_res = await iec61850_client.set_URCB_values(urcb, websocket_info, None, None)
                da_def = await iec61850_client.get_data_definition(
                    "LD0/DWMX1.WMaxSptPct", websocket_info, callback_called, None
                )
                set_da_res = await iec61850_client.set_data_values(
                    "LD0/DWMX1.WMaxSpt.Oper", "co", [data_attribute_value], websocket_info, callback_called, None
                )
                da_val = await iec61850_client.get_data_values(
                    "LD0/DWMX1.WMaxSpt.Oper", "co", True, websocket_info, callback_called, None
                )

                logger.info("Results from client %s", iec61850_client.cp)
                logger.info("server_list: %s", server_list)
                logger.info("ld_directory: %s", ld_directory)
                logger.info("ln_directory_ds: %s", ln_directory_ds)
                logger.info("ln_directory_do: %s", ln_directory_do)
                logger.info("ds_directory: %s", ds_directory)
                logger.info("da_def: %s", da_def)
                logger.info("da_val: %s", da_val)
                logger.info("set_da_res: %s", set_da_res)
                logger.info("set_urcb_res: %s", set_urcb_res)

            except Exception as e:
                logger.exception("Service call failed for %s: %s", iec61850_client.cp, e)


async def main():
    args = parse_args()
    endpoint = PassiveEndpoint()

    clients = []
    for pocc_num in range(1, args.pocc + 1):
        pocc_id = f"EAN{pocc_num:03}"
        logger.info("Registering IEC61850 Client on WS-server with ID: %s", pocc_id)
        client = IEC61850Client(pocc_id)
        endpoint.add_iec61850_client(client)
        clients.append(client)

    logger.info("Starting WebSocket endpoint in passive mode on %s:%s", args.host, args.port)
    server_task = asyncio.create_task(endpoint.start(args.host, args.port))

    await asyncio.sleep(2)

    request_tasks = [asyncio.create_task(add_iec61850_client_requests(client, endpoint)) for client in clients]
    await asyncio.gather(*request_tasks)

    await server_task


if __name__ == "__main__":
    asyncio.run(main())
