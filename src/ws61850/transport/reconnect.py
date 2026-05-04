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

logger = logging.getLogger(__name__)


class ReconnectPolicy:
    """
    Decides whether and how quickly to reconnect after a lost connection.

    Responsibilities (only these):
      - retry count limit
      - delay / exponential backoff between attempts
      - reconnection decision (should_reconnect)
    """

    def __init__(self, enabled: bool = True, max_retries: int | None = None, delay_seconds: float = 5.0):
        self.enabled = enabled
        self.max_retries = max_retries
        self.delay_seconds = delay_seconds
        self._attempts: int = 0

    def should_reconnect(self) -> bool:
        if not self.enabled:
            return False
        if self.max_retries is not None and self._attempts >= self.max_retries:
            return False
        return True

    async def wait(self) -> None:
        self._attempts += 1
        logger.info("Reconnect attempt %d (delay %.1fs)", self._attempts, self.delay_seconds)
        await asyncio.sleep(self.delay_seconds)

    def reset(self) -> None:
        self._attempts = 0
