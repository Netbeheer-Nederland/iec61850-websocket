# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The BFF's playbook store: built-in (read-only) and saved playbooks."""

from __future__ import annotations

import pytest
from bff.playbook import PlaybookError
from bff.playbook_store import BuiltinPlaybookError, PlaybookNameError, PlaybookStore

pytestmark = pytest.mark.unit

DEMO = "name: The demo\nsteps:\n  - wait: 1s\n  - wait: 2s\n"
REC = {
    "name": "My recording",
    "so": "SO",
    "pace": "2s",
    "steps": [{"label": "Read", "read": {"fsp": "F", "ref": "R"}}],
}


@pytest.fixture
def store(tmp_path):
    builtin = tmp_path / "builtin"
    builtin.mkdir()
    (builtin / "demo.yaml").write_text(DEMO, encoding="utf-8")
    (builtin / "broken.yaml").write_text("steps: [", encoding="utf-8")
    (builtin / "README.md").write_text("not a playbook", encoding="utf-8")
    return PlaybookStore(builtin, tmp_path / "saved")


def test_list_builtin_and_saved(store):
    store.save("rec1", REC)
    assert store.list() == [
        {
            "name": "broken",
            "builtin": True,
            "title": "broken",
            "error": store.list()[0]["error"],
        },
        {"name": "demo", "builtin": True, "title": "The demo", "steps": 2},
        {"name": "rec1", "builtin": False, "title": "My recording", "steps": 1},
    ]
    assert "not valid YAML" in store.list()[0]["error"]


def test_list_without_saved_dir(store):
    assert [p["name"] for p in store.list()] == ["broken", "demo"]


def test_save_get_file_delete(store):
    store.save("rec1", REC)
    assert store.get("rec1") == (REC, False)
    text, filename = store.file("rec1")
    assert filename == "rec1.yaml" and text.startswith("name: My recording")
    store.delete("rec1")
    with pytest.raises(KeyError):
        store.get("rec1")


def test_get_builtin(store):
    playbook, builtin = store.get("demo")
    assert builtin is True and playbook["name"] == "The demo"
    with pytest.raises(PlaybookError):
        store.get("broken")


def test_save_overwrites(store):
    store.save("rec1", REC)
    store.save("rec1", {**REC, "name": "Again"})
    assert store.get("rec1")[0]["name"] == "Again"
    assert [p.name for p in store.saved_dir.iterdir()] == [
        "rec1.yaml"
    ]  # no temp files left


def test_save_refuses_builtin_name(store):
    with pytest.raises(BuiltinPlaybookError):
        store.save("demo", REC)


def test_delete_refuses_builtin_and_unknown(store):
    with pytest.raises(BuiltinPlaybookError):
        store.delete("demo")
    with pytest.raises(KeyError):
        store.delete("nope")


@pytest.mark.parametrize(
    "name", ["", "../x", "a/b", ".hidden", "run", "x" * 65, "has space"]
)
def test_bad_names(store, name):
    with pytest.raises(PlaybookNameError):
        store.save(name, REC)
    with pytest.raises(PlaybookNameError):
        store.get(name)


def test_save_validates(store):
    with pytest.raises(PlaybookError):
        store.save("bad", {"steps": []})
