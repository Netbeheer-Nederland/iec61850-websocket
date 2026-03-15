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
from pathlib import Path

from ws61850.endpoint.endpoint import WebSocketEndpoint
from ws61850.iec61850.client.iec61850_client import IEC61850Client
from ws61850.iec61850.data_model.helper import get_now_time

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from testing.certs.paths import CERT_DIR  # noqa: E402

cafile = CERT_DIR / "ca.pem"
cert_path = CERT_DIR / "server.pem"
key_path = CERT_DIR / "server-key.pem"

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)


max_message_size_server = 65000

data_w_max_set_pct = [
    {
        "name": "setMag",
        "data": ("structure", {"name": "f", "data": [("float32", 19.48)]}),
    }
]

opt_flds = {
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
brcb.optFlds = opt_flds
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
urcb.confRev = 5000
urcb.optFlds = opt_flds
urcb.bufTm = 1000
urcb.sqNum = 88
urcb.trgOps = trgOp
urcb.intgPd = 5
urcb.gi = True
urcb.entryId = b"\x01\x02\x03\x04\x05\x06\x07\x08"
urcb.timeOfEntry = get_now_time()
urcb.resv = True


def callback_called(result, param):
    logger.info(f"callback called: {result}")


async def main():
    ep_ws_server = WebSocketEndpoint(
        oauth_enable=True,
        cert_endpoint="https://localhost:8443/realms/iec61850-test/protocol/openid-connect/certs",
        token_issuer="https://localhost:8443/realms/iec61850-test",
        kc_cert=cafile,
    )

    iec61850_client = IEC61850Client("cp1")
    ep_ws_server.add_iec61850_client(iec61850_client)

    server_task = asyncio.create_task(ep_ws_server.start("passive", "localhost", 8765))

    await ep_ws_server.client_list[0].ready_event.wait()
    if ep_ws_server.client_list[0].is_connected is True:
        websocket_info = ep_ws_server.get_websocket_info(ep_ws_server.client_list[0])
        if websocket_info is not None:
            try:
                server_list = await ep_ws_server.client_list[0].get_server_directory(
                    websocket_info, callback_called, None
                )
                ld_directory = await ep_ws_server.client_list[0].get_logical_device_directory(
                    "LD0", websocket_info, callback_called, None
                )
                ln_directory_ds = await ep_ws_server.client_list[0].get_logical_node_directory(
                    "LD0", "LLN0", "dataset", websocket_info, callback_called, None
                )
                ln_directory_do = await ep_ws_server.client_list[0].get_logical_node_directory(
                    "LD0", "LLN0", "dataObject", websocket_info, callback_called, None
                )
                ds_directory = await ep_ws_server.client_list[0].get_dataset_directory(
                    "LD0",
                    "LLN0",
                    "DataSetMinMaxAvg",
                    websocket_info,
                    callback_called,
                    None,
                )
                da_def = await ep_ws_server.client_list[0].get_data_definition(
                    "LD0/LLN0.Mod", websocket_info, callback_called, None
                )
                da_val = await ep_ws_server.client_list[0].get_data_values(
                    "LD0/DWMX1.WMaxSetPct",
                    "sp",
                    True,
                    websocket_info,
                    callback_called,
                    None,
                )
                set_da_res = await ep_ws_server.client_list[0].set_data_values(
                    "LD0/DWMX1.WMaxSetPct",
                    "sp",
                    data_w_max_set_pct,
                    websocket_info,
                    callback_called,
                    None,
                )
                set_brcb_res = await ep_ws_server.client_list[0].set_BRCB_values(
                    brcb, websocket_info, callback_called, None
                )

                logger.info(f"printing the list or returned items from client {iec61850_client.cp}")
                logger.info(f"server_list: {server_list}")
                logger.info(f"ld_directory: {ld_directory}")
                logger.info(f"ln_directory_ds: {ln_directory_ds}")
                logger.info(f"ln_directory_do:{ln_directory_do}")
                logger.info(f"ds_directory: {ds_directory}")
                logger.info(f"da_def: {da_def}")
                logger.info(f"da_val: {da_val}")
                logger.info(f"set_da_res: {set_da_res}")
                logger.info(f"set_brcb_res: {set_brcb_res}")

            except Exception as e:
                logger.error("handler not called:", e)
        else:
            logger.warning("websocket_info is None")
    else:
        logger.warning("did not enter first if ")

    await server_task


if __name__ == "__main__":
    asyncio.run(main())
