# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
#
# Copyright 2025 Netbeheer Nederland
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

"""Run a demo playbook: a YAML (or JSON) list of steps for one SO and its
FSPs, executed through the BFF the same way the HMI does - so the HMI's
Traffic page shows every step while it runs - and checked as it goes.

    cd examples/rti-demo
    uv run python -m playbooks.run playbooks/demo.yaml [--pace 2s] [--keep-going]

The same playbook runs as an integration test (tests/integration/
test_playbook.py). See playbooks/README.md for the step reference.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

DEFAULT_BFF = "http://localhost:5000"

ACTIONS = (
    "link", "unlink", "drop", "read", "write", "operate", "select",
    "enable-report", "disable-report", "wait",
)

# OptFlds / TrgOp a report control block write carries - the SO resets any
# it isn't sent, so all are always sent (as the HMI's Enable report does).
OPT_FLDS_KEYS = ("seqNum", "timeStamp", "dataSet", "reasonCode", "dataRef", "bufOvfl", "entryID", "configRef")
TRG_OP_KEYS = ("dchg", "qchg", "dupd", "integrity", "gi")


class PlaybookError(Exception):
    """A playbook that can't be run as written (bad file, unknown FSP, ...)."""


# -------------------- loading --------------------


def load_playbook(path: str | Path) -> dict[str, Any]:
    """Read and check a playbook file (.yaml / .yml / .json)."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        import yaml

        data = yaml.safe_load(text)
    return validate_playbook(data)


def validate_playbook(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(data.get("steps"), list) or not data["steps"]:
        raise PlaybookError("a playbook needs a non-empty 'steps' list")
    for i, step in enumerate(data["steps"], 1):
        if not isinstance(step, dict):
            raise PlaybookError(f"step {i}: expected a mapping, got {step!r}")
        actions = [k for k in step if k in ACTIONS]
        unknown = [k for k in step if k not in ACTIONS and k not in ("expect", "label")]
        if len(actions) != 1 or unknown:
            raise PlaybookError(
                f"step {i}: needs exactly one of {', '.join(ACTIONS)}"
                + (f" (unknown: {', '.join(unknown)})" if unknown else "")
            )
    return data


def parse_duration(value: Any) -> float:
    """Seconds from 5, "5s", "500ms", "1.5s", "2m"."""
    if isinstance(value, (int, float)):
        return float(value)
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(ms|s|m)?\s*", str(value))
    if not m:
        raise PlaybookError(f"not a duration: {value!r}")
    number, unit = float(m.group(1)), m.group(2) or "s"
    return number / 1000 if unit == "ms" else number * 60 if unit == "m" else number


# -------------------- what the HMI sends --------------------


def control_value(cdc: str, raw: Any) -> tuple[Any, str]:
    """(ctlVal, value_type) for an operate on a DO of `cdc` - the same rules
    as the HMI's controlValue (utils/demoActions.js)."""
    text = str(raw if raw is not None else "").strip()
    low = text.lower()
    cdc = (cdc or "").upper()
    if cdc in ("SPC", "DPC"):
        if low in ("true", "1", "on"):
            return True, "boolean"
        if low in ("false", "0", "off"):
            return False, "boolean"
        raise PlaybookError(f"invalid {cdc} value {raw!r} - use on/off or true/false")
    if cdc == "APC":
        return float(text), "float32"
    if cdc in ("INC", "ENC", "ING", "CTE"):
        return int(text), "int32"
    if cdc == "BSC":
        steps = {"up": "stepUp", "down": "stepDown"}
        if low not in steps:
            raise PlaybookError(f"invalid BSC value {raw!r} - use up or down")
        return steps[low], "string"
    if cdc == "ASG":
        return text, "string"
    if cdc == "ENG":
        return int(text), "enumerated"
    raise PlaybookError(f"unsupported CDC for operate: {cdc!r}")


def so_answer(service: str, http_ok: bool, payload: Any) -> tuple[bool, str]:
    """Whether the FSP did what an SO call asked - the HMI's soAnswer.

    The SO answers a refused operate/select with HTTP 200 { ok: false,
    error }, and a refused read with the serviceError's name as the value.
    """
    answer = payload.get("result") if isinstance(payload, dict) else None
    answer = answer if isinstance(answer, dict) else {}
    refused_read = service == "read" and isinstance(answer.get("value"), str)
    ok = http_ok and answer.get("ok") is not False and answer.get("success") is not False and not refused_read
    if ok:
        return True, "ok"
    if refused_read:
        return False, answer["value"]
    if http_ok and answer.get("ok") is False and not answer.get("error"):
        return False, "refused by the FSP"
    error = answer.get("error") or (payload.get("error") if isinstance(payload, dict) else None)
    return False, str(error or "request failed")


# -------------------- talking to the BFF --------------------


class BffTransport:
    """The BFF's REST API: its connections, and /api/execute towards an instance."""

    def __init__(self, base_url: str, timeout: float = 15):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def connections(self) -> list[dict[str, Any]]:
        r = requests.get(f"{self.base_url}/api/connections", timeout=self.timeout)
        r.raise_for_status()
        return r.json().get("connections", [])

    def execute(self, target: str, method: str, path: str, body: Any = None) -> tuple[bool, Any]:
        """(http_ok, the BFF's response JSON) for one instance call."""
        request = {"target": target, "method": method, "path": path}
        if body is not None:
            request["body"] = body
        r = requests.post(f"{self.base_url}/api/execute", json=request, timeout=self.timeout)
        try:
            payload = r.json()
        except ValueError:
            payload = {"error": r.text}
        return r.ok and (payload.get("ok", True) if isinstance(payload, dict) else True), payload


# -------------------- running --------------------


@dataclass
class StepResult:
    index: int
    action: str
    label: str
    ok: bool
    message: str
    seconds: float = 0.0
    details: list[str] = field(default_factory=list)


def _expects_reports(step: dict[str, Any]) -> bool:
    expect = step.get("expect")
    return isinstance(expect, dict) and "reports" in expect


def _target(conn: dict[str, Any]) -> str:
    return f"{conn['host']}:{conn['port']}"


def _status_dict(raw: Any) -> dict[str, Any]:
    """An FSP's /api/status 'status' - a dict, or its Python repr."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = ast.literal_eval(raw)
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, SyntaxError):
            return {}
    return {}


class Runner:
    """Runs a playbook step by step; each step's result is passed to `log`."""

    def __init__(
        self,
        playbook: dict[str, Any],
        transport: Any = None,
        pace: float | None = None,
        log: Callable[[str], None] = print,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.playbook = validate_playbook(playbook)
        self.transport = transport or BffTransport(playbook.get("bff", DEFAULT_BFF))
        self.pace = parse_duration(playbook.get("pace", 0)) if pace is None else pace
        self.log = log
        self.sleep = sleep
        self._instances: dict[str, dict[str, Any]] | None = None
        self._cps: dict[str, str] = {str(k): str(v) for k, v in (playbook.get("cps") or {}).items()}
        # Step number -> the SO's highest frame id when that step started.
        self._marks: dict[int, int] = {}

    # ----- instances -----

    def instances(self) -> dict[str, dict[str, Any]]:
        if self._instances is None:
            self._instances = {c["name"]: c for c in self.transport.connections() if c.get("name")}
        return self._instances

    def so(self) -> dict[str, Any]:
        wanted = self.playbook.get("so")
        sos = [c for c in self.instances().values() if c.get("type") == "RTI-SO"]
        if wanted:
            sos = [c for c in sos if c["name"] == wanted]
        if len(sos) != 1:
            raise PlaybookError(
                f"SO {wanted!r} not registered with the BFF" if wanted
                else f"expected one RTI-SO registered with the BFF, found {len(sos)} - name it with 'so:'"
            )
        return sos[0]

    def fsp(self, name: str) -> dict[str, Any]:
        conn = self.instances().get(name)
        if conn is None or conn.get("type") != "RTI-FSP":
            raise PlaybookError(f"FSP {name!r} is not registered with the BFF")
        return conn

    def cp(self, fsp_name: str) -> str:
        """The FSP's cp: the playbook's 'cps' entry, else what the FSP reports."""
        if fsp_name not in self._cps:
            ok, payload = self.transport.execute(_target(self.fsp(fsp_name)), "GET", "/api/status")
            status = _status_dict((payload.get("result") or {}).get("status") if isinstance(payload, dict) else None)
            points = status.get("accessPoints") or []
            if not ok or not points:
                raise PlaybookError(f"can't tell {fsp_name}'s cp - is it reachable? (or set it under 'cps:')")
            self._cps[fsp_name] = str(points[0])
        return self._cps[fsp_name]

    def linked_cps(self) -> list[str]:
        ok, payload = self.transport.execute(_target(self.so()), "GET", "/api/properties")
        cps = (payload.get("result") or {}).get("acsi_client_list") if ok and isinstance(payload, dict) else None
        return list(cps or [])

    def so_call(self, service: str, path: str, body: dict[str, Any]) -> tuple[bool, str]:
        http_ok, payload = self.transport.execute(_target(self.so()), "POST", path, body)
        return so_answer(service, http_ok, payload)

    def _so_frames(self) -> list[dict[str, Any]]:
        ok, payload = self.transport.execute(_target(self.so()), "GET", "/api/messages")
        return (payload.get("result") or {}).get("messages", []) if ok and isinstance(payload, dict) else []

    def frame_mark(self) -> int:
        """The SO's highest logged frame id - reports after it are new."""
        return max((int(f.get("id", 0)) for f in self._so_frames()), default=0)

    def reports_since(self, fsp_name: str, mark: int) -> int:
        """Reports the SO has received from this FSP's cp after frame `mark`.

        By frame id, not a count: the SO keeps a bounded log, so old reports
        dropping off would cancel out new ones."""
        cp = self.cp(fsp_name)
        return sum(
            1 for f in self._so_frames()
            if int(f.get("id", 0)) > mark
            and f.get("category") == "unconfirmed" and f.get("direction") == "recv" and f.get("cp") == cp
        )

    # ----- actions -----

    def _fsps(self, spec: dict[str, Any]) -> list[str]:
        names = spec.get("fsp")
        names = names if isinstance(names, list) else [names]
        if not names or not all(isinstance(n, str) and n for n in names):
            raise PlaybookError("needs 'fsp': a name or a list of names")
        return names

    @staticmethod
    def _per_fsp(spec: dict[str, Any], key: str, fsp: str) -> Any:
        value = spec.get(key)
        if isinstance(value, dict) and fsp in value:
            return value[fsp]
        if isinstance(value, dict) and key in ("ref", "rcb", "value"):
            raise PlaybookError(f"no '{key}' given for {fsp}")
        return value

    def _wait_for_link(self, cp: str, linked: bool, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while True:
            if (cp in self.linked_cps()) == linked:
                return True
            if time.monotonic() >= deadline:
                return False
            self.sleep(0.5)

    def do_link(self, spec, fsp):
        so, cp = self.so(), self.cp(fsp)
        # Already linked is fine - the FSP refuses a second /start while it
        # runs, and a playbook should be safe to run again.
        if cp in self.linked_cps():
            return True, f"already linked on {cp}"
        if not so.get("ws_port"):
            raise PlaybookError(f"SO {so['name']!r} has no ws_port configured in the BFF")
        ok, payload = self.transport.execute(
            _target(self.fsp(fsp)), "POST", "/api/start",
            {"host": so["host"], "port": str(so["ws_port"]), "mode": "active", "cp": cp},
        )
        if not ok:
            return False, f"start failed: {payload}"
        if not self._wait_for_link(cp, True, parse_duration(spec.get("timeout", 15))):
            return False, f"{fsp} started, but the SO didn't associate {cp}"
        return True, f"linked on {cp}"

    def do_unlink(self, spec, fsp):
        cp = self.cp(fsp)
        if cp not in self.linked_cps():
            return True, f"already unlinked ({cp})"
        ok, payload = self.transport.execute(_target(self.fsp(fsp)), "POST", "/api/stop", {})
        if not ok:
            return False, f"stop failed: {payload}"
        if not self._wait_for_link(cp, False, parse_duration(spec.get("timeout", 15))):
            return False, f"{fsp} stopped, but the SO still lists {cp}"
        return True, f"unlinked {cp}"

    def do_drop(self, spec, fsp):
        ok, message = self.do_unlink(spec, fsp)
        if not ok:
            return ok, message
        self.sleep(parse_duration(spec.get("for", 10)))
        ok, message = self.do_link(spec, fsp)
        return ok, f"dropped for {spec.get('for', 10)}, then {message}"

    def do_read(self, spec, fsp):
        ref = self._per_fsp(spec, "ref", fsp)
        return self.so_call("read", "/api/readvalue", {"objRef": ref, "fc": spec.get("fc", "st"), "cp": self.cp(fsp)})

    def do_write(self, spec, fsp):
        body = {
            "objRef": self._per_fsp(spec, "ref", fsp),
            "value": self._per_fsp(spec, "value", fsp),
            "fc": spec.get("fc", "sp"),
            "cp": self.cp(fsp),
        }
        if spec.get("type"):
            body["dataType"] = spec["type"]
        return self.so_call("write", "/api/writevalue", body)

    def do_operate(self, spec, fsp):
        value, value_type = control_value(spec.get("cdc", ""), self._per_fsp(spec, "value", fsp))
        origin = spec.get("origin") or {"orCat": 2, "orIdent": "playbook"}
        return self.so_call("operate", "/api/operate", {
            "objRef": self._per_fsp(spec, "ref", fsp),
            "value": value,
            "value_type": value_type,
            "ctlNum": int(spec.get("ctlNum", 0)),
            "origin": origin,
            "test": bool(spec.get("test", False)),
            "cp": self.cp(fsp),
        })

    def do_select(self, spec, fsp):
        return self.so_call("select", "/api/select", {"objRef": self._per_fsp(spec, "ref", fsp), "cp": self.cp(fsp)})

    def _set_reporting(self, spec, fsp, enabled: bool):
        rcb = self._per_fsp(spec, "rcb", fsp)
        kind = "urcb" if str(spec.get("type", "BRCB")).upper() == "URCB" else "brcb"
        cp = self.cp(fsp)
        http_ok, payload = self.transport.execute(
            _target(self.so()), "POST", f"/api/{kind}-read", {"objRef": rcb, "cp": cp}
        )
        current = ((payload.get("result") or {}).get("value") if isinstance(payload, dict) else None)
        if not http_ok or not isinstance(current, dict):
            return False, f"couldn't read {rcb}: {current or payload}"
        if current.get("rptEna") is enabled:
            return True, "already enabled" if enabled else "already disabled"
        data = {
            "ref": rcb,
            "dataSet": current.get("dataSet") or "",
            "intgPd": int(current.get("intgPd") or 0),
            "rptEna": enabled,
            "optFlds": {k: bool((current.get("optFlds") or {}).get(k)) for k in OPT_FLDS_KEYS},
            "trgOp": {k: bool((current.get("trgOp") or {}).get(k)) for k in TRG_OP_KEYS},
        }
        http_ok, payload = self.transport.execute(
            _target(self.so()), "POST", f"/api/{kind}-write", {"objRef": rcb, "data": data, "cp": cp}
        )
        value = (payload.get("result") or {}).get("value") if isinstance(payload, dict) else None
        if http_ok and value is True:
            return True, "ok"
        return False, str(value or payload)

    def do_enable_report(self, spec, fsp):
        return self._set_reporting(spec, fsp, True)

    def do_disable_report(self, spec, fsp):
        return self._set_reporting(spec, fsp, False)

    # ----- expectations -----

    def _check_expect(self, expect: Any, action_ok: bool, action_msg: str, mark: int | None) -> tuple[bool, str]:
        if expect in (None, "ok"):
            return action_ok, action_msg
        if expect in ("fail", "refused"):
            return (not action_ok, f"refused as expected: {action_msg}") if not action_ok else (False, "expected a refusal, got ok")
        if not isinstance(expect, dict):
            raise PlaybookError(f"unknown expect: {expect!r}")
        if not action_ok:
            return action_ok, action_msg
        notes = []
        for kind, arg in expect.items():
            if kind == "reports":
                fsp, minimum = arg["fsp"], int(arg.get("min", 1))
                got = self.reports_since(fsp, mark or 0)
                if got < minimum:
                    return False, f"{got} report(s) from {fsp}, expected at least {minimum}"
                notes.append(f"{got} report(s) from {fsp}")
            elif kind in ("linked", "unlinked"):
                names = arg if isinstance(arg, list) else [arg]
                cps = self.linked_cps()
                for name in names:
                    if (self.cp(name) in cps) != (kind == "linked"):
                        return False, f"{name} is {'not ' if kind == 'linked' else ''}linked"
                notes.append(f"{kind}: {', '.join(names)}")
            else:
                raise PlaybookError(f"unknown expect: {kind!r}")
        return True, "; ".join(notes) or action_msg

    # ----- the loop -----

    def run_step(self, index: int, step: dict[str, Any]) -> StepResult:
        action = next(k for k in step if k in ACTIONS)
        spec = step[action]
        expect = step.get("expect")
        started = time.monotonic()

        # A reports expectation counts the reports after a mark: on a wait,
        # the one taken before the step it follows - that step (an
        # enable-report, say) is what set them off, and some arrive while it
        # runs; on any other step, its own.
        mark = None
        if isinstance(expect, dict) and "reports" in expect:
            mark = self._marks.get(index - 1) if action == "wait" else None
            mark = self._marks.get(index) if mark is None else mark

        if action == "wait":
            self.sleep(parse_duration(spec))
            ok, message, details = True, f"waited {spec}", []
            label = step.get("label") or f"wait {spec}"
        else:
            if not isinstance(spec, dict):
                raise PlaybookError(f"step {index}: '{action}' needs a mapping")
            fsps = self._fsps(spec)
            label = step.get("label") or f"{action} {', '.join(fsps)}" + (
                f" {spec['ref']}" if isinstance(spec.get("ref"), str) else ""
            )
            handler = getattr(self, f"do_{action.replace('-', '_')}")
            details, results = [], []
            for fsp in fsps:
                try:
                    result = handler(spec, fsp)
                except (requests.RequestException, ValueError) as exc:
                    result = (False, f"{type(exc).__name__}: {exc}")
                results.append(result)
                details.append(f"{fsp}: {result[1]}")
            ok = all(r[0] for r in results)
            message = details[0].split(": ", 1)[1] if len(details) == 1 else "; ".join(details)

        ok, message = self._check_expect(expect, ok, message, mark)
        return StepResult(index, action, label, ok, message, time.monotonic() - started, details)

    def run(self, keep_going: bool = False, only: range | None = None) -> list[StepResult]:
        steps = self.playbook["steps"]
        results = []
        name = self.playbook.get("name", "playbook")
        self.log(f"{name} - {len(steps)} steps via {getattr(self.transport, 'base_url', 'BFF')}")
        for index, step in enumerate(steps, 1):
            if only is not None and index not in only:
                continue
            if _expects_reports(step) or (index < len(steps) and _expects_reports(steps[index])):
                self._marks[index] = self.frame_mark()
            result = self.run_step(index, step)
            results.append(result)
            mark = "✓" if result.ok else "✗"
            self.log(f"[{index:>2}/{len(steps)}] {mark} {result.label} · {result.message} ({result.seconds:.1f}s)")
            if not result.ok and not keep_going:
                self.log("stopped at the first failed step (--keep-going runs on)")
                break
            if self.pace and index < len(steps):
                self.sleep(self.pace)
        failed = [r for r in results if not r.ok]
        self.log(f"{len(results) - len(failed)}/{len(results)} steps ok" + (f", {len(failed)} failed" if failed else ""))
        return results


def _step_range(text: str) -> range:
    """"3" or "2-5" -> a range of step numbers."""
    m = re.fullmatch(r"(\d+)(?:-(\d+))?", text)
    if not m:
        raise argparse.ArgumentTypeError(f"not a step or range: {text!r}")
    first = int(m.group(1))
    return range(first, int(m.group(2) or first) + 1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an rti-demo playbook through the BFF.")
    parser.add_argument("playbook", help="playbook file (.yaml or .json)")
    parser.add_argument("--bff", help=f"BFF base URL (default: the playbook's 'bff', else {DEFAULT_BFF})")
    parser.add_argument("--pace", help="pause between steps, e.g. 2s (default: the playbook's 'pace', else none)")
    parser.add_argument("--keep-going", action="store_true", help="run on after a failed step")
    parser.add_argument("--steps", type=_step_range, help="only these steps, e.g. 3 or 2-5")
    args = parser.parse_args(argv)

    try:
        playbook = load_playbook(args.playbook)
        transport = BffTransport(args.bff or playbook.get("bff", DEFAULT_BFF))
        runner = Runner(playbook, transport, pace=parse_duration(args.pace) if args.pace else None)
        results = runner.run(keep_going=args.keep_going, only=args.steps)
    except (PlaybookError, requests.RequestException, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0 if results and all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
