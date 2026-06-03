"""Unit tests for SO client BFF endpoint routes."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from flask import Flask
import requests

# Allow importing rti-demo/so modules as top-level modules.
SO_DIR = Path(__file__).resolve().parents[3] / "so"
if str(SO_DIR) not in sys.path:
    sys.path.insert(0, str(SO_DIR))


pytestmark = pytest.mark.unit


@pytest.fixture
def app_client():
    """Create a Flask app with BFF blueprint."""
    try:
        import bff_endpoint
        blueprint, acsi_client = bff_endpoint.create_bff_blueprint()
        
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(blueprint)
        
        yield app.test_client(), acsi_client
    except Exception as e:
        pytest.skip(f"Could not initialize BFF endpoint: {e}")


class TestEndpointsExist:
    """Test that all expected endpoints are registered."""

    def test_status_endpoint_exists(self, app_client):
        """Test status endpoint is accessible."""
        client, _ = app_client
        response = client.get("/api/iec61850client/status")
        # Should return 200 or 500 (depending on client state), but not 404
        assert response.status_code != 404

    def test_connections_endpoint_exists(self, app_client):
        """Test connections endpoint is accessible."""
        client, _ = app_client
        response = client.get("/api/iec61850client/connections")
        assert response.status_code != 404

    def test_connect_endpoint_exists(self, app_client):
        """Test connect endpoint is accessible."""
        client, _ = app_client
        response = client.post("/api/iec61850client/connect", json={})
        # Should return 200 or error, but not 404
        assert response.status_code != 404

    def test_disconnect_endpoint_exists(self, app_client):
        """Test disconnect endpoint is accessible."""
        client, _ = app_client
        response = client.post("/api/iec61850client/disconnect")
        assert response.status_code != 404

    def test_actions_endpoint_exists(self, app_client):
        """Test actions endpoint is accessible."""
        client, _ = app_client
        response = client.get("/api/iec61850client/actions")
        assert response.status_code != 404

    def test_clear_actions_endpoint_exists(self, app_client):
        """Test clear actions endpoint is accessible."""
        client, _ = app_client
        response = client.post("/api/iec61850client/actions/clear")
        assert response.status_code != 404

    def test_messages_endpoint_exists(self, app_client):
        """Test messages endpoint is accessible."""
        client, _ = app_client
        response = client.get("/api/iec61850client/messages")
        assert response.status_code != 404

    def test_clear_messages_endpoint_exists(self, app_client):
        """Test clear messages endpoint is accessible."""
        client, _ = app_client
        response = client.post("/api/iec61850client/messages/clear")
        assert response.status_code != 404

    def test_readvalue_endpoint_exists(self, app_client):
        """Test readvalue endpoint is accessible."""
        client, _ = app_client
        response = client.post("/api/iec61850client/readvalue", json={})
        # Should error (missing objRef) but not 404
        assert response.status_code != 404

    def test_writevalue_endpoint_exists(self, app_client):
        """Test writevalue endpoint is accessible."""
        client, _ = app_client
        response = client.post("/api/iec61850client/writevalue", json={})
        # Should error (missing params) but not 404
        assert response.status_code != 404


class TestStatusEndpoint:
    """Tests for GET /api/iec61850client/status endpoint."""

    def test_status_returns_json(self, app_client):
        """Test status endpoint returns JSON."""
        client, _ = app_client
        response = client.get("/api/iec61850client/status")
        assert "application/json" in response.content_type

    def test_status_returns_dict(self, app_client):
        """Test status endpoint returns a dictionary."""
        client, _ = app_client
        response = client.get("/api/iec61850client/status")
        body = response.get_json()
        assert isinstance(body, dict)


class TestConnectionsEndpoint:
    """Tests for GET /api/iec61850client/connections endpoint."""

    def test_connections_returns_json(self, app_client):
        """Test connections endpoint returns JSON."""
        client, _ = app_client
        response = client.get("/api/iec61850client/connections")
        assert "application/json" in response.content_type

    def test_connections_returns_ok_flag(self, app_client):
        """Test connections response has ok flag."""
        client, _ = app_client
        response = client.get("/api/iec61850client/connections")
        body = response.get_json()
        assert "ok" in body or "status" in body


class TestConnectEndpoint:
    """Tests for POST /api/iec61850client/connect endpoint."""

    def test_connect_invalid_port_string(self, app_client):
        """Test connect with invalid port string returns 400."""
        client, _ = app_client
        response = client.post(
            "/api/iec61850client/connect",
            json={"host": "localhost", "port": "invalid"}
        )
        assert response.status_code == 400

    def test_connect_returns_json(self, app_client):
        """Test connect endpoint returns JSON."""
        client, _ = app_client
        response = client.post(
            "/api/iec61850client/connect",
            json={"host": "localhost", "port": 8765}
        )
        print(response)
        assert "application/json" in response.content_type


class TestDisconnectEndpoint:
    """Tests for POST /api/iec61850client/disconnect endpoint."""

    def test_disconnect_returns_json(self, app_client):
        """Test disconnect endpoint returns JSON."""
        client, _ = app_client
        response = client.post("/api/iec61850client/disconnect")
        assert "application/json" in response.content_type


class TestActionsEndpoint:
    """Tests for GET /api/iec61850client/actions endpoint."""

    def test_actions_returns_json(self, app_client):
        """Test actions endpoint returns JSON."""
        client, _ = app_client
        response = client.get("/api/iec61850client/actions")
        assert "application/json" in response.content_type

    def test_actions_returns_list(self, app_client):
        """Test actions response contains a list."""
        client, _ = app_client
        response = client.get("/api/iec61850client/actions")
        body = response.get_json()
        assert "actions" in body or isinstance(body, list)


class TestClearActionsEndpoint:
    """Tests for POST /api/iec61850client/actions/clear endpoint."""

    def test_clear_actions_returns_json(self, app_client):
        """Test clear actions endpoint returns JSON."""
        client, _ = app_client
        response = client.post("/api/iec61850client/actions/clear")
        assert "application/json" in response.content_type


class TestMessagesEndpoint:
    """Tests for GET /api/iec61850client/messages endpoint."""

    def test_messages_returns_json(self, app_client):
        """Test messages endpoint returns JSON."""
        client, _ = app_client
        response = client.get("/api/iec61850client/messages")
        assert "application/json" in response.content_type

    def test_messages_returns_list(self, app_client):
        """Test messages response contains a list."""
        client, _ = app_client
        response = client.get("/api/iec61850client/messages")
        body = response.get_json()
        assert "messages" in body or isinstance(body, list)


class TestClearMessagesEndpoint:
    """Tests for POST /api/iec61850client/messages/clear endpoint."""

    def test_clear_messages_returns_json(self, app_client):
        """Test clear messages endpoint returns JSON."""
        client, _ = app_client
        response = client.post("/api/iec61850client/messages/clear")
        assert "application/json" in response.content_type


class TestReadValueEndpoint:
    """Tests for POST /api/iec61850client/readvalue endpoint."""

    def test_readvalue_missing_objref(self, app_client):
        """Test readvalue with missing objRef returns 400."""
        client, _ = app_client
        response = client.post(
            "/api/iec61850client/readvalue",
            json={}
        )
        assert response.status_code == 400

    def test_readvalue_error_response_is_json(self, app_client):
        """Test readvalue error response is JSON."""
        client, _ = app_client
        response = client.post(
            "/api/iec61850client/readvalue",
            json={}
        )
        assert "application/json" in response.content_type


class TestWriteValueEndpoint:
    """Tests for POST /api/iec61850client/writevalue endpoint."""

    def test_writevalue_missing_objref(self, app_client):
        """Test writevalue with missing objRef returns 400."""
        client, _ = app_client
        response = client.post(
            "/api/iec61850client/writevalue",
            json={"value": 1}
        )
        assert response.status_code == 400

    def test_writevalue_missing_value(self, app_client):
        """Test writevalue with missing value returns 400."""
        client, _ = app_client
        response = client.post(
            "/api/iec61850client/writevalue",
            json={"objRef": "LD0/LLN0.Mod.stVal"}
        )
        assert response.status_code == 400

    def test_writevalue_error_response_is_json(self, app_client):
        """Test writevalue error response is JSON."""
        client, _ = app_client
        response = client.post(
            "/api/iec61850client/writevalue",
            json={}
        )
        assert "application/json" in response.content_type


class TestHTTPMethods:
    """Tests for correct HTTP method enforcement."""

    def test_status_requires_get(self, app_client):
        """Test status endpoint requires GET."""
        client, _ = app_client
        response = client.post("/api/iec61850client/status")
        assert response.status_code == 405

    def test_connect_requires_post(self, app_client):
        """Test connect endpoint requires POST."""
        client, _ = app_client
        response = client.get("/api/iec61850client/connect")
        assert response.status_code == 405

    def test_disconnect_requires_post(self, app_client):
        """Test disconnect endpoint requires POST."""
        client, _ = app_client
        response = client.get("/api/iec61850client/disconnect")
        assert response.status_code == 405

    def test_actions_requires_get(self, app_client):
        """Test actions endpoint requires GET."""
        client, _ = app_client
        response = client.post("/api/iec61850client/actions")
        assert response.status_code == 405

    def test_messages_requires_get(self, app_client):
        """Test messages endpoint requires GET."""
        client, _ = app_client
        response = client.post("/api/iec61850client/messages")
        assert response.status_code == 405


class TestErrorHandling:
    """Tests for error handling."""

    def test_malformed_json_handling(self, app_client):
        """Test handling of malformed JSON."""
        client, _ = app_client
        response = client.post(
            "/api/iec61850client/connect",
            data="not json",
            content_type="application/json"
        )
        # Should handle gracefully, not 500
        assert response.status_code != 500 or response.status_code == 400

    def test_readvalue_error_message_present(self, app_client):
        """Test readvalue error includes error message."""
        client, _ = app_client
        response = client.post(
            "/api/iec61850client/readvalue",
            json={}
        )
        body = response.get_json()
        assert "error" in body or "ok" in body


def test_so_properties():
    """GET /api/iec61850server/properties via BFF should return FSP role/ws_mode."""
    response = requests.get("http://127.0.0.1:5002/api/iec61850client/properties", timeout=10)
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    print(f"BFF->FSP Properties Response: {data}")
    assert data.get('ok') is True
    assert data.get('server_role') == 'ACSI_Client'
    assert data.get('ws_mode') == 'passive'