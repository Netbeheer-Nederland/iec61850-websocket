"""Unit tests for the BFF's browser push relay.

Covers WSHub, push_relay_loop and its helpers (_parse_status_repr,
_fetch_fsp_client_count, _build_enriched_connections, _relay_new_messages)
in bff/bff_server.py. These are isolated unit tests - no Docker, no real
RTI-SO/RTI-FSP instances - matching the pattern already used by
tests/unit/fsp/test_bff_endpoint.py and tests/unit/so/test_bff_endpoint.py:
a fake stand-in for the thing being talked to (here, BffClient.request)
instead of a live server.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

# Allow importing rti-demo/bff modules as top-level modules (they use
# unqualified imports like `from bffClient import BffClient`, so bff/ itself
# must be on sys.path). Point BFF_CONNECTIONS_FILE at a throwaway, empty file
# *before* importing bff_server, so its module-level ConnectionManager
# doesn't load or seed from the real connections.json and doesn't register
# any real BffClients.
BFF_DIR = Path(__file__).resolve().parents[3] / "bff"
if str(BFF_DIR) not in sys.path:
    sys.path.insert(0, str(BFF_DIR))

_tmp_connections_file = Path(tempfile.mkdtemp()) / "connections.json"
_tmp_connections_file.write_text("[]", encoding="utf-8")
os.environ.setdefault("BFF_CONNECTIONS_FILE", str(_tmp_connections_file))

import bff_server  # noqa: E402


pytestmark = pytest.mark.unit


class FakeBffClient:
    """Stand-in for bffClient.BffClient: records calls, returns canned data."""

    def __init__(self, responses=None, raises=None):
        self.responses = responses or {}
        self.raises = raises
        self.calls = []

    def request(self, method, path, json=None, params=None, headers=None):
        self.calls.append((method, path))
        if self.raises:
            raise self.raises
        return self.responses.get(path)


class FakeWebSocket:
    """Stand-in for a connected browser WebSocket."""

    def __init__(self, fail=False):
        self.fail = fail
        self.sent = []

    async def send_json(self, message):
        if self.fail:
            raise RuntimeError("client gone")
        self.sent.append(message)


@pytest.fixture(autouse=True)
def _isolated_relay_state(monkeypatch):
    """Every test gets an empty connections list and message watermark table,
    so tests can't leak state into each other via the module-level singletons.
    """
    monkeypatch.setattr(bff_server.conn_manager, "connections", [])
    bff_server._last_relayed_message_id.clear()
    bff_server._last_relayed_client_list.clear()
    yield
    bff_server._last_relayed_message_id.clear()
    bff_server._last_relayed_client_list.clear()


# -------------------- _parse_status_repr --------------------

def test_parse_status_repr_passes_through_dict():
    assert bff_server._parse_status_repr({"status": "listening"}) == {"status": "listening"}


def test_parse_status_repr_parses_python_dict_literal():
    # This is what fsp/acsi_server.py's api_status() actually returns:
    # str(dict) - single-quoted, with True/False/None - not JSON.
    raw = "{'status': 'listening', 'connectedClients': 2, 'error': None, 'ok': True}"
    assert bff_server._parse_status_repr(raw) == {
        "status": "listening",
        "connectedClients": 2,
        "error": None,
        "ok": True,
    }


def test_parse_status_repr_rejects_garbage_string():
    assert bff_server._parse_status_repr("not a dict") is None


@pytest.mark.parametrize("raw", [None, 42, ["a", "list"], "[1, 2, 3]"])
def test_parse_status_repr_rejects_non_dict_input(raw):
    assert bff_server._parse_status_repr(raw) is None


# -------------------- WSHub --------------------

@pytest.mark.asyncio
async def test_wshub_broadcast_reaches_all_registered_clients():
    hub = bff_server.WSHub()
    ws1, ws2 = FakeWebSocket(), FakeWebSocket()
    await hub.register(ws1)
    await hub.register(ws2)

    await hub.broadcast({"type": "connections", "data": []})

    assert ws1.sent == [{"type": "connections", "data": []}]
    assert ws2.sent == [{"type": "connections", "data": []}]


@pytest.mark.asyncio
async def test_wshub_broadcast_drops_clients_whose_send_fails():
    hub = bff_server.WSHub()
    alive, dead = FakeWebSocket(), FakeWebSocket(fail=True)
    await hub.register(alive)
    await hub.register(dead)

    await hub.broadcast({"type": "connections", "data": []})

    assert alive.sent
    assert dead not in hub._clients

    # A later broadcast only reaches the surviving client and doesn't raise,
    # even though "dead" was never explicitly unregistered by the caller.
    await hub.broadcast({"type": "connections", "data": [1]})
    assert alive.sent[-1] == {"type": "connections", "data": [1]}


@pytest.mark.asyncio
async def test_wshub_unregister_stops_further_broadcasts():
    hub = bff_server.WSHub()
    ws = FakeWebSocket()
    await hub.register(ws)
    await hub.unregister(ws)

    await hub.broadcast({"type": "connections", "data": []})
    assert ws.sent == []


@pytest.mark.asyncio
async def test_wshub_broadcast_with_no_clients_is_a_noop():
    hub = bff_server.WSHub()
    await hub.broadcast({"type": "connections", "data": []})  # must not raise


# -------------------- _fetch_fsp_client_count --------------------

@pytest.mark.asyncio
async def test_fetch_fsp_client_count_when_listening(monkeypatch):
    client = FakeBffClient(responses={
        "/api/status": {"ok": True, "status": "{'status': 'listening', 'connectedClients': 3}"}
    })
    monkeypatch.setitem(bff_server._bff_clients, "10.0.0.1:5001", client)

    name, count = await bff_server._fetch_fsp_client_count(
        {"name": "fsp1", "host": "10.0.0.1", "port": 5001}
    )
    assert (name, count) == ("fsp1", 3)


@pytest.mark.asyncio
async def test_fetch_fsp_client_count_when_not_listening(monkeypatch):
    client = FakeBffClient(responses={
        "/api/status": {"ok": True, "status": "{'status': 'stopped', 'connectedClients': 0}"}
    })
    monkeypatch.setitem(bff_server._bff_clients, "10.0.0.1:5001", client)

    name, count = await bff_server._fetch_fsp_client_count(
        {"name": "fsp1", "host": "10.0.0.1", "port": 5001}
    )
    assert (name, count) == ("fsp1", 0)


@pytest.mark.asyncio
async def test_fetch_fsp_client_count_swallows_request_errors(monkeypatch):
    client = FakeBffClient(raises=ConnectionError("refused"))
    monkeypatch.setitem(bff_server._bff_clients, "10.0.0.1:5001", client)

    name, count = await bff_server._fetch_fsp_client_count(
        {"name": "fsp1", "host": "10.0.0.1", "port": 5001}
    )
    assert (name, count) == ("fsp1", 0)


@pytest.mark.asyncio
async def test_fetch_fsp_client_count_defaults_to_zero_when_no_client_registered():
    name, count = await bff_server._fetch_fsp_client_count(
        {"name": "ghost", "host": "1.2.3.4", "port": 9999}
    )
    assert (name, count) == ("ghost", 0)


# -------------------- _build_enriched_connections --------------------

@pytest.mark.asyncio
async def test_build_enriched_connections_adds_fsp_client_counts(monkeypatch):
    connections = [
        {"name": "fsp1", "type": "RTI-FSP", "status": "connected", "host": "10.0.0.1", "port": 5001},
        {"name": "fsp2", "type": "RTI-FSP", "status": "disconnected", "host": "10.0.0.2", "port": 5001},
        {"name": "so1", "type": "RTI-SO", "status": "connected", "host": "10.0.0.3", "port": 5002},
    ]
    monkeypatch.setattr(bff_server.conn_manager, "connections", connections)
    monkeypatch.setitem(
        bff_server._bff_clients,
        "10.0.0.1:5001",
        FakeBffClient(responses={
            "/api/status": {"ok": True, "status": "{'status': 'listening', 'connectedClients': 5}"}
        }),
    )

    enriched = await bff_server._build_enriched_connections()
    by_name = {c["name"]: c for c in enriched}

    assert by_name["fsp1"]["connectedClients"] == 5
    # Disconnected FSPs are never polled for a live count and default to 0.
    assert by_name["fsp2"]["connectedClients"] == 0
    # Non-FSP connections are passed through untouched.
    assert "connectedClients" not in by_name["so1"]
    # The source connection dicts are not mutated in place.
    assert "connectedClients" not in connections[0]


@pytest.mark.asyncio
async def test_build_enriched_connections_empty_list():
    assert await bff_server._build_enriched_connections() == []


# -------------------- _relay_new_messages --------------------

@pytest.mark.asyncio
async def test_relay_new_messages_broadcasts_unseen_ids(monkeypatch):
    broadcasts = []
    monkeypatch.setattr(bff_server.ws_hub, "broadcast", AsyncMock(side_effect=lambda m: broadcasts.append(m)))
    client = FakeBffClient(responses={"/api/messages": {"messages": [
        {"id": 1, "message": "a"}, {"id": 2, "message": "b"},
    ]}})

    await bff_server._relay_new_messages("10.0.0.1:5001", client)

    assert broadcasts == [{
        "type": "messages",
        "target": "10.0.0.1:5001",
        "data": [{"id": 1, "message": "a"}, {"id": 2, "message": "b"}],
    }]
    assert bff_server._last_relayed_message_id["10.0.0.1:5001"] == 2


@pytest.mark.asyncio
async def test_relay_new_messages_only_sends_ids_past_the_watermark(monkeypatch):
    bff_server._last_relayed_message_id["10.0.0.1:5001"] = 2
    broadcasts = []
    monkeypatch.setattr(bff_server.ws_hub, "broadcast", AsyncMock(side_effect=lambda m: broadcasts.append(m)))
    client = FakeBffClient(responses={"/api/messages": {"messages": [
        {"id": 1, "message": "a"}, {"id": 2, "message": "b"}, {"id": 3, "message": "c"},
    ]}})

    await bff_server._relay_new_messages("10.0.0.1:5001", client)

    assert broadcasts == [{
        "type": "messages",
        "target": "10.0.0.1:5001",
        "data": [{"id": 3, "message": "c"}],
    }]


@pytest.mark.asyncio
async def test_relay_new_messages_no_broadcast_when_nothing_new(monkeypatch):
    # Watermark already at the log's current max (not ahead of it, which
    # would instead read as a restart - see the reset test below).
    bff_server._last_relayed_message_id["10.0.0.1:5001"] = 2
    broadcast = AsyncMock()
    monkeypatch.setattr(bff_server.ws_hub, "broadcast", broadcast)
    client = FakeBffClient(responses={"/api/messages": {"messages": [{"id": 1}, {"id": 2}]}})

    await bff_server._relay_new_messages("10.0.0.1:5001", client)

    broadcast.assert_not_awaited()


@pytest.mark.asyncio
async def test_relay_new_messages_resets_watermark_after_instance_restart(monkeypatch):
    # Watermark is 50 from before a restart; the instance's message ids start
    # from 1 again (fresh message_seq), so id=1 must be treated as new, not
    # stale/already-seen.
    bff_server._last_relayed_message_id["10.0.0.1:5001"] = 50
    broadcasts = []
    monkeypatch.setattr(bff_server.ws_hub, "broadcast", AsyncMock(side_effect=lambda m: broadcasts.append(m)))
    client = FakeBffClient(responses={"/api/messages": {"messages": [{"id": 1, "message": "fresh"}]}})

    await bff_server._relay_new_messages("10.0.0.1:5001", client)

    assert broadcasts == [{
        "type": "messages",
        "target": "10.0.0.1:5001",
        "data": [{"id": 1, "message": "fresh"}],
    }]
    assert bff_server._last_relayed_message_id["10.0.0.1:5001"] == 1


@pytest.mark.asyncio
async def test_relay_new_messages_swallows_request_errors(monkeypatch):
    broadcast = AsyncMock()
    monkeypatch.setattr(bff_server.ws_hub, "broadcast", broadcast)
    client = FakeBffClient(raises=ConnectionError("refused"))

    await bff_server._relay_new_messages("10.0.0.1:5001", client)  # must not raise

    broadcast.assert_not_awaited()


# -------------------- _relay_acsi_client_list --------------------

@pytest.mark.asyncio
async def test_relay_acsi_client_list_broadcasts_on_first_seen(monkeypatch):
    broadcasts = []
    monkeypatch.setattr(bff_server.ws_hub, "broadcast", AsyncMock(side_effect=lambda m: broadcasts.append(m)))
    client = FakeBffClient(responses={
        "/api/properties": {"ok": True, "acsi_role": "ACSI-Client", "acsi_client_list": ["cp1"]}
    })

    await bff_server._relay_acsi_client_list("10.0.0.1:5002", client)

    assert broadcasts == [{
        "type": "properties",
        "target": "10.0.0.1:5002",
        "data": {"acsi_client_list": ["cp1"]},
    }]
    assert bff_server._last_relayed_client_list["10.0.0.1:5002"] == ["cp1"]


@pytest.mark.asyncio
async def test_relay_acsi_client_list_no_broadcast_when_unchanged(monkeypatch):
    bff_server._last_relayed_client_list["10.0.0.1:5002"] = ["cp1"]
    broadcast = AsyncMock()
    monkeypatch.setattr(bff_server.ws_hub, "broadcast", broadcast)
    client = FakeBffClient(responses={
        "/api/properties": {"ok": True, "acsi_client_list": ["cp1"]}
    })

    await bff_server._relay_acsi_client_list("10.0.0.1:5002", client)

    broadcast.assert_not_awaited()


@pytest.mark.asyncio
async def test_relay_acsi_client_list_broadcasts_when_a_cp_connects(monkeypatch):
    # An FSP associating with a second cp - the list grows.
    bff_server._last_relayed_client_list["10.0.0.1:5002"] = ["cp1"]
    broadcasts = []
    monkeypatch.setattr(bff_server.ws_hub, "broadcast", AsyncMock(side_effect=lambda m: broadcasts.append(m)))
    client = FakeBffClient(responses={
        "/api/properties": {"ok": True, "acsi_client_list": ["cp1", "cp2"]}
    })

    await bff_server._relay_acsi_client_list("10.0.0.1:5002", client)

    assert broadcasts[0]["data"] == {"acsi_client_list": ["cp1", "cp2"]}


@pytest.mark.asyncio
async def test_relay_acsi_client_list_broadcasts_when_a_cp_disconnects(monkeypatch):
    bff_server._last_relayed_client_list["10.0.0.1:5002"] = ["cp1", "cp2"]
    broadcasts = []
    monkeypatch.setattr(bff_server.ws_hub, "broadcast", AsyncMock(side_effect=lambda m: broadcasts.append(m)))
    client = FakeBffClient(responses={
        "/api/properties": {"ok": True, "acsi_client_list": ["cp1"]}
    })

    await bff_server._relay_acsi_client_list("10.0.0.1:5002", client)

    assert broadcasts[0]["data"] == {"acsi_client_list": ["cp1"]}


@pytest.mark.asyncio
async def test_relay_acsi_client_list_swallows_request_errors(monkeypatch):
    broadcast = AsyncMock()
    monkeypatch.setattr(bff_server.ws_hub, "broadcast", broadcast)
    client = FakeBffClient(raises=ConnectionError("refused"))

    await bff_server._relay_acsi_client_list("10.0.0.1:5002", client)  # must not raise

    broadcast.assert_not_awaited()


@pytest.mark.asyncio
async def test_relay_acsi_client_list_ignores_malformed_response(monkeypatch):
    broadcast = AsyncMock()
    monkeypatch.setattr(bff_server.ws_hub, "broadcast", broadcast)
    client = FakeBffClient(responses={"/api/properties": {"ok": True, "acsi_client_list": "not-a-list"}})

    await bff_server._relay_acsi_client_list("10.0.0.1:5002", client)

    broadcast.assert_not_awaited()


# -------------------- push_relay_loop (single cycle) --------------------

@pytest.mark.asyncio
async def test_push_relay_loop_broadcasts_connections_and_messages(monkeypatch):
    connections = [
        {"name": "fsp1", "type": "RTI-FSP", "status": "connected", "host": "10.0.0.1", "port": 5001},
    ]
    monkeypatch.setattr(bff_server.conn_manager, "connections", connections)
    monkeypatch.setitem(
        bff_server._bff_clients,
        "10.0.0.1:5001",
        FakeBffClient(responses={
            "/api/status": {"ok": True, "status": "{'status': 'listening', 'connectedClients': 1}"},
            "/api/messages": {"messages": [{"id": 1, "message": "hello"}]},
        }),
    )
    broadcasts = []
    monkeypatch.setattr(bff_server.ws_hub, "broadcast", AsyncMock(side_effect=lambda m: broadcasts.append(m)))

    # Let exactly one loop iteration run: a long sleep() means the timeout
    # below fires while the loop is parked in that sleep, after the body
    # (poll + broadcast) has already completed once.
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(bff_server.push_relay_loop(interval=10), timeout=0.2)

    types = [b["type"] for b in broadcasts]
    assert types.count("connections") == 1
    assert types.count("messages") == 1

    connections_msg = next(b for b in broadcasts if b["type"] == "connections")
    assert connections_msg["data"][0]["connectedClients"] == 1

    messages_msg = next(b for b in broadcasts if b["type"] == "messages")
    assert messages_msg == {
        "type": "messages",
        "target": "10.0.0.1:5001",
        "data": [{"id": 1, "message": "hello"}],
    }


@pytest.mark.asyncio
async def test_push_relay_loop_broadcasts_acsi_client_list_for_so_targets(monkeypatch):
    connections = [
        {"name": "fsp1", "type": "RTI-FSP", "status": "connected", "host": "10.0.0.1", "port": 5001},
        {"name": "so1", "type": "RTI-SO", "status": "connected", "host": "10.0.0.2", "port": 5002},
    ]
    monkeypatch.setattr(bff_server.conn_manager, "connections", connections)
    monkeypatch.setitem(
        bff_server._bff_clients,
        "10.0.0.1:5001",
        FakeBffClient(responses={
            "/api/status": {"ok": True, "status": "{'status': 'listening', 'connectedClients': 1}"},
            "/api/messages": {"messages": []},
        }),
    )
    monkeypatch.setitem(
        bff_server._bff_clients,
        "10.0.0.2:5002",
        FakeBffClient(responses={"/api/properties": {"ok": True, "acsi_client_list": ["cp1"]}}),
    )
    broadcasts = []
    monkeypatch.setattr(bff_server.ws_hub, "broadcast", AsyncMock(side_effect=lambda m: broadcasts.append(m)))

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(bff_server.push_relay_loop(interval=10), timeout=0.2)

    properties_msg = next(b for b in broadcasts if b["type"] == "properties")
    assert properties_msg == {
        "type": "properties",
        "target": "10.0.0.2:5002",
        "data": {"acsi_client_list": ["cp1"]},
    }
    # The FSP target only gets a "messages" relay, not "properties" - this
    # push type is RTI-SO-only (acsi_client_list is a WS-Passive/ACSI-Client
    # concept; an FSP has no equivalent list to relay).
    assert not any(b["type"] == "properties" and b["target"] == "10.0.0.1:5001" for b in broadcasts)


@pytest.mark.asyncio
async def test_push_relay_loop_skips_unchanged_connections_snapshot(monkeypatch):
    # A target that never changes (e.g. no connections configured at all)
    # shouldn't cause a "connections" broadcast on every single cycle.
    monkeypatch.setattr(bff_server.conn_manager, "connections", [])
    broadcasts = []
    monkeypatch.setattr(bff_server.ws_hub, "broadcast", AsyncMock(side_effect=lambda m: broadcasts.append(m)))

    async def run_two_cycles():
        task = asyncio.ensure_future(bff_server.push_relay_loop(interval=0.01))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    await run_two_cycles()

    assert [b["type"] for b in broadcasts].count("connections") == 1


# -------------------- /ws endpoint wiring --------------------

def test_ws_endpoint_registers_and_unregisters_client():
    # Plain TestClient (no "with" block) never triggers the app's lifespan,
    # so push_relay_loop's background task is not started here - this test
    # exercises only the /ws route's accept/register/unregister wiring.
    from fastapi.testclient import TestClient

    client = TestClient(bff_server.app)
    assert len(bff_server.ws_hub._clients) == 0

    with client.websocket_connect("/ws") as _ws:
        assert len(bff_server.ws_hub._clients) == 1

    assert len(bff_server.ws_hub._clients) == 0
