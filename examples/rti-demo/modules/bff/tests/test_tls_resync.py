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

"""Unit tests for keeping stored TLS settings across SO/FSP restarts.

RTI-SO and RTI-FSP only hold TLS in memory, so a container restart brings
them back as plain WS while connections.json still says TLS is on. Covers:
- ConnectionManager.sync_runtime_tls() re-applying a passive (RTI-SO)
  connection's stored TLS config when its runtime doesn't match.
- /api/execute enriching an RTI-FSP /start request with its stored TLS
  config, so the dial-out comes back up with TLS.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_tmp_connections_file = Path(tempfile.mkdtemp()) / "connections.json"
_tmp_connections_file.write_text("[]", encoding="utf-8")
os.environ.setdefault("BFF_CONNECTIONS_FILE", str(_tmp_connections_file))

from bff import bff_server  # noqa: E402 - must follow the env var default above
from bff.ConnectionManager import ConnectionManager  # noqa: E402

pytestmark = pytest.mark.unit

STORED_SO_TLS = {
    "enable_tls": True,
    "tls_version": "TLSv1_3",
    "server_key": "KEY-PEM",
    "server_cert": "CERT-PEM",
    "server_ca": None,
}


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class _FakeClient:
    """Stands in for the shared httpx.AsyncClient: serves a fixed runtime
    /api/tls-config and records every /api/reconfig-connection POST."""

    def __init__(self, runtime, reconfig_status=200):
        self.runtime = runtime
        self.reconfig_status = reconfig_status
        self.posts = []

    async def get(self, url, **kwargs):
        assert url == "http://rti-so:5002/api/tls-config"
        return _Response(self.runtime)

    async def post(self, url, json=None, **kwargs):
        self.posts.append((url, json))
        ok = self.reconfig_status < 400
        return _Response({"ok": ok}, status_code=self.reconfig_status)


def _manager(tmp_path):
    return ConnectionManager(
        bff_clients={},
        connections_file=str(tmp_path / "connections.json"),
        logger=bff_server.logger,
    )


def _so(tls=STORED_SO_TLS, status="connected"):
    return {
        "name": "SO",
        "host": "rti-so",
        "port": 5002,
        "type": "RTI-SO",
        "ws_mode": "passive",
        "status": status,
        "TLS": dict(tls) if tls is not None else None,
    }


def _runtime(enable_tls, tls_version="1.2", server_cert=None):
    return {
        "ok": True,
        "enable_tls": enable_tls,
        "tls_version": tls_version,
        "server_key": "KEY-PEM" if enable_tls else None,
        "server_cert": server_cert,
        "server_ca": None,
        "ws_mode": "passive",
    }


async def test_reapplies_stored_tls_after_so_restart(tmp_path):
    client = _FakeClient(_runtime(False))

    await _manager(tmp_path).sync_runtime_tls(_so(), client)

    assert client.posts == [
        (
            "http://rti-so:5002/api/reconfig-connection",
            {
                "connection_name": "SO",
                "enable_tls": True,
                "tls_version": "TLSv1_3",
                "server_key": "KEY-PEM",
                "server_cert": "CERT-PEM",
                "server_ca": None,
                "ws_mode": "passive",
            },
        )
    ]


async def test_reapplies_when_only_the_tls_version_differs(tmp_path):
    client = _FakeClient(_runtime(True, "1.2", "CERT-PEM"))

    await _manager(tmp_path).sync_runtime_tls(_so(), client)

    assert len(client.posts) == 1


async def test_leaves_a_matching_runtime_alone(tmp_path):
    client = _FakeClient(_runtime(True, "1.3", "CERT-PEM"))

    await _manager(tmp_path).sync_runtime_tls(_so(), client)

    assert client.posts == []


async def test_ignores_connections_without_stored_tls_or_not_connected(tmp_path):
    manager = _manager(tmp_path)
    client = _FakeClient(_runtime(False))

    await manager.sync_runtime_tls(_so(tls=None), client)
    await manager.sync_runtime_tls(_so(status="disconnected"), client)
    fsp = {**_so(), "name": "FSP01", "type": "RTI-FSP", "ws_mode": "active"}
    await manager.sync_runtime_tls(fsp, client)

    assert client.posts == []


async def test_backs_off_after_a_failed_reapply(tmp_path):
    # A bad stored cert would otherwise restart the SO's listener on every
    # 10 s status poll.
    manager = _manager(tmp_path)
    client = _FakeClient(_runtime(False), reconfig_status=500)

    await manager.sync_runtime_tls(_so(), client)
    await manager.sync_runtime_tls(_so(), client)

    assert len(client.posts) == 1


# -------------------- /api/execute enrichment of FSP /start --------------------


def test_execute_start_adds_stored_fsp_tls(monkeypatch):
    fsp = {
        "name": "FSP01",
        "host": "rti-fsp01",
        "port": 5001,
        "type": "RTI-FSP",
        "ws_mode": "active",
        "TLS": {
            "enable_tls": True,
            "tls_version": "TLSv1_3",
            "server_key": None,
            "server_cert": None,
            "server_ca": "CA-PEM",
        },
    }
    monkeypatch.setattr(bff_server.conn_manager, "connections", [fsp])
    sent = {}

    class _Client:
        def request(self, method, path, json=None):
            sent.update(method=method, path=path, json=json)
            return {"ok": True}

    monkeypatch.setitem(bff_server._bff_clients, "rti-fsp01:5001", _Client())

    from fastapi.testclient import TestClient

    response = TestClient(bff_server.app).post(
        "/api/execute",
        json={
            "target": "rti-fsp01:5001",
            "method": "POST",
            "path": "/api/start",
            "body": {"host": "rti-so", "port": "8765", "mode": "active", "cp": "cp1"},
        },
    )

    assert response.status_code == 200
    assert sent["json"] == {
        "host": "rti-so",
        "port": "8765",
        "mode": "active",
        "cp": "cp1",
        "enable_tls": True,
        "tls_version": "TLSv1_3",
        "server_ca": "CA-PEM",
    }
