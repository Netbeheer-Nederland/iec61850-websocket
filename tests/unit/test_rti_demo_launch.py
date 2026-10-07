# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""examples/rti-demo/launch.py's options, as its README documents them."""

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

LAUNCH_PY = Path(__file__).resolve().parents[2] / "examples" / "rti-demo" / "launch.py"


@pytest.fixture(scope="module")
def launcher():
    spec = importlib.util.spec_from_file_location("rti_demo_launch", LAUNCH_PY)
    module = importlib.util.module_from_spec(spec)
    sys.modules["rti_demo_launch"] = module
    spec.loader.exec_module(module)
    return module.RTILauncher()


def test_verbose_by_default(launcher):
    _, options = launcher.parse_args(["bff"])
    assert options["verbose"] is True


def test_no_verbose_turns_it_off(launcher):
    _, options = launcher.parse_args(["bff", "--no-verbose"])
    assert options["verbose"] is False


COMPOSE = LAUNCH_PY.parent / "docker-compose.yml"


def test_every_service_type_is_an_rti_type(launcher):
    module = importlib.import_module(type(launcher).__module__)
    types = {c.labels["rti.type"] for c in module.SERVICES.values()}
    assert all(t.startswith("RTI-") for t in types), types


def test_compose_and_launch_agree_on_the_type(launcher):
    module = importlib.import_module(type(launcher).__module__)
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    for config in module.SERVICES.values():
        service = compose.get(config.labels["rti.service"])
        if service is None:  # the FSPs are named differently in compose
            continue
        labels = dict(label.split("=", 1) for label in service.get("labels", []))
        assert labels["rti.type"] == config.labels["rti.type"], config.labels[
            "rti.service"
        ]
