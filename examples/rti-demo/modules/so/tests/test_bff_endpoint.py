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

"""Unit tests for SO ACSI-Client_WebsocketPassive BFF endpoint routes.

so.bff_endpoint is a FastAPI router (create_bff_router), mounted under
the "/api" prefix - not the Flask blueprint this file originally tested
against. Routes are flat (e.g. "/api/status", not
"/api/iec61850client/status"), and a couple of routes changed method or
name entirely: GET /connections -> POST /connections, and
/actions + /actions/clear -> /actions-logs + /clear-logs,
/messages/clear -> /clear-messages.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from so import bff_endpoint

pytestmark = pytest.mark.unit


def content_type(response) -> str:
    return response.headers.get("content-type", "")


@pytest.fixture
def app_client():
    """Create a FastAPI app wrapping the SO's BFF router."""
    app = FastAPI()
    # create_bff_router's first parameter is typed `app: FastAPI` but is
    # unused - it isn't needed to build the router or the ACSIClient() it
    # wraps, and the /apis discovery route (which used to read it via the
    # since-removed Flask-only `app.url_map`) now inspects `router` instead.
    router, acsi_client = bff_endpoint.create_bff_router(app)
    app.include_router(router)

    return TestClient(app), acsi_client


class TestEndpointsExist:
    """Test that all expected endpoints are registered."""

    def test_status_endpoint_exists(self, app_client):
        """Test status endpoint is accessible."""
        client, _ = app_client
        response = client.get("/api/status")
        # Should return 200 or 500 (depending on client state), but not 404
        assert response.status_code != 404

    def test_connections_endpoint_exists(self, app_client):
        """Test connections endpoint is accessible."""
        client, _ = app_client
        response = client.post("/api/connections", json={})
        assert response.status_code != 404

    def test_connect_endpoint_exists(self, app_client):
        """Test connect endpoint is accessible."""
        client, _ = app_client
        response = client.post("/api/connect", json={})
        # Should return 200 or error, but not 404
        assert response.status_code != 404

    def test_disconnect_endpoint_exists(self, app_client):
        """Test disconnect endpoint is accessible."""
        client, _ = app_client
        response = client.post("/api/disconnect")
        assert response.status_code != 404

    def test_actions_endpoint_exists(self, app_client):
        """Test the action log endpoint is accessible."""
        client, _ = app_client
        response = client.get("/api/actions-logs")
        assert response.status_code != 404

    def test_clear_actions_endpoint_exists(self, app_client):
        """Test the clear-action-log endpoint is accessible."""
        client, _ = app_client
        response = client.post("/api/clear-logs")
        assert response.status_code != 404

    def test_messages_endpoint_exists(self, app_client):
        """Test messages endpoint is accessible."""
        client, _ = app_client
        response = client.get("/api/messages")
        assert response.status_code != 404

    def test_clear_messages_endpoint_exists(self, app_client):
        """Test clear messages endpoint is accessible."""
        client, _ = app_client
        response = client.post("/api/clear-messages")
        assert response.status_code != 404

    def test_readvalue_endpoint_exists(self, app_client):
        """Test readvalue endpoint is accessible."""
        client, _ = app_client
        response = client.post("/api/readvalue", json={})
        # Should error (missing objRef, a required field) but not 404
        assert response.status_code != 404

    def test_writevalue_endpoint_exists(self, app_client):
        """Test writevalue endpoint is accessible."""
        client, _ = app_client
        response = client.post("/api/writevalue", json={})
        # Should error (missing params, all required fields) but not 404
        assert response.status_code != 404


class TestApisEndpoint:
    """Tests for GET /api/apis (route discovery/introspection)."""

    def test_apis_lists_registered_routes(self, app_client):
        """Regression test: this used to call the Flask-only app.url_map,
        which doesn't exist on a FastAPI app and would raise AttributeError
        (a 500) for every request. It now inspects the router directly."""
        client, _ = app_client

        response = client.get("/api/apis")

        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["count"] > 0
        paths = {e["path"] for e in body["endpoints"]}
        assert "/api/status" in paths
        assert "/api/readvalue" in paths


class TestStatusEndpoint:
    """Tests for GET /api/status endpoint."""

    def test_status_returns_json(self, app_client):
        """Test status endpoint returns JSON."""
        client, _ = app_client
        response = client.get("/api/status")
        assert "application/json" in content_type(response)

    def test_status_returns_dict(self, app_client):
        """Test status endpoint returns a dictionary."""
        client, _ = app_client
        response = client.get("/api/status")
        assert isinstance(response.json(), dict)


class TestConnectionsEndpoint:
    """Tests for POST /api/connections endpoint."""

    def test_connections_returns_json(self, app_client):
        """Test connections endpoint returns JSON."""
        client, _ = app_client
        response = client.post("/api/connections", json={})
        assert "application/json" in content_type(response)

    def test_connections_returns_ok_flag(self, app_client):
        """Test connections response has ok flag."""
        client, _ = app_client
        response = client.post("/api/connections", json={})
        body = response.json()
        assert "ok" in body or "status" in body


class TestConnectEndpoint:
    """Tests for POST /api/connect endpoint."""

    def test_connect_invalid_port_string(self, app_client):
        """Test connect with a non-numeric port string is rejected."""
        client, _ = app_client
        response = client.post(
            "/api/connect", json={"host": "localhost", "port": "invalid"}
        )
        # port is a pydantic `int` field, so a non-numeric string is now
        # rejected by request validation (422) rather than the handler's own
        # logic (which used to return 400).
        assert response.status_code == 422

    def test_connect_returns_json(self, app_client):
        """Test connect endpoint returns JSON."""
        client, _ = app_client
        # connect() starts a background thread and returns immediately
        # without waiting for the connection to actually succeed - safe to
        # call for real here, nothing to mock.
        response = client.post("/api/connect", json={"host": "localhost", "port": 8765})
        assert "application/json" in content_type(response)


class TestDisconnectEndpoint:
    """Tests for POST /api/disconnect endpoint."""

    def test_disconnect_returns_json(self, app_client):
        """Test disconnect endpoint returns JSON."""
        client, _ = app_client
        response = client.post("/api/disconnect")
        assert "application/json" in content_type(response)


class TestActionsEndpoint:
    """Tests for GET /api/actions-logs endpoint."""

    def test_actions_returns_json(self, app_client):
        """Test the action log endpoint returns JSON."""
        client, _ = app_client
        response = client.get("/api/actions-logs")
        assert "application/json" in content_type(response)

    def test_actions_returns_list(self, app_client):
        """Test action log response contains a list."""
        client, _ = app_client
        response = client.get("/api/actions-logs")
        body = response.json()
        assert "actions" in body or isinstance(body, list)


class TestClearActionsEndpoint:
    """Tests for POST /api/clear-logs endpoint."""

    def test_clear_actions_returns_json(self, app_client):
        """Test clear-action-log endpoint returns JSON."""
        client, _ = app_client
        response = client.post("/api/clear-logs")
        assert "application/json" in content_type(response)


class TestMessagesEndpoint:
    """Tests for GET /api/messages endpoint."""

    def test_messages_returns_json(self, app_client):
        """Test messages endpoint returns JSON."""
        client, _ = app_client
        response = client.get("/api/messages")
        assert "application/json" in content_type(response)

    def test_messages_returns_list(self, app_client):
        """Test messages response contains a list."""
        client, _ = app_client
        response = client.get("/api/messages")
        body = response.json()
        assert "messages" in body or isinstance(body, list)


class TestClearMessagesEndpoint:
    """Tests for POST /api/clear-messages endpoint."""

    def test_clear_messages_returns_json(self, app_client):
        """Test clear messages endpoint returns JSON."""
        client, _ = app_client
        response = client.post("/api/clear-messages")
        assert "application/json" in content_type(response)


class TestReadValueEndpoint:
    """Tests for POST /api/readvalue endpoint."""

    def test_readvalue_missing_objref(self, app_client):
        """Test readvalue with a missing (required) objRef is rejected."""
        client, _ = app_client
        response = client.post("/api/readvalue", json={})
        # objRef is a required field on ReadvalueRequest - rejected by
        # request validation (422) before the handler runs.
        assert response.status_code == 422

    def test_readvalue_error_response_is_json(self, app_client):
        """Test readvalue error response is JSON."""
        client, _ = app_client
        response = client.post("/api/readvalue", json={})
        assert "application/json" in content_type(response)


class TestWriteValueEndpoint:
    """Tests for POST /api/writevalue endpoint."""

    def test_writevalue_missing_objref(self, app_client):
        """Test writevalue with a missing (required) objRef is rejected."""
        client, _ = app_client
        response = client.post("/api/writevalue", json={"value": 1})
        # fc and objRef are both required fields on WriteValueRequest and
        # neither is present here - 422 from request validation.
        assert response.status_code == 422

    def test_writevalue_missing_value(self, app_client):
        """Test writevalue with a missing (required) value is rejected."""
        client, _ = app_client
        response = client.post("/api/writevalue", json={"objRef": "LD0/LLN0.Mod.stVal"})
        # fc and value are both required and neither is present here.
        assert response.status_code == 422

    def test_writevalue_error_response_is_json(self, app_client):
        """Test writevalue error response is JSON."""
        client, _ = app_client
        response = client.post("/api/writevalue", json={})
        assert "application/json" in content_type(response)


class TestHTTPMethods:
    """Tests for correct HTTP method enforcement."""

    def test_status_requires_get(self, app_client):
        """Test status endpoint requires GET."""
        client, _ = app_client
        response = client.post("/api/status")
        assert response.status_code == 405

    def test_connect_requires_post(self, app_client):
        """Test connect endpoint requires POST."""
        client, _ = app_client
        response = client.get("/api/connect")
        assert response.status_code == 405

    def test_disconnect_requires_post(self, app_client):
        """Test disconnect endpoint requires POST."""
        client, _ = app_client
        response = client.get("/api/disconnect")
        assert response.status_code == 405

    def test_actions_requires_get(self, app_client):
        """Test the action log endpoint requires GET."""
        client, _ = app_client
        response = client.post("/api/actions-logs")
        assert response.status_code == 405

    def test_messages_requires_get(self, app_client):
        """Test messages endpoint requires GET."""
        client, _ = app_client
        response = client.post("/api/messages")
        assert response.status_code == 405


class TestErrorHandling:
    """Tests for error handling."""

    def test_malformed_json_handling(self, app_client):
        """Test handling of malformed JSON."""
        client, _ = app_client
        response = client.post(
            "/api/connect",
            content="not json",
            headers={"content-type": "application/json"},
        )
        # Should handle gracefully, not crash with a 500.
        assert response.status_code != 500

    def test_readvalue_error_message_present(self, app_client):
        """Test readvalue error includes some error/detail message."""
        client, _ = app_client
        response = client.post("/api/readvalue", json={})
        body = response.json()
        # FastAPI's own request-validation errors use "detail" rather than
        # this app's usual custom {"ok": False, "error": ...} shape.
        assert "error" in body or "ok" in body or "detail" in body


def test_so_properties(app_client):
    """GET /api/properties should return the SO's fixed role/ws_mode."""
    client, _ = app_client

    response = client.get("/api/properties")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["acsi_role"] == "ACSI-Client"
    assert body["ws_mode"] == "passive"


class TestSelectAndOperateAnswers:
    """POST /api/select (and /api/operate's answer): ok only when the server
    carried it out - its serviceError's name is the error, not the ok."""

    @pytest.mark.parametrize(
        ("result", "expected"),
        [
            (True, {"ok": True, "error": ""}),
            (
                "instance-not-available",
                {"ok": False, "error": "instance-not-available"},
            ),
            (None, {"ok": False, "error": "no response"}),
            (False, {"ok": False, "error": "refused"}),
        ],
    )
    def test_control_answer(self, result, expected):
        assert bff_endpoint.control_answer(result) == expected

    @staticmethod
    def _connected(acsi_client, monkeypatch, select_result):
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        from types import SimpleNamespace

        calls = []

        async def fake_select(obj_ref, cp):
            calls.append((obj_ref, cp))
            return {"objRef": obj_ref, "result": select_result}

        acsi_client.runtime.endpoint = SimpleNamespace(websocket_info_list=[object()])
        monkeypatch.setattr(acsi_client, "get_iec61850_client", lambda cp: object())
        monkeypatch.setattr(acsi_client, "select", fake_select)
        # Like the SO's runtime loop: the coroutine runs on another thread's loop.
        monkeypatch.setattr(
            acsi_client,
            "invoke_on_runtime_loop",
            lambda coro, timeout=10: (
                ThreadPoolExecutor(1).submit(asyncio.run, coro).result(timeout)
            ),
        )
        return calls

    @pytest.mark.parametrize(
        ("select_result", "expected"),
        [
            (True, {"ok": True, "error": ""}),
            ("object-access-denied", {"ok": False, "error": "object-access-denied"}),
            (None, {"ok": False, "error": "no response"}),
        ],
    )
    def test_select_route_reports_what_the_server_answered(
        self, app_client, monkeypatch, select_result, expected
    ):
        client, acsi_client = app_client
        calls = self._connected(acsi_client, monkeypatch, select_result)

        response = client.post(
            "/api/select", json={"objRef": "GenericIO/GGIO1.SPCSO1", "cp": "cp2"}
        )

        assert response.status_code == 200
        assert response.json() == expected
        assert calls == [("GenericIO/GGIO1.SPCSO1", "cp2")]

    def test_select_route_needs_an_active_websocket(self, app_client):
        client, _ = app_client
        response = client.post("/api/select", json={"objRef": "LD0/CSWI1.Pos"})
        assert response.status_code == 503

    def test_select_route_times_out_cleanly(self, app_client, monkeypatch):
        from concurrent.futures import TimeoutError as FuturesTimeoutError

        client, acsi_client = app_client
        self._connected(acsi_client, monkeypatch, True)

        def timeout(coro, timeout=10):
            coro.close()
            raise FuturesTimeoutError()

        monkeypatch.setattr(acsi_client, "invoke_on_runtime_loop", timeout)
        response = client.post("/api/select", json={"objRef": "LD0/CSWI1.Pos"})
        assert response.status_code == 504
        assert response.json() == {"ok": False, "error": "Select timeout"}


class TestOperateRoutePassesControlParameters:
    """POST /api/operate hands ctlNum, origin and test to ACSIClient.operate."""

    @staticmethod
    def _connected(acsi_client, monkeypatch):
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        from types import SimpleNamespace

        calls = []

        async def fake_operate(obj_ref, value, value_type, cp, **kwargs):
            calls.append((obj_ref, value, value_type, cp, kwargs))
            return {"objRef": obj_ref, "result": True}

        acsi_client.runtime.endpoint = SimpleNamespace(websocket_info_list=[object()])
        monkeypatch.setattr(acsi_client, "get_iec61850_client", lambda cp: object())
        monkeypatch.setattr(acsi_client, "operate", fake_operate)
        monkeypatch.setattr(
            acsi_client,
            "invoke_on_runtime_loop",
            lambda coro, timeout=10: (
                ThreadPoolExecutor(1).submit(asyncio.run, coro).result(timeout)
            ),
        )
        monkeypatch.setattr(bff_endpoint, "_use_io_client", False)
        return calls

    def test_passes_ctlnum_origin_and_test(self, app_client, monkeypatch):
        client, acsi_client = app_client
        calls = self._connected(acsi_client, monkeypatch)

        response = client.post(
            "/api/operate",
            json={
                "objRef": "GenericIO/GGIO1.SPCSO1",
                "value": True,
                "value_type": "boolean",
                "cp": "cp2",
                "ctlNum": 3,
                "origin": {"orCat": 1, "orIdent": "0"},
                "test": False,
            },
        )

        assert response.status_code == 200
        assert response.json() == {"ok": True, "error": ""}
        assert calls == [
            (
                "GenericIO/GGIO1.SPCSO1",
                True,
                "boolean",
                "cp2",
                {"ctl_num": 3, "origin": {"orCat": 1, "orIdent": "0"}, "test": False},
            )
        ]

    def test_rejects_an_unknown_originator_category(self, app_client, monkeypatch):
        client, acsi_client = app_client
        calls = self._connected(acsi_client, monkeypatch)

        response = client.post(
            "/api/operate",
            json={
                "objRef": "LD0/CSWI1.Pos",
                "value": "on",
                "value_type": "enumerated",
                "origin": {"orCat": 12},
            },
        )

        assert response.status_code == 400
        assert "orCat" in response.json()["error"]
        assert calls == []


class TestHealthReportsItsPort:
    """GET /api/health names the port the SO listens on (PORT, default 5000)."""

    def test_default_port(self, app_client, monkeypatch):
        monkeypatch.delenv("PORT", raising=False)
        client, _ = app_client
        assert client.get("/api/health").json()["server"]["port"] == 5000

    def test_port_from_environment(self, app_client, monkeypatch):
        monkeypatch.setenv("PORT", "5100")
        client, _ = app_client
        assert client.get("/api/health").json()["server"]["port"] == 5100


class FakeClient:
    def __init__(self, raises=None):
        self.raises = raises
        self.connects = []
        self.logged = []

    def connect(self, host, port):
        if self.raises:
            raise self.raises
        self.connects.append((host, port))

    def _log_action(self, message, level, kind=None):
        self.logged.append((level, message))


class TestListenOnStart:
    """The SO's WebSocket server (passive endpoint) starts with the service."""

    def test_listens_on_all_interfaces_port_8765_by_default(self, monkeypatch):
        for var in ("SO_LISTEN_ON_START", "SO_WS_HOST", "SO_WS_PORT"):
            monkeypatch.delenv(var, raising=False)
        client = FakeClient()
        bff_endpoint._listen_on_start(client)
        assert client.connects == [("0.0.0.0", 8765)]

    def test_host_and_port_from_environment(self, monkeypatch):
        monkeypatch.setenv("SO_WS_HOST", "127.0.0.1")
        monkeypatch.setenv("SO_WS_PORT", "9765")
        client = FakeClient()
        bff_endpoint._listen_on_start(client)
        assert client.connects == [("127.0.0.1", 9765)]

    @pytest.mark.parametrize("value", ["false", "0", "no", "off", "False"])
    def test_can_be_switched_off(self, monkeypatch, value):
        monkeypatch.setenv("SO_LISTEN_ON_START", value)
        client = FakeClient()
        bff_endpoint._listen_on_start(client)
        assert client.connects == []

    def test_a_failed_start_is_logged_not_raised(self, monkeypatch):
        monkeypatch.delenv("SO_LISTEN_ON_START", raising=False)
        client = FakeClient(raises=RuntimeError("port in use"))
        bff_endpoint._listen_on_start(client)
        assert any(
            level == "warn" and "port in use" in msg for level, msg in client.logged
        )

    def test_the_app_starts_listening_on_startup(self, monkeypatch, tmp_path):
        started = []
        monkeypatch.setattr(bff_endpoint, "_listen_on_start", started.append)
        # create_fastapi_app prepares the IO plugin directory (/app/... in Docker).
        monkeypatch.setattr(
            bff_endpoint, "IO_PLUGIN_DYNAMIC_DIR", tmp_path / "io_plugin"
        )
        app = bff_endpoint.create_fastapi_app(tmp_path)
        with TestClient(app):
            pass
        assert started == [app.state.client]
