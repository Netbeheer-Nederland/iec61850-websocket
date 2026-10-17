# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The IO server is a plugin of the FSP and SO (decision 0029): it implements
the plugin API under /plugin, and shows each event on its devices."""

import asyncio

import httpx2 as httpx
import pytest
from acsi_plugins import Associated, PluginEntry, PluginHost, ValueWritten
from acsi_plugins.web import PluginService, attach
from fastapi import FastAPI
from fastapi.testclient import TestClient
from rpi_io import io_controller as controller_module
from rpi_io.api_endpoint import create_fastapi_app
from rpi_io.io_controller import IOController
from rpi_io.mapping import SHIPPED_MAPPING, IOMappingManager
from rpi_io.plugin import EventRequest, Host, IoPlugin, StartRequest

pytestmark = pytest.mark.unit

FSP = {"name": "io", "role": "fsp", "host_url": "http://fsp.test:5001"}
SO = {"name": "io", "role": "so", "host_url": "http://so.test:5000"}


class Led:
    pass


class Display:
    def __init__(self, io, name):
        self.io, self.name = io, name

    def write(self, text):
        self.io.calls.append(("text", self.name, text))
        return True

    def write_line(self, line, text):
        return True


class FakeIO:
    """Stands in for the IOController: the shipped mapping's devices, and what was done to them."""

    def __init__(self):
        self.calls = []
        self._initialized = False
        self.devices = {name: Led() for name in ("led1", "led2", "led3")}
        self.devices.update({n: Display(self, n) for n in ("lcd1", "lcd_i2c")})

    def initialize(self):
        self._initialized = True
        return True

    def get_device(self, name):
        return self.devices.get(name)

    def write(self, name, value):
        self.calls.append(("set", name, value))
        return True


@pytest.fixture(autouse=True)
def acsi_state(monkeypatch):
    # The input sync keeps its target in module state; put it back after.
    monkeypatch.setattr(controller_module, "_acsi_config", None)
    monkeypatch.setattr(controller_module, "_device_mappings", {})


@pytest.fixture
def plugin():
    plugin = IoPlugin(FakeIO(), IOMappingManager(str(SHIPPED_MAPPING)))

    async def instant(_seconds):
        pass

    plugin.sleep = instant
    return plugin


async def deliver(plugin, host, event):
    plugin.handle(EventRequest(host=Host(**host), event=event))
    await asyncio.gather(*plugin._tasks)


def texts(plugin, device="lcd1"):
    return [c[2] for c in plugin.io.calls if c[0] == "text" and c[1] == device]


def sets(plugin):
    return [c for c in plugin.io.calls if c[0] == "set"]


# ==================== The plugin API ====================


def test_it_describes_itself():
    client = TestClient(create_fastapi_app(IOController()))
    body = client.get("/plugin").json()
    assert body["name"] == "io"
    assert body["api"] == 2
    assert body["claims"] == []
    assert body["routes"] == "/api/io"


def test_it_leaves_every_operate_to_the_fsp():
    client = TestClient(create_fastapi_app(IOController()))
    response = client.post(
        "/plugin/control", json={"host": FSP, "obj_ref": "LD0/X", "ctl_val": {}}
    )
    assert response.status_code == 204


def test_an_fsp_connects_to_it_through_its_plugin_configuration():
    # The FSP's plugin service, configured with this server's /plugin URL.
    io_app = create_fastapi_app(IOController())

    def client():
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=io_app), base_url="http://rti-io:9000"
        )

    host = PluginHost(role="fsp", host_url="http://fsp.test:5001")
    service = PluginService(
        host,
        configured=[PluginEntry("io", "http://rti-io:9000/plugin")],
        client_factory=client,
        retry_seconds=0,
    )
    app = FastAPI(lifespan=service.lifespan)
    attach(app, service)
    with TestClient(app) as fsp:
        [status] = fsp.get("/api/plugins").json()["plugins"]
        assert (status["name"], status["routes"]) == ("io", True)
        # Its routes are this server's /api/io.
        assert fsp.get("/api/plugins/io/health").status_code == 200
        for f in host.emit(Associated("cp1")):
            f.result(5)
        assert fsp.get("/api/plugins/io").json()["healthy"] is True
        hosts = TestClient(io_app).get("/plugin/mappings").json()["hosts"]
    assert hosts == [{"name": "io", "role": "fsp", "host_url": "http://fsp.test:5001"}]


# ==================== Start and stop: where inputs go ====================


def test_start_has_the_inputs_write_to_the_host(plugin):
    plugin.start(StartRequest(**FSP))
    assert plugin.io._initialized
    config = controller_module.get_acsi_config()
    assert (config.url, config.enabled) == ("http://fsp.test:5001", True)
    assert controller_module.get_device_mapping("button1") == {
        "objRef": "LD0/DWMX1.DERAvail.stVal",
        "fc": "st",
        "service": "writeValue",
        "dataType": "",
    }
    assert controller_module.get_device_mapping("pot2")["service"] == "operate"
    # Outputs aren't inputs.
    assert controller_module.get_device_mapping("led1") is None


def test_a_host_can_keep_the_inputs_away(plugin):
    plugin.start(StartRequest(**FSP))
    plugin.start(StartRequest(**SO, settings={"write_inputs": False}))
    assert controller_module.get_acsi_config().url == "http://fsp.test:5001"


def test_stop_ends_the_inputs_to_that_host(plugin):
    plugin.start(StartRequest(**FSP))
    plugin.stop(Host(**FSP))
    assert controller_module.get_acsi_config().enabled is False
    assert plugin.hosts == {}


# ==================== Events from an FSP ====================


async def test_fsp_associated_lights_the_led_and_writes_the_displays(plugin):
    await deliver(plugin, FSP, {"type": "Associated", "associate_id": "cp1"})
    assert ("set", "led1", True) in sets(plugin)
    assert texts(plugin) == ["FSP Connected: cp1"]
    assert texts(plugin, "lcd_i2c") == ["FSP Connected: cp1"]


async def test_fsp_operate_received_blinks_once(plugin):
    await deliver(plugin, FSP, {"type": "OperateReceived", "data": {}})
    assert sets(plugin) == [("set", "led2", True), ("set", "led2", False)]


@pytest.mark.parametrize(
    ("event", "text"),
    [
        ({"success": True}, "Operation: SUCCESS"),
        (
            {"success": False, "add_cause": "blocked-by-mode"},
            "Operation: FAILED - blocked-by-mode",
        ),
        ({"success": False, "add_cause": None}, "Operation: FAILED"),
    ],
)
async def test_fsp_operate_response_is_shown(plugin, event, text):
    await deliver(plugin, FSP, {"type": "OperateResponse", **event})
    assert texts(plugin) == [text]


async def test_fsp_stop_turns_the_led_off(plugin):
    await deliver(plugin, FSP, {"type": "ServerStopped"})
    assert ("set", "led1", False) in sets(plugin)
    assert texts(plugin) == ["Stopped"]


async def test_fsp_write_is_shown(plugin):
    event = {"type": "ValueWritten", "obj_ref": "LD0/MMXU1.TotW.mag.f", "value": 12.5}
    await deliver(plugin, FSP, event)
    assert texts(plugin) == ["LD0/MMXU1.TotW.mag.f : 12.5"]
    # pot1 is an input: a write doesn't set it.
    assert sets(plugin) == []


# ==================== Events from an SO ====================


async def test_so_associated_blinks_twice(plugin):
    await deliver(plugin, SO, {"type": "Associated", "associate_id": "cp2"})
    assert sets(plugin).count(("set", "led1", True)) == 2
    assert texts(plugin) == ["Connected: cp2"]


async def test_so_report_is_shown(plugin):
    event = {"type": "ReportReceived", "rpt_id": "rpt1", "data_set": "LD0/LLN0.DS1"}
    await deliver(plugin, SO, event)
    assert texts(plugin) == ["rptID=rpt1 dataSet=LD0/LLN0.DS1"]
    assert ("set", "led2", True) in sets(plugin)


@pytest.mark.parametrize(
    ("ok", "text"),
    [
        (True, "LD0/MMXU1.TotW.mag.f : 3.0"),
        (False, "Readvalue failed - LD0/MMXU1.TotW.mag.f fail"),
    ],
)
async def test_so_read_is_shown(plugin, ok, text):
    event = {
        "type": "ValueRead",
        "obj_ref": "LD0/MMXU1.TotW.mag.f",
        "value": 3.0,
        "ok": ok,
    }
    await deliver(plugin, SO, event)
    assert texts(plugin) == [text]


async def test_so_write_blinks_the_setpoint_led(plugin):
    event = {
        "type": "ValueWritten",
        "obj_ref": "LD0/DWMX1.WMaxSpt",
        "value": 7,
        "ok": True,
    }
    await deliver(plugin, SO, event)
    assert texts(plugin) == ["Write - LD0/DWMX1.WMaxSpt Value: 7"]
    assert ("set", "led3", True) in sets(plugin)


async def test_so_operate_answer_is_shown(plugin):
    event = {"type": "OperateResponse", "success": True, "obj_ref": "LD0/X", "value": 1}
    await deliver(plugin, SO, event)
    assert texts(plugin) == ["Oper LD0/X=1"]


async def test_an_unknown_event_is_ignored(plugin):
    await deliver(plugin, FSP, {"type": "SomethingNew"})
    assert plugin.io.calls == []


def test_the_events_endpoint_answers_before_the_work_is_done():
    client = TestClient(create_fastapi_app(IOController()))
    response = client.post(
        "/plugin/events",
        json={"host": SO, "event": {"type": "Associated", "associate_id": "x"}},
    )
    assert response.status_code == 202


def test_the_host_sends_events_the_plugin_reads():
    # What acsi_plugins sends is what this plugin matches on.
    from acsi_plugins import event_json

    assert event_json(ValueWritten("LD0/X", 1))["type"] == "ValueWritten"
