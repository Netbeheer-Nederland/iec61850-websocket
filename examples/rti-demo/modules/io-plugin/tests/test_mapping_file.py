# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""Which io_mapping.json the IO plugin reads and saves to (decision 0022).

Installed, the plugin's own folder is shared by every FSP and SO that runs
from it, so each one keeps its mapping in a file of its own: the setting
mapping_file, else IO_MAPPING_FILE, seeded once from the shipped file.
"""

import json
from pathlib import Path

import pytest
from acsi_io_plugin import router as io_router
from acsi_io_plugin.mapping import SHIPPED_MAPPING, resolve_mapping_path
from acsi_io_plugin.plugin import RtiIoPlugin
from acsi_plugins import PluginHost

pytestmark = pytest.mark.unit

SHIPPED = (
    Path(__file__).resolve().parents[1] / "src" / "acsi_io_plugin" / "io_mapping.json"
)


@pytest.fixture(autouse=True)
def fresh_router(monkeypatch):
    monkeypatch.delenv("IO_MAPPING_FILE", raising=False)
    monkeypatch.delenv("IO_URL", raising=False)
    io_router.set_mapping_manager(None)
    yield
    io_router.set_mapping_manager(None)


def test_the_shipped_file_is_the_one_in_the_package():
    assert SHIPPED_MAPPING == SHIPPED


def test_without_a_file_it_is_the_shipped_file():
    assert resolve_mapping_path(None) == SHIPPED


def test_a_new_file_is_seeded_from_the_shipped_file(tmp_path):
    target = tmp_path / "fsp" / "io_mapping.json"
    assert resolve_mapping_path(str(target)) == target
    assert json.loads(target.read_text(encoding="utf-8")) == json.loads(
        SHIPPED.read_text(encoding="utf-8")
    )


def test_an_existing_file_is_kept(tmp_path):
    target = tmp_path / "io_mapping.json"
    target.write_text('{"devices": {}}', encoding="utf-8")
    assert resolve_mapping_path(str(target)) == target
    assert target.read_text(encoding="utf-8") == '{"devices": {}}'


async def start(settings):
    host = PluginHost(role="fsp")
    await host.add("io", RtiIoPlugin(), settings=settings)
    return host


async def test_the_plugin_uses_its_mapping_file_setting(tmp_path):
    target = tmp_path / "io_mapping.json"
    host = await start({"mapping_file": str(target)})
    assert io_router.get_mapping_manager().mapping_path == target
    assert target.exists()
    await host.remove("io")


async def test_the_plugin_falls_back_to_io_mapping_file(tmp_path, monkeypatch):
    target = tmp_path / "io_mapping.json"
    monkeypatch.setenv("IO_MAPPING_FILE", str(target))
    host = await start({})
    assert io_router.get_mapping_manager().mapping_path == target
    await host.remove("io")


async def test_a_save_changes_its_own_file_not_the_shipped_one(tmp_path):
    before = SHIPPED.read_bytes()
    target = tmp_path / "io_mapping.json"
    host = await start({"mapping_file": str(target)})
    manager = io_router.get_mapping_manager()
    manager.add_mapping("led_test", description="changed by the test")
    assert manager.save()
    assert "changed by the test" in target.read_text(encoding="utf-8")
    assert SHIPPED.read_bytes() == before
    await host.remove("io")
