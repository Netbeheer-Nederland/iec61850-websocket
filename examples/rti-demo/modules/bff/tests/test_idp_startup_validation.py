# SPDX-FileCopyrightText: 2025-2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
#
# Copyright 2025-2026 Netbeheer Nederland
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

"""Unit tests for ConnectionManager.validate_idp_server_on_start().

On startup the BFF checks the most recently added IDP-Server connection; if
it isn't reachable, OAuth2 is disabled on every connection that authenticates
against it (``OAuth.idp_server`` matching its name), so they stop trying - and
failing - to fetch tokens/JWKS from an IDP that isn't there.

check_connection()'s own IDP-Server reachability probe opens its own httpx
client internally (unlike sync_runtime_tls/sync_runtime_oauth, which take one
as an argument), so these tests monkeypatch check_connection() itself to
control the resulting status - this file tests validate_idp_server_on_start()'s
own orchestration (which IDP-Server counts as "latest", what gets disabled and
persisted), not check_connection()'s network behavior.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

_tmp_connections_file = Path(tempfile.mkdtemp()) / "connections.json"
_tmp_connections_file.write_text("[]", encoding="utf-8")
os.environ.setdefault("BFF_CONNECTIONS_FILE", str(_tmp_connections_file))

from bff import bff_server  # noqa: E402 - must follow the env var default above
from bff.connection_manager import ConnectionManager  # noqa: E402

pytestmark = pytest.mark.unit


def _manager(tmp_path, connections):
    manager = ConnectionManager(
        bff_clients={},
        connections_file=str(tmp_path / "connections.json"),
        logger=bff_server.logger,
    )
    manager.connections = connections
    return manager


def _idp(id_, name="IDP", status=None):
    con = {
        "id": id_,
        "name": name,
        "type": "IDP-Server",
        "endpoint": "http://keycloak:8080",
    }
    if status is not None:
        con["status"] = status
    return con


def _so(name, idp_server, enable_oauth):
    return {
        "id": 100,
        "name": name,
        "type": "RTI-SO",
        "OAuth": {"idp_server": idp_server, "enable_oauth": enable_oauth},
    }


def _fake_check_connection(status):
    """A check_connection() replacement that just stamps the given status."""

    async def check_connection(self, con, client):
        con["status"] = status

    return check_connection


async def test_no_idp_server_is_a_noop(tmp_path, monkeypatch):
    called = False

    async def check_connection(self, con, client):
        nonlocal called
        called = True

    monkeypatch.setattr(ConnectionManager, "check_connection", check_connection)
    manager = _manager(tmp_path, [_so("SO", "IDP", True)])

    await manager.validate_idp_server_on_start()

    assert called is False
    assert manager.connections[0]["OAuth"]["enable_oauth"] is True


async def test_active_idp_server_leaves_oauth_alone(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ConnectionManager, "check_connection", _fake_check_connection("connected")
    )
    manager = _manager(tmp_path, [_idp(1), _so("SO", "IDP", True)])

    await manager.validate_idp_server_on_start()

    assert manager.connections[1]["OAuth"]["enable_oauth"] is True


async def test_inactive_idp_server_disables_dependent_oauth(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ConnectionManager, "check_connection", _fake_check_connection("disconnected")
    )
    manager = _manager(
        tmp_path,
        [_idp(1), _so("SO", "IDP", True), _so("FSP01", "IDP", True)],
    )

    await manager.validate_idp_server_on_start()

    assert manager.connections[1]["OAuth"]["enable_oauth"] is False
    assert manager.connections[2]["OAuth"]["enable_oauth"] is False

    # Persisted, not just updated in memory.
    saved = json.loads(Path(manager.connections_file).read_text())
    saved_by_name = {c["name"]: c for c in saved}
    assert saved_by_name["SO"]["OAuth"]["enable_oauth"] is False
    assert saved_by_name["FSP01"]["OAuth"]["enable_oauth"] is False


async def test_inactive_idp_server_leaves_unrelated_oauth_alone(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ConnectionManager, "check_connection", _fake_check_connection("disconnected")
    )
    manager = _manager(
        tmp_path,
        [_idp(1, name="IDP"), _so("SO", "OtherIDP", True)],
    )

    await manager.validate_idp_server_on_start()

    assert manager.connections[1]["OAuth"]["enable_oauth"] is True


async def test_inactive_idp_server_leaves_already_disabled_oauth_alone(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        ConnectionManager, "check_connection", _fake_check_connection("disconnected")
    )
    manager = _manager(tmp_path, [_idp(1), _so("SO", "IDP", False)])

    await manager.validate_idp_server_on_start()

    # Nothing changed, so nothing should have been (re)written to disk.
    assert not Path(manager.connections_file).exists()


async def test_only_the_latest_idp_server_is_checked(tmp_path, monkeypatch):
    checked = []

    async def check_connection(self, con, client):
        checked.append(con["name"])
        con["status"] = "disconnected"

    monkeypatch.setattr(ConnectionManager, "check_connection", check_connection)
    manager = _manager(
        tmp_path,
        [
            _idp(1, name="OldIDP"),
            _idp(2, name="NewIDP"),
            _so("SO", "NewIDP", True),
            _so("FSP01", "OldIDP", True),
        ],
    )

    await manager.validate_idp_server_on_start()

    assert checked == ["NewIDP"]
    # Only the connection tied to the checked (latest) IDP-Server is touched.
    assert manager.connections[2]["OAuth"]["enable_oauth"] is False
    assert manager.connections[3]["OAuth"]["enable_oauth"] is True
