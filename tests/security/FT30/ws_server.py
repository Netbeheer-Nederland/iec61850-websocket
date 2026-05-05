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
import os
import ssl
import sys
from pathlib import Path

from ws61850.endpoint.passive_endpoint import PassiveEndpoint
from ws61850.iec61850.client.iec61850_client import IEC61850Client
from ws61850.iec61850.data_model.helper import get_now_time
from ws61850.security.tls import TLSConfiguration

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from testing.certs.paths import CERT_DIR  # noqa: E402

cert_path = CERT_DIR / "server.pem"
key_path = CERT_DIR / "server-key.pem"

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    stream=sys.stdout,
)

data_WMaxSetPct = [
    {
        "name": "setMag",
        "data": ("structure", {"name": "f", "data": [("float32", 19.48)]}),
    }
]

optFlds = {
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
brcb.optFlds = optFlds
brcb.bufTm = 1000
brcb.sqNum = 42
brcb.trgOps = trgOp
brcb.intgPd = 2
brcb.gi = True
brcb.purgeBuf = False
brcb.entryId = b"\x01\x02\x03\x04\x05\x06\x07\x08"
brcb.timeOfEntry = get_now_time()
brcb.resvTms = 5

urcb = IEC61850Client.ClientReportControlBlock("LD0/LLN0.rcbSetpoints", True)
urcb.rptEna = True
urcb.confRev = 5
urcb.optFlds = optFlds
urcb.bufTm = 1000
urcb.sqNum = 88
urcb.trgOps = trgOp
urcb.intgPd = 5
urcb.gi = True
urcb.entryId = b"\x01\x02\x03\x04\x05\x06\x07\x08"
urcb.timeOfEntry = get_now_time()
urcb.resv = True

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


async def main():
    tls_config = TLSConfiguration(cert_path, key_path, True)
    tls_config.set_min_and_max_version(min_version=ssl.TLSVersion.TLSv1_2, max_version=ssl.TLSVersion.TLSv1_2)
    tls_config.ssl_context.keylog_filename = os.path.join("tlskeys.log")

    endpoint = PassiveEndpoint(tls_config=tls_config)

    client = IEC61850Client("cp1")
    endpoint.add_iec61850_client(client)

    server_task = asyncio.create_task(endpoint.start("localhost", 8765))

    await client.ready_event.wait()
    if client.is_connected is True:
        websocket_info = endpoint.get_websocket_info(client)
        if websocket_info is not None:
            try:
                server_list = await client.get_server_directory(websocket_info, None, None)
                ld_directory = await client.get_logical_device_directory("LD0", websocket_info, None, None)
                ln_directory_ds = await client.get_logical_node_directory(
                    "LD0", "LLN0", "dataset", websocket_info, None, None
                )
                ln_directory_do = await client.get_logical_node_directory(
                    "LD0", "LLN0", "dataObject", websocket_info, None, None
                )
                ds_directory = await client.get_dataset_directory(
                    "LD0", "LLN0", "DataSetMinMaxAvg", websocket_info, None, None
                )
                set_urcb_res = await client.set_URCB_values(urcb, websocket_info, None, None)
                da_def = await client.get_data_definition("LD0/DWMX1.WMaxSptPct", websocket_info, None, None)
                set_da_res = await client.set_data_values(
                    "LD0/DWMX1.WMaxSpt.Oper", "co", [data_attribute_value], websocket_info, None, None
                )
                da_val = await client.get_data_values("LD0/DWMX1.WMaxSpt.Oper", "co", True, websocket_info, None, None)

                logger.info("Results from client cp1")
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
                logger.exception("Service call failed: %s", e)
    else:
        logger.warning("Client did not connect")

    await server_task


if __name__ == "__main__":
    asyncio.run(main())
