# SPDX-FileCopyrightText: 2025-2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""bff.playbook: parsing, dumping and step labels (the runner itself is
covered by examples/rti-demo/tests/test_playbook.py)."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from bff.playbook import (
    PlaybookError,
    Runner,
    control_value,
    dump_playbook,
    load_playbook,
    parse_playbook,
    step_label,
)

pytestmark = pytest.mark.unit

DEMO = Path(__file__).resolve().parents[3] / "playbooks" / "demo.yaml"


def test_parse_yaml_and_json():
    assert parse_playbook("steps:\n  - wait: 1s\n")["steps"] == [{"wait": "1s"}]
    assert parse_playbook('{"steps": [{"wait": 1}]}', "json")["steps"] == [{"wait": 1}]


def test_parse_rejects_bad_text_and_bad_structure():
    with pytest.raises(PlaybookError, match="not valid YAML"):
        parse_playbook("steps: [", "yaml")
    with pytest.raises(PlaybookError, match="not valid JSON"):
        parse_playbook("{", "json")
    with pytest.raises(PlaybookError, match="non-empty 'steps'"):
        parse_playbook("name: x\n")


def test_dump_round_trips_demo_and_keeps_key_order():
    demo = load_playbook(DEMO)
    text = dump_playbook(demo)
    assert parse_playbook(text) == demo
    assert text.index("name:") < text.index("pace:") < text.index("steps:")


def test_dump_orders_step_keys_label_action_expect():
    text = dump_playbook(
        {"steps": [{"expect": "fail", "read": {"fsp": "F", "ref": "R"}, "label": "L"}]}
    )
    assert text.index("label:") < text.index("read:") < text.index("expect:")


def test_dump_keeps_on_off_strings():
    playbook = {
        "steps": [
            {"operate": {"fsp": "F", "ref": "R", "cdc": "SPC", "value": "on"}},
            {"write": {"fsp": "F", "ref": "R", "value": "off"}},
        ]
    }
    assert parse_playbook(dump_playbook(playbook)) == playbook


def test_step_label():
    assert step_label({"label": "Hi", "wait": 1}) == "Hi"
    assert step_label({"wait": "5s"}) == "wait 5s"


def test_control_value_eng_sends_an_int_for_a_number_else_the_text_enumerated():
    assert control_value("ENG", "3") == (3, "enumerated")
    assert control_value("ENG", "-1") == (-1, "enumerated")
    assert control_value("ENG", "+2") == (2, "enumerated")
    assert control_value("ENG", "open") == ("open", "enumerated")


def test_control_value_apc_is_unchanged():
    assert control_value("APC", "1.5") == (1.5, "float32")
    assert (
        step_label({"read": {"fsp": ["F1", "F2"], "ref": "LD0/X.st"}})
        == "read F1, F2 LD0/X.st"
    )
    assert (
        step_label({"enable-report": {"fsp": "F1", "rcb": {"F1": "R"}}})
        == "enable-report F1"
    )


class TinyBff:
    """Just enough BFF for wait / read / link-unlink steps."""

    base_url = "http://tiny"

    def __init__(self):
        self.linked = {"cp1"}
        self.calls = []

    def connections(self):
        return [
            {"name": "SO", "type": "RTI-SO", "host": "so", "port": 1, "ws_port": 2},
            {"name": "F", "type": "RTI-FSP", "host": "f", "port": 3},
        ]

    def execute(self, target, method, path, body=None):
        self.calls.append(path)
        if path == "/api/status":
            return True, {"result": {"status": {"accessPoints": ["cp1"]}}}
        if path == "/api/properties":
            return True, {"result": {"acsi_client_list": sorted(self.linked)}}
        if path == "/api/stop":
            self.linked.discard("cp1")
            return True, {"result": {"ok": True}}
        if path == "/api/start":
            self.linked.add("cp1")
            return True, {"result": {"ok": True}}
        if path == "/api/readvalue":
            return True, {"result": {"ok": True, "value": [{"data": ["int32", 1]}]}}
        raise AssertionError(path)


READ = {"read": {"fsp": "F", "ref": "LD0/X.st"}}


def test_on_step_and_on_result_report_each_step():
    started, done = [], []
    runner = Runner(
        {"steps": [READ, {"label": "Pause", "wait": 0}]},
        TinyBff(),
        pace=0,
        log=lambda _: None,
        on_step=lambda i, label: started.append((i, label)),
        on_result=done.append,
    )
    runner.run()
    assert started == [(1, "read F LD0/X.st"), (2, "Pause")]
    assert [(r.index, r.ok) for r in done] == [(1, True), (2, True)]
    assert runner.stopped is False


def test_stop_interrupts_a_wait():
    stop = threading.Event()
    runner = Runner(
        {"steps": [{"wait": "30s"}, READ]},
        TinyBff(),
        pace=0,
        log=lambda _: None,
        stop=stop,
    )
    timer = threading.Timer(0.1, stop.set)
    timer.start()
    started = time.monotonic()
    results = runner.run()
    assert time.monotonic() - started < 5
    assert [r.index for r in results] == [1]
    assert results[0].message == "stopped during wait 30s"
    assert runner.stopped is True


def test_stop_skips_the_relink_of_a_drop():
    stop = threading.Event()
    bff = TinyBff()
    runner = Runner(
        {"steps": [{"drop": {"fsp": "F", "for": "30s"}}]},
        bff,
        pace=0,
        log=lambda _: None,
        stop=stop,
    )
    threading.Timer(0.1, stop.set).start()
    results = runner.run()
    assert results[0].ok is False and results[0].message == "stopped"
    assert "/api/start" not in bff.calls
    assert runner.stopped is True


def test_injected_sleep_still_used():
    slept = []
    Runner(
        {"steps": [{"wait": 2}]},
        TinyBff(),
        pace=0,
        log=lambda _: None,
        sleep=slept.append,
    ).run()
    assert slept == [2.0]
