# SPDX-FileCopyrightText: 2025-2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""Integration test: run the demo playbook (playbooks/demo.yaml) against the
live stack - the same file and runner used to present the demo.

Requires the rti-demo Docker Compose stack running, with the BFF knowing an
SO and FSP01 / FSP02 (as registered through the HMI's Connections page):

    docker compose -f docker-compose.yml up -d
    uv run pytest tests/integration -m integration -k playbook -q

It links both FSPs, enables and disables report control blocks and drops
FSP02 for a while - it leaves both FSPs linked and reporting off. Set
RTI_PLAYBOOK to run another playbook file.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import time
from pathlib import Path

import pytest
import requests

pytestmark = pytest.mark.integration

_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "rti_playbook_run", _ROOT / "playbooks" / "run.py"
)
run = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = run  # its dataclasses look their module up there
_spec.loader.exec_module(run)

PLAYBOOK = Path(os.environ.get("RTI_PLAYBOOK", _ROOT / "playbooks" / "demo.yaml"))
SO_URL = "http://localhost:5000/api"
SO_WS_PORT = 8765


@pytest.fixture(autouse=True)
def _so_listening():
    """The SO's WebSocket server must be up for the playbook's FSPs to dial.

    It starts with the SO, but other integration tests disconnect it in
    their teardown - start it again if needed (refused while it runs).
    """
    try:
        status = requests.get(f"{SO_URL}/status", timeout=5).json().get("status")
        if status not in ("connected", "connecting"):
            requests.post(
                f"{SO_URL}/connect",
                json={"host": "0.0.0.0", "port": SO_WS_PORT},
                timeout=5,
            )
            time.sleep(1)
    except requests.RequestException:
        pass  # the tests skip themselves when the stack isn't running


def test_demo_playbook_runs_clean():
    playbook = run.load_playbook(PLAYBOOK)
    bff = playbook.get("bff", run.DEFAULT_BFF)
    # /api/connections, not /api/health: health probes every registered
    # instance and takes seconds when one is down.
    try:
        requests.get(f"{bff}/api/connections", timeout=5).raise_for_status()
    except requests.RequestException as exc:
        pytest.skip(f"BFF not reachable at {bff}: {exc}")

    lines = []
    results = run.Runner(
        playbook, run.BffTransport(bff), pace=0, log=lines.append
    ).run()

    failed = [r for r in results if not r.ok]
    assert not failed, "\n".join(lines)
    assert len(results) == len(playbook["steps"])


def test_demo_playbook_runs_clean_in_the_bff():
    """The same playbook, run by the BFF the way the HMI's Run button does."""
    bff = run.load_playbook(PLAYBOOK).get("bff", run.DEFAULT_BFF)
    name = PLAYBOOK.stem
    r = requests.post(f"{bff}/api/playbooks/{name}/run", json={"pace": 0}, timeout=10)
    if r.status_code == 404:
        pytest.skip(
            f"{name} is not a playbook the BFF has (only built-in ones run here)"
        )
    assert r.status_code == 200, r.text

    deadline = time.monotonic() + 180
    while True:
        state = requests.get(f"{bff}/api/playbooks/run", timeout=10).json()["run"]
        if state["state"] != "running" or time.monotonic() > deadline:
            break
        time.sleep(1)
    lines = [
        f"{s['index']} {s['status']} {s['label']} · {s['message']}"
        for s in state["steps"]
    ]
    assert state["state"] == "passed", "\n".join(lines + [str(state.get("error"))])
