"""
Direct WebSocket connection test using Docker containers.

FSP (rti-server / ActiveEndpoint) connects to SO (rti-client / PassiveEndpoint).
Uses the minimal REST calls needed to trigger start/stop — no business logic.
"""

from __future__ import annotations

import time
import pytest
import requests

FSP_URL = "http://localhost:5001/api/iec61850server"
SO_URL  = "http://localhost:5002/api/iec61850client"

WS_PORT = 8765
CP      = "cp1"


def _services_up() -> bool:
    try:
        return (
            requests.get(f"{FSP_URL}/status", timeout=2).status_code == 200
            and requests.get(f"{SO_URL}/status", timeout=2).status_code == 200
        )
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _services_up(),
    reason="Docker containers not running. Run `docker compose up -d` in rti-demo/.",
)


@pytest.mark.integration
def test_fsp_connects_to_so():
    """
    1. SO (PassiveEndpoint) binds and listens on 0.0.0.0:8765
    2. FSP (ActiveEndpoint) immediately connects to rti-client:8765
    3. Assert SO reaches 'connected' state within the 15s association window
    """
    # --- cleanup any stale state ---
    requests.post(f"{SO_URL}/disconnect", timeout=5)
    requests.post(f"{FSP_URL}/stop", timeout=5)

    # --- Step 1: SO starts listening (15s association timeout starts NOW) ---
    r = requests.post(f"{SO_URL}/connect",
                      json={"host": "0.0.0.0", "port": WS_PORT, "cp": CP},
                      timeout=5)
    assert r.status_code == 200 and r.json().get("ok"), f"SO /connect failed: {r.text}"

    # --- Step 2: FSP connects immediately (no sleep) ---
    r = requests.post(f"{FSP_URL}/start",
                      json={"host": "rti-client", "port": WS_PORT, "mode": "server", "cp": CP},
                      timeout=5)
    assert r.status_code == 200 and r.json().get("ok"), f"FSP /start failed: {r.text}"

    # --- Step 3: Poll SO status until connected or error ---
    deadline = time.time() + 12
    status = None
    while time.time() < deadline:
        resp = requests.get(f"{SO_URL}/status", timeout=3).json()
        status = resp.get("status", "")
        if status == "connected":
            break
        if status == "error":
            pytest.fail(f"SO entered error state: {resp.get('error')}")
        time.sleep(0.5)

    # --- teardown ---
    requests.post(f"{FSP_URL}/stop", timeout=5)
    requests.post(f"{SO_URL}/disconnect", timeout=5)

    assert status == "connected", f"SO never reached 'connected' (last status={status!r})"


@pytest.mark.integration
def test_so_reads_value_over_websocket():
    """
    After FSP connects to SO over WebSocket, SO reads a value from the FSP model.
    Verifies data flows from FSP -> SO over the live WebSocket connection.
    """
    # --- cleanup ---
    requests.post(f"{SO_URL}/disconnect", timeout=5)
    requests.post(f"{FSP_URL}/stop", timeout=5)

    # --- establish connection ---
    r = requests.post(f"{SO_URL}/connect",
                      json={"host": "0.0.0.0", "port": WS_PORT, "cp": CP},
                      timeout=5)
    assert r.status_code == 200 and r.json().get("ok"), f"SO /connect failed: {r.text}"

    r = requests.post(f"{FSP_URL}/start",
                      json={"host": "rti-client", "port": WS_PORT, "mode": "server", "cp": CP},
                      timeout=5)
    assert r.status_code == 200 and r.json().get("ok"), f"FSP /start failed: {r.text}"

    # --- wait for SO to be connected ---
    deadline = time.time() + 12
    status = None
    while time.time() < deadline:
        resp = requests.get(f"{SO_URL}/status", timeout=3).json()
        status = resp.get("status", "")
        if status == "connected":
            break
        if status == "error":
            pytest.fail(f"SO error during connect: {resp.get('error')}")
        time.sleep(0.5)
    assert status == "connected", f"SO never connected (last={status!r})"

    # --- SO reads a value from FSP over the live WebSocket ---
    r = requests.post(f"{SO_URL}/readvalue",
                      json={"objRef": "GenericIO/GGIO1.AnIn1.mag.f", "fc": "mx"},
                      timeout=10)

    # --- print WebSocket messages exchanged during the read ---
    fsp_msgs = requests.get(f"{FSP_URL}/messages", timeout=5).json().get("messages", [])
    so_msgs  = requests.get(f"{SO_URL}/messages",  timeout=5).json().get("messages", [])
    print("\n--- FSP WebSocket messages ---")
    for m in fsp_msgs:
        print(f"  [{m.get('direction')}] [{m.get('service_type')}] {m.get('preview')}")
    print("\n--- SO WebSocket messages ---")
    for m in so_msgs:
        print(f"  [{m.get('direction')}] [{m.get('service_type')}] {m.get('preview')}")

    # --- teardown ---
    requests.post(f"{FSP_URL}/stop", timeout=5)
    requests.post(f"{SO_URL}/disconnect", timeout=5)

    assert r.status_code == 200, f"Read failed: {r.text}"
    body = r.json()
    assert body.get("ok") is True, f"Read not ok: {body}"
    assert "value" in body or "values" in body, f"No value in response: {body}"


@pytest.mark.integration
def test_so_writes_value_over_websocket():
    """
    After FSP connects to SO over WebSocket, SO writes a value to the FSP model.
    Then FSP reads it back locally to confirm the write propagated over WebSocket.
    """
    # --- cleanup ---
    requests.post(f"{SO_URL}/disconnect", timeout=5)
    requests.post(f"{FSP_URL}/stop", timeout=5)

    # --- establish connection ---
    r = requests.post(f"{SO_URL}/connect",
                      json={"host": "0.0.0.0", "port": WS_PORT, "cp": CP},
                      timeout=5)
    assert r.status_code == 200 and r.json().get("ok"), f"SO /connect failed: {r.text}"

    r = requests.post(f"{FSP_URL}/start",
                      json={"host": "rti-client", "port": WS_PORT, "mode": "server", "cp": CP},
                      timeout=5)
    assert r.status_code == 200 and r.json().get("ok"), f"FSP /start failed: {r.text}"

    # --- wait for SO to be connected ---
    deadline = time.time() + 12
    status = None
    while time.time() < deadline:
        resp = requests.get(f"{SO_URL}/status", timeout=3).json()
        status = resp.get("status", "")
        if status == "connected":
            break
        if status == "error":
            pytest.fail(f"SO error during connect: {resp.get('error')}")
        time.sleep(0.5)
    assert status == "connected", f"SO never connected (last={status!r})"

    # --- SO writes a value to the FSP over the live WebSocket ---
    write_value = 99.0
    r = requests.post(f"{SO_URL}/writevalue",
                      json={"objRef": "GenericIO/GGIO1.AnIn1.mag.f", "fc":"mx", "value": write_value,
                            "value_type": "float32"},
                      timeout=10)
    assert r.status_code == 200, f"Write failed: {r.text}"
    assert r.json().get("ok") is True, f"Write not ok: {r.json()}"

    time.sleep(0.5)

    # --- FSP reads back locally to confirm the write arrived ---
    r = requests.post(f"{FSP_URL}/readvalue",
                      json={"objRef": "GenericIO/GGIO1.AnIn1.mag.f", "fc": "mx"},
                      timeout=10)

    # --- teardown ---
    requests.post(f"{FSP_URL}/stop", timeout=5)
    requests.post(f"{SO_URL}/disconnect", timeout=5)

    assert r.status_code == 200, f"FSP read-back failed: {r.text}"
    body = r.json()
    assert body.get("ok") is True, f"FSP read not ok: {body}"
    values = body.get("values") or []
    assert values, f"FSP returned no values: {body}"
    assert float(values[0].get("value")) == pytest.approx(write_value), \
        f"Expected {write_value}, got {values[0].get('value')}"
