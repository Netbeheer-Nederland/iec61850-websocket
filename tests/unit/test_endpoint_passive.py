"""Unit tests for PassiveEndpoint."""

from unittest.mock import MagicMock, patch

import pytest

from ws61850.endpoint.passive_endpoint import PassiveEndpoint


def _make_fake_client(cp: str):
    c = MagicMock()
    c.cp = cp
    c.send_msg_callback = None
    c.recv_msg_callback = None
    return c


def _make_fake_server(cp: str):
    s = MagicMock()
    s.cp = cp
    s.send_msg_callback = None
    s.recv_msg_callback = None
    return s


class TestPassiveEndpointRegistration:
    def test_add_client(self):
        ep = PassiveEndpoint()
        client = _make_fake_client("cp1")
        ep.add_iec61850_client(client)
        assert client in ep.client_list

    def test_add_server(self):
        ep = PassiveEndpoint()
        server = _make_fake_server("cp2")
        ep.add_iec61850_server(server)
        assert server in ep.server_list

    def test_add_client_installs_callbacks_if_set(self):
        ep = PassiveEndpoint()
        ep.send_msg_callback = MagicMock()
        ep.recv_msg_callback = MagicMock()
        client = _make_fake_client("cp1")
        client.install_send_msg_callback = MagicMock()
        client.install_recv_msg_callback = MagicMock()
        ep.add_iec61850_client(client)
        client.install_send_msg_callback.assert_called_once_with(ep.send_msg_callback)
        client.install_recv_msg_callback.assert_called_once_with(ep.recv_msg_callback)

    def test_add_server_installs_callbacks_if_set(self):
        ep = PassiveEndpoint()
        ep.send_msg_callback = MagicMock()
        ep.recv_msg_callback = MagicMock()
        server = _make_fake_server("cp2")
        server.install_send_msg_callback = MagicMock()
        server.install_recv_msg_callback = MagicMock()
        ep.add_iec61850_server(server)
        server.install_send_msg_callback.assert_called_once_with(ep.send_msg_callback)
        server.install_recv_msg_callback.assert_called_once_with(ep.recv_msg_callback)


class TestPassiveEndpointWebSocketInfoLookup:
    def test_get_websocket_info_returns_none_when_empty(self):
        ep = PassiveEndpoint()
        client = _make_fake_client("cp1")
        assert ep.get_websocket_info(client) is None

    def test_get_websocket_info_iec61850_server_returns_none_when_empty(self):
        ep = PassiveEndpoint()
        server = _make_fake_server("cp2")
        assert ep.get_websocket_info_iec61850_server(server) is None

    def test_get_websocket_info_finds_matching_entry(self):
        ep = PassiveEndpoint()
        client = _make_fake_client("cp1")
        ws = MagicMock()
        ws.request.path = "/cp1"
        from ws61850.endpoint.base import WebSocketInfo
        info = WebSocketInfo(ws, "assoc-1", cp="cp1")
        ep.websocket_info_list.append(info)
        found = ep.get_websocket_info(client)
        assert found is info


class TestPassiveEndpointInit:
    def test_default_init(self):
        ep = PassiveEndpoint()
        assert ep.server_list == []
        assert ep.client_list == []
        assert ep.websocket_info_list == []
        assert ep.server is None
        assert ep._oauth_enable is False
        assert ep._is_direct is False

    def test_oauth_validator_created_when_configured(self):
        ep = PassiveEndpoint(
            oauth_enable=True,
            cert_endpoint="https://example.com/jwks",
            token_issuer="https://example.com",
        )
        assert ep._jwt_validator is not None

    def test_oauth_validator_none_when_not_configured(self):
        ep = PassiveEndpoint(oauth_enable=False)
        assert ep._jwt_validator is None
