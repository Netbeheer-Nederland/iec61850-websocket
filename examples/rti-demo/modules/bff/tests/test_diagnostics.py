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

"""Unit tests for the BFF's system events and the Diagnostics endpoint.

Covers ConnectionManager.log_event / status-change events and
GET /api/diagnostics merging BFF events with each reachable instance's kind
"system" actions-log entries. See docs/rti-demo/design/logging-kinds.md.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

import pytest

_tmp_connections_file = Path(tempfile.mkdtemp()) / "connections.json"
_tmp_connections_file.write_text("[]", encoding="utf-8")
os.environ.setdefault("BFF_CONNECTIONS_FILE", str(_tmp_connections_file))

from bff import bff_server  # noqa: E402 - must follow the env var default above
from bff.connection_manager import ConnectionManager  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture
def manager(tmp_path):
    connections_file = tmp_path / "connections.json"
    connections_file.write_text("[]", encoding="utf-8")
    return ConnectionManager({}, str(connections_file), logging.getLogger("test"))


class FakeBffClient:
    def __init__(self, responses=None, raises=None):
        self.responses = responses or {}
        self.raises = raises

    def request(self, method, path, json=None, params=None, headers=None):
        if self.raises:
            raise self.raises
        return self.responses.get(path)


# -------------------- ConnectionManager events --------------------


def test_log_event_records_a_system_entry(manager):
    manager.log_event("SO stopped responding", "warn", instance="SO")

    [event] = manager.get_events()
    assert event["kind"] == "system"
    assert event["level"] == "warn"
    assert event["message"] == "SO stopped responding"
    assert event["instance"] == "SO"
    assert event["id"] == 1


def _statuses(manager, *statuses):
    for status in statuses:
        manager._log_status_change({"name": "SO", "status": status})
    return [(e["level"], e["message"]) for e in manager.get_events()]


def test_the_first_check_is_always_an_event_even_if_status_was_persisted(manager):
    # connections.json persists "connected" across BFF restarts; the first
    # check still reports it.
    assert _statuses(manager, "connected") == [("info", "SO is reachable")]


def test_first_check_unreachable_is_a_warning(manager):
    assert _statuses(manager, "disconnected") == [("warn", "SO is not reachable")]


def test_changes_after_that_become_events(manager):
    assert _statuses(manager, "connected", "disconnected", "connected") == [
        ("info", "SO is reachable"),
        ("warn", "SO stopped responding"),
        ("info", "SO is reachable"),
    ]


def test_an_unchanged_status_or_checking_is_not_an_event(manager):
    assert _statuses(manager, "connected", "connected", "checking", "connected") == [
        ("info", "SO is reachable"),
    ]


# -------------------- GET /api/diagnostics --------------------


@pytest.fixture
def diagnostics_env(monkeypatch, manager):
    monkeypatch.setattr(bff_server, "conn_manager", manager)
    manager.connections = [
        {
            "name": "SO",
            "type": "RTI-SO",
            "status": "connected",
            "host": "rti-so",
            "port": 5002,
        },
        {
            "name": "FSP01",
            "type": "RTI-FSP",
            "status": "disconnected",
            "host": "rti-fsp01",
            "port": 5001,
        },
        {"name": "IDP", "type": "IDP-Server", "status": "connected"},
    ]
    monkeypatch.setitem(
        bff_server._bff_clients,
        "rti-so:5002",
        FakeBffClient(
            responses={
                "/api/actions-logs": {
                    "actions": [
                        {
                            "id": 1,
                            "time": "10:00:01",
                            "kind": "system",
                            "level": "info",
                            "message": "Connected to server",
                        },
                        {
                            "id": 2,
                            "time": "10:00:02",
                            "kind": "acsi",
                            "level": "info",
                            "message": "GetDataValues x - ok",
                        },
                        {
                            "id": 3,
                            "time": "10:00:03",
                            "kind": "system",
                            "level": "error",
                            "message": "Endpoint failed to start",
                        },
                    ]
                }
            }
        ),
    )
    return manager


async def test_diagnostics_merges_bff_events_and_instance_system_entries(
    diagnostics_env,
):
    diagnostics_env.log_event("FSP01 stopped responding", "warn", instance="FSP01")

    body = await bff_server.get_diagnostics()

    messages = [(e["source"], e["level"], e["message"]) for e in body["entries"]]
    # errors first, then warnings, then the rest; acsi entries left out;
    # the disconnected FSP isn't queried.
    assert messages == [
        ("SO", "error", "Endpoint failed to start"),
        ("BFF", "warn", "FSP01 stopped responding"),
        ("SO", "info", "Connected to server"),
    ]
    assert body["sources"] == ["BFF", "SO"]
    assert all(e["kind"] == "system" for e in body["entries"])


async def test_diagnostics_skips_an_instance_whose_log_cannot_be_read(
    diagnostics_env, monkeypatch
):
    monkeypatch.setitem(
        bff_server._bff_clients,
        "rti-so:5002",
        FakeBffClient(raises=ConnectionError("refused")),
    )

    body = await bff_server.get_diagnostics()

    assert body["entries"] == []
