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
            "/api/connect",
            json={"host": "localhost", "port": "invalid"}
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
        response = client.post(
            "/api/connect",
            json={"host": "localhost", "port": 8765}
        )
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
        response = client.post(
            "/api/readvalue",
            json={}
        )
        # objRef is a required field on ReadvalueRequest - rejected by
        # request validation (422) before the handler runs.
        assert response.status_code == 422

    def test_readvalue_error_response_is_json(self, app_client):
        """Test readvalue error response is JSON."""
        client, _ = app_client
        response = client.post(
            "/api/readvalue",
            json={}
        )
        assert "application/json" in content_type(response)


class TestWriteValueEndpoint:
    """Tests for POST /api/writevalue endpoint."""

    def test_writevalue_missing_objref(self, app_client):
        """Test writevalue with a missing (required) objRef is rejected."""
        client, _ = app_client
        response = client.post(
            "/api/writevalue",
            json={"value": 1}
        )
        # fc and objRef are both required fields on WriteValueRequest and
        # neither is present here - 422 from request validation.
        assert response.status_code == 422

    def test_writevalue_missing_value(self, app_client):
        """Test writevalue with a missing (required) value is rejected."""
        client, _ = app_client
        response = client.post(
            "/api/writevalue",
            json={"objRef": "LD0/LLN0.Mod.stVal"}
        )
        # fc and value are both required and neither is present here.
        assert response.status_code == 422

    def test_writevalue_error_response_is_json(self, app_client):
        """Test writevalue error response is JSON."""
        client, _ = app_client
        response = client.post(
            "/api/writevalue",
            json={}
        )
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
            headers={"content-type": "application/json"}
        )
        # Should handle gracefully, not crash with a 500.
        assert response.status_code != 500

    def test_readvalue_error_message_present(self, app_client):
        """Test readvalue error includes some error/detail message."""
        client, _ = app_client
        response = client.post(
            "/api/readvalue",
            json={}
        )
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
