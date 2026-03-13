import argparse
import asyncio
import logging
import os
import random
import sys
import time
from pathlib import Path

from ws61850.endpoint.endpoint import WebSocketEndpoint
from ws61850.iec61850.server.iec61850_server import IEC61850Server
from ws61850.security.oauth import get_access_token
from ws61850.security.tls import TLSConfiguration

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from testing.certs.paths import CERT_DIR  # noqa: E402
from testing.ieds.high_level_model import make_ied_model1  # noqa: E402
from testing.tasks.refresh_token_if_needed import refresh_token_if_needed  # noqa: E402
from testing.tasks.runner import run_tasks  # noqa: E402
from testing.utils.credentials_store import load_credentials  # noqa: E402

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)

cafile = CERT_DIR / "ca.pem"
CREDENTIALS_FILE = "data/client_credentials.json"

max_message_size_client = 65000


def resolve_credentials_path(credentials_file_path: str) -> Path:
    path = Path(credentials_file_path)
    if path.is_absolute():
        return path
    project_root = Path(__file__).resolve().parent
    return (project_root / path).resolve()


def parse_args() -> argparse.Namespace:
    global default_port
    parser = argparse.ArgumentParser(description="WebSocketClient + IEC61850-Controller")
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
        "--start",
        type=int,
        default="1",
        help="the number of support PoCC (default: '1').",
    )
    parser.add_argument(
        "--stop",
        type=int,
        default="50",
        help="the number of support PoCC (default: '50').",
    )
    parser.add_argument(
        "--delay",
        type=int,
        default="2",
        help="the delay to start next (default: '2').",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=default_host,
        help="hostname for the websocket server (env: WS_SERVER_HOST, default: 'localhost').",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=default_port,
        help="port for the websocket server (env: WS_SERVER_PORT, default: 8765).",
    )
    parser.add_argument(
        "--report",
        type=bool,
        default=True,
        help="report enabled (default: 'True').",
    )
    return parser.parse_args()


async def toggle_float_value(iec61150_server, obj_ref):
    while True:
        value = random.uniform(5.5, 10.0)
        await iec61150_server.update_value(obj_ref, value)
        # logger.info(f"Value of {obj_ref} changed to {value} of server instance {iec61150_server}")
        await asyncio.sleep(1)


async def add_iec61850_client_requests(iec61850_client, ws_client):
    """
    Handles IEC 61850 client requests after connection.
    """
    await iec61850_client.ready_event.wait()

    if iec61850_client.is_connected is True:
        websocket_info = ws_client.get_websocket_info(iec61850_client)

        if websocket_info is not None:
            logger.info(f"[{iec61850_client.cp}] Connection established. Performing requests...")

            try:
                # Placeholder: Clients stay connected for 5 seconds to simulate activity
                await asyncio.sleep(5)

            except Exception:
                logger.exception(f"[{iec61850_client.cp}] Error during request handler")
        else:
            logger.info(f"[{iec61850_client.cp}] Connection information not found after ready event.")


BASE = os.environ.get("KEYCLOAK_URL", "https://localhost:8443")
TARGET_REALM = os.environ.get("IEC61850_REALM", "iec61850-test")
token_endpoint = f"{BASE}/realms/{TARGET_REALM}/protocol/openid-connect/token"


async def start_client_process(client_config, i, args):
    """
    Initializes and starts a single WebSocket client/IED using its configuration.
    """
    client_id = client_config["client_id"]
    client_secret = client_config["client_secret"]
    access_token = await get_access_token(token_endpoint, client_id, client_secret, cafile)
    logger.info(f"Access-Token: {access_token}")

    # TLS Configuration for Client ---
    tls_config = TLSConfiguration(cafile, None, False)

    # Initialize Endpoint and Server
    ep_ws_client = WebSocketEndpoint(oauth_enable=True, tls_config=tls_config)

    # Assign IED Model based on client ID number
    pocc_id = client_config["pocc_id"]
    iec61850_server = IEC61850Server(make_ied_model1(), pocc_id)
    ep_ws_client.add_iec61850_server(iec61850_server)

    task_list = []
    # start WebSocket Connection - Now correctly including an empty list [] for subprotocols
    controller_task = asyncio.create_task(
        ep_ws_client.start("active", args.host, args.port, pocc_id, access_token=access_token)
    )
    task_list.append(controller_task)

    # add a report task
    if args.report:
        report_task = asyncio.create_task(iec61850_server.periodic_report_start())
        task_list.append(report_task)

    refresh_task = asyncio.create_task(
        refresh_token_if_needed(
            token_endpoint,
            client_config["client_id"],
            client_config["client_secret"],
            client_config["pocc_id"],
            access_token,
            ep_ws_client,
            cafile,
        )
    )
    task_list.append(refresh_task)

    logger.info(f"[{pocc_id}] Starting WSS connection...")
    await run_tasks(task_list)


async def run_multi_clients():
    args = parse_args()

    credentials_path = resolve_credentials_path(CREDENTIALS_FILE)
    credentials = load_credentials(credentials_path)
    total = args.stop - args.start + 1
    logger.info(f"Starting concurrent execution of {total} clients...")

    startup_tasks = []
    for i, config in enumerate(credentials):
        if args.start - 1 > i >= args.stop:
            break
        routine = start_client_process(config, i, args)
        task = asyncio.create_task(routine, name=f"Task-{config['pocc_id']}")
        startup_tasks.append(task)
        await asyncio.sleep(args.delay)

    await run_tasks(startup_tasks)


if __name__ == "__main__":
    try:
        asyncio.run(run_multi_clients())
    except KeyboardInterrupt:
        logger.info("\nDynamic Client Runner (Batch 1) stopped by user (Ctrl+C).")
    except Exception:
        logger.exception("Critical error in main runner")
