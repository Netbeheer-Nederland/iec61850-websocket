# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""/api/playbooks endpoints, against the real app with a temp store."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_tmp_connections_file = Path(tempfile.mkdtemp()) / "connections.json"
_tmp_connections_file.write_text("[]", encoding="utf-8")
os.environ.setdefault("BFF_CONNECTIONS_FILE", str(_tmp_connections_file))

from fastapi.testclient import TestClient  # noqa: E402

from bff import bff_server  # noqa: E402
from bff.playbook_runs import PlaybookRuns  # noqa: E402
from bff.playbook_store import PlaybookStore  # noqa: E402

from .test_playbook_module import TinyBff  # noqa: E402

pytestmark = pytest.mark.unit

REC = {"name": "Rec", "steps": [{"label": "Read", "read": {"fsp": "F", "ref": "LD0/X.st"}}]}


@pytest.fixture
def client(tmp_path, monkeypatch):
    builtin = tmp_path / "builtin"
    builtin.mkdir()
    (builtin / "demo.yaml").write_text("name: Demo\nsteps:\n  - wait: 0\n", encoding="utf-8")
    store = PlaybookStore(builtin, tmp_path / "saved")
    monkeypatch.setattr(bff_server, "playbook_store", store)
    monkeypatch.setattr(bff_server, "playbook_runs", PlaybookRuns(store, lambda playbook: TinyBff()))
    return TestClient(bff_server.app)


def test_list_get_and_download(client):
    assert client.get("/api/playbooks").json()["playbooks"] == [
        {"name": "demo", "builtin": True, "title": "Demo", "steps": 1}
    ]
    body = client.get("/api/playbooks/demo").json()
    assert body["builtin"] is True and body["labels"] == ["wait 0"]
    r = client.get("/api/playbooks/demo/file")
    assert r.status_code == 200 and r.text.startswith("name: Demo")
    assert r.headers["content-disposition"] == 'attachment; filename="demo.yaml"'


def test_save_recording_and_upload(client):
    assert client.put("/api/playbooks/rec1", json={"playbook": REC}).json() == {"ok": True, "name": "rec1"}
    assert client.get("/api/playbooks/rec1").json()["playbook"] == REC
    r = client.put("/api/playbooks/up", json={"text": '{"steps": [{"wait": 1}]}', "format": "json"})
    assert r.status_code == 200
    assert client.get("/api/playbooks/up/file").text.startswith("steps:")


def test_save_errors(client):
    r = client.put("/api/playbooks/bad", json={"text": "steps: [", "format": "yaml"})
    assert r.status_code == 400 and "not valid YAML" in r.json()["error"]
    assert client.put("/api/playbooks/bad", json={}).status_code == 400
    assert client.put("/api/playbooks/demo", json={"playbook": REC}).status_code == 409
    assert client.put("/api/playbooks/a%20b", json={"playbook": REC}).status_code == 400


def test_delete(client):
    client.put("/api/playbooks/rec1", json={"playbook": REC})
    assert client.delete("/api/playbooks/rec1").json() == {"ok": True}
    assert client.delete("/api/playbooks/rec1").status_code == 404
    assert client.delete("/api/playbooks/demo").status_code == 409


def test_run_state_and_stop(client):
    assert client.get("/api/playbooks/run").json() == {"ok": True, "run": None}
    client.put("/api/playbooks/slow", json={"playbook": {"steps": [{"wait": "30s"}]}})
    r = client.post("/api/playbooks/slow/run", json={"pace": 0})
    assert r.status_code == 200 and r.json()["run"]["state"] == "running"
    assert client.post("/api/playbooks/demo/run").status_code == 409
    client.post("/api/playbooks/run/stop")
    bff_server.playbook_runs.join(5)
    assert client.get("/api/playbooks/run").json()["run"]["state"] == "stopped"


def test_run_errors(client):
    assert client.post("/api/playbooks/missing/run").status_code == 404
    assert client.post("/api/playbooks/demo/run", json={"pace": "soon"}).status_code == 400
