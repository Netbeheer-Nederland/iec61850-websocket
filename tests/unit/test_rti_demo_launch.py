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


def test_io_runs_as_a_module_from_modules_io_src(launcher):
    module = importlib.import_module(type(launcher).__module__)
    config = module.SERVICES[module.ServiceType.IO]
    cmd, cwd = launcher._command_for(config)
    assert cmd[-2:] == ["-m", "rpi_io.main"]
    assert cwd == LAUNCH_PY.parent / "modules" / "io" / "src"
    assert (cwd / "rpi_io" / "main.py").is_file()
    assert (LAUNCH_PY.parent / config.entry_point) == cwd / "rpi_io" / "main.py"


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


def _launch_module():
    return sys.modules["rti_demo_launch"]


def _config(launcher, role, port=None):
    module = _launch_module()
    return launcher._get_service_config(module.ServiceType(role), port)


@pytest.mark.parametrize(
    ("role", "port"), [("fsp", 5001), ("fsp2", 5005), ("so", 5000)]
)
def test_the_io_plugin_reaches_the_io_server_and_back(launcher, role, port):
    # The IO plugin is installed and starts by itself (decision 0022).
    env = _config(launcher, role).env_vars
    assert env["IO_URL"] == "http://localhost:9000"
    assert env["ACSI_BASE_URL"] == f"http://localhost:{port}"


def test_each_service_keeps_its_io_mapping_out_of_git(launcher):
    paths = {
        role: (LAUNCH_PY.parent / _config(launcher, role).env_vars["IO_MAPPING_FILE"])
        for role in ("fsp", "fsp2", "so")
    }
    assert (
        paths["fsp"]
        == LAUNCH_PY.parent / "config" / "plugins" / "fsp" / "io_mapping.json"
    )
    assert len(set(paths.values())) == 3
    for path in paths.values():
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", str(path)], cwd=LAUNCH_PY.parent
        ).returncode
        assert ignored == 0, f"{path} is not git-ignored"


def test_another_port_is_where_the_io_server_writes_to(launcher):
    assert _config(launcher, "so", 5010).env_vars["ACSI_BASE_URL"] == (
        "http://localhost:5010"
    )


def test_in_docker_the_io_plugin_uses_the_container_names(launcher):
    env = launcher._docker_env(_config(launcher, "fsp2"))
    assert env["IO_URL"] == "http://rti-io:9000"
    assert env["ACSI_BASE_URL"] == "http://rti-fsp2:5005"


def test_no_plugin_is_downloaded_by_default(launcher, monkeypatch):
    monkeypatch.delenv("PLUGIN_ALLOWED_SOURCES", raising=False)
    env = _launch_module()._plugin_env("fsp", 5001)
    assert env["PLUGIN_ALLOWED_SOURCES"] == ""


def test_a_developer_s_plugin_sources_are_allowed(launcher, monkeypatch):
    # GETTING_STARTED.md: serve a plugin folder and allow it when launching.
    monkeypatch.setenv("PLUGIN_ALLOWED_SOURCES", "http://localhost:8099")
    env = _launch_module()._plugin_env("so", 5000)
    assert env["PLUGIN_ALLOWED_SOURCES"] == "http://localhost:8099"
