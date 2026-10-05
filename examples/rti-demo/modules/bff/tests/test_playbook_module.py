# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""bff.playbook: parsing, dumping and step labels (the runner itself is
covered by examples/rti-demo/tests/test_playbook.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from bff.playbook import PlaybookError, dump_playbook, load_playbook, parse_playbook, step_label

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
    text = dump_playbook({"steps": [{"expect": "fail", "read": {"fsp": "F", "ref": "R"}, "label": "L"}]})
    assert text.index("label:") < text.index("read:") < text.index("expect:")


def test_dump_keeps_on_off_strings():
    playbook = {"steps": [{"operate": {"fsp": "F", "ref": "R", "cdc": "SPC", "value": "on"}},
                          {"write": {"fsp": "F", "ref": "R", "value": "off"}}]}
    assert parse_playbook(dump_playbook(playbook)) == playbook


def test_step_label():
    assert step_label({"label": "Hi", "wait": 1}) == "Hi"
    assert step_label({"wait": "5s"}) == "wait 5s"
    assert step_label({"read": {"fsp": ["F1", "F2"], "ref": "LD0/X.st"}}) == "read F1, F2 LD0/X.st"
    assert step_label({"enable-report": {"fsp": "F1", "rcb": {"F1": "R"}}}) == "enable-report F1"
