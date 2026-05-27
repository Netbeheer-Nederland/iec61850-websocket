"""Integration test: rti-server (FSP) <-> rti-client (SO) round-trip.

Verifies real IEC 61850 / WebSocket communication between the two Docker
containers defined in rti-demo/docker-compose.yml.

Prerequisites
-------------
Both containers must be running on the same Docker network:

    cd rti-demo
    docker compose up -d --build

The test runs from the *host*: it talks to each container's REST API on
localhost (FSP=5001, SO=5002). Inside the docker network, the SO reaches
the FSP's WebSocket using the container hostname ``rti-server``.

Run with:
    pytest rti-demo/tests/integration/so-fsp.py -v -s
"""

from __future__ import annotations

import time
from http.client import responses

import pytest
import requests

# ---------------------------------------------------------------------------
# Configuration -- single source of truth for URLs / ports
# ---------------------------------------------------------------------------

FSP_HTTP_PORT = 5001           # host port exposed by rti-server container
SO_HTTP_PORT = 5002            # host port exposed by rti-client container

FSP_BASE_URL = f"http://localhost:{FSP_HTTP_PORT}/api"
SO_BASE_URL = f"http://localhost:{SO_HTTP_PORT}/api"

# How the FSP (running INSIDE the docker network) reaches the SO's WebSocket.
SO_WS_HOST_FOR_FSP = "rti-client"   # docker-compose service name
FSP_WS_PORT = 8765
FSP_CP = "cp1"

# An objRef expected to exist in the default fsp/model.py (GenericIO simpleIO)
TEST_OBJ_REF = "GenericIO/GGIO1.AnIn1.mag.f"
TEST_VALUE = 42.0

REQ_TIMEOUT = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _service_up(url: str) -> bool:
    try:
        return requests.get(url, timeout=2).status_code == 200
    except Exception:
        return False


def _wait_for(predicate, timeout: float = 15.0, interval: float = 0.5,
              fail_msg: str = "condition not met"):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            last = predicate()
            if last:
                return last
        except Exception as e:
            last = e
        time.sleep(interval)
    pytest.fail(f"{fail_msg} (last={last!r})")


# ---------------------------------------------------------------------------
# Skip whole module if either container isn't reachable
# ---------------------------------------------------------------------------

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _service_up(f"{FSP_BASE_URL}/iec61850server/status"),
        reason=f"FSP not reachable on {FSP_BASE_URL}. Run `docker compose up -d` in rti-demo/.",
    ),
    pytest.mark.skipif(
        not _service_up(f"{SO_BASE_URL}/iec61850client/status"),
        reason=f"SO not reachable on {SO_BASE_URL}. Run `docker compose up -d` in rti-demo/.",
    ),
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def so_connected():
    """Start SO listening, then immediately have FSP connect to it."""
    # Clean up any stale state
    try:
        requests.post(f"{SO_BASE_URL}/iec61850client/disconnect", timeout=REQ_TIMEOUT)
    except Exception:
        pass
    try:
        requests.post(f"{FSP_BASE_URL}/iec61850server/stop", timeout=REQ_TIMEOUT)
    except Exception:
        pass
    time.sleep(0.5)

    # Step 1: Start SO listening (PassiveEndpoint binds port, 15s association timeout starts NOW)
    r = requests.post(
        f"{SO_BASE_URL}/iec61850client/connect",
        json={"host": "0.0.0.0", "port": FSP_WS_PORT, "cp": FSP_CP},
        timeout=REQ_TIMEOUT,
    )
    assert r.status_code == 200, f"SO /connect failed: {r.status_code} {r.text}"
    assert r.json().get("ok") is True

    # Step 2: Immediately start FSP connecting to SO (no sleep — every second counts)
    r = requests.post(
        f"{FSP_BASE_URL}/iec61850server/start",
        json={"host": SO_WS_HOST_FOR_FSP, "port": FSP_WS_PORT, "mode": "server", "cp": FSP_CP},
        timeout=REQ_TIMEOUT,
    )
    assert r.status_code == 200, f"FSP /start failed: {r.status_code} {r.text}"

    # Wait for SO to report connected (ready_event fires once FSP connects and association completes)
    def _so_connected():
        s = requests.get(f"{SO_BASE_URL}/iec61850client/status", timeout=REQ_TIMEOUT)
        if s.status_code != 200:
            return False
        data = s.json()
        if data.get("status") == "error":
            pytest.fail(f"SO entered error state: {data.get('error')}")
        return (data.get("status") or "").lower() in ("connected", "associated", "ready")

    _wait_for(_so_connected, timeout=12, fail_msg="SO did not reach connected state")

    yield

    try:
        requests.post(f"{FSP_BASE_URL}/iec61850server/stop", timeout=REQ_TIMEOUT)
    except Exception:
        pass
    try:
        requests.post(f"{SO_BASE_URL}/iec61850client/disconnect", timeout=REQ_TIMEOUT)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_fsp_and_so_services_are_up():
    """Sanity check: both Flask BFFs respond on their REST APIs."""
    assert requests.get(f"{FSP_BASE_URL}/iec61850server/status", timeout=REQ_TIMEOUT).status_code == 200
    assert requests.get(f"{SO_BASE_URL}/iec61850client/status", timeout=REQ_TIMEOUT).status_code == 200


def test_so_can_associate_with_fsp(so_connected):
    """Test that SO can connect to FSP and both report association."""
    fsp_status = requests.get(f"{FSP_BASE_URL}/iec61850server/status", timeout=REQ_TIMEOUT).json()
    so_status = requests.get(f"{SO_BASE_URL}/iec61850client/status", timeout=REQ_TIMEOUT).json()
    assert fsp_status.get("status", "").lower() in ("connected", "associated", "listening", "ready")
    assert so_status.get("connectedClients", 0) >= 1


def test_so_reads_value_from_fsp(so_connected):
    """SO reads a value over WebSocket from the FSP."""
    r = requests.post(
        f"{SO_BASE_URL}/iec61850client/readvalue",
        json={"objRef": TEST_OBJ_REF},
        timeout=REQ_TIMEOUT,
    )
    assert r.status_code == 200, f"SO read failed: {r.status_code} {r.text}"
    body = r.json()
    print("SO read response:", body)
    assert body.get("ok") is True
    # Response shape may be {values: [...]} or {value: ...} depending on impl.
    assert "values" in body or "value" in body


def test_round_trip_so_writes_fsp_reads(so_connected):
    """SO writes a value to the FSP, then FSP's local read returns it."""
    # SO -> FSP write
    w = requests.post(
        f"{SO_BASE_URL}/iec61850client/writevalue",
        json={"objRef": TEST_OBJ_REF, "value": TEST_VALUE},
        timeout=REQ_TIMEOUT,
    )
    assert w.status_code == 200, f"SO write failed: {w.status_code} {w.text}"
    assert w.json().get("ok") is True

    # Give the FSP a moment to apply the update.
    time.sleep(0.5)

    # FSP local read confirms the value landed in its model.
    r = requests.post(
        f"{FSP_BASE_URL}/iec61850server/readvalue",
        json={"objRef": TEST_OBJ_REF},
        timeout=REQ_TIMEOUT,
    )
    assert r.status_code == 200, f"FSP read failed: {r.status_code} {r.text}"
    body = r.json()
    print("FSP read-after-SO-write response:", body)
    assert body.get("ok") is True

    values = body.get("values") or []
    assert values, f"FSP returned no values: {body}"
    got = values[0].get("value")
    assert float(got) == pytest.approx(TEST_VALUE), f"expected {TEST_VALUE}, got {got}"


def test_round_trip_fsp_writes_so_reads(so_connected):
    """FSP changes a value locally; SO reads the updated value over the wire."""
    new_value = 7.5

    # FSP local write
    w = requests.post(
        f"{FSP_BASE_URL}/iec61850server/writevalue",
        json={"objRef": TEST_OBJ_REF, "value": new_value},
        timeout=REQ_TIMEOUT,
    )
    assert w.status_code == 200, f"FSP write failed: {w.status_code} {w.text}"
    assert w.json().get("ok") is True

    time.sleep(0.5)

    # SO read should reflect the new value.
    r = requests.post(
        f"{SO_BASE_URL}/iec61850client/readvalue",
        json={"objRef": TEST_OBJ_REF},
        timeout=REQ_TIMEOUT,
    )
    assert r.status_code == 200, f"SO read failed: {r.status_code} {r.text}"
    body = r.json()
    print("SO read-after-FSP-write response:", body)
    assert body.get("ok") is True

    # Normalize across possible response shapes.
    if "values" in body and body["values"]:
        got = body["values"][0].get("value")
    else:
        got = body.get("value")
    assert got is not None, f"SO returned no value: {body}"
    assert float(got) == pytest.approx(new_value), f"expected {new_value}, got {got}"


def test_protocol_messages_were_exchanged(so_connected):
    """Both ends recorded WebSocket protocol messages -- proof of comms."""
    fsp_msgs = requests.get(
        f"{FSP_BASE_URL}/iec61850server/messages", timeout=REQ_TIMEOUT
    ).json()
    so_msgs = requests.get(
        f"{SO_BASE_URL}/iec61850client/messages", timeout=REQ_TIMEOUT
    ).json()

    def _count(payload):
        # Endpoints sometimes return {"messages": [...]} and sometimes
        # {"messages": {"messages": [...]}}.
        m = payload.get("messages")
        if isinstance(m, list):
            return len(m)
        if isinstance(m, dict):
            return len(m.get("messages", []))
        return 0

    fsp_n = _count(fsp_msgs)
    so_n = _count(so_msgs)
    print(f"FSP messages={fsp_n}  SO messages={so_n}")
    assert fsp_n > 0, "FSP did not log any protocol messages"
    assert so_n > 0, "SO did not log any protocol messages"

