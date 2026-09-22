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

"""Integration test: the BFF's live WebSocket push actually reaches a client.

Requires the rti-demo Docker Compose stack running - see TESTING.md's
"Integration tests (Docker required)" section:

    docker compose -f docker-compose.yml up -d
    uv run pytest tests/integration -m integration -q

Regression coverage for a real bug: bff's pyproject.toml declared plain
`uvicorn` with no WebSocket implementation in its dependency tree, so
uvicorn logged "No supported WebSocket library detected" and every /ws
handshake 404'd - push_relay_loop (bff/bff_server.py) kept broadcasting
into a channel no browser could ever actually connect to. The HMI's
Setup page then only ever reflected a connection change after a full
page load (App.jsx's one-time fetchConnections() on mount), never live.

bff/tests/test_push_relay.py's existing unit tests exercise push_relay_loop
and the /ws route's accept/register/unregister wiring, but do so through
Starlette's ASGI-transport TestClient, which never touches uvicorn's real
HTTP/1.1 Upgrade handling - that's exactly the layer the actual bug was
in, so those unit tests kept passing throughout. Only a test against the
real running server (this one) can catch a regression here.
"""

from __future__ import annotations

import asyncio
import json
import time

import pytest
import requests
import websockets

pytestmark = pytest.mark.integration

BFF_WS_URL = "ws://localhost:5000/ws"
FSP_URL = "http://localhost:5001/api"
SO_URL = "http://localhost:5002/api"
WS_PORT = 8765
CP = "cp1"


@pytest.fixture(autouse=True)
def _stopped():
    """Leave the FSP<->SO association stopped before and after each test."""
    requests.post(f"{FSP_URL}/stop", timeout=5)
    requests.post(f"{SO_URL}/disconnect", timeout=5)
    time.sleep(0.5)
    yield
    requests.post(f"{FSP_URL}/stop", timeout=5)
    requests.post(f"{SO_URL}/disconnect", timeout=5)


def test_ws_endpoint_upgrades_successfully():
    """The handshake itself must succeed against the real server.

    Before the fix, this raised websockets.exceptions.InvalidStatus with a
    404 response - uvicorn had no WebSocket library to perform the
    HTTP/1.1 Upgrade with, regardless of how correct bff_server.py's own
    route/relay logic was.
    """

    async def _connect():
        async with websockets.connect(BFF_WS_URL, open_timeout=5):
            pass

    asyncio.run(_connect())  # must not raise


def test_live_push_delivers_fsp_connect_update():
    """A client connected *before* an FSP starts receives the update live.

    This is the actual end-user scenario the bug report described: the
    Setup page (or any open tab) should see a connection's live state
    change without a manual reload. Mirrors the manual verification done
    when this bug was fixed: attach the listener first, then trigger the
    state change, and require the delta to arrive over the same socket.
    """
    so_connect = requests.post(
        f"{SO_URL}/connect", json={"host": "0.0.0.0", "port": WS_PORT, "cp": CP}, timeout=5
    )
    assert so_connect.status_code == 200 and so_connect.json().get("ok")

    async def _listen_and_trigger():
        async with websockets.connect(BFF_WS_URL, open_timeout=5) as ws:
            loop = asyncio.get_event_loop()
            # Trigger the state change from a worker thread so it overlaps
            # with the recv() loop below instead of happening entirely
            # before or after it - matching how a real browser tab and a
            # real "Connect" click on another page are two independent,
            # concurrent things.
            start_future = loop.run_in_executor(
                None,
                lambda: requests.post(
                    f"{FSP_URL}/start",
                    json={"host": "rti-so", "port": str(WS_PORT), "mode": "active", "cp": CP},
                    timeout=5,
                ),
            )

            deadline = time.monotonic() + 10
            found_connected_clients = None
            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=max(remaining, 0.1))
                except asyncio.TimeoutError:
                    break
                msg = json.loads(raw)
                if msg.get("type") != "connections":
                    continue
                fsp = next((c for c in msg["data"] if c.get("host") == "rti-fsp01"), None)
                if fsp and (fsp.get("connectedClients") or 0) > 0:
                    found_connected_clients = fsp["connectedClients"]
                    break

            start_resp = await start_future
            assert start_resp.status_code == 200 and start_resp.json().get("ok")
            return found_connected_clients

        return None

    connected_clients = asyncio.run(_listen_and_trigger())
    assert connected_clients is not None, (
        "no 'connections' push with connectedClients > 0 for rti-fsp01 "
        "arrived over the live socket within 10s of starting it"
    )
    assert connected_clients >= 1
