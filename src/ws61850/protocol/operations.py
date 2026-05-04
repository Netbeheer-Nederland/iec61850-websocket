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

from dataclasses import dataclass
from typing import Any


@dataclass
class OperationResult:
    raw: bytes
    decoded: Any
    invoke_id: int | None


class OperationExecutor:
    """
    Single send/recv primitive that replaces the copy-pasted pattern in compact.py.

    Every service call boils down to:
      1. build a TPAA message
      2. encode it
      3. send over the WebSocket
      4. (optionally) recv and decode the response
      5. return a typed result

    Centralising here gives one place for timeout handling, logging,
    correlation validation, retry policy, and metrics.
    """

    def __init__(self, codec, websocket):
        self._codec = codec
        self._ws = websocket

    async def call(self, message, *, invoke_id=None, expects_response=True) -> OperationResult | None:
        encoded = self._codec.encode(message)
        await self._ws.send(encoded)

        if not expects_response:
            return None

        raw = await self._ws.recv()
        decoded = self._codec.decode(raw)
        return OperationResult(raw=raw, decoded=decoded, invoke_id=invoke_id)
