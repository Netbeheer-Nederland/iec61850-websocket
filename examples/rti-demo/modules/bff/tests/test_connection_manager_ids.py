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

"""Unit tests for ConnectionManager.add_connection()'s id assignment.

Regression coverage for a duplicate-id bug: ids used to be
len(self.connections) + 1, which is only unique if connections are never
deleted out of order. Delete one that isn't the most-recently-added, then
add a new one, and the new id collides with a surviving connection's id -
observed live as two connections both reporting id=4 in /api/connections.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_tmp_connections_file = Path(tempfile.mkdtemp()) / "connections.json"
_tmp_connections_file.write_text("[]", encoding="utf-8")
os.environ.setdefault("BFF_CONNECTIONS_FILE", str(_tmp_connections_file))

from bff import bff_server  # noqa: E402 - must follow the env var default above
from bff.ConnectionManager import ConnectionManager  # noqa: E402

pytestmark = pytest.mark.unit


def _fresh_manager(tmp_path):
    """A ConnectionManager with its own isolated connections.json, entirely
    separate from bff_server.py's module-level singleton."""
    return ConnectionManager(
        bff_clients={},
        connections_file=str(tmp_path / "connections.json"),
        logger=bff_server.logger,
    )


def test_ids_increment_sequentially_for_fresh_connections(tmp_path):
    manager = _fresh_manager(tmp_path)

    a = manager.add_connection(name="a", host="10.0.0.1", port=5001, conn_type="RTI-FSP")
    b = manager.add_connection(name="b", host="10.0.0.2", port=5002, conn_type="RTI-SO")
    c = manager.add_connection(name="c", host="10.0.0.3", port=5003, conn_type="RTI-FSP")

    assert [a["id"], b["id"], c["id"]] == [1, 2, 3]


def test_new_id_does_not_collide_after_deleting_a_middle_connection(tmp_path):
    manager = _fresh_manager(tmp_path)
    manager.add_connection(name="a", host="10.0.0.1", port=5001, conn_type="RTI-FSP")  # id 1
    manager.add_connection(name="b", host="10.0.0.2", port=5002, conn_type="RTI-SO")   # id 2
    c = manager.add_connection(name="c", host="10.0.0.3", port=5003, conn_type="RTI-FSP")  # id 3

    manager.delete_connection("b")
    # len(self.connections) is now 2, so the old "len + 1" scheme would
    # hand out id=3 again here - colliding with "c", which is still id=3.
    d = manager.add_connection(name="d", host="10.0.0.4", port=5004, conn_type="RTI-FSP")

    ids = [conn["id"] for conn in manager.connections]
    assert len(ids) == len(set(ids)), f"duplicate id among {manager.connections}"
    assert d["id"] != c["id"]


def test_new_id_is_higher_than_any_existing_id_even_after_deletes(tmp_path):
    manager = _fresh_manager(tmp_path)
    for i in range(5):
        manager.add_connection(name=f"c{i}", host="10.0.0.1", port=5000 + i, conn_type="RTI-FSP")

    manager.delete_connection("c0")
    manager.delete_connection("c1")
    manager.delete_connection("c2")
    new_conn = manager.add_connection(name="new", host="10.0.0.9", port=5099, conn_type="RTI-FSP")

    existing_ids = [c["id"] for c in manager.connections if c["name"] != "new"]
    assert new_conn["id"] > max(existing_ids)
