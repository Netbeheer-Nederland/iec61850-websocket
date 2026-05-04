# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
import pytest
from unittest.mock import patch

from ws61850.transport.reconnect import ReconnectPolicy


def test_enabled_no_limit_always_reconnects():
    p = ReconnectPolicy(enabled=True, max_retries=None)
    for _ in range(100):
        assert p.should_reconnect() is True


def test_disabled_never_reconnects():
    p = ReconnectPolicy(enabled=False)
    assert p.should_reconnect() is False


def test_max_retries_limit():
    p = ReconnectPolicy(enabled=True, max_retries=3)
    assert p.should_reconnect() is True


@pytest.mark.asyncio
async def test_wait_increments_attempts():
    p = ReconnectPolicy(enabled=True, max_retries=2, delay_seconds=0.0)
    with patch("asyncio.sleep"):
        await p.wait()
        assert p._attempts == 1
        assert p.should_reconnect() is True
        await p.wait()
        assert p._attempts == 2
        assert p.should_reconnect() is False


@pytest.mark.asyncio
async def test_reset_clears_attempts():
    p = ReconnectPolicy(enabled=True, max_retries=1, delay_seconds=0.0)
    with patch("asyncio.sleep"):
        await p.wait()
    assert p.should_reconnect() is False
    p.reset()
    assert p._attempts == 0
    assert p.should_reconnect() is True


def test_default_delay():
    p = ReconnectPolicy()
    assert p.delay_seconds == 5.0
