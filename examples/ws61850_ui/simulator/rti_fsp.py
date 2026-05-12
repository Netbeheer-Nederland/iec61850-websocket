# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""
RTI-FSP: Headless ws_client + iec_server.

Connects to an RTI-SO endpoint (ws_server + iec_client) and serves an IEC 61850
data model, simulating a field service point / field device.

Environment variables:
  FSP_TARGET_HOST     Remote RTI-SO ws_server host     (default: rti-so)
  FSP_TARGET_PORT     Remote RTI-SO ws_server port     (default: 8765)
  FSP_CP              Connection point                  (default: cp1)
  FSP_MODEL           Data model variant (1 or 2)       (default: 1)
  FSP_UPDATE_INTERVAL Simulated value update interval   (default: 15; 0 = off)
  LOG_LEVEL           Logging level                     (default: INFO)
"""
import asyncio
import logging
import os
import pathlib
import random
import sys

from ws61850.endpoint import ActiveEndpoint
from ws61850.iec61850.data_model import IedModelLoader
from ws61850.iec61850.server.iec61850_server import IEC61850Server

_MODEL1_PATH = pathlib.Path(__file__).parent / "ied_model1.json"
_MODEL2_PATH = pathlib.Path(__file__).parent / "ied_model2.json"

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

FSP_HOST = os.environ.get("FSP_TARGET_HOST", "localhost")
FSP_PORT = int(os.environ.get("FSP_TARGET_PORT", "8765"))
FSP_CP = os.environ.get("FSP_CP", "cp1")
FSP_MODEL = os.environ.get("FSP_MODEL", "1")
UPDATE_INTERVAL = int(os.environ.get("FSP_UPDATE_INTERVAL", "15"))

# Well-known refs present in both example models; errors are silently ignored.
_UPDATE_CANDIDATES = [
    ("LD0/MMXU1.TotW.mag.f",  lambda: round(random.uniform(800.0, 1200.0), 2)),
    ("LD0/MMXU1.Hz.mag.f",    lambda: round(random.uniform(49.8, 50.2), 3)),
    ("LD0/MMXU1.TotVAr.mag.f", lambda: round(random.uniform(-200.0, 200.0), 2)),
]


async def _simulate_values(server: IEC61850Server) -> None:
    """Periodically update values to trigger reports on active RCBs."""
    while True:
        await asyncio.sleep(UPDATE_INTERVAL)
        for ref, gen in _UPDATE_CANDIDATES:
            try:
                await server.update_value(ref, gen())
                logger.debug("simulated update %s", ref)
            except Exception as exc:
                logger.debug("update %s skipped: %s", ref, exc)


async def main() -> None:
    endpoint = ActiveEndpoint(is_direct=False, try_reconnect=True)
    ied_model = IedModelLoader.from_file(_MODEL2_PATH if FSP_MODEL == "2" else _MODEL1_PATH)
    server = IEC61850Server(ied_model, FSP_CP)

    endpoint.add_iec61850_server(server)
    server.send_msg_callback = endpoint.send_msg_callback
    server.recv_msg_callback = endpoint.recv_msg_callback

    logger.info(
        "RTI-FSP starting — ws_client → ws://%s:%d  cp=%s  model=%s",
        FSP_HOST, FSP_PORT, FSP_CP, FSP_MODEL,
    )

    tasks: list[asyncio.Task] = [
        asyncio.create_task(endpoint.start(FSP_HOST, FSP_PORT, FSP_CP)),
    ]
    if UPDATE_INTERVAL > 0:
        tasks.append(asyncio.create_task(_simulate_values(server)))

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
