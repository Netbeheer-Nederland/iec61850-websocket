# SPDX-FileCopyrightText: 2025-2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
#
# Copyright 2025-2026 Netbeheer Nederland
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

"""Unit tests for connection ids: opaque UUIDs.

Ids used to be integers, first len(connections) + 1 (which collided after an
out-of-order delete, observed live as two connections both reporting id=4),
then the highest id + 1 (which reused the ids of deleted connections). They
are UUIDs now: never repeated, and with no meaning of their own.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path

import pytest

_tmp_connections_file = Path(tempfile.mkdtemp()) / "connections.json"
_tmp_connections_file.write_text("[]", encoding="utf-8")
os.environ.setdefault("BFF_CONNECTIONS_FILE", str(_tmp_connections_file))

from bff import bff_server  # noqa: E402 - must follow the env var default above
from bff.connection_manager import (  # noqa: E402
    ConnectionManager,
    is_connection_id,
)

pytestmark = pytest.mark.unit


def _fresh_manager(tmp_path):
    """A ConnectionManager with its own isolated connections.json, entirely
    separate from bff_server.py's module-level singleton."""
    return ConnectionManager(
        bff_clients={},
        connections_file=str(tmp_path / "connections.json"),
        logger=bff_server.logger,
    )


def test_a_new_connection_gets_a_uuid(tmp_path):
    manager = _fresh_manager(tmp_path)

    conn = manager.add_connection(
        name="a", host="10.0.0.1", port=5001, conn_type="RTI-FSP"
    )

    assert is_connection_id(conn["id"])
    assert uuid.UUID(conn["id"]).version == 4


def test_ids_are_never_reused_after_deletes(tmp_path):
    manager = _fresh_manager(tmp_path)
    seen = set()
    for i in range(5):
        seen.add(
            manager.add_connection(
                name=f"c{i}", host="10.0.0.1", port=5000 + i, conn_type="RTI-FSP"
            )["id"]
        )
    for i in range(5):
        manager.delete_connection(f"c{i}")

    new_conn = manager.add_connection(
        name="new", host="10.0.0.9", port=5099, conn_type="RTI-FSP"
    )

    assert new_conn["id"] not in seen


def test_old_integer_ids_become_uuids_on_load(tmp_path):
    file = tmp_path / "connections.json"
    file.write_text(
        json.dumps(
            [
                {"id": 1, "name": "SO", "host": "h", "port": 5000},
                {"id": 2, "name": "FSP01", "host": "h", "port": 5001},
            ]
        ),
        encoding="utf-8",
    )

    manager = _fresh_manager(tmp_path)

    ids = [c["id"] for c in manager.connections]
    assert all(is_connection_id(i) for i in ids)
    assert len(set(ids)) == 2
    # Saved, so they stay the same across restarts.
    assert [c["id"] for c in json.loads(file.read_text())] == ids


def test_a_repeated_id_gets_a_new_one_on_load(tmp_path):
    same = str(uuid.uuid4())
    (tmp_path / "connections.json").write_text(
        json.dumps(
            [
                {"id": same, "name": "a", "host": "h", "port": 1},
                {"id": same, "name": "b", "host": "h", "port": 2},
            ]
        ),
        encoding="utf-8",
    )

    manager = _fresh_manager(tmp_path)

    first, second = (c["id"] for c in manager.connections)
    assert first == same
    assert second != same and is_connection_id(second)


def test_a_valid_file_is_left_as_it_is(tmp_path):
    file = tmp_path / "connections.json"
    text = json.dumps([{"id": str(uuid.uuid4()), "name": "a", "host": "h", "port": 1}])
    file.write_text(text, encoding="utf-8")

    _fresh_manager(tmp_path)

    assert file.read_text(encoding="utf-8") == text
