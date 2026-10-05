# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The BFF's single playbook run: state, progress messages, stop, errors."""

from __future__ import annotations

import time

import pytest

from bff.playbook_runs import PlaybookBusy, PlaybookRuns
from bff.playbook_store import PlaybookStore

from .test_playbook_module import TinyBff

pytestmark = pytest.mark.unit

READ = {"label": "Read", "read": {"fsp": "F", "ref": "LD0/X.st"}}


@pytest.fixture
def store(tmp_path):
    s = PlaybookStore(tmp_path / "builtin", tmp_path / "saved")
    s.save("quick", {"name": "Quick", "steps": [READ, {"wait": 0}]})
    s.save("slow", {"steps": [{"wait": "30s"}, READ]})
    s.save("unknownfsp", {"steps": [{"read": {"fsp": "Nobody", "ref": "R"}}]})
    return s


def test_a_run_publishes_each_change_and_passes(store):
    published = []
    runs = PlaybookRuns(store, lambda playbook: TinyBff())
    initial = runs.start("quick", pace=0, publish=published.append)
    runs.join(5)

    assert initial["name"] == "quick" and initial["title"] == "Quick"
    assert [s["label"] for s in initial["steps"]] == ["Read", "wait 0"]
    final = runs.state()
    assert final["state"] == "passed" and final["current"] is None and final["error"] is None
    assert [s["status"] for s in final["steps"]] == ["ok", "ok"]
    assert published[-1] == final
    assert any(p["steps"][0]["status"] == "running" for p in published)
    # The "all pending" state is published first - before any step update, and
    # before start() even starts the worker thread (so a slow browser can't
    # see a step update, or the final state, before it).
    assert published[0] == initial
    assert published[0]["steps"][0]["status"] == "pending"


def test_one_run_at_a_time_and_stop(store):
    runs = PlaybookRuns(store, lambda playbook: TinyBff())
    runs.start("slow", pace=0)
    with pytest.raises(PlaybookBusy):
        runs.start("quick")
    time.sleep(0.1)
    runs.stop()
    runs.join(5)
    state = runs.state()
    assert state["state"] == "stopped"
    assert [s["status"] for s in state["steps"]] == ["ok", "pending"]
    runs.start("quick", pace=0)  # free again
    runs.join(5)


def test_a_playbook_that_cannot_run_ends_in_error(store):
    runs = PlaybookRuns(store, lambda playbook: TinyBff())
    runs.start("unknownfsp", pace=0)
    runs.join(5)
    state = runs.state()
    assert state["state"] == "error" and "Nobody" in state["error"]
    assert state["steps"][0]["status"] == "failed"


def test_start_errors(store):
    runs = PlaybookRuns(store, lambda playbook: TinyBff())
    with pytest.raises(KeyError):
        runs.start("missing")
    assert runs.state() is None
