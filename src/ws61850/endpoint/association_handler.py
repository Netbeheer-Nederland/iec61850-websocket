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

from ws61850.asn1.encode_decode import encode_tpaa_message
from ws61850.endpoint.base import WebSocketInfo
from ws61850.iec61850.server.response_handling import (
    create_tpaa_abort_response,
    create_tpaa_release_response,
)
from ws61850.security.oauth import check_token_validity_and_expiry

logger = logging.getLogger(__name__)

# Sentinel return values for the caller's message loop.
ACTION_ABORT = "abort"
ACTION_RELEASE = "release"
ACTION_CONTINUE = "continue"


class AssociationHandler:
    """
    Handles the TPAA association control messages that appear in every receive loop:
      - abortRequest  → send abort response, abort transport
      - releaseRequest → send release response, close
      - refreshToken  → validate new token, reschedule expiry task

    Previously copy-pasted verbatim in three places inside endpoint.py.
    Callers check the returned action string and break out of their loop on
    ACTION_ABORT or ACTION_RELEASE.
    """

    def __init__(
        self,
        *,
        kc_cert: str | None = None,
        own_cert: str | None = None,
        cert_endpoint: str | None = None,
        token_issuer: str | None = None,
        close_on_expiry_fn=None,
    ):
        self._kc_cert = kc_cert
        self._own_cert = own_cert
        self._cert_endpoint = cert_endpoint
        self._token_issuer = token_issuer
        # Callable(websocket, exp_timestamp) -> asyncio.Task, injected by the endpoint.
        self._close_on_expiry_fn = close_on_expiry_fn

    async def handle(
        self,
        associate_type: str,
        decoded_message,
        websocket,
        websocket_info: WebSocketInfo,
    ) -> str:
        """
        Process one associate-layer message.

        Returns ACTION_ABORT, ACTION_RELEASE, or ACTION_CONTINUE.
        """
        logger.debug(
            "Handling association message type=%r associate_id=%r",
            associate_type,
            websocket_info.associate_id,
        )

        if associate_type == "abortRequest":
            tpaa = create_tpaa_abort_response(
                websocket_info.invoke_id, websocket_info.associate_id
            )
            encoded = await asyncio.to_thread(
                encode_tpaa_message, tpaa, websocket_info.is_ber_protocol
            )
            await websocket.send(encoded)
            websocket.transport.abort()
            logger.info("Association aborted associate_id=%r", websocket_info.associate_id)
            return ACTION_ABORT

        if associate_type == "releaseRequest":
            tpaa = create_tpaa_release_response(
                websocket_info.invoke_id, websocket_info.associate_id
            )
            encoded = await asyncio.to_thread(
                encode_tpaa_message, tpaa, websocket_info.is_ber_protocol
            )
            await websocket.send(encoded)
            await websocket.close()
            logger.info("Association released associate_id=%r", websocket_info.associate_id)
            return ACTION_RELEASE

        if associate_type == "refreshToken":
            token = decoded_message[1][1][1]["token"]
            validity, expiry = check_token_validity_and_expiry(
                token,
                self._kc_cert,
                self._own_cert,
                self._cert_endpoint,
                self._token_issuer,
            )
            if validity and expiry is not None and websocket_info.expiry_task is not None:
                logger.debug(
                    "Token refresh accepted associate_id=%r new_expiry=%s",
                    websocket_info.associate_id,
                    expiry,
                )
                websocket_info.expiry_task.cancel()
                try:
                    await websocket_info.expiry_task
                except asyncio.CancelledError:
                    pass
                if self._close_on_expiry_fn is not None:
                    websocket_info.expiry_task = asyncio.create_task(
                        self._close_on_expiry_fn(websocket, expiry)
                    )
            else:
                logger.warning(
                    "Token refresh rejected validity=%s expiry=%s associate_id=%r",
                    validity,
                    expiry,
                    websocket_info.associate_id,
                )

        return ACTION_CONTINUE
