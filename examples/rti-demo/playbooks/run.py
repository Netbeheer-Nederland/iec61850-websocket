# SPDX-FileCopyrightText: 2025-2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
#
# Copyright 2025-2026 Netbeheer Nederland
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


def _step_range(text: str) -> range:
    """ "3" or "2-5" -> a range of step numbers."""
    m = re.fullmatch(r"(\d+)(?:-(\d+))?", text)
    if not m:
        raise argparse.ArgumentTypeError(f"not a step or range: {text!r}")
    first = int(m.group(1))
    return range(first, int(m.group(2) or first) + 1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run an rti-demo playbook through the BFF."
    )
    parser.add_argument("playbook", help="playbook file (.yaml or .json)")
    parser.add_argument(
        "--bff",
        help=f"BFF base URL (default: the playbook's 'bff', else {DEFAULT_BFF})",
    )
    parser.add_argument(
        "--pace",
        help="pause between steps, e.g. 2s (default: the playbook's 'pace', else none)",
    )
    parser.add_argument(
        "--keep-going", action="store_true", help="run on after a failed step"
    )
    parser.add_argument(
        "--steps", type=_step_range, help="only these steps, e.g. 3 or 2-5"
    )
    args = parser.parse_args(argv)

    try:
        playbook = load_playbook(args.playbook)
        transport = BffTransport(args.bff or playbook.get("bff", DEFAULT_BFF))
        runner = Runner(
            playbook, transport, pace=parse_duration(args.pace) if args.pace else None
        )
        results = runner.run(keep_going=args.keep_going, only=args.steps)
    except (PlaybookError, requests.RequestException, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0 if results and all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
