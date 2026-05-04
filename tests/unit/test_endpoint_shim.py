"""Unit tests for WebSocketEndpoint backward-compat shim."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ws61850.endpoint.endpoint import WebSocketEndpoint, WebSocketInfo


def _make_fake_client(cp: str):
    c = MagicMock()
    c.cp = cp
    c.send_msg_callback = None
    c.recv_msg_callback = None
    c.install_send_msg_callback = MagicMock()
    c.install_recv_msg_callback = MagicMock()
    return c


def _make_fake_server(cp: str):
    s = MagicMock()
    s.cp = cp
    s.send_msg_callback = None
    s.recv_msg_callback = None
    s.install_send_msg_callback = MagicMock()
    s.install_recv_msg_callback = MagicMock()
    return s


class TestWebSocketEndpointShim:
    def test_websocket_info_list_is_empty_before_start(self):
        ep = WebSocketEndpoint()
        assert ep.websocket_info_list == []

    def test_server_is_none_before_start(self):
        ep = WebSocketEndpoint()
        assert ep.server is None

    def test_buffers_clients_before_start(self):
        ep = WebSocketEndpoint()
        client = _make_fake_client("cp1")
        ep.add_iec61850_client(client)
        assert len(ep._pending_clients) == 1

    def test_buffers_servers_before_start(self):
        ep = WebSocketEndpoint()
        server = _make_fake_server("cp2")
        ep.add_iec61850_server(server)
        assert len(ep._pending_servers) == 1

    def test_get_websocket_info_returns_none_before_start(self):
        ep = WebSocketEndpoint()
        client = _make_fake_client("cp1")
        assert ep.get_websocket_info(client) is None

    def test_get_websocket_info_iec61850_server_returns_none_before_start(self):
        ep = WebSocketEndpoint()
        server = _make_fake_server("cp2")
        assert ep.get_websocket_info_iec61850_server(server) is None

    def test_start_passive_creates_passive_endpoint(self):
        import asyncio

        ep = WebSocketEndpoint()

        async def _run():
            with patch("ws61850.endpoint.passive_endpoint.serve") as mock_serve:
                mock_server = AsyncMock()
                mock_server.__aenter__ = AsyncMock(return_value=MagicMock(serve_forever=AsyncMock()))
                mock_server.__aexit__ = AsyncMock(return_value=False)
                mock_serve.return_value = mock_server
                try:
                    await asyncio.wait_for(ep.start("passive", "localhost", 12345), timeout=0.1)
                except (asyncio.TimeoutError, Exception):
                    pass

        asyncio.get_event_loop().run_until_complete(_run())
        assert ep._impl is not None
        from ws61850.endpoint.passive_endpoint import PassiveEndpoint
        assert isinstance(ep._impl, PassiveEndpoint)

    def test_start_active_creates_active_endpoint(self):
        import asyncio

        ep = WebSocketEndpoint()

        async def _run():
            with patch("ws61850.endpoint.active_endpoint.websockets.connect") as mock_connect:
                mock_connect.side_effect = ConnectionRefusedError("no server")
                try:
                    await asyncio.wait_for(
                        ep.start("active", "localhost", 12345, cp="cp1"),
                        timeout=0.2,
                    )
                except (asyncio.TimeoutError, Exception):
                    pass

        asyncio.get_event_loop().run_until_complete(_run())
        from ws61850.endpoint.active_endpoint import ActiveEndpoint
        assert isinstance(ep._impl, ActiveEndpoint)

    def test_buffered_clients_replayed_on_start_passive(self):
        import asyncio

        ep = WebSocketEndpoint()
        client = _make_fake_client("cp1")
        ep.add_iec61850_client(client)

        async def _run():
            with patch("ws61850.endpoint.passive_endpoint.serve") as mock_serve:
                mock_server_ctx = MagicMock()
                mock_server_ctx.__aenter__ = AsyncMock(return_value=MagicMock(serve_forever=AsyncMock()))
                mock_server_ctx.__aexit__ = AsyncMock(return_value=False)
                mock_serve.return_value = mock_server_ctx
                try:
                    await asyncio.wait_for(ep.start("passive", "localhost", 12345), timeout=0.1)
                except (asyncio.TimeoutError, Exception):
                    pass

        asyncio.get_event_loop().run_until_complete(_run())
        if ep._impl is not None:
            assert client in ep._impl.client_list

    def test_invalid_mode_raises(self):
        import asyncio

        ep = WebSocketEndpoint()

        async def _run():
            await ep.start("unknown", "localhost", 12345)

        with pytest.raises(ValueError, match="Unknown mode"):
            asyncio.get_event_loop().run_until_complete(_run())
