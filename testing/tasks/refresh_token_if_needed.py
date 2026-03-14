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
import time

import jwt

from ws61850 import asn1
from ws61850.iec61850.client.request_handling import create_token_refresh
from ws61850.security.oauth import get_access_token

logger = logging.getLogger(__name__)


async def refresh_token_if_needed(
    url,
    client_id,
    client_secret,
    pocc_id,
    token,
    websocket_endpoint,
    ca_file,
):
    while True:
        websocket_info = next(
            (ws_info for ws_info in websocket_endpoint.websocket_info_list if ws_info.cp == pocc_id),
            None,
        )

        if websocket_info is not None:
            decoded = jwt.decode(token, options={"verify_signature": False})
            # Check if less than 3 seconds until expiration
            if decoded["exp"] - time.time() < 3:
                logger.info(f"The access token for {pocc_id} endpoint is expiring soon, requesting a new token...")
                token = await get_access_token(url, client_id, client_secret, ca_file)
                refresh_token_message = create_token_refresh(websocket_info.associate_id, token)
                encoded_message = asn1.encode_decode.encode_tpaa_message(refresh_token_message)

                logger.info(f"Sending message: {encoded_message}")
                await websocket_info.websocket.send(encoded_message)

        await asyncio.sleep(1)  # check every second
