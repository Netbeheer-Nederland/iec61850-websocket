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

import logging

import websockets

logger = logging.getLogger(__name__)


class WebSocketTransport:
    """
    Responsible only for the WebSocket connection lifecycle.

    Knows: connect / accept, send / recv, close, ping/health, SSL context.
    Does NOT know: TPAA protocol, association state, reconnect policy, OAuth.

    endpoint.py delegates its raw socket operations here.
    """

    def __init__(self, ssl_context=None, extra_headers=None):
        self._ssl_context = ssl_context
        self._extra_headers = extra_headers or {}

    async def connect(self, uri: str):
        """Open an outbound WebSocket connection, returning the websocket object."""
        return await websockets.connect(
            uri,
            ssl=self._ssl_context,
            additional_headers=self._extra_headers,
        )

    async def send(self, websocket, data: bytes) -> None:
        await websocket.send(data)

    async def recv(self, websocket) -> bytes:
        return await websocket.recv()

    async def close(self, websocket) -> None:
        await websocket.close()

    @property
    def ssl_context(self):
        return self._ssl_context

    @ssl_context.setter
    def ssl_context(self, ctx):
        self._ssl_context = ctx
