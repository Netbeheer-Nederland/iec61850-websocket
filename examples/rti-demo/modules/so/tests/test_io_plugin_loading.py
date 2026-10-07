# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The SO loads the IO plugin's files and finds what it uses from them."""

import shutil
from pathlib import Path

import pytest
from so import bff_endpoint as be

# The plugin files the IO server serves, as they are in the repository.
PLUGIN_SRC = Path(__file__).resolve().parents[2] / "io" / "io_client"

ROUTER_FUNCTIONS = ("create_io_router", "get_io_client", "get_mapping_manager")
UTILS_FUNCTIONS = ("sync_to_io_device", "write_to_lcd", "blink_led_task")


@pytest.fixture
def plugin_dir(tmp_path, monkeypatch):
    """The plugin files, as a download would leave them."""
    for name in be.IO_PLUGIN_REQUIRED_FILES:
        shutil.copy(PLUGIN_SRC / name, tmp_path / name)
    monkeypatch.setattr(be, "IO_PLUGIN_DYNAMIC_DIR", tmp_path)
    yield tmp_path
    be.clear_io_plugin_modules()


def test_the_repository_has_every_required_file():
    missing = [n for n in be.IO_PLUGIN_REQUIRED_FILES if not (PLUGIN_SRC / n).is_file()]
    assert not missing


def test_loads_the_plugin(plugin_dir):
    assert be.load_io_plugin_modules() is True
    for name in ROUTER_FUNCTIONS:
        assert callable(getattr(be._io_plugin_module, name)), name
    for name in UTILS_FUNCTIONS:
        assert callable(getattr(be._io_utils_module, name)), name
    assert be._io_plugin_module.create_io_router() is not None


def test_a_missing_file_fails_the_load(plugin_dir):
    (plugin_dir / be.IO_PLUGIN_REQUIRED_FILES[0]).unlink()
    assert be.load_io_plugin_modules() is False
