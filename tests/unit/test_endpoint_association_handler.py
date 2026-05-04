"""Unit tests for AssociationHandler."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ws61850.endpoint.association_handler import (
    ACTION_ABORT,
    ACTION_CONTINUE,
    ACTION_RELEASE,
    AssociationHandler,
)
from ws61850.endpoint.base import WebSocketInfo


@pytest.fixture
def websocket_info():
    ws = MagicMock()
    info = WebSocketInfo(ws, associate_id="assoc-1")
    info.invoke_id = 0
    info.is_ber_protocol = False
    return info


@pytest.fixture
def mock_websocket():
    ws = MagicMock()
    ws.send = AsyncMock()
    ws.close = AsyncMock()
    transport_mock = MagicMock()
    ws.transport = transport_mock
    return ws


class TestAssociationHandlerAbort:
    def test_abort_returns_abort_sentinel(self, mock_websocket, websocket_info):
        handler = AssociationHandler()

        async def _run():
            with patch("ws61850.endpoint.association_handler.encode_tpaa_message", return_value=b"abort-frame"):
                with patch("ws61850.endpoint.association_handler.create_tpaa_abort_response", return_value=object()):
                    return await handler.handle("abortRequest", None, mock_websocket, websocket_info)

        result = asyncio.get_event_loop().run_until_complete(_run())
        assert result == ACTION_ABORT

    def test_abort_sends_response_and_aborts_transport(self, mock_websocket, websocket_info):
        handler = AssociationHandler()

        async def _run():
            with patch("ws61850.endpoint.association_handler.encode_tpaa_message", return_value=b"abort-frame"):
                with patch("ws61850.endpoint.association_handler.create_tpaa_abort_response", return_value=object()):
                    await handler.handle("abortRequest", None, mock_websocket, websocket_info)

        asyncio.get_event_loop().run_until_complete(_run())
        mock_websocket.send.assert_awaited_once()
        mock_websocket.transport.abort.assert_called_once()


class TestAssociationHandlerRelease:
    def test_release_returns_release_sentinel(self, mock_websocket, websocket_info):
        handler = AssociationHandler()

        async def _run():
            with patch("ws61850.endpoint.association_handler.encode_tpaa_message", return_value=b"release-frame"):
                with patch("ws61850.endpoint.association_handler.create_tpaa_release_response", return_value=object()):
                    return await handler.handle("releaseRequest", None, mock_websocket, websocket_info)

        result = asyncio.get_event_loop().run_until_complete(_run())
        assert result == ACTION_RELEASE

    def test_release_sends_response_and_closes(self, mock_websocket, websocket_info):
        handler = AssociationHandler()

        async def _run():
            with patch("ws61850.endpoint.association_handler.encode_tpaa_message", return_value=b"release-frame"):
                with patch("ws61850.endpoint.association_handler.create_tpaa_release_response", return_value=object()):
                    await handler.handle("releaseRequest", None, mock_websocket, websocket_info)

        asyncio.get_event_loop().run_until_complete(_run())
        mock_websocket.send.assert_awaited_once()
        mock_websocket.close.assert_awaited_once()


class TestAssociationHandlerUnknown:
    def test_unknown_type_returns_continue(self, mock_websocket, websocket_info):
        handler = AssociationHandler()

        async def _run():
            return await handler.handle("associateResponse", MagicMock(), mock_websocket, websocket_info)

        result = asyncio.get_event_loop().run_until_complete(_run())
        assert result == ACTION_CONTINUE

    def test_unknown_type_sends_nothing(self, mock_websocket, websocket_info):
        handler = AssociationHandler()

        async def _run():
            await handler.handle("associateResponse", MagicMock(), mock_websocket, websocket_info)

        asyncio.get_event_loop().run_until_complete(_run())
        mock_websocket.send.assert_not_awaited()
