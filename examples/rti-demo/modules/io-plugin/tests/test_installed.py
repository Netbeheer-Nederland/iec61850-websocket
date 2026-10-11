# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The IO plugin is installed with the FSP and SO, not downloaded (decision 0022)."""

import ast
from pathlib import Path

import pytest
from acsi_plugins import loader

pytestmark = pytest.mark.unit

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "acsi_io_plugin"


def test_the_plugin_host_finds_it_as_io():
    cls, version = loader.installed()["io"]
    assert (cls.__module__, cls.__name__) == ("acsi_io_plugin.plugin", "RtiIoPlugin")
    assert version == "2.0.0"


def test_it_has_no_download_manifest():
    assert not (PACKAGE / "plugin.json").exists()


@pytest.mark.parametrize("path", sorted(PACKAGE.glob("*.py")), ids=lambda p: p.name)
def test_it_imports_nothing_of_the_io_server(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = [
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    ] + [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    ]
    # rpi_io, and rti_io before decision 0023.
    assert [m for m in imported if m.split(".")[0] in {"rpi_io", "rti_io"}] == []
