# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
import pytest
from unittest.mock import AsyncMock, MagicMock

from ws61850.transport.session_manager import SessionManager


def _make_ws():
    ws = MagicMock()
    ws.send = AsyncMock()
    ws.recv = AsyncMock(return_value=b"data")
    ws.close = AsyncMock()
    return ws


def test_defaults():
    sm = SessionManager(_make_ws(), associate_id=1)
    assert sm.associate_id == 1
    assert sm.invoke_id == 0
    assert sm.is_ber_protocol is False
    assert sm.max_message_size is None
    assert sm.max_outstanding_calls == 0


def test_next_invoke_id_increments():
    sm = SessionManager(_make_ws(), associate_id=1)
    assert sm.next_invoke_id() == 0
    assert sm.next_invoke_id() == 1
    assert sm.next_invoke_id() == 2


@pytest.mark.asyncio
async def test_send_delegates_to_websocket():
    ws = _make_ws()
    sm = SessionManager(ws, associate_id=1)
    await sm.send(b"hello")
    ws.send.assert_awaited_once_with(b"hello")


@pytest.mark.asyncio
async def test_recv_returns_websocket_data():
    ws = _make_ws()
    ws.recv = AsyncMock(return_value=b"frame")
    sm = SessionManager(ws, associate_id=1)
    result = await sm.recv()
    assert result == b"frame"


@pytest.mark.asyncio
async def test_close_delegates_to_websocket():
    ws = _make_ws()
    sm = SessionManager(ws, associate_id=1)
    await sm.close()
    ws.close.assert_awaited_once()


def test_access_token_stored():
    sm = SessionManager(_make_ws(), associate_id=1, access_token="tok")
    assert sm.access_token == "tok"
