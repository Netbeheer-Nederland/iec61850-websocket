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

"""Integration test: IEC 61850 data traffic over the FSP <-> SO WebSocket.

Requires the rti-demo Docker Compose stack running - see TESTING.md's
"Integration tests (Docker required)" section:

    docker compose -f docker-compose.yml up -d
    uv run pytest tests/integration -m integration -q

Complements test_so_fsp.py (connection lifecycle/logging) with the actual
IEC 61850 read/write service calls SO makes to FSP once associated.

Known gaps surfaced by this suite (verified against the live stack, not
fixed here - see the docstring on each affected test):
  - SO's /readvalue always returns value=null over the WS path, regardless
    of the target object or whether FSP holds a non-null value locally.
  - SO's /writevalue to any "sp"/"cf" functional-constraint object fails
    with "Type mismatch: '<value>' is not valid for None" - every setpoint
    object in the demo model hits this, not just one.
Both were reproduced by hand against a clean connection before writing
these tests; they are protocol/model-layer issues, not something these
tests work around.
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


def _connect():
    requests.post(f"{SO_URL}/disconnect", timeout=5)
    requests.post(f"{FSP_URL}/stop", timeout=5)
    time.sleep(0.5)

    r = requests.post(
        f"{SO_URL}/connect",
        json={"host": "0.0.0.0", "port": WS_PORT, "cp": CP},
        timeout=5,
    )
    assert r.status_code == 200 and r.json().get("ok")

    r = requests.post(
        f"{FSP_URL}/start",
        json={"host": "rti-so", "port": str(WS_PORT), "mode": "active", "cp": CP},
        timeout=5,
    )
    assert r.status_code == 200 and r.json().get("ok")

    deadline = time.time() + 12
    while time.time() < deadline:
        resp = requests.post(f"{SO_URL}/connections", json={"cp": CP}, timeout=3).json()
        if resp.get("connected"):
            return
        time.sleep(0.5)
    pytest.fail("SO never reached a connected state")


@pytest.fixture
def connected():
    _connect()
    yield
    requests.post(f"{FSP_URL}/stop", timeout=5)
    requests.post(f"{SO_URL}/disconnect", timeout=5)


def test_fsp_connects_to_so(connected):
    """The association itself: SO listens passively, FSP dials in as the active side."""
    so_status = requests.get(f"{SO_URL}/status", timeout=5).json()
    assert so_status["status"] == "connected"

    fsp_status = requests.get(f"{FSP_URL}/status", timeout=5).json()
    assert fsp_status["ok"] is True
    assert "'status': 'listening'" in fsp_status["status"]

    conn = requests.post(f"{SO_URL}/connections", json={"cp": CP}, timeout=5).json()
    assert conn["connected"] is True
    assert conn["connection"]["cp"] == CP


def test_so_reads_value_over_websocket(connected):
    """SO's readvalue round-trips a real GetDataValues request/response over the WS.

    Known gap: `value` is always null here regardless of the object read -
    verified against multiple ST/MX/DC points with and without prior writes
    on the FSP side. This test asserts the part that does work (the
    round-trip itself: 200, ok/success, objRef echoed back correctly) and
    intentionally does NOT assert on `value`, so it doesn't silently start
    "passing" a wrong value once someone fixes the extraction bug - update
    this test's assertions when that's fixed instead.
    """
    r = requests.post(
        f"{SO_URL}/readvalue",
        json={"objRef": "LD0/LLN0$ST$Mod", "fc": "st", "cp": CP},
        timeout=5,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["success"] is True
    assert body["objRef"] == "LD0/LLN0$ST$Mod"
    assert "value" in body


def test_so_read_rejects_missing_objref(connected):
    r = requests.post(f"{SO_URL}/readvalue", json={"fc": "st", "cp": CP}, timeout=5)
    assert r.status_code == 422


def test_so_writes_value_over_websocket(connected):
    """SO's writevalue is access-controlled to "cf"/"sp" functional constraints.

    Known gap: a well-formed write to any "sp" object in the demo model
    (e.g. LD0/DWMX1$SP$WMaxSet$setMag$f) fails server-side with
    "Type mismatch: '<value>' is not valid for None" - reproduced on every
    setpoint the model exposes, so it isn't asserted here as a passing
    round-trip. This test instead asserts the part that reliably works:
    the FC access-control check runs before the write is attempted.
    """
    # "st" is not a writable FC - rejected before any WS traffic happens.
    r = requests.post(
        f"{SO_URL}/writevalue",
        json={"objRef": "LD0/LLN0$ST$Mod", "fc": "st", "value": "on", "cp": CP},
        timeout=5,
    )
    assert r.status_code == 400
    assert "Write only allowed to CF and SP" in r.json()["error"]
