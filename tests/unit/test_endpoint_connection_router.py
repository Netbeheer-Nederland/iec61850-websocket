"""Unit tests for ConnectionRouter."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ws61850.endpoint.connection_router import ConnectionRouter


def _make_mock_entity(cp: str):
    m = MagicMock()
    m.cp = cp
    return m


@pytest.fixture
def router():
    servers = [_make_mock_entity("cp1"), _make_mock_entity("cp2")]
    clients = [_make_mock_entity("cp3"), _make_mock_entity("cp4")]
    return ConnectionRouter(servers, clients)


class TestConnectionRouterLookup:
    def test_find_server_known_cp(self, router):
        result = router.find_server("cp1")
        assert result is not None
        assert result.cp == "cp1"

    def test_find_server_unknown_cp(self, router):
        assert router.find_server("unknown") is None

    def test_find_client_known_cp(self, router):
        result = router.find_client("cp3")
        assert result is not None
        assert result.cp == "cp3"

    def test_find_client_unknown_cp(self, router):
        assert router.find_client("cp1") is None  # cp1 is a server, not a client

    def test_find_server_second_entry(self, router):
        assert router.find_server("cp2").cp == "cp2"

    def test_find_client_second_entry(self, router):
        assert router.find_client("cp4").cp == "cp4"


class TestConnectionRouterNotFound:
    def test_send_not_found_sends_encoded_message(self):
        router = ConnectionRouter([], [])
        ws = MagicMock()
        ws.send = AsyncMock()
        ws.close = AsyncMock()

        async def _run():
            with patch("ws61850.endpoint.connection_router.encode_tpaa_message", return_value=b"encoded"):
                with patch("ws61850.endpoint.connection_router.create_tpaa_associate_response", return_value=object()):
                    await router.send_not_found_response(ws, "cp-missing", None, None)

        asyncio.get_event_loop().run_until_complete(_run())
        ws.send.assert_awaited_once_with(b"encoded")
        ws.close.assert_awaited_once()

    def test_send_not_found_invokes_callback(self):
        router = ConnectionRouter([], [])
        ws = MagicMock()
        ws.send = AsyncMock()
        ws.close = AsyncMock()
        callback = MagicMock()

        async def _run():
            with patch("ws61850.endpoint.connection_router.encode_tpaa_message", return_value=b"encoded"):
                with patch("ws61850.endpoint.connection_router.create_tpaa_associate_response", return_value=object()):
                    await router.send_not_found_response(ws, "cp-missing", None, callback)

        asyncio.get_event_loop().run_until_complete(_run())
        callback.assert_called_once()

    def test_send_not_found_ber_protocol(self):
        router = ConnectionRouter([], [])
        ws = MagicMock()
        ws.send = AsyncMock()
        ws.close = AsyncMock()
        captured_is_ber = []

        async def _run():
            with patch(
                "ws61850.endpoint.connection_router.encode_tpaa_message",
                side_effect=lambda msg, is_ber: captured_is_ber.append(is_ber) or b"encoded",
            ):
                with patch("ws61850.endpoint.connection_router.create_tpaa_associate_response", return_value=object()):
                    await router.send_not_found_response(ws, "cp", "iec61850-tpaa-ber-v1", None)

        asyncio.get_event_loop().run_until_complete(_run())
        assert captured_is_ber[0] is True

    def test_send_not_found_non_ber_protocol(self):
        router = ConnectionRouter([], [])
        ws = MagicMock()
        ws.send = AsyncMock()
        ws.close = AsyncMock()
        captured_is_ber = []

        async def _run():
            with patch(
                "ws61850.endpoint.connection_router.encode_tpaa_message",
                side_effect=lambda msg, is_ber: captured_is_ber.append(is_ber) or b"encoded",
            ):
                with patch("ws61850.endpoint.connection_router.create_tpaa_associate_response", return_value=object()):
                    await router.send_not_found_response(ws, "cp", None, None)

        asyncio.get_event_loop().run_until_complete(_run())
        assert captured_is_ber[0] is False
