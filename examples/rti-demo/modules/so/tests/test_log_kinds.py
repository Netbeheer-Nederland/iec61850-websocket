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

"""Every _log_action call site in so must say which kind of entry it is.

kind is a required keyword, so a missing one only fails when that line
actually runs - often an error path no test reaches. Scanning the source
catches it up front. See docs/rti-demo/design/logging-kinds.md.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import so

pytestmark = pytest.mark.unit

SRC = Path(so.__file__).parent
KINDS = {"system", "acsi"}


def _log_action_calls():
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "_log_action"
            ):
                yield path, node


def test_there_are_call_sites_to_check():
    assert any(True for _ in _log_action_calls())


def test_every_log_action_call_passes_a_literal_known_kind():
    bad = []
    for path, node in _log_action_calls():
        kind = next((k.value for k in node.keywords if k.arg == "kind"), None)
        if not (isinstance(kind, ast.Constant) and kind.value in KINDS):
            bad.append(f"{path.name}:{node.lineno}")
    assert bad == [], f"_log_action calls without kind=system|acsi: {bad}"
