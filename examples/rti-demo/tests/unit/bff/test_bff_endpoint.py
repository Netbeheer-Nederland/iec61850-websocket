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

"""Integration test for BFF connection management against live containers.

Requires the rti-demo Docker Compose stack running (rti-bff on :5000,
rti-fsp on :5001, rti-so on :5002) - see TESTING.md's "Integration tests
(Docker required)" section:

    docker compose -f docker-compose.yml up -d
    uv run pytest tests/unit -m integration -q

Unlike tests/integration/test_so_fsp.py and test_ws_connection.py (which
talk to FSP/SO directly), this exercises the BFF's own /api/* connection
registry: add/edit/delete/list, plus validation and health. All test
connections use a "test-*-itest" name prefix and are deleted in a fixture
teardown, so this doesn't disturb the stack's real registered connections
(e.g. any "FSP01"/"SO" entries configured through the HMI).
"""

from __future__ import annotations

import pytest
import requests

pytestmark = pytest.mark.integration

BFF_URL = "http://localhost:5000/api"

SO_NAME = "test-so-itest"
FSP_NAME = "test-fsp-itest"


def _delete(name: str) -> None:
    requests.delete(f"{BFF_URL}/delete-connection/{name}", timeout=5)


@pytest.fixture(autouse=True)
def _cleanup():
    """Belt-and-braces: remove test connections before and after each test."""
    _delete(SO_NAME)
    _delete(FSP_NAME)
    yield
    _delete(SO_NAME)
    _delete(FSP_NAME)


def test_health_reports_reachable_targets():
    r = requests.get(f"{BFF_URL}/health", timeout=5)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "targets" in body


def test_add_connection_requires_name_and_type():
    r = requests.post(f"{BFF_URL}/add-connection", json={"type": "RTI-SO"}, timeout=5)
    assert r.status_code == 422


def test_add_edit_delete_so_connection():
    r = requests.post(f"{BFF_URL}/add-connection", json={
        "name": SO_NAME,
        "host": "rti-so",
        "port": 5002,
        "ws_port": 8765,
        "type": "RTI-SO",
        "acsi": "client",
        "ws_mode": "passive",
    }, timeout=5)
    assert r.status_code == 201
    created = r.json()
    assert created["name"] == SO_NAME
    assert created["ws_port"] == 8765

    r = requests.get(f"{BFF_URL}/connections", timeout=5)
    assert r.status_code == 200
    names = [c["name"] for c in r.json()["connections"]]
    assert SO_NAME in names

    r = requests.put(f"{BFF_URL}/edit-connection/{SO_NAME}",
                      json={"ws_port": 8766}, timeout=5)
    assert r.status_code == 200
    assert r.json()["ws_port"] == 8766

    r = requests.delete(f"{BFF_URL}/delete-connection/{SO_NAME}", timeout=5)
    assert r.status_code == 200
    assert r.json()["status"] == "deleted"

    r = requests.get(f"{BFF_URL}/connections", timeout=5)
    names = [c["name"] for c in r.json()["connections"]]
    assert SO_NAME not in names


def test_add_fsp_connection_stores_cp():
    """RTI-FSP's `cp` (connection point) attribute round-trips through the BFF.

    Regression test for the RTI-FSP connection-type schema: `cp` must be
    persisted on create and editable afterwards, not silently dropped.
    """
    r = requests.post(f"{BFF_URL}/add-connection", json={
        "name": FSP_NAME,
        "host": "rti-fsp",
        "port": 5001,
        "type": "RTI-FSP",
        "acsi": "server",
        "ws_mode": "active",
        "cp": "cp1",
    }, timeout=5)
    assert r.status_code == 201
    assert r.json()["cp"] == "cp1"

    r = requests.put(f"{BFF_URL}/edit-connection/{FSP_NAME}",
                      json={"cp": "cp2"}, timeout=5)
    assert r.status_code == 200
    assert r.json()["cp"] == "cp2"


def test_delete_nonexistent_connection_404():
    r = requests.delete(f"{BFF_URL}/delete-connection/does-not-exist", timeout=5)
    assert r.status_code == 404
