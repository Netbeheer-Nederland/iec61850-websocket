# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""examples/rti-demo/launch.py's options, as its README documents them."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

LAUNCH_PY = Path(__file__).resolve().parents[2] / "examples" / "rti-demo" / "launch.py"


@pytest.fixture(scope="module")
def launcher():
    spec = importlib.util.spec_from_file_location("rti_demo_launch", LAUNCH_PY)
    module = importlib.util.module_from_spec(spec)
    # Registered while the tests run (they look it up by name), then removed.
    sys.modules["rti_demo_launch"] = module
    spec.loader.exec_module(module)
    yield module.RTILauncher()
    sys.modules.pop("rti_demo_launch", None)


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


def test_io_runs_as_a_module_from_modules_io(launcher):
    module = importlib.import_module(type(launcher).__module__)
    config = module.SERVICES[module.ServiceType.IO]
    cmd, cwd = launcher._command_for(config)
    assert cmd[-2:] == ["-m", "rti_io.server.main"]
    assert cwd == LAUNCH_PY.parent / "modules" / "io"
    assert (cwd / "rti_io" / "server" / "main.py").is_file()


def test_bff_still_runs_its_script(launcher):
    module = importlib.import_module(type(launcher).__module__)
    cmd, cwd = launcher._command_for(module.SERVICES[module.ServiceType.BFF])
    assert cmd[-1].endswith("modules/bff/src/bff/bff_server.py")
    assert cwd == LAUNCH_PY.parent


def test_a_local_io_server_keeps_its_config_out_of_git(launcher):
    module = importlib.import_module(type(launcher).__module__)
    config = module.SERVICES[module.ServiceType.IO]
    path = (
        LAUNCH_PY.parent / config.working_dir / config.env_vars["IO_CONFIG_FILE"]
    ).resolve()
    assert path == (LAUNCH_PY.parent / "config" / "io_config.json").resolve()
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", str(path)], cwd=LAUNCH_PY.parent
    ).returncode
    assert ignored == 0, f"{path} is not git-ignored"
