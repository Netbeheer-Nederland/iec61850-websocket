# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The IO plugin on the plugin contract (decision 0021): loaded as acsi_io_plugin,
its routes under /api/plugins/io/, and what it does with each event."""

import asyncio
import json
import sys
from pathlib import Path

import pytest
from acsi_plugins import (
    Associated,
    OperateReceived,
    OperateResponse,
    PluginHost,
    ReportReceived,
    ServerStopped,
    ValueRead,
    ValueWritten,
    loader,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

PLUGIN = Path(__file__).resolve().parents[1] / "rti_io" / "plugin"


class FakeIO:
    """Stands in for the AsyncIOClient: records what the plugin asks of the IO server."""

    base_url = "http://io.test"

    def __init__(self):
        self.calls = []

    async def is_healthy(self):
        return True

    async def write_iec61850_value(self, obj_ref, value):
        self.calls.append(("value", obj_ref, value))

    async def write_lcd(self, device, text):
        self.calls.append(("lcd", device, text))

    async def set_device(self, device, state):
        self.calls.append(("set", device, state))

    async def aclose(self):
        pass


@pytest.fixture
def io_plugin(monkeypatch):
    monkeypatch.delenv("IO_URL", raising=False)
    plugin, manifest = loader.load("io", PLUGIN)
    fake = FakeIO()
    sys.modules["acsi_io_plugin.router"].set_io_client(fake)
    yield plugin, manifest, fake
    loader.unload_modules("io")


async def started(io_plugin, role):
    plugin, manifest, fake = io_plugin
    host = PluginHost(role=role, event_timeout=10)
    host.bind_loop(asyncio.get_running_loop())
    await host.add("io", plugin, version=manifest.version)
    # start() gives the router a fresh client when it has an io_url; with
    # none it keeps whatever the router has, here the fake.
    return host, fake


async def deliver(host, event):
    for f in host.emit(event):
        await asyncio.wrap_future(f)


def lcd(fake):
    return [c[2] for c in fake.calls if c[0] == "lcd" and c[1] == "lcd1"]


# ==================== Manifest and loading ====================


def test_the_manifest_names_every_plugin_file():
    manifest = json.loads((PLUGIN / "plugin.json").read_text(encoding="utf-8"))
    on_disk = sorted(
        p.name
        for p in PLUGIN.iterdir()
        if p.suffix in (".py", ".json") and p.name != "plugin.json"
    )
    assert manifest["name"] == "io"
    assert sorted(manifest["files"]) == on_disk


def test_loads_as_acsi_io_plugin(io_plugin):
    plugin, manifest, _ = io_plugin
    assert type(plugin).__module__ == "acsi_io_plugin.plugin"
    assert manifest.entry == "plugin:RtiIoPlugin"
    assert "rti_io_plugin" not in sys.modules


async def test_its_routes_have_no_api_io_prefix(io_plugin):
    host, _ = await started(io_plugin, "fsp")
    paths = {r.path for r in host.plugin("io").router().routes}
    assert "/leds/{name}/set" in paths
    assert not any(p.startswith("/api/io") for p in paths)
    await host.remove("io")


async def test_start_without_an_io_server_does_not_fail(io_plugin):
    plugin, manifest, _ = io_plugin
    host = PluginHost(role="fsp")
    await host.add(
        "io",
        plugin,
        settings={"io_url": "http://127.0.0.1:9"},
        version=manifest.version,
    )
    assert host.names() == ["io"]
    await host.remove("io")


def test_the_routes_are_reached_through_the_host(io_plugin, tmp_path):
    from acsi_plugins.web import PluginService, attach

    plugin, manifest, _ = io_plugin
    service = PluginService(
        PluginHost(role="fsp"), storage=tmp_path, allowed_sources=[]
    )
    app = FastAPI(lifespan=service.lifespan)
    attach(app, service)
    with TestClient(app) as client:
        client.portal.call(
            lambda: service.host.add("io", plugin, version=manifest.version)
        )
        body = client.get("/api/plugins/io/mappings").json()
    assert "led1" in json.dumps(body)


# ==================== Events in the FSP ====================


async def test_fsp_associated_lights_the_led_and_writes_the_lcd(io_plugin):
    host, fake = await started(io_plugin, "fsp")
    await deliver(host, Associated("cp1"))
    assert ("value", "connected", True) in fake.calls
    assert lcd(fake) == ["FSP Connected: cp1"]


async def test_fsp_operate_received_blinks_once(io_plugin):
    host, fake = await started(io_plugin, "fsp")
    await deliver(host, OperateReceived({"objRef": "LD0/CSWI1.Pos"}))
    assert [c for c in fake.calls if c[0] == "set"] == [
        ("set", "led2", True),
        ("set", "led2", False),
    ]


@pytest.mark.parametrize(
    ("event", "text"),
    [
        (OperateResponse(success=True), "Operation: SUCCESS"),
        (
            OperateResponse(success=False, add_cause="blocked-by-mode"),
            "Operation: FAILED - blocked-by-mode",
        ),
        (OperateResponse(success=False), "Operation: FAILED"),
    ],
)
async def test_fsp_operate_response_is_written_to_the_lcd(io_plugin, event, text):
    host, fake = await started(io_plugin, "fsp")
    await deliver(host, event)
    assert lcd(fake) == [text]


async def test_fsp_stop_turns_the_led_off(io_plugin):
    host, fake = await started(io_plugin, "fsp")
    await deliver(host, ServerStopped())
    assert ("value", "stopped", False) in fake.calls
    assert lcd(fake) == ["Stopped"]


async def test_fsp_write_goes_to_the_mapped_device(io_plugin):
    host, fake = await started(io_plugin, "fsp")
    await deliver(host, ValueWritten("LD0/MMXU1.TotW.mag.f", 12.5))
    assert ("value", "LD0/MMXU1.TotW.mag.f", 12.5) in fake.calls
    assert lcd(fake) == ["LD0/MMXU1.TotW.mag.f : 12.5"]


# ==================== Events in the SO ====================


async def test_so_associated_blinks_twice(io_plugin):
    host, fake = await started(io_plugin, "so")
    await deliver(host, Associated("cp2"))
    assert [c for c in fake.calls if c[0] == "set"].count(("set", "led1", True)) == 2
    assert lcd(fake) == ["Connected: cp2"]


async def test_so_report_is_shown(io_plugin):
    host, fake = await started(io_plugin, "so")
    await deliver(host, ReportReceived("rpt1", "LD0/LLN0.DS1"))
    assert lcd(fake) == ["rptID=rpt1 dataSet=LD0/LLN0.DS1"]


@pytest.mark.parametrize(
    ("event", "text"),
    [
        (ValueRead("LD0/MMXU1.TotW.mag.f", 3.0), "LD0/MMXU1.TotW.mag.f : 3.0"),
        (
            ValueRead("LD0/MMXU1.TotW.mag.f", None, ok=False),
            "Readvalue failed - LD0/MMXU1.TotW.mag.f fail",
        ),
    ],
)
async def test_so_read_is_shown(io_plugin, event, text):
    host, fake = await started(io_plugin, "so")
    await deliver(host, event)
    assert lcd(fake) == [text]


async def test_so_write_syncs_the_device_and_is_shown(io_plugin):
    host, fake = await started(io_plugin, "so")
    await deliver(host, ValueWritten("LD0/DWMX1.WMaxSpt", 7))
    assert ("value", "LD0/DWMX1.WMaxSpt", 7) in fake.calls
    assert lcd(fake) == ["Write - LD0/DWMX1.WMaxSpt Value: 7"]


async def test_so_write_blinks_led3(io_plugin):
    host, fake = await started(io_plugin, "so")
    await deliver(host, ValueWritten("LD0/DWMX1.WMaxSpt", 7))
    assert [c for c in fake.calls if c[0] == "set"] == [
        ("set", "led3", True),
        ("set", "led3", False),
    ]


async def test_so_failed_write_is_not_synced(io_plugin):
    host, fake = await started(io_plugin, "so")
    await deliver(host, ValueWritten("LD0/DWMX1.WMaxSpt", 7, ok=False))
    assert not [c for c in fake.calls if c[0] == "value"]
    assert lcd(fake) == ["Write - LD0/DWMX1.WMaxSpt fail"]


async def test_so_operate_is_shown(io_plugin):
    host, fake = await started(io_plugin, "so")
    await deliver(
        host, OperateResponse(success=True, obj_ref="LD0/DWMX1.WMaxSpt", value=5)
    )
    assert lcd(fake) == ["Oper LD0/DWMX1.WMaxSpt=5"]
