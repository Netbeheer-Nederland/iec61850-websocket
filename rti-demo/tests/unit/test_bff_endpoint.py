"""Unit tests for FSP BFF endpoint routes."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from flask import Flask

# Allow importing rti-demo/fsp modules as top-level modules.
FSP_DIR = Path(__file__).resolve().parents[2] / "fsp"
if str(FSP_DIR) not in sys.path:
    sys.path.insert(0, str(FSP_DIR))

import bff_endpoint


pytestmark = pytest.mark.unit


@pytest.fixture
def client_and_server(tmp_path: Path):
    (tmp_path / "model.py").write_text(
        "from ws61850.iec61850.data_model.ied_model import IedModel\n"
        "ied = IedModel(name='TestIED')\n",
        encoding="utf-8",
    )
    app = Flask(__name__)
    blueprint, server = bff_endpoint.create_bff_blueprint(tmp_path)
    app.register_blueprint(blueprint)
    return app.test_client(), server


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

    response = client.get("/api/iec61850server/status")

    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "stopped"
    assert body["port"] == 8765


def test_start_rejects_unsupported_mode(client_and_server):
    client, _ = client_and_server

    response = client.post(
        "/api/iec61850server/start",
        json={"mode": "client", "host": "localhost", "port": 8765},
    )

    assert response.status_code == 400
    assert "Only 'server' mode is supported" in response.get_json()["error"]


def test_start_rejects_invalid_port(client_and_server):
    client, _ = client_and_server

    response = client.post(
        "/api/iec61850server/start",
        json={"mode": "server", "host": "localhost", "port": "bad"},
    )

    assert response.status_code == 400
    assert "Invalid port value" in response.get_json()["error"]


def test_start_calls_server_and_updates_cp(client_and_server):
    client, server = client_and_server

    called = {}

    def fake_start(host: str, port: int) -> None:
        called["host"] = host
        called["port"] = port

    server.start_server = fake_start

    response = client.post(
        "/api/iec61850server/start",
        json={"mode": "server", "host": "127.0.0.1", "port": 9000, "cp": "cp2"},
    )

    assert response.status_code == 200
    assert response.get_json()["ok"] is True
    assert called == {"host": "127.0.0.1", "port": 9000}
    assert server.runtime.cp == "cp2"


def test_stop_returns_stopped_when_already_stopped(client_and_server):
    client, server = client_and_server
    server.runtime.status = "stopped"

    response = client.post("/api/iec61850server/stop")

    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "status": "stopped"}


def test_readvalue_requires_objref(client_and_server):
    client, server = client_and_server
    server.runtime.server_cp1 = object()

    response = client.post("/api/iec61850server/readvalue", json={"fc": "mx"})

    assert response.status_code == 400
    assert response.get_json()["error"] == "objRef is required"


def test_readvalue_rejects_when_server_not_running(client_and_server):
    client, server = client_and_server
    server.runtime.server_cp1 = None

    response = client.post("/api/iec61850server/readvalue", json={"objRef": "LD0/LLN0.Mod.stVal"})

    assert response.status_code == 503
    assert response.get_json()["error"] == "Server is not running"


def test_readvalue_success_wraps_single_value(client_and_server):
    client, server = client_and_server
    server.runtime.server_cp1 = object()
    server.read_value = lambda _obj_ref: {"type": "boolean", "value": True}

    response = client.post(
        "/api/iec61850server/readvalue",
        json={"objRef": "LD0/LLN0.Mod.stVal", "fc": "st"},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    assert body["success"] is True
    assert body["values"] == [{"type": "boolean", "value": True}]


def test_writevalue_requires_value(client_and_server):
    client, server = client_and_server
    server.runtime.server_cp1 = object()

    response = client.post(
        "/api/iec61850server/writevalue",
        json={"objRef": "LD0/LLN0.Mod.stVal", "fc": "st"},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "value is required"


def test_writevalue_success_response(client_and_server):
    client, server = client_and_server
    server.runtime.server_cp1 = object()

    def fake_write(obj_ref: str, value, data_type: str = "unknown"):
        return {
            "objRef": obj_ref,
            "value": value,
            "dataType": data_type,
        }

    server.write_value = fake_write

    response = client.post(
        "/api/iec61850server/writevalue",
        json={
            "objRef": "LD0/LLN0.Mod.stVal",
            "fc": "st",
            "value": 1,
            "dataType": "int32",
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    assert body["success"] is True
    assert body["objRef"] == "LD0/LLN0.Mod.stVal"
    assert body["value"] == 1
    assert body["dataType"] == "int32"


def test_update_iedmodel_requires_model_py(client_and_server):
    client, _ = client_and_server

    response = client.post("/api/iec61850server/update-iedmodel", json={})

    assert response.status_code == 400
    assert "modelPy is required" in response.get_json()["error"]


def test_update_iedmodel_success(client_and_server):
    client, server = client_and_server

    class _FakeIed:
        name = "UpdatedIED"

    server.update_model_file = lambda _content: _FakeIed()

    response = client.post(
        "/api/iec61850server/update-iedmodel",
        json={"modelPy": "from ws61850.iec61850.data_model.ied_model import IedModel\nied = IedModel(name='UpdatedIED')\n"},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    assert body["ied"] == "UpdatedIED"


def test_connections_returns_server_info_when_no_clients(client_and_server):
    client, server = client_and_server
    server.runtime.endpoint = None

    response = client.get("/api/iec61850server/connections")

    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    assert body["server_role"] == "ACSI_Server"
    assert body["ws_mode"] == "passive"
    assert body["connected_clients"] == 0
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

    response = client.get("/api/iec61850server/connections")

    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    assert body["connected_clients"] == 1
    assert len(body["connections"]) == 1

    conn = body["connections"][0]
    assert conn["peer_address"] == "192.168.1.100"
    assert conn["peer_port"] == 54321
    assert conn["server_role"] == "ACSI_Server"
    assert conn["ws_mode"] == "passive"
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
    response = client.get("/api/iec61850server/connections")

    assert response.status_code == 200
    body = response.get_json()
    assert body["connected_clients"] == 2

    assert body["connections"][0]["status"] == "active"
    assert body["connections"][1]["status"] == "disconnected"
