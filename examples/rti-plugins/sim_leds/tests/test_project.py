# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""sim_leds has the plugin layout (decision 0030): the package sim_leds in
src/, with the subpackages server and plugin, and its own image and stack."""

import ast
import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
PACKAGE = ROOT / "src" / "sim_leds"


def test_the_server_and_the_plugin_are_subpackages():
    assert (PACKAGE / "server" / "app.py").is_file()
    assert (PACKAGE / "plugin" / "plugin.py").is_file()
    assert sorted(p.name for p in PACKAGE.glob("*.py")) == ["__init__.py"]


def test_the_script_starts_the_server():
    assert PROJECT["project"]["scripts"] == {"sim-leds": "sim_leds.server.main:main"}


def test_docker_and_compose_files_are_where_every_plugin_has_them():
    assert (ROOT / "docker" / "Dockerfile").is_file()
    assert (ROOT / "docker" / "Dockerfile.dockerignore").is_file()
    assert (ROOT / "docker-compose.yaml").is_file()
    assert (ROOT / "uv.lock").is_file()


def test_it_imports_nothing_of_the_fsp_or_so():
    imported = set()
    for path in PACKAGE.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                imported.add(node.module.split(".")[0])
    assert imported <= {
        "__future__",
        "asyncio",
        "collections",
        "contextlib",
        "importlib",
        "os",
        "time",
        "typing",
        "fastapi",
        "pydantic",
        "uvicorn",
    }
