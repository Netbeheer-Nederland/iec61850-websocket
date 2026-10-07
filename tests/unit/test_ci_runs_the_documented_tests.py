# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""CI runs every test command examples/rti-demo/TESTING.md documents, so a
change that breaks a module's tests can't pass CI."""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
TESTING = ROOT / "examples" / "rti-demo" / "TESTING.md"
CI = ROOT / ".github" / "workflows" / "ci.yml"
HMI = "examples/rti-demo/modules/hmi"


def _documented_commands() -> list[str]:
    """The commands in TESTING.md's 'Running everything in one go' block."""
    text = TESTING.read_text(encoding="utf-8")
    block = text.split("## Running everything in one go", 1)[1].split("```")[1]
    return re.findall(r"\((?:cd \S+ && )?([^()]+?)\)", block)


def _ci_steps() -> list[tuple[str, str]]:
    """(working directory, command) for every run step in ci.yml."""
    jobs = yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]
    steps = []
    for job in jobs.values():
        workdir = job.get("defaults", {}).get("run", {}).get("working-directory", ".")
        for step in job["steps"]:
            if "run" in step:
                steps.append((step.get("working-directory", workdir), step["run"]))
    return steps


def test_testing_md_lists_the_module_and_hmi_tests():
    commands = _documented_commands()
    assert any("--package bff" in c for c in commands)
    assert any("npm test" in c for c in commands)


@pytest.mark.parametrize(
    "command", [c for c in _documented_commands() if c.startswith("uv run")]
)
def test_ci_runs_the_python_tests(command):
    assert any(command == run.strip() for _, run in _ci_steps()), command


def test_ci_runs_the_hmi_tests_and_build():
    runs = [run.strip() for workdir, run in _ci_steps() if workdir == HMI]
    assert "npm ci" in runs
    assert "npm test" in runs
    assert "npx vite build" in runs
