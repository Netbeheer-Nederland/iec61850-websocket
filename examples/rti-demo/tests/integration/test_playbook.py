# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
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
from pathlib import Path

import pytest
import requests

pytestmark = pytest.mark.integration

_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("rti_playbook_run", _ROOT / "playbooks" / "run.py")
run = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = run  # its dataclasses look their module up there
_spec.loader.exec_module(run)

PLAYBOOK = Path(os.environ.get("RTI_PLAYBOOK", _ROOT / "playbooks" / "demo.yaml"))


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
    results = run.Runner(playbook, run.BffTransport(bff), pace=0, log=lines.append).run()

    failed = [r for r in results if not r.ok]
    assert not failed, "\n".join(lines)
    assert len(results) == len(playbook["steps"])
