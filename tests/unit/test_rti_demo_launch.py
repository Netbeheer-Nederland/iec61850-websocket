# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""examples/rti-demo/launch.py's options, as its README documents them."""

import importlib.util
from pathlib import Path

import pytest

LAUNCH_PY = Path(__file__).resolve().parents[2] / "examples" / "rti-demo" / "launch.py"


@pytest.fixture(scope="module")
def launcher():
    spec = importlib.util.spec_from_file_location("rti_demo_launch", LAUNCH_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.RTILauncher()


def test_verbose_by_default(launcher):
    _, options = launcher.parse_args(["bff"])
    assert options["verbose"] is True


def test_no_verbose_turns_it_off(launcher):
    _, options = launcher.parse_args(["bff", "--no-verbose"])
    assert options["verbose"] is False
