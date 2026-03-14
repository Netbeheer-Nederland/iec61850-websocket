import asyncio
import logging
import sys
import time
from pathlib import Path

import jwt

from ws61850 import asn1
from ws61850.endpoint.endpoint import WebSocketEndpoint
from ws61850.iec61850.client.request_handling import create_token_refresh
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


# async def refresh_token_if_needed(url, client_id, client_secret, token, websocket_endpoint, cp):
#     while True:
#         websocket_info = next(
#             (ws_info for ws_info in websocket_endpoint.websocket_info_list if ws_info.cp == cp),
#             None,
#         )
#
#         if websocket_info is not None:
#             decoded = jwt.decode(token, options={"verify_signature": False})
#
#             # Check if less than 3 seconds until expiration
#             if decoded["exp"] - time.time() < 3:
#                 logging.info(f"The access token for {cp} endpoint is expiring soon, requesting a new token...")
#                 token = get_access_token(url, client_id, client_secret)
#                 refresh_token_message = create_token_refresh(websocket_info.associate_id, token)
#                 encoded_message = asn1.encode_decode.encode_tpaa_message(refresh_token_message)
#
#                 await websocket_info.websocket.send(encoded_message)
#
#         await asyncio.sleep(1)  # check every second


async def main():
    at = "eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICI4SUdMWmlEQ1M5dzZ2aFdZOFZmYW9zaTYxNDN5OFM4NlV6UjY0bHh2X2pZIn0.eyJleHAiOjE3NjA1MTY5NzYsImlhdCI6MTc2MDUxNjkxNiwianRpIjoidHJydGNjOmE5NjA1MTBjLTkyNTQtNGY0MC05NDkxLTY5NjA5YTEzNThkYiIsImlzcyI6Imh0dHBzOi8vbG9jYWxob3N0Ojg0NDMvcmVhbG1zL21hc3RlciIsImF1ZCI6ImFjY291bnQiLCJzdWIiOiJmNjE1OWU5My0zMDRiLTRmNGEtODAzMy1jNjRmZGNhNGJlYjQiLCJ0eXAiOiJCZWFyZXIiLCJhenAiOiJ3c19jbGllbnRfMSIsImFjciI6IjEiLCJhbGxvd2VkLW9yaWdpbnMiOlsiLyoiXSwicmVhbG1fYWNjZXNzIjp7InJvbGVzIjpbImRlZmF1bHQtcm9sZXMtbWFzdGVyIiwib2ZmbGluZV9hY2Nlc3MiLCJ1bWFfYXV0aG9yaXphdGlvbiJdfSwicmVzb3VyY2VfYWNjZXNzIjp7ImFjY291bnQiOnsicm9sZXMiOlsibWFuYWdlLWFjY291bnQiLCJtYW5hZ2UtYWNjb3VudC1saW5rcyIsInZpZXctcHJvZmlsZSJdfX0sInNjb3BlIjoicHJvZmlsZSBlbWFpbCIsImVtYWlsX3ZlcmlmaWVkIjpmYWxzZSwiY2xpZW50SG9zdCI6IjA6MDowOjA6MDowOjA6MSIsInByZWZlcnJlZF91c2VybmFtZSI6InNlcnZpY2UtYWNjb3VudC13c19jbGllbnRfMSIsImNsaWVudEFkZHJlc3MiOiIwOjA6MDowOjA6MDowOjEiLCJjbGllbnRfaWQiOiJ3c19jbGllbnRfMSJ9.EJVfanhbxkCwCoC94DwNq2p9D15N7iCVo4LNNiPXRRwbD0SLB_bSnukoSjvugAhmOK74VfvkcwIbXmLGKbf3v_TP7Ng8pKRA8pNoL0mtbtmsDgql82wXDKvn3lk_erFYjDpxmdnySl-JWHR1PbF69nCs8a2HI4Afg3GDq6s-R1FtJgU-z2K-nfBtpdIAy8a_8DEdzvLmqU94yHGDi9QZ_TjbGZWcadg4cVadBFRLW82JzMlbGuoU9rfAfYxs-tNn0ZDiNWNsc2b6eo98QWiS9Rm9P9LwlMJhKqhp3cKRYKQ6NAs7Rl2KoQKtByeZYEnF8Emo2_uTkllZ9e_JVIxsZT"

    ep_ws_client = WebSocketEndpoint(oauth_enable=True)
    iec61850_server_1 = IEC61850Server(make_ied_model1(), "cp1")
    ep_ws_client.add_iec61850_server(iec61850_server_1)

    task1 = asyncio.create_task(ep_ws_client.start("active", "localhost", 8765, "cp1", at))

    await asyncio.gather(task1)


if __name__ == "__main__":
    asyncio.run(main())
