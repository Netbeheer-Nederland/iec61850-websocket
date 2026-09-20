"""Unit tests for ActiveEndpoint."""

from unittest.mock import MagicMock

import pytest

from ws61850.endpoint.active_endpoint import ActiveEndpoint


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


class TestActiveEndpointInit:
    def test_default_init(self):
        ep = ActiveEndpoint()
        assert ep.server_list == []
        assert ep.client_list == []
        assert ep.websocket_info_list == []
        assert ep.server is None
        assert ep._is_direct is False

    def test_reconnect_policy_enabled_by_default(self):
        ep = ActiveEndpoint()
        assert ep._reconnect_policy.enabled is True

    def test_reconnect_policy_disabled(self):
        ep = ActiveEndpoint(try_reconnect=False)
        assert ep._reconnect_policy.enabled is False

    def test_reconnect_policy_max_retries(self):
        ep = ActiveEndpoint(max_retries=3)
        assert ep._reconnect_policy.max_retries == 3

    def test_reconnect_policy_delay(self):
        ep = ActiveEndpoint(retry_connection_delay=10.0)
        assert ep._reconnect_policy.delay_seconds == 10.0


class TestActiveEndpointRegistration:
    def test_add_client(self):
        ep = ActiveEndpoint()
        client = _make_fake_client("cp1")
        ep.add_iec61850_client(client)
        assert client in ep.client_list

    def test_add_server(self):
        ep = ActiveEndpoint()
        server = _make_fake_server("cp2")
        ep.add_iec61850_server(server)
        assert server in ep.server_list

    def test_add_client_installs_callbacks_if_set(self):
        ep = ActiveEndpoint()
        ep.send_msg_callback = MagicMock()
        ep.recv_msg_callback = MagicMock()
        client = _make_fake_client("cp1")
        client.install_send_msg_callback = MagicMock()
        client.install_recv_msg_callback = MagicMock()
        ep.add_iec61850_client(client)
        client.install_send_msg_callback.assert_called_once_with(ep.send_msg_callback)
        client.install_recv_msg_callback.assert_called_once_with(ep.recv_msg_callback)


class TestActiveEndpointWebSocketInfoLookup:
    def test_get_websocket_info_returns_none_when_empty(self):
        ep = ActiveEndpoint()
        client = _make_fake_client("cp1")
        assert ep.get_websocket_info(client) is None

    def test_get_websocket_info_iec61850_server_returns_none_when_empty(self):
        ep = ActiveEndpoint()
        server = _make_fake_server("cp2")
        assert ep.get_websocket_info_iec61850_server(server) is None

    def test_get_websocket_info_finds_matching_entry(self):
        ep = ActiveEndpoint()
        client = _make_fake_client("cp1")
        ws = MagicMock()
        ws.request.path = "/cp1"
        from ws61850.endpoint.base import WebSocketInfo
        info = WebSocketInfo(ws, "assoc-1", cp="cp1")
        ep.websocket_info_list.append(info)
        found = ep.get_websocket_info(client)
        assert found is info


class TestActiveEndpointStopPassive:
    def test_stop_passive_is_no_op(self):
        import asyncio
        ep = ActiveEndpoint()
        asyncio.get_event_loop().run_until_complete(ep.stop_passive())  # should not raise


class TestActiveEndpointConnectionClosed:
    """get_status()'s connectedClients is len(websocket_info_list), so a
    closed session left in that list understates a disconnect as still
    connected until the next connect for the same cp overwrites it.
    """

    def test_removes_the_closed_cp_websocket_info(self):
        import asyncio
        from ws61850.endpoint.base import WebSocketInfo

        ep = ActiveEndpoint()
        client = _make_fake_client("cp1")
        ep.add_iec61850_client(client)
        ws = MagicMock()
        info = WebSocketInfo(ws, "assoc-1", cp="cp1")
        ep.websocket_info_list.append(info)

        asyncio.get_event_loop().run_until_complete(ep._on_connection_closed("cp1"))

        assert ep.websocket_info_list == []

    def test_leaves_other_cps_websocket_info_alone(self):
        import asyncio
        from ws61850.endpoint.base import WebSocketInfo

        ep = ActiveEndpoint()
        ep.add_iec61850_client(_make_fake_client("cp1"))
        ep.add_iec61850_client(_make_fake_client("cp2"))
        info1 = WebSocketInfo(MagicMock(), "assoc-1", cp="cp1")
        info2 = WebSocketInfo(MagicMock(), "assoc-2", cp="cp2")
        ep.websocket_info_list.extend([info1, info2])

        asyncio.get_event_loop().run_until_complete(ep._on_connection_closed("cp1"))

        assert ep.websocket_info_list == [info2]

    def test_clears_the_client_connection_flags(self):
        import asyncio

        ep = ActiveEndpoint()
        client = _make_fake_client("cp1")
        client.is_connected = True
        client.ready_event = MagicMock()
        client.disconnect_event = MagicMock()
        ep.add_iec61850_client(client)

        asyncio.get_event_loop().run_until_complete(ep._on_connection_closed("cp1"))

        assert client.is_connected is False
        client.ready_event.clear.assert_called_once()
        client.disconnect_event.set.assert_called_once()
