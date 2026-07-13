import requests
import pytest
import time

FSP_URL = "http://localhost:5001/api/iec61850server"
SO_URL  = "http://localhost:5002/api/iec61850client"

WS_PORT = 8765
CP      = "cp1"

# ---------------------------------------------------------------------------
# Shared helper: establish WebSocket connection between FSP and SO
# ---------------------------------------------------------------------------

def _establish_connection():
    """Start SO listening then FSP connecting. Returns when SO is connected."""
    requests.post(f"{SO_URL}/disconnect", timeout=5)
    requests.post(f"{FSP_URL}/stop", timeout=5)

    r = requests.post(f"{SO_URL}/connect",
                      json={"host": "0.0.0.0", "port": WS_PORT, "cp": CP}, timeout=5)
    assert r.status_code == 200 and r.json().get("ok"), f"SO /connect failed: {r.text}"

    r = requests.post(f"{FSP_URL}/start",
                      json={"host": "rti-client", "port": WS_PORT, "mode": "server", "cp": CP}, timeout=5)
    assert r.status_code == 200 and r.json().get("ok"), f"FSP /start failed: {r.text}"

    deadline = time.time() + 12
    while time.time() < deadline:
        resp = requests.get(f"{SO_URL}/status", timeout=3).json()
        status = resp.get("status", "")
        if status == "connected":
            return
        if status == "error":
            pytest.fail(f"SO error during connect: {resp.get('error')}")
        time.sleep(0.5)
    pytest.fail("SO never reached 'connected' state")


def _teardown():
    requests.post(f"{FSP_URL}/stop", timeout=5)
    requests.post(f"{SO_URL}/disconnect", timeout=5)


# ---------------------------------------------------------------------------
# New tests — all use a live WebSocket connection
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_connections_endpoint_after_websocket():
    """
    GET /connections should report the FSP peer address and role
    after a live WebSocket connection is established.
    """
    _establish_connection()

    r = requests.get(f"{SO_URL}/connections", timeout=5)

    _teardown()

    assert r.status_code == 200, f"Connections failed: {r.text}"
    body = r.json()
    assert body.get("ok") is True
    assert body.get("connected") is True
    assert body.get("server_role") == "ACSI_Client"
    assert body.get("ws_mode") == "passive"
    conn = body.get("connection")
    assert conn is not None, "No connection info returned"
    assert conn.get("remote_role") == "ACSI_Server"
    assert conn.get("cp") == CP


@pytest.mark.integration
def test_status_fields_when_connected():
    """
    GET /status should return all documented fields with correct values
    when the SO is connected over WebSocket.
    """
    _establish_connection()

    r = requests.get(f"{SO_URL}/status", timeout=5)

    _teardown()

    assert r.status_code == 200, f"Status failed: {r.text}"
    body = r.json()
    assert body.get("status") == "connected"
    assert "host" in body
    assert "port" in body
    assert "cp" in body
    assert "error" in body
    assert "modelStatus" in body
    assert "modelError" in body


@pytest.mark.integration
def test_actions_logged_after_websocket_read():
    """
    After a WebSocket read, GET /actions should contain at least one action entry.
    Then POST /actions/clear should empty the log.
    Verifies both the actions and clear-actions endpoints using real WebSocket traffic.
    """
    _establish_connection()

    # Trigger a read so an action is logged
    requests.post(f"{SO_URL}/readvalue",
                  json={"objRef": "GenericIO/GGIO1.AnIn1.mag.f", "fc": "mx"}, timeout=10)

    # Check actions were logged
    r = requests.get(f"{SO_URL}/actions", timeout=5)
    assert r.status_code == 200, f"Actions failed: {r.text}"
    body = r.json()
    actions = body.get("actions", [])
    assert len(actions) > 0, "No actions logged after WebSocket read"

    # Clear and verify empty
    r_clear = requests.post(f"{SO_URL}/actions/clear", timeout=5)
    assert r_clear.status_code == 200
    assert r_clear.json().get("ok") is True

    r_after = requests.get(f"{SO_URL}/actions", timeout=5)
    assert len(r_after.json().get("actions", [])) == 0, "Actions not cleared"

    _teardown()


@pytest.mark.integration
def test_messages_logged_after_websocket_read():
    """
    After a WebSocket read, GET /messages should contain protocol messages
    exchanged over the wire. Then POST /messages/clear should empty the log.
    Verifies both the messages and clear-messages endpoints.
    """
    _establish_connection()

    # Clear first to start fresh
    requests.post(f"{SO_URL}/messages/clear", timeout=5)
    requests.post(f"{FSP_URL}/messages/clear", timeout=5)

    # Trigger a read — this sends a getDataValues request over WebSocket
    requests.post(f"{SO_URL}/readvalue",
                  json={"objRef": "GenericIO/GGIO1.AnIn1.mag.f", "fc": "mx"}, timeout=10)

    # SO should have sent a request and received a response
    r = requests.get(f"{SO_URL}/messages", timeout=5)
    assert r.status_code == 200, f"Messages failed: {r.text}"
    msgs = r.json().get("messages", [])
    assert len(msgs) >= 2, f"Expected at least 2 messages (request + response), got {len(msgs)}"

    directions = {m.get("direction") for m in msgs}
    assert "send" in directions, "No outgoing WebSocket message recorded"
    assert "recv" in directions, "No incoming WebSocket message recorded"

    # FSP should also have messages on its side
    r_fsp = requests.get(f"{FSP_URL}/messages", timeout=5)
    fsp_msgs = r_fsp.json().get("messages", [])
    assert len(fsp_msgs) >= 2, f"FSP expected at least 2 messages, got {len(fsp_msgs)}"

    # Clear and verify empty
    r_clear = requests.post(f"{SO_URL}/messages/clear", timeout=5)
    assert r_clear.status_code == 200
    assert r_clear.json().get("ok") is True

    r_after = requests.get(f"{SO_URL}/messages", timeout=5)
    assert len(r_after.json().get("messages", [])) == 0, "Messages not cleared"

    _teardown()


@pytest.mark.integration
def test_readvalue_503_when_not_connected():
    """
    POST /readvalue should return 503 when no WebSocket connection is established.
    """
    # Ensure disconnected
    requests.post(f"{SO_URL}/disconnect", timeout=5)
    requests.post(f"{FSP_URL}/stop", timeout=5)
    time.sleep(0.5)

    r = requests.post(f"{SO_URL}/readvalue",
                      json={"objRef": "GenericIO/GGIO1.AnIn1.mag.f", "fc": "mx"}, timeout=5)

    assert r.status_code == 503, f"Expected 503, got {r.status_code}: {r.text}"
    assert r.json().get("ok") is False


@pytest.mark.integration
def test_writevalue_503_when_not_connected():
    """
    POST /writevalue should return 503 when no WebSocket connection is established.
    """
    requests.post(f"{SO_URL}/disconnect", timeout=5)
    requests.post(f"{FSP_URL}/stop", timeout=5)
    time.sleep(0.5)

    r = requests.post(f"{SO_URL}/writevalue",
                      json={"objRef": "GenericIO/GGIO1.AnIn1.mag.f",
                            "fc": "mx", "value": 1.0, "value_type": "float32"}, timeout=5)

    assert r.status_code == 503, f"Expected 503, got {r.status_code}: {r.text}"
    assert r.json().get("ok") is False


@pytest.mark.integration
def test_writevalue_missing_fc():
    """
    POST /writevalue without fc should return 400 (fc is required).
    """
    r = requests.post(f"{SO_URL}/writevalue",
                      json={"objRef": "GenericIO/GGIO1.AnIn1.mag.f", "value": 1.0}, timeout=5)

    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
    assert r.json().get("ok") is False
    assert "fc" in r.json().get("error", "").lower()


@pytest.mark.integration
def test_disconnect_when_already_disconnected():
    """
    POST /disconnect when already disconnected should return ok: true
    and status: disconnected without error.
    """
    requests.post(f"{SO_URL}/disconnect", timeout=5)
    time.sleep(0.3)

    r = requests.post(f"{SO_URL}/disconnect", timeout=5)

    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    body = r.json()
    assert body.get("ok") is True
    assert body.get("status") == "disconnected"