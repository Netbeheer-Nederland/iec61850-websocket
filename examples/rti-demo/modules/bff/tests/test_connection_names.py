# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""Connection names are unique: they are how a connection is found (edit,
delete, TLS/OAuth settings, the push). Adding or renaming to a name another
connection has is refused (409), never overwrites or duplicates it; a delete
removes exactly one connection; and an instance's HTTP client stays while
another connection still names it."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

_tmp_connections_file = Path(tempfile.mkdtemp()) / "connections.json"
_tmp_connections_file.write_text("[]", encoding="utf-8")
os.environ.setdefault("BFF_CONNECTIONS_FILE", str(_tmp_connections_file))

from bff import bff_server  # noqa: E402 - must follow the env var default above
from bff.connection_manager import (  # noqa: E402
    ConnectionConflictError,
    ConnectionManager,
)
from fastapi.testclient import TestClient  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture
def client(monkeypatch):
    """The BFF's routes on an empty connection list, with no real probes."""
    monkeypatch.setattr(bff_server.conn_manager, "connections", [])
    monkeypatch.setattr(bff_server.conn_manager, "check_connection", AsyncMock())
    clients = {}
    monkeypatch.setattr(bff_server.conn_manager, "_bff_clients", clients)
    monkeypatch.setattr(bff_server, "_bff_clients", clients)
    return TestClient(bff_server.app)


def add(client, name, host="127.0.0.1", port=5001, type_="RTI-FSP"):
    return client.post(
        "/api/add-connection",
        json={"name": name, "host": host, "port": port, "type": type_},
    )


def names():
    return [c["name"] for c in bff_server.conn_manager.connections]


def _manager(tmp_path, connections=None):
    if connections is not None:
        (tmp_path / "connections.json").write_text(json.dumps(connections))
    return ConnectionManager(
        bff_clients={},
        connections_file=str(tmp_path / "connections.json"),
        logger=bff_server.logger,
    )


# -------------------- add --------------------


def test_adding_a_name_another_connection_has_is_refused(client):
    assert add(client, "A", port=1).status_code == 201

    response = add(client, "A", host="10.0.0.9", port=9)

    assert response.status_code == 409
    assert "already exists" in response.json()["error"]
    # Not overwritten.
    [a] = bff_server.conn_manager.connections
    assert (a["host"], a["port"]) == ("127.0.0.1", 1)


@pytest.mark.parametrize("other", ["a", " A ", "a "])
def test_names_differing_only_in_case_or_spaces_are_the_same(client, other):
    add(client, "A", port=1)
    assert add(client, other, port=2).status_code == 409
    assert names() == ["A"]


def test_registering_the_same_connection_again_changes_nothing(client):
    first = add(client, "A", port=1).json()

    again = add(client, "A", port=1)

    assert again.status_code == 200
    assert again.json()["id"] == first["id"]
    assert names() == ["A"]


def test_a_name_is_stored_without_surrounding_spaces(client):
    assert add(client, "  B  ", port=2).json()["name"] == "B"


def test_an_empty_name_is_refused(client):
    assert add(client, "   ", port=2).status_code == 400
    assert names() == []


# -------------------- rename --------------------


def test_renaming_to_a_name_another_connection_has_is_refused(client):
    add(client, "B", port=2)
    add(client, "C", port=3)

    response = client.put("/api/edit-connection/C", json={"name": "b", "port": 4})

    assert response.status_code == 409
    # Nothing of the edit is applied.
    assert names() == ["B", "C"]
    assert bff_server.conn_manager.get_connection("C")["port"] == 3


def test_a_connection_can_keep_or_recase_its_own_name(client):
    add(client, "C", port=3)
    assert client.put("/api/edit-connection/C", json={"name": "C"}).status_code == 200
    assert client.put("/api/edit-connection/C", json={"name": "c"}).status_code == 200
    assert names() == ["c"]


def test_a_name_with_special_characters_can_be_edited_and_deleted(client):
    add(client, "FSP 01/a?b#c", port=3)

    path = "FSP%2001%2Fa%3Fb%23c"
    assert (
        client.put(f"/api/edit-connection/{path}", json={"port": 4}).status_code == 200
    )
    assert client.delete(f"/api/delete-connection/{path}").status_code == 200
    assert names() == []


# -------------------- delete and clients --------------------


def test_delete_removes_exactly_one_connection(tmp_path):
    # Two connections named alike can only come from an old file; the load
    # keeps the first, so build the list directly.
    manager = _manager(tmp_path)
    manager.connections = [
        {"id": "1", "name": "B", "host": "h", "port": 1},
        {"id": "2", "name": "B", "host": "h", "port": 2},
    ]

    assert manager.delete_connection("B") is True

    assert [c["id"] for c in manager.connections] == ["2"]


def test_a_shared_client_stays_while_another_connection_uses_it(client):
    add(client, "B", port=2)
    add(client, "C", port=2)  # the same instance, under another name
    assert "127.0.0.1:2" in bff_server._bff_clients

    client.delete("/api/delete-connection/C")
    assert "127.0.0.1:2" in bff_server._bff_clients

    client.put("/api/edit-connection/B", json={"port": 5})
    assert "127.0.0.1:2" not in bff_server._bff_clients
    assert "127.0.0.1:5" in bff_server._bff_clients


def test_moving_one_of_two_connections_keeps_the_other_s_client(client):
    add(client, "B", port=2)
    add(client, "C", port=2)

    client.put("/api/edit-connection/C", json={"port": 3})

    assert {"127.0.0.1:2", "127.0.0.1:3"} <= set(bff_server._bff_clients)


# -------------------- load and discovery --------------------


def test_a_repeated_name_in_the_file_is_dropped_on_load(tmp_path):
    manager = _manager(
        tmp_path,
        [
            {"name": "FSP01", "host": "h", "port": 1},
            {"name": "fsp01 ", "host": "h", "port": 2},
            {"name": "", "host": "h", "port": 3},
            {"name": "SO", "host": "h", "port": 4},
        ],
    )

    assert [(c["name"], c["port"]) for c in manager.connections] == [
        ("FSP01", 1),
        ("SO", 4),
    ]
    saved = json.loads((tmp_path / "connections.json").read_text())
    assert [c["name"] for c in saved] == ["FSP01", "SO"]


def test_discovery_does_not_take_over_a_name(tmp_path):
    manager = _manager(tmp_path)
    manager.add_connection(name="FSP01", host="h", port=1, conn_type="RTI-FSP")

    registered = manager.auto_register_discovered(
        {"x": {"name": "FSP01", "host": "other", "port": 9, "type": "RTI-FSP"}}
    )

    assert registered == 0
    [con] = manager.connections
    assert (con["host"], con["port"]) == ("h", 1)


def test_claim_name_refuses_another_connection_s_name(tmp_path):
    manager = _manager(tmp_path)
    a = manager.add_connection(name="A", host="h", port=1, conn_type="RTI-FSP")
    manager.add_connection(name="B", host="h", port=2, conn_type="RTI-FSP")

    assert manager.claim_name(" a ", a) == "a"
    with pytest.raises(ConnectionConflictError):
        manager.claim_name("b", a)
