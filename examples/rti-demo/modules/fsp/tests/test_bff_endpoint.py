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

"""Unit tests for FSP BFF endpoint routes.

fsp.bff_endpoint is a FastAPI router (create_bff_router), mounted under
the "/api" prefix - not the Flask blueprint this file originally tested
against. Routes are flat (e.g. "/api/status", not
"/api/iec61850server/status").
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# bff_endpoint.py reads IO_PLUGIN_STORAGE at import time and defaults to
# "/app/io_plugin_dynamic" (a Docker-only path) - unwritable outside a
# container, so create_bff_router() below would fail on every test. Point it
# at a throwaway temp dir before the import, same as the env var is meant to
# be used for any non-Docker deployment.
os.environ.setdefault("IO_PLUGIN_STORAGE", tempfile.mkdtemp(prefix="io_plugin_dynamic_"))

from fsp import bff_endpoint  # noqa: E402 - must follow the env var default above

pytestmark = pytest.mark.unit


@pytest.fixture
def client_and_server(tmp_path: Path):
    (tmp_path / "model.py").write_text(
        "from ws61850.iec61850.data_model.ied_model import IedModel\n"
        "ied = IedModel(name='TestIED')\n",
        encoding="utf-8",
    )
    app = FastAPI()
    router, server = bff_endpoint.create_bff_router(tmp_path)
    app.include_router(router)
    return TestClient(app), server


def test_status_returns_server_status(client_and_server):
    client, server = client_and_server
    server.get_status = lambda: {
        "status": "stopped",
        "host": "localhost",
        "port": 8765,
        "error": None,
        "connectedClients": 0,
        "tasks": {},
        "accessPoints": ["cp1"],
    }

    response = client.get("/api/status")

    assert response.status_code == 200
    # The route wraps get_status()'s dict as a str() repr in the "status"
    # field - see fsp/acsi_server.py get_status()/api_status().
    body = response.json()
    assert body["ok"] is True
    assert "'status': 'stopped'" in body["status"]
    assert "'port': 8765" in body["status"]


def test_start_rejects_unsupported_mode(client_and_server):
    client, _ = client_and_server

    response = client.post(
        "/api/start",
        json={"mode": "passive", "host": "localhost", "port": "8765"},
    )

    assert response.status_code == 400
    assert "Only 'active' mode is supported" in response.json()["error"]


def test_start_rejects_invalid_port(client_and_server):
    client, _ = client_and_server

    response = client.post(
        "/api/start",
        json={"mode": "active", "host": "localhost", "port": "bad"},
    )

    assert response.status_code == 400
    assert "Invalid port value" in response.json()["error"]


def test_start_calls_server_and_updates_cp(client_and_server):
    client, server = client_and_server

    called = {}

    def fake_start(host: str, port: int) -> None:
        called["host"] = host
        called["port"] = port

    server.start_server = fake_start

    response = client.post(
        "/api/start",
        json={"mode": "active", "host": "127.0.0.1", "port": "9000", "cp": "cp2"},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert called == {"host": "127.0.0.1", "port": 9000}
    assert server.runtime.cp == "cp2"


def test_stop_returns_stopped_when_already_stopped(client_and_server):
    client, server = client_and_server
    server.runtime.status = "stopped"

    response = client.post("/api/stop")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "status": "stopped"}


def test_readvalue_requires_objref(client_and_server):
    client, server = client_and_server
    server.runtime.server = object()

    # objRef is a required field on ReadvalueRequest, so omitting it entirely
    # is rejected by FastAPI's own request validation (422) before the
    # handler runs - send an empty string instead, which is schema-valid and
    # actually exercises the handler's own `if not obj_ref` check below.
    response = client.post("/api/readvalue", json={"objRef": "", "fc": "mx"})

    assert response.status_code == 400
    assert response.json()["error"] == "objRef is required"


def test_readvalue_rejects_when_server_not_running(client_and_server):
    client, server = client_and_server
    server.runtime.server = None

    response = client.post("/api/readvalue", json={"objRef": "LD0/LLN0.Mod.stVal"})

    assert response.status_code == 503
    assert response.json()["error"] == "Server is not running"


def test_readvalue_success_wraps_single_value(client_and_server):
    client, server = client_and_server
    server.runtime.server = object()
    server.read_value = lambda _obj_ref: {"type": "boolean", "value": True}

    response = client.post(
        "/api/readvalue",
        json={"objRef": "LD0/LLN0.Mod.stVal", "fc": "st"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["success"] is True
    # Unlike the client-side (SO) readvalue route, the server side returns
    # the single value dict directly under "values", not wrapped in a list.
    assert body["values"] == {"type": "boolean", "value": True}


def test_writevalue_requires_value(client_and_server):
    client, server = client_and_server
    server.runtime.server = object()

    # WritevalueRequest.value is a required, non-nullable `str` field, so a
    # request missing it is rejected by FastAPI's own request validation
    # (422) before the handler's own `if value is None` check can run - that
    # check is unreachable through the API as currently typed. This asserts
    # the actual current behavior: still rejected, just at the request-
    # validation layer rather than with the handler's custom error message.
    response = client.post(
        "/api/writevalue",
        json={"objRef": "LD0/LLN0.Mod.stVal", "fc": "st"},
    )

    assert response.status_code == 422


def test_writevalue_success_response(client_and_server):
    client, server = client_and_server
    server.runtime.server = object()

    def fake_write(obj_ref: str, value, data_type: str = "unknown"):
        return {
            "objRef": obj_ref,
            "value": value,
            "dataType": data_type,
        }

    server.write_value = fake_write

    response = client.post(
        "/api/writevalue",
        # value is typed as `str` on WritevalueRequest ("value to write as
        # string representation") - pydantic v2 doesn't coerce an int here.
        json={
            "objRef": "LD0/LLN0.Mod.stVal",
            "fc": "st",
            "value": "1",
            "dataType": "int32",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["success"] is True
    assert body["objRef"] == "LD0/LLN0.Mod.stVal"
    assert body["value"] == "1"
    assert body["dataType"] == "int32"


def test_update_iedmodel_requires_model_py(client_and_server):
    client, _ = client_and_server

    response = client.post("/api/update-iedmodel", json={"modelPy": ""})

    assert response.status_code == 400
    assert "modelPy is required" in response.json()["error"]


def test_update_iedmodel_success(client_and_server):
    client, server = client_and_server

    class _FakeIed:
        name = "UpdatedIED"

    server.update_model_file = lambda _content, apply_dynamically=True: _FakeIed()

    response = client.post(
        "/api/update-iedmodel",
        json={"modelPy": "from ws61850.iec61850.data_model.ied_model import IedModel\nied = IedModel(name='UpdatedIED')\n"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["ied"] == "UpdatedIED"


def test_connections_returns_server_info_when_no_clients(client_and_server):
    client, server = client_and_server
    server.runtime.endpoint = None

    response = client.get("/api/connections")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["role"] == "ACSI-Server"
    assert body["ws_mode"] == "active"
    assert body["connected_servers"] == 0
    assert body["connections"] == []


def test_connections_extracts_client_tpa_info(client_and_server):
    client, server = client_and_server

    class _FakeWebSocketInfo:
        def __init__(self):
            self.remote_address = ("192.168.1.100", 54321)

    class _FakeEndpoint:
        pass

    fake_endpoint = _FakeEndpoint()
    fake_endpoint.websocket_info_list = [_FakeWebSocketInfo()]
    server.runtime.endpoint = fake_endpoint

    response = client.get("/api/connections")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["connected_servers"] == 1
    assert len(body["connections"]) == 1

    conn = body["connections"][0]
    assert conn["peer_address"] == "192.168.1.100"
    assert conn["peer_port"] == 54321
    assert conn["role"] == "ACSI-Server"
    assert conn["ws_mode"] == "active"
    assert conn["status"] == "active"


def test_connections_marks_disconnected_clients(client_and_server):
    client, server = client_and_server

    class _FakeWebSocketInfo:
        def __init__(self, connected=True):
            self.remote_address = ("192.168.1.100", 54321)
            self.connected = connected

    class _FakeEndpoint:
        pass

    fake_endpoint = _FakeEndpoint()
    fake_endpoint.websocket_info_list = [
        _FakeWebSocketInfo(connected=True),
        _FakeWebSocketInfo(connected=False),
    ]

    server.runtime.endpoint = fake_endpoint
    response = client.get("/api/connections")

    assert response.status_code == 200
    body = response.json()
    assert body["connected_servers"] == 2

    assert body["connections"][0]["status"] == "active"
    assert body["connections"][1]["status"] == "disconnected"


def test_apis_lists_registered_routes(client_and_server):
    """Regression test: route.path on a route added through a prefixed
    APIRouter (here, prefix="/api") is already the full path, so this
    handler's `f"/api{route.path}"` used to double it into
    "/api/api/status" etc. instead of listing the real paths."""
    client, _ = client_and_server

    response = client.get("/api/apis")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["count"] > 0
    paths = {e["path"] for e in body["endpoints"]}
    assert "/api/status" in paths
    assert "/api/readvalue" in paths


def test_fsp_properties(client_and_server):
    """GET /api/properties should return the FSP's fixed role/ws_mode."""
    client, _ = client_and_server

    response = client.get("/api/properties")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["acsi_role"] == "ACSI-Server"
    assert body["ws_mode"] == "Active"
