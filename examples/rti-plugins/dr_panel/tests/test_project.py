# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The IO project has the plugin layout (decision 0030): the package dr_panel
in src/, with the subpackages server and plugin."""

import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

IO = Path(__file__).resolve().parents[1]
PROJECT = tomllib.loads((IO / "pyproject.toml").read_text(encoding="utf-8"))


def test_the_distribution_is_named_after_the_package():
    assert PROJECT["project"]["name"] == "dr-panel"


def test_the_package_is_built_from_src():
    assert PROJECT["build-system"]["build-backend"] == "setuptools.build_meta"
    assert PROJECT["tool"]["setuptools"]["packages"]["find"]["where"] == ["src"]
    data = PROJECT["tool"]["setuptools"]["package-data"]
    assert data == {
        "dr_panel.server": ["io_config.json"],
        "dr_panel.plugin": ["io_mapping.json"],
    }


def test_the_server_and_the_plugin_are_subpackages():
    package = IO / "src" / "dr_panel"
    assert (package / "server" / "main.py").is_file()
    assert (package / "server" / "io_config.json").is_file()
    assert (package / "plugin" / "plugin.py").is_file()
    assert (package / "plugin" / "io_mapping.json").is_file()
    assert sorted(p.name for p in package.glob("*.py")) == ["__init__.py"]
    assert not (IO / "rti_io").exists()
    assert not (IO / "server").exists()


def test_the_script_starts_the_server():
    assert PROJECT["project"]["scripts"] == {"dr-panel": "dr_panel.server.main:main"}


def test_docker_and_compose_files_are_where_every_plugin_has_them():
    assert (IO / "docker" / "Dockerfile").is_file()
    assert (IO / "docker" / "Dockerfile.dockerignore").is_file()
    assert (IO / "docker-compose.yaml").is_file()
    assert (IO / "docker-compose.pi.yaml").is_file()


def test_it_depends_only_on_what_it_imports():
    names = {
        dep.split(">")[0].split("=")[0].split("<")[0].strip().lower()
        for dep in PROJECT["project"]["dependencies"]
    }
    assert names == {
        "fastapi",
        "pydantic",
        "uvicorn",
        "httpx2",
        "gpiod",
        "gpiozero",
        "smbus2",
        "adafruit-ads1x15",
    }
