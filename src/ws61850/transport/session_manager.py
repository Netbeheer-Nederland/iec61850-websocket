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


class SessionManager:
    """
    Holds all state for one active TPAA session on a WebSocket connection.

    Responsibilities (only these):
      - store associate_id / max_message_size after association handshake
      - dispense and track invoke_ids
      - store per-connection metadata (access token, BER flag)

    Transport, reconnect, and auth policy live elsewhere.
    """

    def __init__(self, websocket, associate_id, *, cp=None, access_token=None):
        self.websocket = websocket
        self.associate_id = associate_id
        self.invoke_id: int = 0
        self.cp = cp
        self.expiry_task = None
        self.access_token = access_token
        self.is_ber_protocol: bool = False
        self.max_message_size: int | None = None
        self.max_outstanding_calls: int = 0

    def next_invoke_id(self) -> int:
        iid = self.invoke_id
        self.invoke_id += 1
        return iid

    async def send(self, data: bytes) -> None:
        await self.websocket.send(data)

    async def recv(self) -> bytes:
        return await self.websocket.recv()

    async def close(self) -> None:
        await self.websocket.close()
