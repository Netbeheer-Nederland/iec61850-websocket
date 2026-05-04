# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
import pytest
from unittest.mock import AsyncMock, MagicMock

from ws61850.protocol.operations import OperationExecutor, OperationResult


def _make_executor(send_side_effect=None, recv_return=b"response"):
    codec = MagicMock()
    codec.encode.return_value = b"encoded"
    codec.decode.return_value = ("response", {"invokeId": 1})

    ws = MagicMock()
    ws.send = AsyncMock(side_effect=send_side_effect)
    ws.recv = AsyncMock(return_value=recv_return)

    return OperationExecutor(codec, ws), codec, ws


@pytest.mark.asyncio
async def test_call_encodes_and_sends():
    executor, codec, ws = _make_executor()
    msg = ("request", {"invokeId": 1})

    result = await executor.call(msg, invoke_id=1)

    codec.encode.assert_called_once_with(msg)
    ws.send.assert_awaited_once_with(b"encoded")


@pytest.mark.asyncio
async def test_call_returns_operation_result():
    executor, codec, ws = _make_executor()
    result = await executor.call(("request", {}), invoke_id=5)

    assert isinstance(result, OperationResult)
    assert result.raw == b"response"
    assert result.invoke_id == 5
    assert result.decoded == ("response", {"invokeId": 1})


@pytest.mark.asyncio
async def test_call_no_response_returns_none():
    executor, codec, ws = _make_executor()
    result = await executor.call(("request", {}), expects_response=False)

    assert result is None
    ws.recv.assert_not_awaited()


@pytest.mark.asyncio
async def test_call_does_not_recv_when_no_response_expected():
    executor, codec, ws = _make_executor()
    await executor.call(("notify", {}), expects_response=False)
    ws.recv.assert_not_awaited()


def test_operation_result_fields():
    r = OperationResult(raw=b"x", decoded={"a": 1}, invoke_id=3)
    assert r.raw == b"x"
    assert r.decoded == {"a": 1}
    assert r.invoke_id == 3
