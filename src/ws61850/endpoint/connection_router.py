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
import datetime
import logging

from ws61850.asn1.encode_decode import encode_tpaa_message
from ws61850.iec61850.server.response_handling import create_tpaa_associate_response
from ws61850.iec61850.server.service_error import ServiceStatusKind

logger = logging.getLogger(__name__)


class ConnectionRouter:
    """
    Resolves a control-point path (cp) to a registered IEC 61850 server or client,
    and sends the standard 'instanceNotAvailable' response when no match is found.

    Previously, the lookup + not-found block was copy-pasted four times across
    handle_client() and __start_active().
    """

    def __init__(self, server_list: list, client_list: list):
        self._servers = server_list
        self._clients = client_list

    def find_server(self, cp: str):
        """Return the IEC61850Server registered for cp, or None."""
        return next((s for s in self._servers if s.cp == cp), None)

    def find_client(self, cp: str):
        """Return the IEC61850Client registered for cp, or None."""
        return next((c for c in self._clients if c.cp == cp), None)

    async def send_not_found_response(
        self,
        websocket,
        cp: str,
        protocol: str | None,
        send_callback=None,
    ) -> None:
        """Encode and send an instanceNotAvailable associateResponse, then close."""
        tpaa = create_tpaa_associate_response(
            65000, cp, ServiceStatusKind.instanceNotAvailable.name
        )
        is_ber = protocol is not None and "iec61850-tpaa-ber-v1" in protocol
        encoded = await asyncio.to_thread(encode_tpaa_message, tpaa, is_ber)
        await websocket.send(encoded)
        if send_callback is not None:
            send_callback(encoded, datetime.datetime.now())
        logger.info("Connection failed: access point %r not available", cp)
        await websocket.close()
