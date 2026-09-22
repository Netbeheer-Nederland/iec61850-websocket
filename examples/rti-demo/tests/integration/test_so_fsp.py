# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
#
# Copyright 2025 Netbeheer Nederland
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Integration test: FSP <-> SO WebSocket connection lifecycle.

Requires the rti-demo Docker Compose stack running (rti-fsp on :5001,
rti-so on :5002) - see TESTING.md's "Integration tests (Docker required)"
section:

    docker compose -f docker-compose.yml up -d
    uv run pytest tests/integration -m integration -q

Talks to FSP/SO over their published host ports for everything except the
FSP's own /start call - the FSP container dials out to the SO using the
compose network's service hostname ("rti-so"), which only resolves inside
that network, not from wherever this test runs.
"""

from __future__ import annotations

import time

import pytest
import requests

pytestmark = pytest.mark.integration

FSP_URL = "http://localhost:5001/api"
SO_URL = "http://localhost:5002/api"

WS_PORT = 8765
CP = "cp1"


def _establish_connection():
    """Reset both sides, then bring SO up (passive listener) and FSP up (active dial-out)."""
    requests.post(f"{SO_URL}/disconnect", timeout=5)
    requests.post(f"{FSP_URL}/stop", timeout=5)
    time.sleep(0.5)

    r = requests.post(
        f"{SO_URL}/connect",
        json={"host": "0.0.0.0", "port": WS_PORT, "cp": CP},
        timeout=5,
    )
    assert r.status_code == 200 and r.json().get("ok"), f"SO /connect failed: {r.text}"

    # FSP's StartRequest.port is typed str, unlike SO's ConnectRequest.port (int).
    r = requests.post(
        f"{FSP_URL}/start",
        json={"host": "rti-so", "port": str(WS_PORT), "mode": "active", "cp": CP},
        timeout=5,
    )
    assert r.status_code == 200 and r.json().get("ok"), f"FSP /start failed: {r.text}"

    deadline = time.time() + 12
    while time.time() < deadline:
        resp = requests.post(f"{SO_URL}/connections", json={"cp": CP}, timeout=3).json()
        if resp.get("connected"):
            return
        time.sleep(0.5)
    pytest.fail("SO never reached a connected state")


def _teardown():
    requests.post(f"{FSP_URL}/stop", timeout=5)
    requests.post(f"{SO_URL}/disconnect", timeout=5)


@pytest.fixture
def connected():
    """Establish a real FSP<->SO WebSocket connection for the duration of one test."""
    _establish_connection()
    yield
    _teardown()


@pytest.fixture
def disconnected():
    """Ensure neither side has an active WebSocket connection for one test."""
    requests.post(f"{FSP_URL}/stop", timeout=5)
    requests.post(f"{SO_URL}/disconnect", timeout=5)
    yield


# ---------------------------------------------------------------------------
# Connected-state behavior
# ---------------------------------------------------------------------------


def test_connections_endpoint_after_websocket(connected):
    r = requests.post(f"{SO_URL}/connections", json={"cp": CP}, timeout=5)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["connected"] is True
    assert body["connection"]["cp"] == CP


def test_status_fields_when_connected(connected):
    r = requests.get(f"{SO_URL}/status", timeout=5)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "connected"
    assert body["error"] is None

    r = requests.get(f"{FSP_URL}/status", timeout=5)
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_actions_logged_after_websocket_read(connected):
    requests.post(
        f"{SO_URL}/readvalue",
        json={"objRef": "LD0/LLN0$ST$Mod", "fc": "st", "cp": CP},
        timeout=5,
    )

    r = requests.get(f"{SO_URL}/actions-logs", timeout=5)
    assert r.status_code == 200
    actions = r.json()["actions"]
    assert len(actions) > 0
    assert any("Connected to server" in a["message"] for a in actions)


def test_messages_logged_after_websocket_read(connected):
    requests.post(
        f"{SO_URL}/readvalue",
        json={"objRef": "LD0/LLN0$ST$Mod", "fc": "st", "cp": CP},
        timeout=5,
    )

    r = requests.get(f"{SO_URL}/messages", timeout=5)
    assert r.status_code == 200
    messages = r.json()["messages"]
    assert len(messages) > 0
    assert any(m.get("cp") == CP for m in messages)


# ---------------------------------------------------------------------------
# Disconnected-state error handling
# ---------------------------------------------------------------------------


def test_readvalue_503_when_not_connected(disconnected):
    r = requests.post(
        f"{SO_URL}/readvalue",
        json={"objRef": "LD0/LLN0$ST$Mod", "fc": "st", "cp": CP},
        timeout=5,
    )
    assert r.status_code == 503


def test_writevalue_503_when_not_connected(disconnected):
    # writevalue wraps the same "no-active-websocket-connection" failure in a
    # 500 (unlike readvalue's plain 503) - this asserts today's actual
    # behavior, not necessarily the ideal one.
    r = requests.post(
        f"{SO_URL}/writevalue",
        json={"objRef": "LD0/LLN0$ST$Mod", "fc": "st", "cp": CP, "value": "on"},
        timeout=5,
    )
    assert r.status_code == 500
    assert "no-active-websocket-connection" in r.json().get("error", "")


def test_writevalue_missing_fc(disconnected):
    r = requests.post(
        f"{SO_URL}/writevalue",
        json={"objRef": "LD0/LLN0$ST$Mod", "cp": CP, "value": "on"},
        timeout=5,
    )
    assert r.status_code == 422


def test_disconnect_when_already_disconnected(disconnected):
    r = requests.post(f"{SO_URL}/disconnect", timeout=5)
    assert r.status_code == 200
    assert r.json()["status"] == "disconnected"
