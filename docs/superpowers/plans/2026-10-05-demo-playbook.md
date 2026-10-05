# Demo Playbook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record pinned demo-button clicks in the HMI as run.py playbooks, store playbooks in the BFF, and run any playbook (including `demo.yaml`) in the BFF with live per-step progress on Traffic.

**Architecture:** The playbook runner moves from `examples/rti-demo/playbooks/run.py` into the BFF package (`bff/playbook.py`); `run.py` stays as the CLI. The BFF gets a file store (`bff/playbook_store.py`), a single-run manager running the runner in a worker thread (`bff/playbook_runs.py`) and REST endpoints; progress is pushed over the existing `/ws` as `playbook-run` messages. The HMI gets a recorder store fed by `DemoActionsBar` clicks, a `PlaybookBar` (load / run / stop / download / upload / delete / record) above the pinned buttons, and a run-state hook.

**Tech Stack:** Python 3.10+, FastAPI, PyYAML, requests, pytest (uv workspace); React 19, Vite, vitest + Testing Library.

**Spec:** `docs/superpowers/specs/2026-10-05-demo-playbook-design.md`

## Global Constraints

- Pinned buttons (`DemoActionsBar`, `PinActionForm`, `useDemoActions`, localStorage `traffic-demo-actions`) keep their current behavior.
- Playbook file format is run.py's YAML; the HMI never parses or writes YAML (the BFF does).
- Playbook names match `^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$`; `run` is reserved.
- One playbook run at a time in the BFF.
- Recordings are saved with `pace: "2s"`; no timing is recorded.
- A recorded operate carries `origin: {orCat: 1, orIdent: "0"}`.
- `/ws` push message: `{type: "playbook-run", data: <run state>}`.
- Run state: `{name, title, state: running|passed|failed|stopped|error, current, error, steps: [{index, label, status: pending|running|ok|failed, message, seconds}]}`.
- The CLI (`uv run python -m playbooks.run …`) and the existing tests `tests/test_playbook.py`, `tests/integration/test_playbook.py` keep working without edits.
- Every new source file starts with the repo's SPDX + Apache-2.0 header (copy from a neighboring file).
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **A playbook value `"on"` / `"off"` survives save → load.** Unquoted, YAML reads them as booleans and `control_value("SPC", True)` would still work but `"on"` for a write would not; `dump_playbook` must keep them strings. Test: Task 1 `test_dump_keeps_on_off_strings`.
2. **Stop during a long `wait` or `drop`.** A presenter pressing Stop expects it to end now, not after 10 s. Test: Task 2 `test_stop_interrupts_a_wait`, `test_stop_skips_the_relink_of_a_drop`.
3. **An All FSPs click where one FSP refuses and the other succeeds.** One step with `expect: fail` would pass at replay even if the other FSP broke. Expected: split into one ok step and one `expect: fail` step. Test: Task 6 `splits a mixed outcome into an ok and a refused step`.
4. **Uploading a file named like a built-in (`demo.yaml`) or with spaces / odd characters.** Expected: a 409 shown in the bar for the built-in; the name sanitized (`My demo (2).yml` → `My-demo-2`). Tests: Task 3 `test_save_refuses_builtin_name`, Task 6 `uploadName`.
5. **Page reload or second HMI while a run is going.** Expected: the bar shows the running playbook's progress, Run disabled. Test: Task 8 `shows a run already going on load`.

---

### Task 1: Move the runner into the BFF package

**Files:**
- Move: `examples/rti-demo/playbooks/run.py` → `examples/rti-demo/modules/bff/src/bff/playbook.py`
- Create: `examples/rti-demo/playbooks/run.py` (CLI only)
- Modify: `examples/rti-demo/modules/bff/pyproject.toml` (dependency), `uv.lock`
- Test: `examples/rti-demo/modules/bff/tests/test_playbook_module.py`

**Interfaces:**
- Produces (in `bff.playbook`): everything run.py had (`DEFAULT_BFF`, `ACTIONS`, `PlaybookError`, `load_playbook`, `validate_playbook`, `parse_duration`, `control_value`, `so_answer`, `BffTransport`, `StepResult`, `Runner`) plus
  - `parse_playbook(text: str, fmt: str = "yaml") -> dict` — raises `PlaybookError` on bad YAML/JSON or bad structure
  - `dump_playbook(data: dict) -> str` — YAML text
  - `step_label(step: dict) -> str` — the label the runner shows for a step

- [ ] **Step 1: Write the failing tests**

`examples/rti-demo/modules/bff/tests/test_playbook_module.py`:

```python
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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd examples/rti-demo && uv run --package bff pytest modules/bff/tests/test_playbook_module.py -m unit -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'bff.playbook'`

- [ ] **Step 3: Move the file and declare PyYAML**

```bash
cd examples/rti-demo
git mv playbooks/run.py modules/bff/src/bff/playbook.py
```

In `modules/bff/pyproject.toml` add to `dependencies`: `"pyyaml>=6.0",`. Then at the repo root: `uv lock` (the Docker build uses `--frozen`, so the lock must include it).

- [ ] **Step 4: Edit `bff/playbook.py`**

1. Replace the module docstring with:

```python
"""Demo playbooks: a YAML (or JSON) list of steps for one SO and its FSPs,
executed through the BFF the same way the HMI does - so the HMI's Traffic
page shows every step while it runs - and checked as it goes.

Used by the CLI (examples/rti-demo/playbooks/run.py), the integration test,
and the BFF itself (the HMI's Demo Playbook block). Step reference:
examples/rti-demo/playbooks/README.md.
"""
```

2. Remove `import argparse` and `import sys`; add `import yaml` after `import requests`.
3. Delete `_step_range`, `main` and the `if __name__ == "__main__":` block at the end (they go to the new run.py in Step 5).
4. Replace `load_playbook` with `parse_playbook` + `load_playbook`:

```python
def parse_playbook(text: str, fmt: str = "yaml") -> dict[str, Any]:
    """Parse and check playbook text - fmt 'yaml' or 'json'."""
    try:
        data = json.loads(text) if fmt == "json" else yaml.safe_load(text)
    except (ValueError, yaml.YAMLError) as exc:
        raise PlaybookError(f"not valid {fmt.upper()}: {exc}") from exc
    return validate_playbook(data)


def load_playbook(path: str | Path) -> dict[str, Any]:
    """Read and check a playbook file (.yaml / .yml / .json)."""
    path = Path(path)
    return parse_playbook(path.read_text(encoding="utf-8"), "json" if path.suffix.lower() == ".json" else "yaml")
```

5. After `parse_duration`, add:

```python
_TOP_ORDER = ("name", "bff", "so", "pace", "cps", "steps")


def _ordered_step(step: dict[str, Any]) -> dict[str, Any]:
    action = next(k for k in step if k in ACTIONS)
    out: dict[str, Any] = {}
    if "label" in step:
        out["label"] = step["label"]
    out[action] = step[action]
    if "expect" in step:
        out["expect"] = step["expect"]
    return out


def dump_playbook(data: dict[str, Any]) -> str:
    """YAML text for a playbook, keys in reading order (name, so, pace,
    steps; in a step label, the action, expect). Strings like "on" stay
    quoted - PyYAML quotes anything that would read back as another type."""
    ordered = {k: data[k] for k in _TOP_ORDER if k in data}
    ordered.update({k: v for k, v in data.items() if k not in ordered})
    ordered["steps"] = [_ordered_step(s) for s in data["steps"]]
    return yaml.safe_dump(ordered, sort_keys=False, allow_unicode=True, default_flow_style=None, width=120)


def step_label(step: dict[str, Any]) -> str:
    """The label a step is shown with: its own, else what it does."""
    if step.get("label"):
        return str(step["label"])
    action = next((k for k in step if k in ACTIONS), "?")
    spec = step.get(action)
    if action == "wait":
        return f"wait {spec}"
    spec = spec if isinstance(spec, dict) else {}
    names = spec.get("fsp")
    names = names if isinstance(names, list) else [names]
    return f"{action} {', '.join(str(n) for n in names if n)}" + (
        f" {spec['ref']}" if isinstance(spec.get("ref"), str) else ""
    )
```

6. In `Runner.run_step`, use `step_label` for both labels: replace `label = step.get("label") or f"wait {spec}"` with `label = step_label(step)`, and replace the multi-line `label = step.get("label") or f"{action} {', '.join(fsps)}" + (...)` with `label = step_label(step)`.

- [ ] **Step 5: Create the new CLI `playbooks/run.py`**

Copy the SPDX/Apache header from `bff/playbook.py`, then:

```python
"""Run a demo playbook from the command line, through the BFF:

    cd examples/rti-demo
    uv run python -m playbooks.run playbooks/demo.yaml [--pace 2s] [--keep-going]

The runner is bff.playbook - the BFF runs playbooks with it too (the HMI's
Demo Playbook block). The names below are re-exported so the tests that load
this file by path keep working. See playbooks/README.md.
"""

from __future__ import annotations

import argparse
import re
import sys

import requests

from bff.playbook import (  # noqa: F401 - re-exported
    ACTIONS,
    DEFAULT_BFF,
    BffTransport,
    PlaybookError,
    Runner,
    StepResult,
    control_value,
    dump_playbook,
    load_playbook,
    parse_duration,
    parse_playbook,
    so_answer,
    step_label,
    validate_playbook,
)
```

followed by `_step_range`, `main` and the `if __name__ == "__main__":` block exactly as they were in the old run.py (from `git show HEAD:examples/rti-demo/playbooks/run.py`, lines 531–561).

- [ ] **Step 6: Run the new and the existing tests**

```bash
cd examples/rti-demo
uv run --package bff pytest modules/bff/tests/test_playbook_module.py -m unit -q
uv run pytest tests/test_playbook.py -q
uv run python -m playbooks.run --help
```
Expected: all pass (27 existing runner tests unchanged); `--help` prints the usage.

- [ ] **Step 7: Commit**

```bash
git add -A examples/rti-demo/playbooks/run.py examples/rti-demo/modules/bff uv.lock
git commit -m "bff: playbook runner moves into the BFF package; run.py stays the CLI"
```

---

### Task 2: Runner stop and progress callbacks

**Files:**
- Modify: `examples/rti-demo/modules/bff/src/bff/playbook.py` (`Runner`)
- Test: `examples/rti-demo/modules/bff/tests/test_playbook_module.py`

**Interfaces:**
- Consumes: Task 1's `Runner`, `step_label`.
- Produces: `Runner(playbook, transport=None, pace=None, log=print, sleep=None, stop: threading.Event | None = None, on_step: Callable[[int, str], None] | None = None, on_result: Callable[[StepResult], None] | None = None)`; attribute `runner.stopped: bool` (True when a stop ended the run before its last step).

- [ ] **Step 1: Write the failing tests** (append to `test_playbook_module.py`)

```python
import threading
import time

from bff.playbook import Runner


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
    runner = Runner({"steps": [READ, {"label": "Pause", "wait": 0}]}, TinyBff(), pace=0, log=lambda _: None,
                    on_step=lambda i, label: started.append((i, label)), on_result=done.append)
    runner.run()
    assert started == [(1, "read F LD0/X.st"), (2, "Pause")]
    assert [(r.index, r.ok) for r in done] == [(1, True), (2, True)]
    assert runner.stopped is False


def test_stop_interrupts_a_wait():
    stop = threading.Event()
    runner = Runner({"steps": [{"wait": "30s"}, READ]}, TinyBff(), pace=0, log=lambda _: None, stop=stop)
    timer = threading.Timer(0.1, stop.set)
    timer.start()
    started = time.monotonic()
    results = runner.run()
    assert time.monotonic() - started < 5
    assert [r.index for r in results] == [1]
    assert runner.stopped is True


def test_stop_skips_the_relink_of_a_drop():
    stop = threading.Event()
    bff = TinyBff()
    runner = Runner({"steps": [{"drop": {"fsp": "F", "for": "30s"}}]}, bff, pace=0, log=lambda _: None, stop=stop)
    threading.Timer(0.1, stop.set).start()
    results = runner.run()
    assert results[0].ok is False and results[0].message == "stopped"
    assert "/api/start" not in bff.calls


def test_injected_sleep_still_used():
    slept = []
    Runner({"steps": [{"wait": 2}]}, TinyBff(), pace=0, log=lambda _: None, sleep=slept.append).run()
    assert slept == [2.0]
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd examples/rti-demo && uv run --package bff pytest modules/bff/tests/test_playbook_module.py -m unit -q`
Expected: FAIL — `TypeError: Runner.__init__() got an unexpected keyword argument 'on_step'` (and `stop`).

- [ ] **Step 3: Implement**

In `bff/playbook.py` add `import threading`. Change `Runner.__init__`'s signature and the start of its body:

```python
    def __init__(
        self,
        playbook: dict[str, Any],
        transport: Any = None,
        pace: float | None = None,
        log: Callable[[str], None] = print,
        sleep: Callable[[float], Any] | None = None,
        stop: threading.Event | None = None,
        on_step: Callable[[int, str], None] | None = None,
        on_result: Callable[[StepResult], None] | None = None,
    ):
        self.playbook = validate_playbook(playbook)
        self.transport = transport or BffTransport(playbook.get("bff", DEFAULT_BFF))
        self.pace = parse_duration(playbook.get("pace", 0)) if pace is None else pace
        self.log = log
        # Every pause waits on the stop event, so Stop ends a wait at once.
        self.stop = stop or threading.Event()
        self.sleep = sleep if sleep is not None else self.stop.wait
        self.on_step = on_step
        self.on_result = on_result
        self.stopped = False
```

(keep the remaining lines of `__init__` — `_instances`, `_cps`, `_marks` — as they are).

In `_wait_for_link`, first line inside `while True:`:

```python
            if self.stop.is_set():
                return False
```

In `do_drop`, after `self.sleep(parse_duration(spec.get("for", 10)))`:

```python
        if self.stop.is_set():
            return False, "stopped"
```

In `run`, inside the `for` loop after the `only` filter:

```python
            if self.stop.is_set():
                self.stopped = True
                self.log("stopped")
                break
```

and replace `result = self.run_step(index, step)` / `results.append(result)` with:

```python
            if self.on_step:
                self.on_step(index, step_label(step))
            result = self.run_step(index, step)
            results.append(result)
            if self.on_result:
                self.on_result(result)
```

- [ ] **Step 4: Run tests**

```bash
cd examples/rti-demo
uv run --package bff pytest modules/bff/tests/test_playbook_module.py -m unit -q
uv run pytest tests/test_playbook.py -q
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add examples/rti-demo/modules/bff
git commit -m "bff: playbook runner can be stopped mid-wait and reports each step"
```

---

### Task 3: Playbook store

**Files:**
- Create: `examples/rti-demo/modules/bff/src/bff/playbook_store.py`
- Test: `examples/rti-demo/modules/bff/tests/test_playbook_store.py`

**Interfaces:**
- Consumes: `bff.playbook.load_playbook`, `validate_playbook`, `dump_playbook`, `PlaybookError`.
- Produces:
  - `PlaybookNameError(ValueError)`, `BuiltinPlaybookError(Exception)`, `check_name(name: str) -> str`
  - `PlaybookStore(builtin_dir, saved_dir)` with
    - `list() -> list[dict]` — `{name, builtin, title, steps}` or `{name, builtin, title, error}`; built-in first, each group sorted by name
    - `get(name) -> tuple[dict, bool]` — (playbook, builtin); `KeyError` unknown, `PlaybookNameError`, `PlaybookError` broken file
    - `file(name) -> tuple[str, str]` — (text, file name)
    - `save(name, playbook: dict) -> None` — `PlaybookNameError`, `BuiltinPlaybookError`, `PlaybookError`
    - `delete(name) -> None` — `KeyError`, `BuiltinPlaybookError`, `PlaybookNameError`

- [ ] **Step 1: Write the failing tests**

`examples/rti-demo/modules/bff/tests/test_playbook_store.py`:

```python
# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The BFF's playbook store: built-in (read-only) and saved playbooks."""

from __future__ import annotations

import pytest

from bff.playbook import PlaybookError
from bff.playbook_store import BuiltinPlaybookError, PlaybookNameError, PlaybookStore

pytestmark = pytest.mark.unit

DEMO = "name: The demo\nsteps:\n  - wait: 1s\n  - wait: 2s\n"
REC = {"name": "My recording", "so": "SO", "pace": "2s", "steps": [{"label": "Read", "read": {"fsp": "F", "ref": "R"}}]}


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
        {"name": "broken", "builtin": True, "title": "broken", "error": store.list()[0]["error"]},
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
    assert [p.name for p in store.saved_dir.iterdir()] == ["rec1.yaml"]  # no temp files left


def test_save_refuses_builtin_name(store):
    with pytest.raises(BuiltinPlaybookError):
        store.save("demo", REC)


def test_delete_refuses_builtin_and_unknown(store):
    with pytest.raises(BuiltinPlaybookError):
        store.delete("demo")
    with pytest.raises(KeyError):
        store.delete("nope")


@pytest.mark.parametrize("name", ["", "../x", "a/b", ".hidden", "run", "x" * 65, "has space"])
def test_bad_names(store, name):
    with pytest.raises(PlaybookNameError):
        store.save(name, REC)
    with pytest.raises(PlaybookNameError):
        store.get(name)


def test_save_validates(store):
    with pytest.raises(PlaybookError):
        store.save("bad", {"steps": []})
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd examples/rti-demo && uv run --package bff pytest modules/bff/tests/test_playbook_store.py -m unit -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'bff.playbook_store'`

- [ ] **Step 3: Implement `bff/playbook_store.py`** (SPDX/Apache header, then)

```python
"""Where the BFF keeps demo playbooks: built-in ones shipped with the repo
(examples/rti-demo/playbooks, read-only) and ones saved from the HMI
(recordings and uploads, on the config volume). A playbook's name is its file
name without the extension; a built-in name can't be saved over."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any

from bff.playbook import PlaybookError, dump_playbook, load_playbook, validate_playbook

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
# "run" would clash with /api/playbooks/run.
RESERVED = {"run"}
SUFFIXES = (".yaml", ".yml", ".json")


class PlaybookNameError(ValueError):
    """A name that can't be a playbook's (paths, odd characters, reserved)."""


class BuiltinPlaybookError(Exception):
    """A change to a built-in playbook."""


def check_name(name: str) -> str:
    if not NAME_RE.fullmatch(name or "") or name in RESERVED:
        raise PlaybookNameError(
            f"invalid playbook name {name!r} - use letters, digits, '_', '.' and '-' (at most 64), not 'run'"
        )
    return name


class PlaybookStore:
    def __init__(self, builtin_dir: str | Path, saved_dir: str | Path):
        self.builtin_dir = Path(builtin_dir)
        self.saved_dir = Path(saved_dir)

    @staticmethod
    def _files(directory: Path, suffixes: tuple[str, ...] = SUFFIXES) -> dict[str, Path]:
        if not directory.is_dir():
            return {}
        found: dict[str, Path] = {}
        for path in sorted(directory.iterdir()):
            if (path.is_file() and path.suffix.lower() in suffixes
                    and NAME_RE.fullmatch(path.stem) and path.stem not in RESERVED):
                found.setdefault(path.stem, path)
        return found

    def _path(self, name: str) -> tuple[Path, bool]:
        check_name(name)
        builtin = self._files(self.builtin_dir)
        if name in builtin:
            return builtin[name], True
        saved = self.saved_dir / f"{name}.yaml"
        if saved.is_file():
            return saved, False
        raise KeyError(name)

    def list(self) -> list[dict[str, Any]]:
        builtin = self._files(self.builtin_dir)
        saved = {n: p for n, p in self._files(self.saved_dir, (".yaml",)).items() if n not in builtin}
        entries = []
        for is_builtin, files in ((True, builtin), (False, saved)):
            for name, path in files.items():
                entry: dict[str, Any] = {"name": name, "builtin": is_builtin}
                try:
                    playbook = load_playbook(path)
                    entry.update(title=str(playbook.get("name") or name), steps=len(playbook["steps"]))
                except (PlaybookError, OSError, ValueError) as exc:
                    entry.update(title=name, error=str(exc))
                entries.append(entry)
        return entries

    def get(self, name: str) -> tuple[dict[str, Any], bool]:
        path, builtin = self._path(name)
        return load_playbook(path), builtin

    def file(self, name: str) -> tuple[str, str]:
        path, _ = self._path(name)
        return path.read_text(encoding="utf-8"), path.name

    def save(self, name: str, playbook: dict[str, Any]) -> None:
        check_name(name)
        if name in self._files(self.builtin_dir):
            raise BuiltinPlaybookError(f"{name!r} is a built-in playbook - save under another name")
        validate_playbook(playbook)
        self.saved_dir.mkdir(parents=True, exist_ok=True)
        # Temp file + rename in the same dir, as connections.json is saved.
        fd, tmp = tempfile.mkstemp(dir=self.saved_dir, prefix=f".{name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(dump_playbook(playbook))
            os.replace(tmp, self.saved_dir / f"{name}.yaml")
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def delete(self, name: str) -> None:
        path, builtin = self._path(name)
        if builtin:
            raise BuiltinPlaybookError(f"{name!r} is a built-in playbook")
        path.unlink()
```

- [ ] **Step 4: Run tests**

Run: `cd examples/rti-demo && uv run --package bff pytest modules/bff/tests/test_playbook_store.py -m unit -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add examples/rti-demo/modules/bff
git commit -m "bff: playbook store - built-in and saved playbooks"
```

---

### Task 4: Playbook run manager

**Files:**
- Create: `examples/rti-demo/modules/bff/src/bff/playbook_runs.py`
- Test: `examples/rti-demo/modules/bff/tests/test_playbook_runs.py`

**Interfaces:**
- Consumes: `PlaybookStore.get`, `Runner` (Task 2 signature), `step_label`, `parse_duration`, `PlaybookError`.
- Produces:
  - `PlaybookBusy(Exception)`
  - `PlaybookRuns(store, transport_factory: Callable[[dict], Any])` with
    - `start(name, *, pace=None, keep_going=False, publish=lambda state: None) -> dict` — the initial run state; raises `KeyError`, `PlaybookNameError`, `PlaybookError` (broken file or bad pace), `PlaybookBusy`
    - `stop() -> None`, `state() -> dict | None` (a copy), `join(timeout=None) -> None`

- [ ] **Step 1: Write the failing tests**

`examples/rti-demo/modules/bff/tests/test_playbook_runs.py`:

```python
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
```

Also add an empty `examples/rti-demo/modules/bff/tests/__init__.py` check: it already exists, so the relative import `from .test_playbook_module import TinyBff` works.

- [ ] **Step 2: Run to verify they fail**

Run: `cd examples/rti-demo && uv run --package bff pytest modules/bff/tests/test_playbook_runs.py -m unit -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'bff.playbook_runs'`

- [ ] **Step 3: Implement `bff/playbook_runs.py`** (SPDX/Apache header, then)

```python
"""The one playbook run the BFF does at a time. The runner is synchronous
(requests, sleeps), so it runs in a worker thread; every change to the run's
state (a step starting, a step done, the run ending) goes to `publish`, which
the BFF turns into a "playbook-run" message on /ws."""

from __future__ import annotations

import copy
import logging
import threading
from collections.abc import Callable
from typing import Any

import requests

from bff.playbook import PlaybookError, Runner, StepResult, parse_duration, step_label
from bff.playbook_store import PlaybookStore

logger = logging.getLogger(__name__)


class PlaybookBusy(Exception):
    """A run was asked for while another one is going."""


class PlaybookRuns:
    def __init__(self, store: PlaybookStore, transport_factory: Callable[[dict[str, Any]], Any]):
        self.store = store
        self.transport_factory = transport_factory
        self._lock = threading.Lock()
        self._state: dict[str, Any] | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._publish: Callable[[dict[str, Any]], None] = lambda state: None

    def state(self) -> dict[str, Any] | None:
        with self._lock:
            return copy.deepcopy(self._state)

    def start(self, name: str, *, pace: Any = None, keep_going: bool = False,
              publish: Callable[[dict[str, Any]], None] = lambda state: None) -> dict[str, Any]:
        playbook, _ = self.store.get(name)
        pace_s = parse_duration(pace) if pace not in (None, "") else None
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise PlaybookBusy(f"playbook {self._state['name']!r} is running")
            self._stop = threading.Event()
            self._publish = publish
            self._state = {
                "name": name,
                "title": str(playbook.get("name") or name),
                "state": "running",
                "current": None,
                "error": None,
                "steps": [
                    {"index": i, "label": step_label(step), "status": "pending", "message": "", "seconds": None}
                    for i, step in enumerate(playbook["steps"], 1)
                ],
            }
            initial = copy.deepcopy(self._state)
            self._thread = threading.Thread(
                target=self._work, args=(playbook, pace_s, keep_going), name=f"playbook-{name}", daemon=True
            )
            self._thread.start()
        return initial

    def stop(self) -> None:
        self._stop.set()

    def join(self, timeout: float | None = None) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def _update(self, change: Callable[[dict[str, Any]], None]) -> None:
        with self._lock:
            change(self._state)
            snapshot = copy.deepcopy(self._state)
        try:
            self._publish(snapshot)
        except Exception:
            logger.exception("publishing the playbook run failed")

    def _work(self, playbook: dict[str, Any], pace: float | None, keep_going: bool) -> None:
        def on_step(index: int, label: str) -> None:
            def change(s):
                s["current"] = index
                s["steps"][index - 1].update(status="running", label=label)
            self._update(change)

        def on_result(r: StepResult) -> None:
            self._update(lambda s: s["steps"][r.index - 1].update(
                status="ok" if r.ok else "failed", message=r.message, seconds=round(r.seconds, 1), label=r.label
            ))

        error = None
        try:
            runner = Runner(playbook, self.transport_factory(playbook), pace=pace, log=logger.info,
                            stop=self._stop, on_step=on_step, on_result=on_result)
            results = runner.run(keep_going=keep_going)
            final = "stopped" if runner.stopped else "passed" if results and all(r.ok for r in results) else "failed"
        except (PlaybookError, requests.RequestException, OSError) as exc:
            final, error = "error", str(exc)
        except Exception as exc:  # a bug - don't leave the run "running" forever
            logger.exception("playbook run failed")
            final, error = "error", f"{type(exc).__name__}: {exc}"

        def finish(s):
            s.update(state=final, error=error, current=None)
            for step in s["steps"]:
                if step["status"] == "running":
                    step.update(status="failed", message=step["message"] or error or "stopped")
        self._update(finish)
```

- [ ] **Step 4: Run tests**

Run: `cd examples/rti-demo && uv run --package bff pytest modules/bff/tests/test_playbook_runs.py modules/bff/tests/test_playbook_module.py -m unit -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add examples/rti-demo/modules/bff
git commit -m "bff: playbook runs - one at a time, in a worker thread, state published"
```

---

### Task 5: BFF playbook endpoints, Docker and compose

**Files:**
- Modify: `examples/rti-demo/modules/bff/src/bff/bff_server.py` (imports; new section before `# -------------------- Dynamic API Execution --------------------`; `openapi_tags`; `__main__`)
- Modify: `examples/rti-demo/modules/bff/src/bff/pydantic_models.py` (two request models)
- Modify: `examples/rti-demo/modules/bff/docker/Dockerfile`, `examples/rti-demo/docker-compose.yml`, `.gitignore`, `examples/rti-demo/modules/bff/README.md`
- Test: `examples/rti-demo/modules/bff/tests/test_playbook_endpoints.py`

**Interfaces:**
- Consumes: `PlaybookStore`, `PlaybookRuns`, `PlaybookBusy`, `parse_playbook`, `step_label`, `BffTransport`.
- Produces (HTTP, errors as `{ok: false, error}` via the existing handler):
  - `GET /api/playbooks` → `{ok, playbooks: [...]}`
  - `GET /api/playbooks/run` → `{ok, run: state|null}`
  - `POST /api/playbooks/run/stop` → `{ok, run}`
  - `GET /api/playbooks/{name}` → `{ok, name, builtin, playbook, labels}`; 400 bad name, 404, 422 broken file
  - `GET /api/playbooks/{name}/file` → text, `Content-Disposition: attachment; filename="<file>"`
  - `PUT /api/playbooks/{name}` body `{playbook}` or `{text, format}` → `{ok, name}`; 400, 409
  - `DELETE /api/playbooks/{name}` → `{ok}`; 400, 404, 409
  - `POST /api/playbooks/{name}/run` body `{pace?, keep_going?}` (optional) → `{ok, run}`; 400, 404, 409
  - module globals `bff_server.playbook_store`, `bff_server.playbook_runs`

- [ ] **Step 1: Write the failing tests**

`examples/rti-demo/modules/bff/tests/test_playbook_endpoints.py`:

```python
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd examples/rti-demo && uv run --package bff pytest modules/bff/tests/test_playbook_endpoints.py -m unit -q`
Expected: FAIL — `AttributeError: ... has no attribute 'playbook_store'`

- [ ] **Step 3: Request models** — append to `pydantic_models.py` (add `Literal` to its `typing` import if missing):

```python
class PlaybookSaveRequest(BaseModel):
    """A playbook to save: a recording as JSON, or an uploaded file's text."""

    playbook: dict[str, Any] | None = Field(default=None, description="The playbook (a recording from the HMI)")
    text: str | None = Field(default=None, description="A playbook file's text (an upload)")
    format: Literal["yaml", "json"] = Field(default="yaml", description="The text's format")


class PlaybookRunRequest(BaseModel):
    """Options for a playbook run."""

    pace: str | float | None = Field(default=None, description="Pause between steps, e.g. 2s (default: the playbook's)")
    keep_going: bool = Field(default=False, description="Run on after a failed step")
```

- [ ] **Step 4: Endpoints in `bff_server.py`**

Imports: add `from pathlib import Path`; extend `from fastapi.responses import JSONResponse` to `JSONResponse, Response`; add

```python
from bff.playbook import BffTransport, PlaybookError, parse_playbook, step_label
from bff.playbook_runs import PlaybookBusy, PlaybookRuns
from bff.playbook_store import BuiltinPlaybookError, PlaybookNameError, PlaybookStore
```

and `PlaybookRunRequest, PlaybookSaveRequest` to the `bff.pydantic_models` import list.

In `openapi_tags` add `{"name": "Playbooks", "description": "Store and run demo playbooks"},`.

Insert before `# -------------------- Dynamic API Execution --------------------`:

```python
# -------------------- Playbooks --------------------

# Built-in playbooks: the repo's examples/rti-demo/playbooks (the Dockerfile
# copies them to the same place in the image). Saved ones (recordings and
# uploads from the HMI) sit next to connections.json - in Docker, on the
# config volume.
playbook_store = PlaybookStore(
    os.environ.get("BFF_PLAYBOOKS_BUILTIN_DIR") or Path(__file__).resolve().parents[4] / "playbooks",
    os.environ.get("BFF_PLAYBOOKS_DIR") or Path(CONNECTIONS_FILE).parent / "playbooks",
)
# A run goes through this BFF's own /api/execute, the path an HMI click takes,
# so Traffic shows every step.
playbook_runs = PlaybookRuns(
    playbook_store, lambda playbook: BffTransport(f"http://localhost:{os.getenv('PORT', '5000')}")
)


def _run_publisher(loop: asyncio.AbstractEventLoop):
    """Push a run's state to every browser - called from the run's thread."""

    def publish(state: dict[str, Any]) -> None:
        asyncio.run_coroutine_threadsafe(ws_hub.broadcast({"type": "playbook-run", "data": state}), loop)

    return publish


# /api/playbooks/run before /api/playbooks/{name}, so "run" isn't taken for a name.
@app.get("/api/playbooks/run", summary="Current playbook run", tags=["Playbooks"])
async def get_playbook_run():
    return {"ok": True, "run": playbook_runs.state()}


@app.post("/api/playbooks/run/stop", summary="Stop the playbook run", tags=["Playbooks"])
async def stop_playbook_run():
    playbook_runs.stop()
    return {"ok": True, "run": playbook_runs.state()}


@app.get("/api/playbooks", summary="List playbooks", tags=["Playbooks"])
async def list_playbooks():
    return {"ok": True, "playbooks": await asyncio.to_thread(playbook_store.list)}


@app.get("/api/playbooks/{name}", summary="Get a playbook", tags=["Playbooks"])
async def get_playbook(name: str):
    try:
        playbook, builtin = playbook_store.get(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"no playbook {name!r}")
    except PlaybookNameError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PlaybookError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {
        "ok": True,
        "name": name,
        "builtin": builtin,
        "playbook": playbook,
        "labels": [step_label(step) for step in playbook["steps"]],
    }


@app.get("/api/playbooks/{name}/file", summary="Download a playbook file", tags=["Playbooks"])
async def download_playbook(name: str):
    try:
        text, filename = playbook_store.file(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"no playbook {name!r}")
    except PlaybookNameError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Response(
        text,
        media_type="application/json" if filename.endswith(".json") else "application/yaml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.put("/api/playbooks/{name}", summary="Save a playbook", tags=["Playbooks"])
async def save_playbook(name: str, request: PlaybookSaveRequest):
    try:
        if request.playbook is not None:
            playbook = request.playbook
        elif request.text is not None:
            playbook = parse_playbook(request.text, request.format)
        else:
            raise HTTPException(status_code=400, detail="send 'playbook', or 'text' with its 'format'")
        playbook_store.save(name, playbook)
    except (PlaybookNameError, PlaybookError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except BuiltinPlaybookError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"ok": True, "name": name}


@app.delete("/api/playbooks/{name}", summary="Delete a saved playbook", tags=["Playbooks"])
async def delete_playbook(name: str):
    try:
        playbook_store.delete(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"no playbook {name!r}")
    except PlaybookNameError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except BuiltinPlaybookError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"ok": True}


@app.post("/api/playbooks/{name}/run", summary="Run a playbook", tags=["Playbooks"])
async def run_playbook(name: str, request: PlaybookRunRequest | None = None):
    request = request or PlaybookRunRequest()
    try:
        state = playbook_runs.start(
            name, pace=request.pace, keep_going=request.keep_going,
            publish=_run_publisher(asyncio.get_running_loop()),
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"no playbook {name!r}")
    except (PlaybookNameError, PlaybookError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PlaybookBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"ok": True, "run": state}
```

In the `__main__` block, right after `args = parser.parse_args()`, add:

```python
    # The playbook runner calls this BFF on its own port.
    os.environ["PORT"] = str(args.port)
```

- [ ] **Step 5: Run the tests**

Run: `cd examples/rti-demo && uv run --package bff pytest modules/bff/tests -m unit -q`
Expected: all pass (new and existing).

- [ ] **Step 6: Docker, compose, gitignore, README**

`modules/bff/docker/Dockerfile`, builder stage, right after `COPY examples/rti-demo/modules/bff/ ./examples/rti-demo/modules/bff/`:

```dockerfile
# Built-in demo playbooks, where bff_server looks for them (next to modules/).
COPY examples/rti-demo/playbooks/*.yaml ./examples/rti-demo/playbooks/
```

`docker-compose.yml`, `rti-bff`: add to `environment`:

```yaml
      # Playbooks saved from the HMI (recordings, uploads), on the config volume.
      - BFF_PLAYBOOKS_DIR=/config/playbooks
```

and to `volumes` (so an edited demo.yaml is picked up without a rebuild, like the code mount):

```yaml
      - ./playbooks:/app/examples/rti-demo/playbooks:ro
```

`.gitignore` (repo root, in the "RTI Demo - local configuration" block): `examples/rti-demo/modules/bff/src/bff/playbooks/` (where saved playbooks land when the BFF runs from source).

`modules/bff/README.md`: add a "Playbooks" section with the endpoint table from this task's Interfaces, the `playbook-run` message, and the env vars `BFF_PLAYBOOKS_DIR` (default: next to the connections file, `playbooks/`) and `BFF_PLAYBOOKS_BUILTIN_DIR` (default: `examples/rti-demo/playbooks`).

- [ ] **Step 7: Check the image**

```bash
cd examples/rti-demo
docker compose build rti-bff && docker compose up -d rti-bff
curl -s localhost:5000/api/playbooks
```
Expected: `{"ok":true,"playbooks":[{"name":"demo","builtin":true,"title":"SO with two FSPs","steps":13}]}`

- [ ] **Step 8: Commit**

```bash
git add .gitignore examples/rti-demo/docker-compose.yml examples/rti-demo/modules/bff
git commit -m "bff: /api/playbooks - list, get, save, upload, delete, run, stop"
```

---

### Task 6: HMI playbook utils (steps from clicks, BFF calls) and the `refused` flag

**Files:**
- Modify: `examples/rti-demo/modules/hmi/src/utils/demoActions.js` (`soAnswer`, `setReporting`)
- Modify: `examples/rti-demo/modules/hmi/src/utils/demoActions.test.js`
- Create: `examples/rti-demo/modules/hmi/src/utils/playbooks.js`
- Test: `examples/rti-demo/modules/hmi/src/utils/playbooks.test.js`

**Interfaces:**
- Consumes: pinned action shape `{id, label, service, soTarget, soName, cp, fspName, objRef, fc?, valueType?, cdc?, rcbType?, value?}`; `buildBffApiUrl` from `services/apiService`.
- Produces:
  - `runAction` / `soAnswer` results gain `refused: true` when the FSP answered and refused (the SO got the request and passed on a refusal).
  - `clicksToSteps(entries) -> { steps: object[], skipped: entry[] }` where `entry = { action, fsp: string, result: {ok, message, refused?} }`
  - `listPlaybooks() -> Promise<object[]>`, `getPlaybook(name) -> Promise<{name, builtin, playbook, labels}>`, `savePlaybook(name, playbook)`, `uploadPlaybook(name, text, format)`, `deletePlaybook(name)`, `runPlaybook(name, options = {}) -> Promise<run state>`, `stopPlaybook()`, `getPlaybookRun() -> Promise<run state|null>`, `playbookFileUrl(name) -> string`, `uploadName(fileName) -> string`, `uploadFormat(fileName) -> 'yaml'|'json'`, `recordingName(date = new Date()) -> string`. API calls throw `Error(<BFF's error>)` on a non-2xx.

- [ ] **Step 1: Write the failing tests**

In `demoActions.test.js`, change these expectations to include `refused: true`:
- `'treats an operate the FSP refused as failed'`: `{ ok: false, message: 'blocked-by-interlocking', refused: true }`
- `'treats a read the FSP refused as failed'`: `{ ok: false, message: 'instanceNotAvailable', refused: true }`
- `'names a refusal without a reason'`: `{ ok: false, message: 'Refused by the FSP', refused: true }`
- `"reports the server's serviceError from the read or the write"`: both — `{ ok: false, message: 'instance-not-available', refused: true }` and `{ ok: false, message: 'parameter-value-inconsistent', refused: true }`

(`'passes the SO request failing through'`, `'fails without writing when the read fails'`, `'reports a failed write'` and the null-result case stay without `refused`.)

`src/utils/playbooks.test.js`:

```js
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/apiService', () => ({
  buildBffApiUrl: (path) => `http://bff${path}`,
}));

import {
  clicksToSteps, listPlaybooks, savePlaybook, uploadPlaybook, runPlaybook, getPlaybookRun,
  playbookFileUrl, uploadName, uploadFormat, recordingName,
} from './playbooks';

const OK = { ok: true, message: 'ok' };
const REFUSED = { ok: false, message: 'blocked', refused: true };
const action = (extra) => ({ id: 'x', label: 'Act', soTarget: 'so:1', soName: 'SO', cp: 'cp1', service: 'read', objRef: 'LD0/A.st', fc: 'st', ...extra });
const entry = (fsp, extra, result = OK) => ({ action: action(extra), fsp, result });

describe('clicksToSteps', () => {
  it('makes a step per service', () => {
    const steps = (extra) => clicksToSteps([entry('F1', extra)]).steps;
    expect(steps({})).toEqual([{ label: 'Act', read: { fsp: 'F1', ref: 'LD0/A.st', fc: 'st' } }]);
    expect(steps({ service: 'write', fc: 'sp', value: '5', valueType: 'int32' }))
      .toEqual([{ label: 'Act', write: { fsp: 'F1', ref: 'LD0/A.st', value: '5', fc: 'sp', type: 'int32' } }]);
    expect(steps({ service: 'operate', fc: undefined, cdc: 'SPC', value: 'on' }))
      .toEqual([{ label: 'Act', operate: { fsp: 'F1', ref: 'LD0/A.st', cdc: 'SPC', value: 'on', origin: { orCat: 1, orIdent: '0' } } }]);
    expect(steps({ service: 'enable-report', fc: undefined, objRef: 'LD0/LLN0.rcb', rcbType: 'urcb' }))
      .toEqual([{ label: 'Act', 'enable-report': { fsp: 'F1', rcb: 'LD0/LLN0.rcb', type: 'URCB' } }]);
    expect(steps({ service: 'disable-report', fc: undefined, objRef: 'R' }))
      .toEqual([{ label: 'Act', 'disable-report': { fsp: 'F1', rcb: 'R', type: 'BRCB' } }]);
  });

  it('turns an All FSPs click into one step with per-FSP values where they differ', () => {
    const { steps } = clicksToSteps([entry('F1', { objRef: 'A' }), entry('F2', { objRef: 'B' })]);
    expect(steps).toEqual([{ label: 'Act', read: { fsp: ['F1', 'F2'], ref: { F1: 'A', F2: 'B' }, fc: 'st' } }]);
  });

  it('records a refusal as expect: fail', () => {
    expect(clicksToSteps([entry('F1', {}, REFUSED)]).steps)
      .toEqual([{ label: 'Act', read: { fsp: 'F1', ref: 'LD0/A.st', fc: 'st' }, expect: 'fail' }]);
  });

  it('splits a mixed outcome into an ok and a refused step', () => {
    const { steps } = clicksToSteps([entry('F1', {}), entry('F2', {}, REFUSED)]);
    expect(steps).toEqual([
      { label: 'Act', read: { fsp: 'F1', ref: 'LD0/A.st', fc: 'st' } },
      { label: 'Act', read: { fsp: 'F2', ref: 'LD0/A.st', fc: 'st' }, expect: 'fail' },
    ]);
  });

  it('splits FSPs whose fc differs, since only ref / rcb / value can be per FSP', () => {
    const { steps } = clicksToSteps([entry('F1', { fc: 'st' }), entry('F2', { fc: 'mx' })]);
    expect(steps.map((s) => s.read.fsp)).toEqual(['F1', 'F2']);
  });

  it('skips clicks that failed for another reason', () => {
    const failed = entry('F1', {}, { ok: false, message: 'Client is not connected' });
    expect(clicksToSteps([failed])).toEqual({ steps: [], skipped: [failed] });
  });
});

describe('file names', () => {
  it('derives a valid playbook name from an uploaded file', () => {
    expect(uploadName('demo.yaml')).toBe('demo');
    expect(uploadName('My demo (2).yml')).toBe('My-demo-2');
    expect(uploadName('..json')).toBe('upload');
    expect(uploadName('run.yaml')).toBe('run-upload');
    expect(uploadFormat('x.JSON')).toBe('json');
    expect(uploadFormat('x.yml')).toBe('yaml');
  });

  it('names a recording after the time', () => {
    expect(recordingName(new Date(2026, 9, 5, 9, 7))).toBe('recording-20261005-0907');
  });
});

describe('BFF calls', () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });
  const answer = (status, body) => fetch.mockResolvedValueOnce({ ok: status < 400, status, json: async () => body });

  it('lists, saves, uploads and runs', async () => {
    answer(200, { ok: true, playbooks: [{ name: 'demo' }] });
    await expect(listPlaybooks()).resolves.toEqual([{ name: 'demo' }]);
    expect(fetch).toHaveBeenLastCalledWith('http://bff/api/playbooks', expect.anything());

    answer(200, { ok: true, name: 'r' });
    await savePlaybook('r', { steps: [] });
    expect(fetch.mock.lastCall[1]).toMatchObject({ method: 'PUT', body: JSON.stringify({ playbook: { steps: [] } }) });

    answer(200, { ok: true, name: 'u' });
    await uploadPlaybook('u', 'steps: []', 'yaml');
    expect(fetch.mock.lastCall[1].body).toBe(JSON.stringify({ text: 'steps: []', format: 'yaml' }));

    answer(200, { ok: true, run: { state: 'running' } });
    await expect(runPlaybook('demo')).resolves.toEqual({ state: 'running' });
    expect(fetch.mock.lastCall[0]).toBe('http://bff/api/playbooks/demo/run');

    answer(200, { ok: true, run: null });
    await expect(getPlaybookRun()).resolves.toBeNull();
  });

  it("throws the BFF's error", async () => {
    answer(409, { ok: false, error: "'demo' is a built-in playbook" });
    await expect(savePlaybook('demo', {})).rejects.toThrow("'demo' is a built-in playbook");
  });

  it('builds the download URL', () => {
    expect(playbookFileUrl('my rec')).toBe('http://bff/api/playbooks/my%20rec/file');
  });
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd examples/rti-demo/modules/hmi && npx vitest run src/utils`
Expected: FAIL — `playbooks.js` missing; the `refused` expectations fail.

- [ ] **Step 3: `refused` in `demoActions.js`**

In `soAnswer`, replace the three non-ok returns with:

```js
  // refused: the SO got the request and the FSP said no - as opposed to the
  // request not getting through. A recording keeps a refusal (expect: fail).
  if (refusedRead) return { ok, message: answer.value, refused: true };
  if (result?.ok && answer?.ok === false && !answer.error) return { ok, message: 'Refused by the FSP', refused: true };
  const message = (typeof answer?.error === 'string' && answer.error) || errorOf(result, 'Request failed');
  return result?.ok && answer ? { ok, message, refused: true } : { ok, message };
```

In `setReporting`, change the read-failure return to:

```js
    const message = read?.ok && typeof current === 'string' ? current : errorOf(read, 'Could not read the report control block');
    return read?.ok && typeof current === 'string' ? { ok: false, message, refused: true } : { ok: false, message };
```

and the final return to:

```js
  if (write?.ok && typeof value === 'string') return { ok: false, message: value, refused: true };
  return { ok: false, message: errorOf(write, failed) };
```

- [ ] **Step 4: Create `src/utils/playbooks.js`** (SPDX/Apache header as in `demoActions.js`, then)

```js
import { buildBffApiUrl } from '../services/apiService';

// Demo playbooks (examples/rti-demo/playbooks/README.md): turning pinned-
// button clicks into playbook steps for a recording, and the BFF's
// /api/playbooks calls. The BFF keeps and runs playbooks; the HMI never
// reads or writes YAML itself.

// The origin a pinned operate sends (buildRequest), so a replay sends the same.
const OPERATE_ORIGIN = { orCat: 1, orIdent: '0' };
// The fields run.py takes per FSP (a map from FSP name to value).
const PER_FSP = ['ref', 'rcb', 'value'];

/** A pinned action's step fields, without `fsp`. */
function specOf(action) {
  const { service } = action;
  if (service === 'read') return { ref: action.objRef, fc: action.fc || 'st' };
  if (service === 'write') {
    return { ref: action.objRef, value: action.value, fc: action.fc || 'sp', ...(action.valueType ? { type: action.valueType } : {}) };
  }
  if (service === 'operate') return { ref: action.objRef, cdc: action.cdc, value: action.value, origin: OPERATE_ORIGIN };
  return { rcb: action.objRef, type: String(action.rcbType || 'BRCB').toUpperCase() };
}

/** One step from clicks that share a label, service, outcome and fixed fields. */
function stepOf(entries, refused) {
  const { service, label } = entries[0].action;
  const specs = entries.map((e) => specOf(e.action));
  const fsps = entries.map((e) => e.fsp);
  const spec = { fsp: fsps.length === 1 ? fsps[0] : fsps };
  Object.keys(specs[0]).forEach((key) => {
    const values = specs.map((s) => s[key]);
    const same = values.every((v) => JSON.stringify(v) === JSON.stringify(values[0]));
    spec[key] = same ? values[0] : Object.fromEntries(fsps.map((f, i) => [f, values[i]]));
  });
  return { label, [service]: spec, ...(refused ? { expect: 'fail' } : {}) };
}

/**
 * Playbook steps for one click on a pinned button (one entry) or on an All
 * FSPs button (an entry per FSP): { steps, skipped }. A refusal is kept, as
 * a step expecting one; a click that didn't get through is skipped. Clicks
 * end up in one step unless their outcome, service or a field run.py can't
 * take per FSP (fc, cdc, type) differs.
 *
 * @param {{action: Object, fsp: string, result: {ok: boolean, message: string, refused?: boolean}}[]} entries
 */
export function clicksToSteps(entries) {
  const skipped = entries.filter((e) => !e.result?.ok && !e.result?.refused);
  const groups = new Map();
  entries.filter((e) => !skipped.includes(e)).forEach((e) => {
    const refused = !e.result.ok;
    const fixed = Object.fromEntries(Object.entries(specOf(e.action)).filter(([k]) => !PER_FSP.includes(k)));
    const key = JSON.stringify([refused, e.action.service, fixed]);
    if (!groups.has(key)) groups.set(key, { refused, entries: [] });
    groups.get(key).entries.push(e);
  });
  return { steps: [...groups.values()].map((g) => stepOf(g.entries, g.refused)), skipped };
}

/** A playbook name for an uploaded file: its base name, made valid. */
export function uploadName(fileName) {
  const name = String(fileName).replace(/\.(ya?ml|json)$/i, '')
    .replace(/[^A-Za-z0-9_.-]+/g, '-').replace(/^[^A-Za-z0-9]+/, '').replace(/-+$/, '').slice(0, 64);
  if (!name) return 'upload';
  return name === 'run' ? 'run-upload' : name;
}

export const uploadFormat = (fileName) => (/\.json$/i.test(fileName) ? 'json' : 'yaml');

const pad = (n) => String(n).padStart(2, '0');
export const recordingName = (date = new Date()) =>
  `recording-${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}-${pad(date.getHours())}${pad(date.getMinutes())}`;

const path = (name, rest = '') => `/api/playbooks/${encodeURIComponent(name)}${rest}`;

async function bff(apiPath, options = {}) {
  const response = await fetch(buildBffApiUrl(apiPath), { headers: { 'Content-Type': 'application/json' }, ...options });
  let body = null;
  try {
    body = await response.json();
  } catch {
    // no JSON body
  }
  if (!response.ok) throw new Error(body?.error || `HTTP ${response.status}`);
  return body;
}

export const listPlaybooks = async () => (await bff('/api/playbooks')).playbooks;
export const getPlaybook = (name) => bff(path(name));
export const savePlaybook = (name, playbook) => bff(path(name), { method: 'PUT', body: JSON.stringify({ playbook }) });
export const uploadPlaybook = (name, text, format) => bff(path(name), { method: 'PUT', body: JSON.stringify({ text, format }) });
export const deletePlaybook = (name) => bff(path(name), { method: 'DELETE' });
export const runPlaybook = async (name, options = {}) =>
  (await bff(path(name, '/run'), { method: 'POST', body: JSON.stringify(options) })).run;
export const stopPlaybook = () => bff('/api/playbooks/run/stop', { method: 'POST' });
export const getPlaybookRun = async () => (await bff('/api/playbooks/run')).run;
export const playbookFileUrl = (name) => buildBffApiUrl(path(name, '/file'));
```

- [ ] **Step 5: Run tests**

Run: `cd examples/rti-demo/modules/hmi && npx vitest run src/utils src/components/ControlModal*`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add examples/rti-demo/modules/hmi/src/utils
git commit -m "hmi: playbook steps from demo-button clicks, BFF playbook calls"
```

---

### Task 7: Recorder store, fed by `DemoActionsBar`

**Files:**
- Create: `examples/rti-demo/modules/hmi/src/hooks/usePlaybookRecorder.js`
- Modify: `examples/rti-demo/modules/hmi/src/components/DemoActionsBar.jsx` (`run`)
- Test: `examples/rti-demo/modules/hmi/src/hooks/usePlaybookRecorder.test.js`, `examples/rti-demo/modules/hmi/src/components/DemoActionsBar.test.jsx`

**Interfaces:**
- Consumes: `clicksToSteps` (Task 6), `runAction` results with `refused`.
- Produces (module `hooks/usePlaybookRecorder.js`):
  - `usePlaybookRecorder() -> { recording: boolean, so: {name, target}|null, steps: object[], notes: string[] }`
  - `startRecording()`, `stopRecording()` (keeps steps), `clearRecording()`, `recordClick(entries)` (no-op unless recording), `recordedPlaybook(title) -> { name, so, pace: '2s', steps }`, `resetPlaybookRecorderStore()` (tests)

- [ ] **Step 1: Write the failing tests**

`src/hooks/usePlaybookRecorder.test.js`:

```js
import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import {
  usePlaybookRecorder, startRecording, stopRecording, recordClick, recordedPlaybook, resetPlaybookRecorderStore,
} from './usePlaybookRecorder';

const OK = { ok: true, message: 'ok' };
const entry = (soTarget, label = 'Read', result = OK) => ({
  action: { label, service: 'read', soTarget, soName: soTarget === 'so:1' ? 'SO' : 'Other SO', objRef: 'R', fc: 'st' },
  fsp: 'F1',
  result,
});

describe('usePlaybookRecorder', () => {
  beforeEach(() => resetPlaybookRecorderStore());

  it('records only while recording', () => {
    const { result } = renderHook(() => usePlaybookRecorder());
    act(() => recordClick([entry('so:1')]));
    expect(result.current.steps).toEqual([]);

    act(() => startRecording());
    act(() => recordClick([entry('so:1')]));
    expect(result.current).toMatchObject({ recording: true, so: { name: 'SO', target: 'so:1' } });
    expect(result.current.steps).toHaveLength(1);

    act(() => stopRecording());
    expect(result.current.recording).toBe(false);
    expect(recordedPlaybook('My demo')).toEqual({
      name: 'My demo', so: 'SO', pace: '2s', steps: [{ label: 'Read', read: { fsp: 'F1', ref: 'R', fc: 'st' } }],
    });
  });

  it('keeps to the first SO and notes what it left out', () => {
    const { result } = renderHook(() => usePlaybookRecorder());
    act(() => startRecording());
    act(() => recordClick([entry('so:1')]));
    act(() => recordClick([entry('so:2', 'Elsewhere')]));
    act(() => recordClick([entry('so:1', 'Broken', { ok: false, message: 'Client is not connected' })]));
    expect(result.current.steps).toHaveLength(1);
    expect(result.current.notes).toEqual([
      'Not recorded: "Elsewhere" is on Other SO - a playbook drives one SO (SO)',
      'Not recorded: "Broken" on F1 failed (Client is not connected)',
    ]);
  });

  it('starts over on a new recording', () => {
    const { result } = renderHook(() => usePlaybookRecorder());
    act(() => startRecording());
    act(() => recordClick([entry('so:1')]));
    act(() => startRecording());
    expect(result.current).toMatchObject({ recording: true, so: null, steps: [], notes: [] });
  });
});
```

Append to `src/components/DemoActionsBar.test.jsx` (inside the `describe`), and add the import `import { startRecording, resetPlaybookRecorderStore, recordedPlaybook } from '../hooks/usePlaybookRecorder';` plus `resetPlaybookRecorderStore();` in the existing `beforeEach`:

```js
  it('records clicks while recording, an All FSPs click as one step', async () => {
    pin([action('1', 'Read status', 'cp1', 'FSP_North'), action('2', 'Read status', 'cp2', 'FSP_South')]);
    render(<DemoActionsBar connections={[SO]} />);
    startRecording();

    fireEvent.click(screen.getByTitle(/Run "Read status" on/));
    await waitFor(() => expect(recordedPlaybook('t').steps).toHaveLength(1));
    expect(recordedPlaybook('t').steps[0]).toEqual({
      label: 'Read status',
      read: { fsp: ['FSP_North', 'FSP_South'], ref: { FSP_North: 'LD0/X1.stVal', FSP_South: 'LD0/X2.stVal' }, fc: 'st' },
    });
    expect(recordedPlaybook('t').so).toBe('Demo_SO');
  });

  it('does not record when not recording', async () => {
    pin([action('1', 'A', 'cp1', 'FSP_North')]);
    render(<DemoActionsBar connections={[SO]} />);
    fireEvent.click(screen.getByText('A'));
    await waitFor(() => expect(executeApiCall).toHaveBeenCalled());
    expect(recordedPlaybook('t').steps).toEqual([]);
  });
```

Note: the test file's `executeApiCall` mock resolves `{ ok: true, payload: {} }`, which `soAnswer` treats as ok for a read (no refusal, no string value).

- [ ] **Step 2: Run to verify they fail**

Run: `cd examples/rti-demo/modules/hmi && npx vitest run src/hooks/usePlaybookRecorder.test.js src/components/DemoActionsBar.test.jsx`
Expected: FAIL — module `./usePlaybookRecorder` not found.

- [ ] **Step 3: Create `src/hooks/usePlaybookRecorder.js`** (SPDX/Apache header, then)

```js
import { useSyncExternalStore } from 'react';
import { clicksToSteps } from '../utils/playbooks';

// The playbook being recorded: one store for the whole page, so clicks on
// the demo bar's pinned buttons land in the Playbook bar's recording. Not
// persisted - a reload ends a recording.

const EMPTY = { recording: false, so: null, steps: [], notes: [] };
let state = EMPTY;
const listeners = new Set();

const set = (next) => {
  state = next;
  listeners.forEach((l) => l());
};

const subscribe = (listener) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};

export const startRecording = () => set({ ...EMPTY, recording: true });
/** Stop adding clicks; the steps stay until saved or discarded. */
export const stopRecording = () => set({ ...state, recording: false });
export const clearRecording = () => set(EMPTY);
export const resetPlaybookRecorderStore = clearRecording;

/**
 * Add one click (an entry per action it ran: { action, fsp, result }).
 * The first recorded click fixes the SO - run.py drives one SO.
 */
export function recordClick(entries) {
  if (!state.recording || entries.length === 0) return;
  const first = entries[0].action;
  const so = state.so || { name: first.soName || first.soTarget, target: first.soTarget };
  const notes = [...state.notes];
  const elsewhere = entries.filter((e) => e.action.soTarget !== so.target);
  if (elsewhere.length > 0) {
    const other = elsewhere[0].action;
    notes.push(`Not recorded: "${other.label}" is on ${other.soName || other.soTarget} - a playbook drives one SO (${so.name})`);
  }
  const { steps, skipped } = clicksToSteps(entries.filter((e) => e.action.soTarget === so.target));
  skipped.forEach((e) => notes.push(`Not recorded: "${e.action.label}" on ${e.fsp} failed (${e.result?.message})`));
  set({ ...state, so: steps.length > 0 ? so : state.so, steps: [...state.steps, ...steps], notes });
}

/** The recording as a playbook, titled `title`. */
export const recordedPlaybook = (title) => ({ name: title, so: state.so?.name, pace: '2s', steps: state.steps });

/** @returns {{recording: boolean, so: ?{name: string, target: string}, steps: Object[], notes: string[]}} */
export function usePlaybookRecorder() {
  return useSyncExternalStore(subscribe, () => state);
}
```

- [ ] **Step 4: Feed it from `DemoActionsBar.jsx`**

Add `import { recordClick } from '../hooks/usePlaybookRecorder';`. Replace the `run` `useCallback` with a plain function (it needs the current `fspOf`):

```js
  // Runs the actions of one click; while a playbook is being recorded, the
  // click is added to it once every action has answered.
  const run = async (list) => {
    const fsps = list.map(fspOf);
    setResults((prev) => ({ ...prev, ...Object.fromEntries(list.map((a) => [a.id, 'running'])) }));
    const answers = await Promise.all(list.map(async (a) => {
      const result = await runAction(a);
      setResults((prev) => ({ ...prev, [a.id]: result }));
      return result;
    }));
    recordClick(list.map((action, i) => ({ action, fsp: fsps[i], result: answers[i] })));
  };
```

Remove `useCallback` from the React import if nothing else uses it.

- [ ] **Step 5: Run tests**

Run: `cd examples/rti-demo/modules/hmi && npx vitest run src/hooks src/components/DemoActionsBar.test.jsx`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add examples/rti-demo/modules/hmi/src
git commit -m "hmi: record demo-button clicks as playbook steps"
```

---

### Task 8: Run-state hook, `PlaybookBar` and the Traffic block

**Files:**
- Create: `examples/rti-demo/modules/hmi/src/hooks/usePlaybookRun.js`
- Create: `examples/rti-demo/modules/hmi/src/components/PlaybookBar.jsx`
- Modify: `examples/rti-demo/modules/hmi/src/pages/Traffic.jsx` (block title, `PlaybookBar` above `DemoActionsBar`)
- Modify: `examples/rti-demo/modules/hmi/src/pages/Traffic.test.jsx` (mock `PlaybookBar`)
- Test: `examples/rti-demo/modules/hmi/src/components/PlaybookBar.test.jsx`

**Interfaces:**
- Consumes: Task 6 API functions; Task 7 recorder; `subscribe` from `services/liveSocket`.
- Produces: `usePlaybookRun() -> run state | null` (initial `GET`, then `playbook-run` pushes); `<PlaybookBar />` (no props).

- [ ] **Step 1: Write the failing tests**

`src/components/PlaybookBar.test.jsx`:

```jsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';

const pushes = new Map();
vi.mock('../services/liveSocket', () => ({
  subscribe: (type, fn) => {
    pushes.set(type, fn);
    return () => pushes.delete(type);
  },
}));
vi.mock('../utils/playbooks', () => ({
  listPlaybooks: vi.fn(),
  getPlaybook: vi.fn(),
  savePlaybook: vi.fn(async () => ({ ok: true })),
  uploadPlaybook: vi.fn(async () => ({ ok: true })),
  deletePlaybook: vi.fn(async () => ({ ok: true })),
  runPlaybook: vi.fn(),
  stopPlaybook: vi.fn(async () => ({ ok: true })),
  getPlaybookRun: vi.fn(),
  playbookFileUrl: (name) => `http://bff/api/playbooks/${name}/file`,
  uploadName: (n) => n.replace(/\.ya?ml$/, ''),
  uploadFormat: () => 'yaml',
  recordingName: () => 'recording-20261005-0900',
}));

import PlaybookBar from './PlaybookBar';
import * as api from '../utils/playbooks';
import { startRecording, recordClick, resetPlaybookRecorderStore } from '../hooks/usePlaybookRecorder';

const LIST = [
  { name: 'demo', builtin: true, title: 'SO with two FSPs', steps: 2 },
  { name: 'rec1', builtin: false, title: 'Rec', steps: 1 },
];
const DEMO = { name: 'demo', builtin: true, playbook: { steps: [{}, {}] }, labels: ['FSP01 dials the SO', 'Read status'] };
const runState = (state, statuses, extra = {}) => ({
  name: 'demo', title: 'SO with two FSPs', state, current: null, error: null,
  steps: statuses.map((status, i) => ({ index: i + 1, label: DEMO.labels[i], status, message: status === 'ok' ? 'fine' : '', seconds: 0.1 })),
  ...extra,
});

// The select only takes a value once its options have loaded.
const pick = async (value) => {
  await waitFor(() => expect(screen.getByLabelText('Playbook').querySelector(`option[value="${value}"]`)).not.toBeNull());
  fireEvent.change(screen.getByLabelText('Playbook'), { target: { value } });
};

describe('PlaybookBar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetPlaybookRecorderStore();
    localStorage.clear();
    api.listPlaybooks.mockResolvedValue(LIST);
    api.getPlaybook.mockResolvedValue(DEMO);
    api.getPlaybookRun.mockResolvedValue(null);
  });

  it('loads a playbook and shows its steps', async () => {
    render(<PlaybookBar />);
    await pick('demo');
    expect(await screen.findByText('FSP01 dials the SO')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Download/ })).toHaveAttribute('href', 'http://bff/api/playbooks/demo/file');
    expect(screen.queryByTitle('Delete this playbook')).not.toBeInTheDocument(); // built-in
  });

  it('runs and follows the pushed progress', async () => {
    api.runPlaybook.mockResolvedValue(runState('running', ['pending', 'pending']));
    render(<PlaybookBar />);
    await pick('demo');
    await screen.findByText('FSP01 dials the SO');
    fireEvent.click(screen.getByRole('button', { name: /Run/ }));
    await waitFor(() => expect(api.runPlaybook).toHaveBeenCalledWith('demo'));

    act(() => pushes.get('playbook-run')({ type: 'playbook-run', data: runState('running', ['ok', 'running']) }));
    expect(screen.getByTestId('playbook-step-1').textContent).toContain('✓');
    expect(screen.getByTestId('playbook-step-1').textContent).toContain('fine');
    expect(screen.getByRole('button', { name: /Run/ })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: /Stop/ }));
    expect(api.stopPlaybook).toHaveBeenCalled();

    act(() => pushes.get('playbook-run')({ type: 'playbook-run', data: runState('error', ['ok', 'failed'], { error: "FSP 'X' is not registered" }) }));
    expect(screen.getByText(/FSP 'X' is not registered/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Run/ })).not.toBeDisabled();
  });

  it('shows a run already going on load', async () => {
    api.getPlaybookRun.mockResolvedValue(runState('running', ['ok', 'running']));
    render(<PlaybookBar />);
    expect(await screen.findByTestId('playbook-step-1')).toHaveTextContent('✓');
    await waitFor(() => expect(screen.getByLabelText('Playbook')).toHaveValue('demo'));
    expect(screen.getByRole('button', { name: /Run/ })).toBeDisabled();
  });

  it('records, then saves under a name and title', async () => {
    render(<PlaybookBar />);
    fireEvent.click(await screen.findByRole('button', { name: /Record/ }));
    act(() => recordClick([{
      action: { label: 'Read', service: 'read', soTarget: 'so:1', soName: 'SO', objRef: 'R', fc: 'st' },
      fsp: 'F1', result: { ok: true, message: 'ok' },
    }]));
    expect(screen.getByText('Read')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Stop recording/ }));

    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'My demo' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(api.savePlaybook).toHaveBeenCalledWith('recording-20261005-0900', {
      name: 'My demo', so: 'SO', pace: '2s', steps: [{ label: 'Read', read: { fsp: 'F1', ref: 'R', fc: 'st' } }],
    }));
  });

  it('ends an empty recording without asking to save', async () => {
    render(<PlaybookBar />);
    fireEvent.click(await screen.findByRole('button', { name: /Record/ }));
    fireEvent.click(screen.getByRole('button', { name: /Stop recording/ }));
    expect(screen.queryByLabelText('Title')).not.toBeInTheDocument();
  });

  it('shows an upload refused by the BFF', async () => {
    api.uploadPlaybook.mockRejectedValueOnce(new Error("'demo' is a built-in playbook - save under another name"));
    render(<PlaybookBar />);
    const file = new File(['steps: []'], 'demo.yaml');
    fireEvent.change(await screen.findByLabelText('Upload a playbook file'), { target: { files: [file] } });
    expect(await screen.findByText(/built-in playbook/)).toBeInTheDocument();
  });

  it('deletes a saved playbook after confirming', async () => {
    api.getPlaybook.mockResolvedValue({ ...DEMO, name: 'rec1', builtin: false });
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<PlaybookBar />);
    await pick('rec1');
    fireEvent.click(await screen.findByTitle('Delete this playbook'));
    await waitFor(() => expect(api.deletePlaybook).toHaveBeenCalledWith('rec1'));
  });
});
```

In `src/pages/Traffic.test.jsx`, next to the existing `DemoActionsBar` mock, add:

```js
vi.mock('../components/PlaybookBar', () => ({ default: () => <div data-testid="playbook-bar" /> }));
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd examples/rti-demo/modules/hmi && npx vitest run src/components/PlaybookBar.test.jsx`
Expected: FAIL — `./PlaybookBar` not found.

- [ ] **Step 3: Create `src/hooks/usePlaybookRun.js`** (SPDX/Apache header, then)

```js
import { useEffect, useState } from 'react';
import { subscribe } from '../services/liveSocket';
import { getPlaybookRun } from '../utils/playbooks';

/**
 * The BFF's current (or last) playbook run: fetched once, then kept up to
 * date by its "playbook-run" pushes on /ws - so a reloaded page, or a second
 * HMI, follows a run started elsewhere.
 * @returns {?Object} run state (bff/playbook_runs.py), or null before any run
 */
export function usePlaybookRun() {
  const [run, setRun] = useState(null);
  useEffect(() => {
    let alive = true;
    let pushed = false;
    const off = subscribe('playbook-run', (msg) => {
      pushed = true;
      setRun(msg.data);
    });
    getPlaybookRun()
      .then((r) => { if (alive && !pushed) setRun(r); })
      .catch(() => {});
    return () => {
      alive = false;
      off();
    };
  }, []);
  return run;
}
```

- [ ] **Step 4: Create `src/components/PlaybookBar.jsx`** (SPDX/Apache header, then)

```jsx
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  listPlaybooks, getPlaybook, savePlaybook, uploadPlaybook, deletePlaybook, runPlaybook, stopPlaybook,
  playbookFileUrl, uploadName, uploadFormat, recordingName,
} from '../utils/playbooks';
import { usePlaybookRun } from '../hooks/usePlaybookRun';
import {
  usePlaybookRecorder, startRecording, stopRecording, clearRecording, recordedPlaybook,
} from '../hooks/usePlaybookRecorder';

const LAST_KEY = 'traffic-playbook';
const buttonStyle = { padding: '4px 10px', fontSize: '12px' };

const remembered = () => {
  try {
    return localStorage.getItem(LAST_KEY) || '';
  } catch {
    return '';
  }
};
const remember = (name) => {
  try {
    localStorage.setItem(LAST_KEY, name);
  } catch {
    // storage unavailable - only the convenience is lost
  }
};

function StepMark({ status }) {
  if (status === 'running') return <i className="fas fa-spinner fa-spin" style={{ fontSize: '10px' }}></i>;
  if (status === 'ok') return <span style={{ color: 'var(--success-color)' }}>{'✓'}</span>;
  if (status === 'failed') return <span style={{ color: 'var(--danger-color)' }}>{'✗'}</span>;
  if (status === 'recorded') return <span style={{ color: 'var(--danger-color)' }}>{'●'}</span>;
  return <span style={{ color: 'var(--text-muted)' }}>{'·'}</span>;
}

/**
 * Traffic's playbook bar: pick a playbook the BFF keeps (built-in or saved),
 * run it in the BFF and follow each step; download / upload / delete; and
 * record one from clicks on the pinned demo buttons below it.
 */
function PlaybookBar() {
  const [playbooks, setPlaybooks] = useState([]);
  const [selected, setSelected] = useState(remembered);
  const [loaded, setLoaded] = useState(null); // { name, builtin, labels }
  const [error, setError] = useState('');
  const [title, setTitle] = useState('');
  const [saveName, setSaveName] = useState('');
  const run = usePlaybookRun();
  const recorder = usePlaybookRecorder();
  const fileInput = useRef(null);

  const running = run?.state === 'running';
  const unsaved = !recorder.recording && recorder.steps.length > 0;
  const busy = recorder.recording || unsaved;

  const refresh = useCallback(async () => {
    try {
      setPlaybooks(await listPlaybooks());
    } catch (e) {
      setError(e.message);
    }
  }, []);
  useEffect(() => {
    refresh();
  }, [refresh]);

  // A run (started here or elsewhere) shows the playbook it runs.
  useEffect(() => {
    if (run?.name && run.state === 'running' && run.name !== selected) setSelected(run.name);
  }, [run, selected]);

  useEffect(() => {
    if (!selected) {
      setLoaded(null);
      return;
    }
    remember(selected);
    let alive = true;
    getPlaybook(selected)
      .then((p) => { if (alive) setLoaded({ name: p.name, builtin: p.builtin, labels: p.labels }); })
      .catch((e) => { if (alive) { setLoaded(null); setError(e.message); } });
    return () => { alive = false; };
  }, [selected]);

  const attempt = async (fn) => {
    setError('');
    try {
      await fn();
    } catch (e) {
      setError(e.message);
    }
  };

  const onUpload = (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    attempt(async () => {
      const name = uploadName(file.name);
      await uploadPlaybook(name, await file.text(), uploadFormat(file.name));
      await refresh();
      setSelected(name);
    });
  };

  const onStopRecording = () => {
    stopRecording();
    if (recorder.steps.length === 0) {
      clearRecording();
      return;
    }
    setSaveName(recordingName());
    setTitle('');
  };

  const onSave = () => attempt(async () => {
    await savePlaybook(saveName, recordedPlaybook(title || saveName));
    clearRecording();
    await refresh();
    setSelected(saveName);
  });

  const onDiscard = () => {
    if (window.confirm('Discard this recording?')) clearRecording();
  };

  const onDelete = () => {
    if (!window.confirm(`Delete playbook "${selected}"?`)) return;
    attempt(async () => {
      await deletePlaybook(selected);
      setSelected('');
      await refresh();
    });
  };

  // What the step list shows: the recording, the run of this playbook, or
  // the loaded playbook's steps.
  let rows = [];
  if (busy) {
    rows = recorder.steps.map((s, i) => ({ index: i + 1, label: s.label, status: 'recorded', message: s.expect === 'fail' ? 'expects a refusal' : '' }));
  } else if (run && run.name === selected) {
    rows = run.steps;
  } else if (loaded) {
    rows = loaded.labels.map((label, i) => ({ index: i + 1, label, status: 'pending', message: '' }));
  }

  return (
    <div className="playbook-bar" style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '12px', marginBottom: '12px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
        <select
          aria-label="Playbook"
          value={selected}
          disabled={running || busy}
          onChange={(e) => setSelected(e.target.value)}
          style={{ fontSize: '12px', padding: '3px 6px' }}
        >
          <option value="">Choose a playbook…</option>
          {playbooks.map((p) => (
            <option key={p.name} value={p.name} disabled={Boolean(p.error)} title={p.error || ''}>
              {p.title}{p.title !== p.name ? ` (${p.name})` : ''}{p.builtin ? ' - built-in' : ''}
            </option>
          ))}
        </select>
        <button className="btn-primary" style={buttonStyle} disabled={!loaded || running || busy}
          onClick={() => attempt(() => runPlaybook(selected))} title="Run this playbook in the BFF">
          <i className="fas fa-play" style={{ fontSize: '10px' }}></i>Run
        </button>
        {running && (
          <button className="btn-secondary" style={buttonStyle} onClick={() => attempt(stopPlaybook)} title="Stop after the current step">
            <i className="fas fa-stop" style={{ fontSize: '10px' }}></i>Stop
          </button>
        )}
        {loaded && (
          <a className="btn-secondary" style={buttonStyle} href={playbookFileUrl(selected)} download>
            <i className="fas fa-download" style={{ fontSize: '10px' }}></i>Download
          </a>
        )}
        <button className="btn-secondary" style={buttonStyle} disabled={running || busy}
          onClick={() => fileInput.current?.click()} title="Upload a .yaml or .json playbook">
          <i className="fas fa-upload" style={{ fontSize: '10px' }}></i>Upload
        </button>
        <input ref={fileInput} type="file" accept=".yaml,.yml,.json" aria-label="Upload a playbook file"
          style={{ display: 'none' }} onChange={onUpload} />
        {loaded && !loaded.builtin && (
          <button className="btn-secondary" style={buttonStyle} disabled={running || busy} onClick={onDelete} title="Delete this playbook">
            <i className="fas fa-trash" style={{ fontSize: '10px' }}></i>
          </button>
        )}
        <span style={{ flex: 1 }} />
        {recorder.recording ? (
          <button className="btn-secondary" style={{ ...buttonStyle, color: 'var(--danger-color)' }} onClick={onStopRecording}>
            <i className="fas fa-stop" style={{ fontSize: '10px' }}></i>Stop recording
          </button>
        ) : (
          <button className="btn-secondary" style={buttonStyle} disabled={running || unsaved} onClick={startRecording}
            title="Record clicks on the demo buttons below as a playbook">
            <i className="fas fa-circle" style={{ fontSize: '10px', color: 'var(--danger-color)' }}></i>Record
          </button>
        )}
      </div>

      {unsaved && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <label>Name <input aria-label="Name" value={saveName} onChange={(e) => setSaveName(e.target.value)} style={{ fontSize: '12px' }} /></label>
          <label>Title <input aria-label="Title" value={title} placeholder={saveName} onChange={(e) => setTitle(e.target.value)} style={{ fontSize: '12px' }} /></label>
          <button className="btn-primary" style={buttonStyle} disabled={!saveName} onClick={onSave}>Save</button>
          <button className="btn-secondary" style={buttonStyle} onClick={onDiscard}>Discard</button>
        </div>
      )}

      {error && <div style={{ color: 'var(--danger-color)' }}>{error}</div>}
      {run?.name === selected && run.state === 'error' && run.error && (
        <div style={{ color: 'var(--danger-color)' }}>Couldn't run: {run.error}</div>
      )}
      {recorder.notes.map((note) => <div key={note} style={{ color: 'var(--text-muted)' }}>{note}</div>)}
      {recorder.recording && rows.length === 0 && (
        <div style={{ color: 'var(--text-muted)' }}>Recording - click the demo buttons below.</div>
      )}

      {rows.length > 0 && (
        <ol style={{ margin: 0, paddingLeft: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '2px' }}>
          {rows.map((step) => (
            <li key={step.index} data-testid={`playbook-step-${step.index}`} style={{ display: 'flex', gap: '6px', alignItems: 'baseline' }}>
              <span style={{ minWidth: '20px', textAlign: 'right', color: 'var(--text-muted)' }}>{step.index}</span>
              <StepMark status={step.status} />
              <span>{step.label}</span>
              {step.message && <span style={{ color: 'var(--text-muted)' }}>· {step.message}</span>}
              {step.seconds != null && step.status !== 'running' && step.status !== 'pending' && (
                <span style={{ color: 'var(--text-muted)' }}>({step.seconds}s)</span>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

export default PlaybookBar;
```

- [ ] **Step 5: Traffic block**

In `src/pages/Traffic.jsx`: add `import PlaybookBar from '../components/PlaybookBar';`; change the comment `{/* Collapsible demo actions block */}` to `{/* Collapsible demo playbook block: playbooks above, the pinned buttons below */}`; change the heading text `Demo Actions` to `Demo Playbook`; and inside the `display: demoExpanded ? …` div put `<PlaybookBar />` before `<DemoActionsBar … />`.

- [ ] **Step 6: Run the HMI tests**

Run: `cd examples/rti-demo/modules/hmi && npx vitest run`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add examples/rti-demo/modules/hmi/src
git commit -m "hmi: Demo Playbook - load, run, record, download / upload playbooks on Traffic"
```

---

### Task 9: Integration test through the BFF, docs

**Files:**
- Modify: `examples/rti-demo/tests/integration/test_playbook.py` (add a test)
- Modify: `docs/rti-demo/includes/hmi.adoc`, `examples/rti-demo/playbooks/README.md`, `examples/rti-demo/TESTING.md`, `examples/rti-demo/README.md`

**Interfaces:**
- Consumes: Task 5 endpoints.

- [ ] **Step 1: Add the integration test** (append to `tests/integration/test_playbook.py`; it already imports `requests`? if not, add `import time` and `import requests` at the top)

```python
def test_demo_playbook_runs_clean_in_the_bff():
    """The same playbook, run by the BFF the way the HMI's Run button does."""
    bff = run.load_playbook(PLAYBOOK).get("bff", run.DEFAULT_BFF)
    name = PLAYBOOK.stem
    r = requests.post(f"{bff}/api/playbooks/{name}/run", json={"pace": 0}, timeout=10)
    if r.status_code == 404:
        pytest.skip(f"{name} is not a playbook the BFF has (only built-in ones run here)")
    assert r.status_code == 200, r.text

    deadline = time.monotonic() + 180
    while True:
        state = requests.get(f"{bff}/api/playbooks/run", timeout=10).json()["run"]
        if state["state"] != "running" or time.monotonic() > deadline:
            break
        time.sleep(1)
    lines = [f"{s['index']} {s['status']} {s['label']} · {s['message']}" for s in state["steps"]]
    assert state["state"] == "passed", "\n".join(lines + [str(state.get("error"))])
```

- [ ] **Step 2: Run it against the stack**

```bash
cd examples/rti-demo
docker compose up -d --build
uv run pytest tests/integration -m integration -k playbook -q
```
Expected: both playbook tests pass. (If the stack can't be started here, say so in the task report — don't mark the step done.)

- [ ] **Step 3: Docs**

- `docs/rti-demo/includes/hmi.adoc`: rename the "Demo Actions" bullet to "Demo Playbook" and add, before the pinned-buttons text: the playbook bar (pick a built-in or saved playbook, Run in the BFF with ✓ / ✗ per step, Stop after the current step, Download / Upload / Delete), Record (clicks on the pinned buttons, including All FSPs, become steps; a refusal is kept as `expect: fail`; a click that didn't get through, or on another SO, isn't recorded; Stop recording → name and title → saved in the BFF with `pace: 2s`), and that any open HMI follows a run. Update the other "demo actions row" mention in the same file to "demo buttons row".
- `examples/rti-demo/playbooks/README.md`: a "From the HMI" section — Traffic → Demo Playbook; built-in = this folder, saved = `BFF_PLAYBOOKS_DIR` (`/config/playbooks` on the `bff-config` volume); a recording is an ordinary playbook (download it, put it here, and it runs from the CLI and as the test). Note that the CLI imports the runner from the BFF package, so it needs `uv sync --all-packages` (or `--package bff`).
- `examples/rti-demo/TESTING.md`: in the integration section, mention `test_demo_playbook_runs_clean_in_the_bff`; in the unit section list `modules/bff/tests/test_playbook_{module,store,runs,endpoints}.py`.
- `examples/rti-demo/README.md`: in the playbooks paragraph, one sentence that playbooks can also be recorded and run from Traffic's Demo Playbook block.

- [ ] **Step 4: Full test pass**

```bash
cd examples/rti-demo
uv run --package bff pytest modules/bff/tests -m unit -q
uv run pytest tests/test_playbook.py -q
cd modules/hmi && npx vitest run
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add docs/rti-demo examples/rti-demo
git commit -m "rti-demo: demo playbooks from the HMI - integration test and docs"
```
