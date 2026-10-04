# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the playbook runner (playbooks/run.py), against a fake BFF.

The same runner drives the live stack in tests/integration/test_playbook.py.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_RUN = Path(__file__).resolve().parents[1] / "playbooks" / "run.py"
_spec = importlib.util.spec_from_file_location("rti_playbook_run", _RUN)
run = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = run  # its dataclasses look their module up there
_spec.loader.exec_module(run)

DEMO = Path(__file__).resolve().parents[1] / "playbooks" / "demo.yaml"


class FakeBff:
    """Enough of the BFF and its instances for the runner: links, reads,
    operates, report control blocks, and the SO's report frames."""

    def __init__(self):
        self.base_url = "http://fake-bff"
        self.calls = []
        self.linked = set()
        self.rcbs = {}
        self.frames = []
        self.read_values = {}
        self.operate_answer = {"ok": True, "error": ""}
        self.reports_per_wait = {}

    def connections(self):
        return [
            {"name": "SO", "type": "RTI-SO", "host": "so", "port": 5002, "ws_port": 8765, "status": "connected"},
            {"name": "FSP01", "type": "RTI-FSP", "host": "f1", "port": 5001, "status": "connected"},
            {"name": "FSP02", "type": "RTI-FSP", "host": "f2", "port": 5005, "status": "connected"},
        ]

    def _report(self, cp):
        self.frames.append({"id": len(self.frames) + 1, "category": "unconfirmed", "direction": "recv", "cp": cp})

    def execute(self, target, method, path, body=None):
        self.calls.append((target, method, path, body))
        cps = {"f1:5001": "cp1", "f2:5005": "cp2"}
        if path == "/api/status":
            return True, {"ok": True, "result": {"ok": True, "status": {"status": "listening", "accessPoints": [cps[target]]}}}
        if path == "/api/start":
            self.linked.add(cps[target])
            return True, {"ok": True, "result": {"ok": True, "status": "listening"}}
        if path == "/api/stop":
            self.linked.discard(cps[target])
            return True, {"ok": True, "result": {"ok": True, "status": "stopped"}}
        if path == "/api/properties":
            return True, {"ok": True, "result": {"ok": True, "acsi_client_list": sorted(self.linked)}}
        if path == "/api/readvalue":
            value = self.read_values.get(body["objRef"], [{"data": ["int32", 1]}])
            return True, {"ok": True, "result": {"ok": True, "success": True, "value": value}}
        if path in ("/api/operate", "/api/select"):
            return True, {"ok": True, "result": dict(self.operate_answer)}
        if path.endswith("-read"):
            enabled = self.rcbs.get(body["objRef"], False)
            return True, {"ok": True, "result": {"ok": True, "value": {"dataSet": "DS", "intgPd": 1000, "rptEna": enabled, "optFlds": {}, "trgOp": {"integrity": True}}}}
        if path.endswith("-write"):
            self.rcbs[body["objRef"]] = body["data"]["rptEna"]
            if body["data"]["rptEna"]:
                self._report(body["cp"])
            return True, {"ok": True, "result": {"ok": True, "success": True, "value": True}}
        if path == "/api/messages":
            return True, {"ok": True, "result": {"ok": True, "messages": list(self.frames)}}
        raise AssertionError(f"unexpected call {method} {path}")


def make_runner(playbook, bff=None, log=None):
    bff = bff or FakeBff()
    lines = log if log is not None else []

    def fake_sleep(seconds):
        # A wait while an RCB is on: the FSP keeps reporting (1 per second).
        for rcb, on in bff.rcbs.items():
            if on:
                cp = "cp2" if rcb.startswith("GenericIO") else "cp1"
                for _ in range(int(seconds)):
                    bff._report(cp)

    return run.Runner(playbook, transport=bff, pace=0, log=lines.append, sleep=fake_sleep), bff, lines


def test_demo_playbook_is_valid_and_runs_end_to_end():
    runner, bff, lines = make_runner(run.load_playbook(DEMO))
    results = runner.run()

    assert [r.ok for r in results] == [True] * len(results), lines
    assert len(results) == 13
    # 1 sent on enabling (step 6) + 5 during the wait.
    assert results[6].message == "6 report(s) from FSP02"
    assert bff.linked == {"cp1", "cp2"}
    assert bff.rcbs == {"GenericIO/LLN0.EventsRCB": False, "LD0/LLN0.rcbActualValues": False}
    assert lines[-1] == "13/13 steps ok"


def test_read_on_several_fsps_uses_each_ones_ref_and_cp():
    runner, bff, _ = make_runner({"steps": [{"read": {"fsp": ["FSP01", "FSP02"], "ref": {"FSP01": "LD0/A.stVal", "FSP02": "GenericIO/B.stVal"}, "fc": "st"}}]})
    [result] = runner.run()

    assert result.ok
    reads = [c for c in bff.calls if c[2] == "/api/readvalue"]
    assert [(c[0], c[3]) for c in reads] == [
        ("so:5002", {"objRef": "LD0/A.stVal", "fc": "st", "cp": "cp1"}),
        ("so:5002", {"objRef": "GenericIO/B.stVal", "fc": "st", "cp": "cp2"}),
    ]


def test_a_read_the_fsp_refused_fails_the_step_and_stops_the_run():
    bff = FakeBff()
    bff.read_values["LD0/X.stVal"] = "instance-not-available"
    runner, _, lines = make_runner({"steps": [
        {"read": {"fsp": "FSP01", "ref": "LD0/X.stVal"}},
        {"read": {"fsp": "FSP01", "ref": "LD0/Y.stVal"}},
    ]}, bff)
    results = runner.run()

    assert [(r.ok, r.message) for r in results] == [(False, "instance-not-available")]
    assert "stopped at the first failed step" in lines[-2]


def test_keep_going_runs_on_after_a_failure():
    bff = FakeBff()
    bff.read_values["LD0/X.stVal"] = "instance-not-available"
    runner, _, _ = make_runner({"steps": [
        {"read": {"fsp": "FSP01", "ref": "LD0/X.stVal"}},
        {"read": {"fsp": "FSP01", "ref": "LD0/Y.stVal"}},
    ]}, bff)
    assert [r.ok for r in runner.run(keep_going=True)] == [False, True]


def test_operate_sends_what_the_hmi_sends():
    runner, bff, _ = make_runner({"steps": [{"operate": {"fsp": "FSP02", "ref": "GenericIO/GGIO1.SPCSO1", "cdc": "SPC", "value": "on"}}]})
    assert runner.run()[0].ok
    body = next(c[3] for c in bff.calls if c[2] == "/api/operate")
    assert body == {
        "objRef": "GenericIO/GGIO1.SPCSO1", "value": True, "value_type": "boolean",
        "ctlNum": 0, "origin": {"orCat": 2, "orIdent": "playbook"}, "test": False, "cp": "cp2",
    }


def test_expect_fail_passes_on_a_refused_operate():
    bff = FakeBff()
    bff.operate_answer = {"ok": False, "error": "blocked-by-interlocking"}
    runner, _, _ = make_runner({"steps": [
        {"operate": {"fsp": "FSP02", "ref": "GenericIO/GGIO1.SPCSO1", "cdc": "SPC", "value": "on"}, "expect": "fail"},
    ]}, bff)
    [result] = runner.run()
    assert result.ok
    assert result.message == "refused as expected: blocked-by-interlocking"


def test_reports_expectation_counts_only_new_reports():
    bff = FakeBff()
    bff._report("cp2")  # one already there before the step
    runner, _, _ = make_runner({"steps": [{"wait": "1s", "expect": {"reports": {"fsp": "FSP02", "min": 1}}}]}, bff)
    [result] = runner.run()
    assert not result.ok
    assert result.message == "0 report(s) from FSP02, expected at least 1"


def test_enable_report_leaves_an_enabled_rcb_alone():
    bff = FakeBff()
    bff.rcbs["GenericIO/LLN0.EventsRCB"] = True
    runner, _, _ = make_runner({"steps": [{"enable-report": {"fsp": "FSP02", "rcb": "GenericIO/LLN0.EventsRCB", "type": "URCB"}}]}, bff)
    [result] = runner.run()
    assert (result.ok, result.message) == (True, "already enabled")
    assert not [c for c in bff.calls if c[2].endswith("-write")]


def test_cps_can_be_given_in_the_playbook():
    runner, bff, _ = make_runner({"cps": {"FSP01": "custom1"}, "steps": [{"read": {"fsp": "FSP01", "ref": "LD0/A.stVal"}}]})
    runner.run()
    assert next(c[3]["cp"] for c in bff.calls if c[2] == "/api/readvalue") == "custom1"
    assert not [c for c in bff.calls if c[2] == "/api/status"]


@pytest.mark.parametrize(
    ("playbook", "message"),
    [
        ({}, "non-empty 'steps'"),
        ({"steps": [{"read": {}, "link": {}}]}, "exactly one of"),
        ({"steps": [{"reed": {"fsp": "FSP01"}}]}, "unknown: reed"),
    ],
)
def test_invalid_playbooks_are_rejected(playbook, message):
    with pytest.raises(run.PlaybookError, match=message):
        run.validate_playbook(playbook)


def test_an_unknown_fsp_is_a_playbook_error():
    runner, _, _ = make_runner({"steps": [{"read": {"fsp": "FSP09", "ref": "LD0/A.stVal"}}]})
    with pytest.raises(run.PlaybookError, match="FSP09"):
        runner.run()


@pytest.mark.parametrize(("text", "seconds"), [(5, 5.0), ("5s", 5.0), ("500ms", 0.5), ("1.5s", 1.5), ("2m", 120.0)])
def test_parse_duration(text, seconds):
    assert run.parse_duration(text) == seconds


@pytest.mark.parametrize(
    ("cdc", "value", "expected"),
    [("SPC", "on", (True, "boolean")), ("DPC", "off", (False, "boolean")), ("APC", "50", (50.0, "float32")),
     ("INC", "3", (3, "int32")), ("BSC", "up", ("stepUp", "string")), ("ENG", "2", (2, "enumerated"))],
)
def test_control_value_matches_the_hmi(cdc, value, expected):
    assert run.control_value(cdc, value) == expected


def test_link_and_unlink_are_fine_when_already_so():
    bff = FakeBff()
    bff.linked = {"cp1"}
    runner, _, _ = make_runner({"steps": [{"link": {"fsp": "FSP01"}}, {"unlink": {"fsp": "FSP02"}}]}, bff)
    results = runner.run()

    assert [(r.ok, r.message) for r in results] == [(True, "already linked on cp1"), (True, "already unlinked (cp2)")]
    assert not [c for c in bff.calls if c[2] in ("/api/start", "/api/stop")]


def test_a_wait_counts_the_reports_its_previous_step_set_off():
    # Enabling the RCB makes the FSP send its values at once - during the
    # enable step itself, before the wait starts.
    runner, bff, _ = make_runner({"steps": [
        {"enable-report": {"fsp": "FSP01", "rcb": "LD0/LLN0.rcbActualValues", "type": "URCB"}},
        {"wait": "0s", "expect": {"reports": {"fsp": "FSP01", "min": 1}}},
    ]})
    results = runner.run()
    assert [(r.ok, r.message) for r in results][1] == (True, "1 report(s) from FSP01")


def test_reports_are_counted_by_frame_id_not_by_total():
    # The SO keeps a bounded log: an old report dropping off as a new one
    # arrives leaves the total unchanged.
    bff = FakeBff()
    bff._report("cp1")
    runner, _, _ = make_runner({"steps": [{"wait": "0s", "expect": {"reports": {"fsp": "FSP01", "min": 1}}}]}, bff)
    original_sleep = runner.sleep

    def drop_oldest_and_report(seconds):
        original_sleep(seconds)
        bff.frames.pop(0)
        bff.frames.append({"id": 99, "category": "unconfirmed", "direction": "recv", "cp": "cp1"})

    runner.sleep = drop_oldest_and_report
    [result] = runner.run()
    assert (result.ok, result.message) == (True, "1 report(s) from FSP01")
