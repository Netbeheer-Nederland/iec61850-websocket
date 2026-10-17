# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""Two LEDs that exist only in memory, with a history of what changed them."""

from __future__ import annotations

import asyncio
import time
from collections import deque

COLORS = ("red", "green")


class SimulatedLeds:
    def __init__(self, blink_seconds: float = 0.3, history: int = 50):
        self.blink_seconds = blink_seconds
        self.state = dict.fromkeys(COLORS, False)
        self.history: deque[dict] = deque(maxlen=history)
        self._blinks: set[asyncio.Task] = set()

    def set(self, color: str, on: bool, reason: str) -> None:
        if color not in self.state:
            raise KeyError(color)
        self.state[color] = on
        self.history.append(
            {"time": time.time(), "led": color, "on": on, "reason": reason}
        )

    def blink(self, color: str, reason: str) -> None:
        """On now, off after blink_seconds; doesn't wait for the off."""
        self.set(color, True, reason)
        task = asyncio.create_task(self._off_later(color, reason))
        self._blinks.add(task)
        task.add_done_callback(self._blinks.discard)

    async def _off_later(self, color: str, reason: str) -> None:
        await asyncio.sleep(self.blink_seconds)
        self.set(color, False, f"{reason} (blink end)")

    def reset(self, reason: str = "reset") -> None:
        for color in COLORS:
            self.set(color, False, reason)

    async def close(self) -> None:
        for task in list(self._blinks):
            task.cancel()
        await asyncio.gather(*self._blinks, return_exceptions=True)

    def snapshot(self) -> dict:
        return {"leds": dict(self.state), "history": list(self.history)}
