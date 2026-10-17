# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The FSP hosts plugins (decision 0021): it tells them what happens, and an
Operate on an objRef a plugin owns gets that plugin's answer."""

import asyncio
import threading

import pytest
from acsi_plugins import (
    AcsiPlugin,
    Associated,
    ControlResult,
    OperateReceived,
    OperateResponse,
    PluginHost,
    ServerStopped,
    ValueWritten,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fsp import bff_endpoint as be

from ws61850.iec61850.server.control_handling import (
    ControlHandlerResult,
    ControlServiceStatusKind,
)

pytestmark = pytest.mark.unit

POS = "LD0/CSWI1.Pos.Oper.ctlVal"
CTL_VAL = {"type": "boolean", "value": ("boolean", True)}


class Recorder(AcsiPlugin):
    def __init__(self, owns=(), answer=None):
        self.owns = owns
        self.answer = answer
        self.events = []
        self.arrived = threading.Event()

    def claims(self):
        return self.owns

    async def on_event(self, event):
        self.events.append(event)
        self.arrived.set()

    def handle_control(self, obj_ref, ctl_val):
        return self.answer

    def wait(self):
        assert self.arrived.wait(2), "no event arrived"
        return self.events


@pytest.fixture
def host(monkeypatch):
    """A plugin host on its own loop thread, as the FSP's app loop would be."""
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    host = PluginHost(role="fsp", control_timeout=1)
    host.bind_loop(loop)
    monkeypatch.setattr(be, "plugin_host", host)
    host.add_now = lambda name, plugin: asyncio.run_coroutine_threadsafe(
        host.add(name, plugin), loop
    ).result(5)
    yield host
    for name in host.names():
        asyncio.run_coroutine_threadsafe(host.remove(name), loop).result(5)
    loop.call_soon_threadsafe(loop.stop)
    thread.join(5)
    loop.close()


@pytest.fixture
def model_dir(tmp_path):
    (tmp_path / "model.py").write_text(
        "from ws61850.iec61850.data_model.ied_model import IedModel\n"
        "ied = IedModel(name='TestIED')\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def fsp(model_dir):
    app = FastAPI()
    router, server = be.create_bff_router(model_dir)
    app.include_router(router)
    return TestClient(app), server


# ==================== Operate ====================


def test_the_owner_of_an_objref_answers_its_operate(host, fsp):
    _, server = fsp
    host.add_now(
        "owner",
        Recorder(owns=[POS], answer=ControlResult(False, "blockedByInterlocking")),
    )
    assert server.handle_control(POS, CTL_VAL, None) == (
        ControlHandlerResult.FAILED,
        ControlServiceStatusKind.blockedByInterlocking,
    )


def test_an_owner_can_accept_an_operate(host, fsp):
    _, server = fsp
    host.add_now("owner", Recorder(owns=[POS], answer=ControlResult(True)))
    assert server.handle_control(POS, CTL_VAL, None) == (ControlHandlerResult.OK, None)


def test_an_unknown_add_cause_is_sent_as_unknown(host, fsp):
    _, server = fsp
    host.add_now(
        "owner", Recorder(owns=[POS], answer=ControlResult(False, "notACause"))
    )
    assert server.handle_control(POS, CTL_VAL, None) == (
        ControlHandlerResult.FAILED,
        ControlServiceStatusKind.unknown,
    )


def test_an_objref_no_plugin_owns_is_checked_as_before(host, fsp):
    _, server = fsp
    host.add_now(
        "owner",
        Recorder(owns=["LD0/XCBR1.Pos.Oper.ctlVal"], answer=ControlResult(False)),
    )
    assert server.handle_control(POS, CTL_VAL, None) == (ControlHandlerResult.OK, None)
    wrong_type = {"type": "boolean", "value": ("boolean", "yes")}
    assert server.handle_control(POS, wrong_type, None) == (
        ControlHandlerResult.FAILED,
        ControlServiceStatusKind.invalidPosition,
    )


# ==================== Events ====================


def test_an_association_is_an_event(host, fsp):
    _, server = fsp
    plugin = Recorder()
    host.add_now("rec", plugin)
    server.runtime.connected_callback({"associateId": "cp1"})
    assert plugin.wait() == [Associated("cp1")]


def test_an_operate_request_is_an_event(host, fsp):
    _, server = fsp
    plugin = Recorder()
    host.add_now("rec", plugin)
    server.runtime.operate_received_callback({"objRef": POS})
    assert plugin.wait() == [OperateReceived({"objRef": POS})]


def test_an_operate_response_is_an_event(host, fsp):
    _, server = fsp
    plugin = Recorder()
    host.add_now("rec", plugin)
    answer = {"success": False, "addCause": "blockedByMode"}
    server.runtime.operate_response_callback(answer)
    assert plugin.wait() == [
        OperateResponse(success=False, add_cause="blockedByMode", data=answer)
    ]


def test_a_local_write_is_an_event(host, fsp):
    client, server = fsp
    plugin = Recorder()
    host.add_now("rec", plugin)
    server.runtime.server = object()
    server.write_value = lambda obj_ref, value, data_type: {
        "objRef": obj_ref,
        "value": 12.5,
        "dataType": "float32",
    }
    response = client.post(
        "/api/writevalue",
        json={"objRef": "LD0/MMXU1.TotW.mag.f", "fc": "MX", "value": "12.5"},
    )
    assert response.status_code == 200, response.text
    assert plugin.wait() == [ValueWritten("LD0/MMXU1.TotW.mag.f", 12.5)]


def test_disconnect_tells_the_plugins_before_the_connection_drops(host, fsp):
    client, server = fsp
    order = []

    class Watcher(Recorder):
        async def on_event(self, event):
            await asyncio.sleep(0.1)
            order.append(type(event).__name__)

    host.add_now("watch", Watcher())
    server.runtime.status = "listening"
    server.disconnect = lambda: order.append("disconnect")
    assert client.post("/api/stop").status_code == 200
    assert order == ["ServerStopped", "disconnect"]


def test_events_without_plugins_are_fine(host, fsp):
    _, server = fsp
    server.runtime.connected_callback({"associateId": "cp1"})
    server.runtime.operate_response_callback({"success": True})


# ==================== The app ====================


@pytest.fixture
def app_client(model_dir, monkeypatch):
    monkeypatch.setenv("MODELPATH", str(model_dir))
    monkeypatch.setattr(
        be,
        "plugin_service",
        be.PluginService(be.plugin_host),
    )
    with TestClient(be.create_fastapi_app()) as client:
        yield client


def test_without_a_plugin_configuration_the_app_has_no_plugins(app_client):
    # Nothing is built in: plugins come from the configuration (decision 0029).
    assert app_client.get("/api/plugins").json() == {"plugins": [], "failed": {}}


def test_the_fsp_has_no_io_plugin_code_installed():
    import importlib.util

    assert importlib.util.find_spec("acsi_io_plugin") is None


@pytest.mark.parametrize("path", ["/api/io/leds", "/api/io-plugin/connect"])
def test_the_old_io_paths_are_not_served(app_client, path):
    assert app_client.post(path, json={}, follow_redirects=False).status_code == 404


def test_no_io_plugin_code_is_left_in_the_fsp():
    source = be.__file__
    with open(source, encoding="utf-8") as f:
        text = f.read()
    for name in (
        "_use_io_plugin",
        "load_io_plugin_modules",
        "IO_PLUGIN_REQUIRED_FILES",
        "blink_led_task",
        "write_to_lcd",
    ):
        assert name not in text, name


def test_stopping_the_app_stops_its_plugins(model_dir, monkeypatch):
    monkeypatch.setenv("MODELPATH", str(model_dir))
    host = PluginHost(role="fsp")
    service = be.PluginService(host)
    monkeypatch.setattr(be, "plugin_host", host)
    monkeypatch.setattr(be, "plugin_service", service)
    stopped = []

    class Stops(AcsiPlugin):
        async def stop(self):
            stopped.append(True)

    with TestClient(be.create_fastapi_app()) as client:
        client.portal.call(host.add, "stops", Stops())
    assert stopped == [True]


def test_stop_emits_server_stopped(host, fsp):
    client, server = fsp
    plugin = Recorder()
    host.add_now("rec", plugin)
    server.runtime.status = "listening"
    server.disconnect = lambda: None
    client.post("/api/stop")
    assert plugin.wait() == [ServerStopped()]
