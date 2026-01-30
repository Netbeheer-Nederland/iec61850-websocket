import asyncio
import logging
import time

import jwt

from testing.certs.paths import CERT_DIR
from testing.ieds.high_level_model import make_ied_model1
from ws61850 import asn1
from ws61850.endpoint.endpoint import WebSocketEndpoint
from ws61850.iec61850.client.request_handling import create_token_refresh
from ws61850.iec61850.server.iec61850_server import IEC61850Server
from ws61850.security.oauth import get_access_token

logger = logging.getLogger(__name__)

cafile = CERT_DIR / "ca.pem"


async def refresh_token_if_needed(url, client_id, client_secret, token, websocket_endpoint, cp):
    while True:
        websocket_info = next(
            (ws_info for ws_info in websocket_endpoint.websocket_info_list if ws_info.cp == cp),
            None,
        )

        if websocket_info is not None:
            decoded = jwt.decode(token, options={"verify_signature": False})
            # Check if less than 3 seconds until expiration
            if decoded["exp"] - time.time() < 3:
                logger.info(f"The access token for {cp} endpoint is expiring soon, requesting a new token...")
                token = await get_access_token(url, client_id, client_secret, cafile)
                refresh_token_message = create_token_refresh(websocket_info.associate_id, token)
                encoded_message = asn1.encode_decode.encode_tpaa_message(refresh_token_message)

                logger.info(f"Sending message: {encoded_message}")
                await websocket_info.websocket.send(encoded_message)

        await asyncio.sleep(1)  # check every second


async def main():
    logger.info("Start Client")

    token_request_url = "https://localhost:8443/realms/iec61850-test/protocol/openid-connect/token"

    client_id = "ws-client"
    client_secret = "K4Nrd14seXG52J3xpnIqfMyILTJJu3VI"
    access_token = await get_access_token(token_request_url, client_id, client_secret, cafile)
    logger.info(f"Access-Token: {access_token}")

    ep_ws_client_1 = WebSocketEndpoint(oauth_enable=True)
    iec61850_server_1 = IEC61850Server(make_ied_model1(), "cp1")
    ep_ws_client_1.add_iec61850_server(iec61850_server_1)

    task1 = asyncio.create_task(ep_ws_client_1.start("active", "localhost", 8765, "cp1", access_token=access_token))
    task_token_1 = asyncio.create_task(
        refresh_token_if_needed(
            token_request_url,
            client_id,
            client_secret,
            access_token,
            ep_ws_client_1,
            "cp1",
        )
    )

    await asyncio.gather(task1, task_token_1)


if __name__ == "__main__":
    asyncio.run(main())
