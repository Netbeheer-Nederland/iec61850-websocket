# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
#
# Copyright 2025 Netbeheer Nederland
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unit tests for the RTI-SO ws_port connection field.

An RTI-SO connection needs two distinct ports: the BFF server's own port
(`host`/`port` - used for all /api/execute proxying to that instance) and
the port its WebSocket (Passive) endpoint listens on (`ws_port`). Before
this, only one port was modeled, and it was ambiguous/wrong which one a
consumer (e.g. the FSP page's "Start Server" dial-out target) was actually
supposed to use.

Covers two layers:
- ConnectionManager.add_connection() storing/updating ws_port, using a
  fresh, fully isolated ConnectionManager instance (not the module-level
  singleton bff_server.py constructs at import time).
- The /api/add-connection and /api/edit-connection HTTP endpoints
  round-tripping ws_port through ConnectionCreateRequest/
  ConnectionUpdateRequest, via a FastAPI TestClient against the real app -
  with the module-level `conn_manager.connections` reset around each test
  so this file doesn't depend on, or leak into, other test files sharing
  the same bff_server module.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from unittest.mock import AsyncMock

_tmp_connections_file = Path(tempfile.mkdtemp()) / "connections.json"
_tmp_connections_file.write_text("[]", encoding="utf-8")
os.environ.setdefault("BFF_CONNECTIONS_FILE", str(_tmp_connections_file))

from bff import bff_server  # noqa: E402 - must follow the env var default above
from bff.ConnectionManager import ConnectionManager  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _isolated_connections(monkeypatch):
    """Reset the shared module-level connections list around every test in
    this file, regardless of what other test files sharing bff_server.py
    left it as."""
    monkeypatch.setattr(bff_server.conn_manager, "connections", [])
    yield


def _fresh_manager(tmp_path):
    """A ConnectionManager with its own isolated connections.json, entirely
    separate from bff_server.py's module-level singleton."""
    return ConnectionManager(
        bff_clients={},
        connections_file=str(tmp_path / "connections.json"),
        logger=bff_server.logger,
    )


# -------------------- ConnectionManager.add_connection --------------------

def test_add_connection_stores_ws_port_for_new_connection(tmp_path):
    manager = _fresh_manager(tmp_path)

    conn = manager.add_connection(
        name="so1", host="127.0.0.1", port=5002, conn_type="RTI-SO",
        acsi="client", ws_mode="passive", ws_port=8765,
    )

    assert conn["port"] == 5002
    assert conn["ws_port"] == 8765


def test_add_connection_defaults_ws_port_to_none_when_not_given(tmp_path):
    manager = _fresh_manager(tmp_path)

    conn = manager.add_connection(
        name="so1", host="127.0.0.1", port=5002, conn_type="RTI-SO",
        acsi="client", ws_mode="passive",
    )

    assert conn["port"] == 5002
    assert conn.get("ws_port") is None


def test_add_connection_updates_ws_port_on_existing_connection_by_name(tmp_path):
    manager = _fresh_manager(tmp_path)
    manager.add_connection(
        name="so1", host="127.0.0.1", port=5002, conn_type="RTI-SO",
        acsi="client", ws_mode="passive", ws_port=8765,
    )

    # add_connection() short-circuits as a no-op when name+host+port all
    # already match an existing connection, so the port has to actually
    # change here to take the "update existing connection by name" branch
    # rather than the "already exists" early return.
    updated = manager.add_connection(
        name="so1", host="127.0.0.1", port=5003, conn_type="RTI-SO",
        acsi="client", ws_mode="passive", ws_port=9000,
    )

    assert updated["port"] == 5003
    assert updated["ws_port"] == 9000
    assert len(manager.connections) == 1  # updated in place, not duplicated


def test_add_connection_ws_port_is_independent_of_bff_port(tmp_path):
    # The two ports must never collapse into each other: the BFF port stays
    # whatever it was even as ws_port changes, and vice versa.
    manager = _fresh_manager(tmp_path)
    manager.add_connection(
        name="so1", host="127.0.0.1", port=5002, conn_type="RTI-SO",
        acsi="client", ws_mode="passive", ws_port=8765,
    )

    updated = manager.add_connection(
        name="so1", host="127.0.0.1", port=5555, conn_type="RTI-SO",
        acsi="client", ws_mode="passive",
    )

    assert updated["port"] == 5555
    assert updated["ws_port"] == 8765  # untouched - ws_port wasn't passed this time


# -------------------- HTTP layer: create/update connection --------------------

def test_create_connection_endpoint_stores_ws_port(monkeypatch):
    from fastapi.testclient import TestClient

    # create_connection() probes the new connection for real after saving it
    # (conn_manager.check_connection, via a cached httpx.AsyncClient bound to
    # whichever event loop first created it) - irrelevant to what this test
    # verifies, and flaky across separate TestClient instances/event loops,
    # so stub it out.
    monkeypatch.setattr(bff_server.conn_manager, "check_connection", AsyncMock())

    client = TestClient(bff_server.app)
    response = client.post("/api/add-connection", json={
        "name": "so-http-1",
        "host": "127.0.0.1",
        "port": 5002,
        "ws_port": 8765,
        "type": "RTI-SO",
        "acsi": "client",
        "ws_mode": "passive",
    })

    assert response.status_code == 201
    body = response.json()
    assert body["port"] == 5002
    assert body["ws_port"] == 8765


def test_update_connection_endpoint_updates_ws_port_independently(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(bff_server.conn_manager, "check_connection", AsyncMock())

    client = TestClient(bff_server.app)
    create_resp = client.post("/api/add-connection", json={
        "name": "so-http-2",
        "host": "127.0.0.1",
        "port": 5002,
        "ws_port": 8765,
        "type": "RTI-SO",
        "acsi": "client",
        "ws_mode": "passive",
    })
    assert create_resp.status_code == 201

    update_resp = client.put("/api/edit-connection/so-http-2", json={"ws_port": 9000})

    assert update_resp.status_code == 200
    body = update_resp.json()
    assert body["ws_port"] == 9000
    assert body["port"] == 5002  # BFF port untouched by a ws_port-only update
