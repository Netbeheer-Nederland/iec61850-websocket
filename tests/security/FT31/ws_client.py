import asyncio
import logging
import os
import sys
from pathlib import Path

from ws61850.endpoint.endpoint import WebSocketEndpoint
from ws61850.iec61850.server.iec61850_server import IEC61850Server
from ws61850.security.oauth import get_access_token

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from testing.certs.paths import CERT_DIR  # noqa: E402
from testing.ieds.high_level_model import make_ied_model1  # noqa: E402
from testing.tasks.refresh_token_if_needed import refresh_token_if_needed  # noqa: E402

cafile = CERT_DIR / "ca.pem"

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)


BASE = os.environ.get("KEYCLOAK_URL", "https://localhost:8443")
TARGET_REALM = os.environ.get("IEC61850_REALM", "iec61850-test")
token_endpoint = f"{BASE}/realms/{TARGET_REALM}/protocol/openid-connect/token"


async def main():
    logger.info("Start Client")

    client_id = "ws-client"
    client_secret = "K4Nrd14seXG52J3xpnIqfMyILTJJu3VI"
    access_token = await get_access_token(token_endpoint, client_id, client_secret, cafile)
    logger.info(f"Access-Token: {access_token}")

    ep_ws_client_1 = WebSocketEndpoint(oauth_enable=True)
    iec61850_server_1 = IEC61850Server(make_ied_model1(), "cp1")
    ep_ws_client_1.add_iec61850_server(iec61850_server_1)

    task1 = asyncio.create_task(ep_ws_client_1.start("active", "localhost", 8765, "cp1", access_token=access_token))
    task_token_1 = asyncio.create_task(
        refresh_token_if_needed(token_endpoint, client_id, client_secret, "cp1", access_token, ep_ws_client_1, cafile)
    )

    await asyncio.gather(task1, task_token_1)


if __name__ == "__main__":
    asyncio.run(main())
