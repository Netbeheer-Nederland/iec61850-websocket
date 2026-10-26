# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""examples/rti-demo/launch.py's options, as its README documents them."""

import importlib.util
import json
import os
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
# The IO plugin is its own stack (decisions 0028, 0030); launch.py still runs it.
IO_PLUGIN = LAUNCH_PY.parents[1] / "rti-plugins" / "dr_panel"


def test_every_service_type_is_an_rti_type(launcher):
    module = importlib.import_module(type(launcher).__module__)
    types = {c.labels["rti.type"] for c in module.SERVICES.values()}
    assert all(t.startswith("RTI-") for t in types), types


def test_compose_and_launch_agree_on_the_type(launcher):
    module = importlib.import_module(type(launcher).__module__)
    compose = {
        **yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"],
        **yaml.safe_load(
            (IO_PLUGIN / "docker-compose.yaml").read_text(encoding="utf-8")
        )["services"],
    }
    for config in module.SERVICES.values():
        service = compose.get(config.labels["rti.service"])
        if service is None:  # the FSPs are named differently in compose
            continue
        labels = dict(label.split("=", 1) for label in service.get("labels", []))
        assert labels["rti.type"] == config.labels["rti.type"], config.labels[
            "rti.service"
        ]


def test_io_runs_as_a_module_from_the_io_plugin_s_src(launcher):
    module = importlib.import_module(type(launcher).__module__)
    config = module.SERVICES[module.ServiceType.IO]
    cmd, cwd = launcher._command_for(config)
    assert cmd[-2:] == ["-m", "dr_panel.server.main"]
    assert cwd.resolve() == IO_PLUGIN / "src"
    main = cwd / "dr_panel" / "server" / "main.py"
    assert main.is_file()
    assert (LAUNCH_PY.parent / config.entry_point).resolve() == main.resolve()


def test_io_files_are_the_demo_s_git_ignored_copies(launcher):
    module = importlib.import_module(type(launcher).__module__)
    config = module.SERVICES[module.ServiceType.IO]
    _, cwd = launcher._command_for(config)
    config_dir = (LAUNCH_PY.parent / "config").resolve()
    for var in ("IO_CONFIG_FILE", "IO_MAPPING_FILE"):
        assert (cwd / config.env_vars[var]).resolve().parent == config_dir, var


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
def test_each_fsp_and_so_connects_the_io_plugin(launcher, role, port):
    # The IO server's plugin API, from the plugin configuration (decision 0029).
    env = _config(launcher, role).env_vars
    [io] = json.loads(env["PLUGINS"])
    assert io["url"] == "http://localhost:9000/plugin"
    assert env["PLUGIN_HOST_URL"] == f"http://localhost:{port}"
    # Only the first FSP gets the input devices' changes.
    assert io.get("settings", {}).get("write_inputs", True) is (role == "fsp")


def test_the_io_server_keeps_its_mapping_out_of_git(launcher):
    module = _launch_module()
    config = module.SERVICES[module.ServiceType.IO]
    path = (
        LAUNCH_PY.parent / config.working_dir / config.env_vars["IO_MAPPING_FILE"]
    ).resolve()
    assert path == (LAUNCH_PY.parent / "config" / "io_mapping.json").resolve()
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", str(path)], cwd=LAUNCH_PY.parent
    ).returncode
    assert ignored == 0, f"{path} is not git-ignored"


def test_another_port_is_where_the_plugins_reach_it(launcher):
    assert _config(launcher, "so", 5010).env_vars["PLUGIN_HOST_URL"] == (
        "http://localhost:5010"
    )


def test_in_docker_the_plugins_use_the_container_names(launcher):
    env = launcher._docker_env(_config(launcher, "fsp2"))
    assert json.loads(env["PLUGINS"])[0]["url"] == "http://dr-panel:9000/plugin"
    assert env["PLUGIN_HOST_URL"] == "http://rti-fsp2:5005"


def test_the_so_an_fsp_connects_to_is_localhost_or_in_docker_by_name(launcher):
    # Decision 0033: where FSP_AUTOCONNECT dials.
    config = _config(launcher, "fsp")
    assert config.env_vars["FSP_SO_HOST"] == "localhost"
    assert launcher._docker_env(config)["FSP_SO_HOST"] == "rti-so"


def test_allowed_sources_are_left_to_the_services_default(launcher, monkeypatch):
    # Unset, the FSP and SO allow any URL (decision 0037).
    monkeypatch.delenv("PLUGIN_ALLOWED_SOURCES", raising=False)
    env = _launch_module()._plugin_env("fsp", 5001)
    assert "PLUGIN_ALLOWED_SOURCES" not in env


def test_allowed_sources_set_empty_are_passed_on(launcher, monkeypatch):
    monkeypatch.setenv("PLUGIN_ALLOWED_SOURCES", "")
    env = _launch_module()._plugin_env("fsp", 5001)
    assert env["PLUGIN_ALLOWED_SOURCES"] == ""


def test_a_developer_s_plugin_sources_are_allowed(launcher, monkeypatch):
    # GETTING_STARTED.md: serve a plugin folder and allow it when launching.
    monkeypatch.setenv("PLUGIN_ALLOWED_SOURCES", "http://localhost:8099")
    env = _launch_module()._plugin_env("so", 5000)
    assert env["PLUGIN_ALLOWED_SOURCES"] == "http://localhost:8099"


def test_in_docker_the_io_server_is_named_after_its_plugin():
    module = _launch_module()
    assert module.container_name(module.ServiceType.IO) == "dr-panel"
    assert module.container_name(module.ServiceType.SO) == "rti-so"


def test_in_docker_the_io_server_runs_the_dr_panel_image(launcher):
    # The image docker-compose.io.yaml runs (decision 0038), not an rti-<role> one.
    overlay = yaml.safe_load(
        (LAUNCH_PY.parent / "docker-compose.io.yaml").read_text(encoding="utf-8")
    )
    service = overlay["services"]["dr-panel"]
    repo = os.environ.get("RTI_IMAGE_REPO", "netbeheer-nederland/iec61850-websocket")
    tag = os.environ.get("RTI_IMAGE_TAG", "latest")
    expected = (
        service["image"]
        .replace("${RTI_IMAGE_REPO:-netbeheer-nederland/iec61850-websocket}", repo)
        .replace("${RTI_IMAGE_TAG:-latest}", tag)
    )
    assert expected == f"{repo}/dr-panel:{tag}"
    assert _config(launcher, "io").docker_image == expected
