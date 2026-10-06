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


class PlaybookBusyError(Exception):
    """A run was asked for while another one is going."""


class PlaybookRuns:
    def __init__(
        self, store: PlaybookStore, transport_factory: Callable[[dict[str, Any]], Any]
    ):
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

    def start(
        self,
        name: str,
        *,
        pace: Any = None,
        keep_going: bool = False,
        publish: Callable[[dict[str, Any]], None] = lambda state: None,
    ) -> dict[str, Any]:
        playbook, _ = self.store.get(name)
        pace_s = parse_duration(pace) if pace not in (None, "") else None
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise PlaybookBusyError(f"playbook {self._state['name']!r} is running")
            self._stop = threading.Event()
            self._publish = publish
            self._state = {
                "name": name,
                "title": str(playbook.get("name") or name),
                "state": "running",
                "current": None,
                "error": None,
                "steps": [
                    {
                        "index": i,
                        "label": step_label(step),
                        "status": "pending",
                        "message": "",
                        "seconds": None,
                    }
                    for i, step in enumerate(playbook["steps"], 1)
                ],
            }
            initial = copy.deepcopy(self._state)
            self._thread = threading.Thread(
                target=self._work,
                args=(playbook, pace_s, keep_going),
                name=f"playbook-{name}",
                daemon=True,
            )
        # Published before the worker thread starts, so the "all pending"
        # state is always the first thing a browser sees for this run -
        # never after a step update, or even the final state.
        try:
            publish(initial)
        except Exception:
            logger.exception("publishing the initial playbook run state failed")
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

    def _work(
        self, playbook: dict[str, Any], pace: float | None, keep_going: bool
    ) -> None:
        def on_step(index: int, label: str) -> None:
            def change(s):
                s["current"] = index
                s["steps"][index - 1].update(status="running", label=label)

            self._update(change)

        def on_result(r: StepResult) -> None:
            self._update(
                lambda s: s["steps"][r.index - 1].update(
                    status="ok" if r.ok else "failed",
                    message=r.message,
                    seconds=round(r.seconds, 1),
                    label=r.label,
                )
            )

        error = None
        try:
            runner = Runner(
                playbook,
                self.transport_factory(playbook),
                pace=pace,
                log=logger.info,
                stop=self._stop,
                on_step=on_step,
                on_result=on_result,
            )
            results = runner.run(keep_going=keep_going)
            final = (
                "stopped"
                if runner.stopped
                else "passed"
                if results and all(r.ok for r in results)
                else "failed"
            )
        except (PlaybookError, requests.RequestException, OSError) as exc:
            final, error = "error", str(exc)
        except Exception as exc:  # a bug - don't leave the run "running" forever
            logger.exception("playbook run failed")
            final, error = "error", f"{type(exc).__name__}: {exc}"

        def finish(s):
            s.update(state=final, error=error, current=None)
            for step in s["steps"]:
                if step["status"] == "running":
                    step.update(
                        status="failed", message=step["message"] or error or "stopped"
                    )

        self._update(finish)
