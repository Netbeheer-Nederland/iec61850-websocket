# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""
RTI-SO: Headless ws_server + iec_client.

Listens for IEC 61850 WebSocket connections from field devices / RTI-FSP instances.
When a client connects, logs the event and optionally polls its server directory
on a fixed interval.

Environment variables:
  IEC_HOST          Bind address          (default: 0.0.0.0)
  IEC_PORT          WebSocket listen port (default: 9100)
  IEC_CP            Comma-separated CPs   (default: cp1,cp2)
  IEC_POLL_INTERVAL Seconds between polls (default: 30; 0 = disabled)
  LOG_LEVEL         Logging level         (default: INFO)
"""
import asyncio
import logging
import os
import sys

from ws61850.endpoint import PassiveEndpoint
from ws61850.iec61850.client.iec61850_client import IEC61850Client

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

IEC_HOST = os.environ.get("IEC_HOST", "0.0.0.0")
IEC_PORT = int(os.environ.get("IEC_PORT", "8765"))
IEC_CPS = [cp.strip() for cp in os.environ.get("IEC_CP", "cp1,cp2").split(",") if cp.strip()]
POLL_INTERVAL = int(os.environ.get("IEC_POLL_INTERVAL", "30"))


async def _poll(client: IEC61850Client, endpoint: PassiveEndpoint) -> None:
    """Periodically query the connected IED's server directory."""
    while client.is_connected:
        ws_info = endpoint.get_websocket_info(client)
        if ws_info is not None:
            try:
                result = await client.get_server_directory(ws_info, None, None)
                logger.info("poll cp=%s server_directory=%s", client.cp, result)
            except Exception as exc:
                logger.warning("poll cp=%s error: %s", client.cp, exc)
        await asyncio.sleep(POLL_INTERVAL)


async def _watch(client: IEC61850Client, endpoint: PassiveEndpoint) -> None:
    """Watch a single IEC client slot for connect / disconnect events."""
    while True:
        await client.ready_event.wait()
        if not client.is_connected:
            client.ready_event.clear()
            continue

        logger.info("IED connected cp=%s", client.cp)
        client.disconnect_event.clear()

        poll_task: asyncio.Task | None = None
        if POLL_INTERVAL > 0:
            poll_task = asyncio.create_task(_poll(client, endpoint))

        await client.disconnect_event.wait()

        if poll_task is not None:
            poll_task.cancel()
            await asyncio.gather(poll_task, return_exceptions=True)

        logger.info("IED disconnected cp=%s", client.cp)
        client.ready_event.clear()


async def main() -> None:
    endpoint = PassiveEndpoint()
    clients: list[IEC61850Client] = []

    for cp in IEC_CPS:
        client = IEC61850Client(cp)
        endpoint.add_iec61850_client(client)
        clients.append(client)
        logger.info("registered IEC client cp=%s", cp)

    logger.info("starting ws_server on %s:%d  cps=%s", IEC_HOST, IEC_PORT, IEC_CPS)
    server_task = asyncio.create_task(endpoint.start(IEC_HOST, IEC_PORT))
    watch_tasks = [asyncio.create_task(_watch(c, endpoint)) for c in clients]

    await asyncio.gather(server_task, *watch_tasks)


if __name__ == "__main__":
    asyncio.run(main())
