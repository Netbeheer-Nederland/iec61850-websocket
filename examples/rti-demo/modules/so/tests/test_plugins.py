# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The SO hosts plugins (decision 0021) and tells them what happens."""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from acsi_plugins import (
    AcsiPlugin,
    Associated,
    OperateResponse,
    PluginHost,
    ReportReceived,
    ValueRead,
    ValueWritten,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from so import bff_endpoint as be

pytestmark = pytest.mark.unit


class Recorder(AcsiPlugin):
    def __init__(self):
        self.events = []
        self.arrived = threading.Event()

    async def on_event(self, event):
        self.events.append(event)
        self.arrived.set()

    def wait(self):
        assert self.arrived.wait(2), "no event arrived"
        return self.events


@pytest.fixture
def plugin(monkeypatch):
    """A plugin, in a host on its own loop thread as the SO's app loop would be."""
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    host = PluginHost(role="so")
    host.bind_loop(loop)
    monkeypatch.setattr(be, "plugin_host", host)
    recorder = Recorder()
    asyncio.run_coroutine_threadsafe(host.add("rec", recorder), loop).result(5)
    yield recorder
    asyncio.run_coroutine_threadsafe(host.remove("rec"), loop).result(5)
    loop.call_soon_threadsafe(loop.stop)
    thread.join(5)
    loop.close()


@pytest.fixture
def so(monkeypatch):
    app = FastAPI()
    router, acsi_client = be.create_bff_router(app)
    app.include_router(router)
    acsi_client.runtime.endpoint = SimpleNamespace(websocket_info_list=[object()])
    monkeypatch.setattr(acsi_client, "get_iec61850_client", lambda cp: object())
    monkeypatch.setattr(
        acsi_client,
        "invoke_on_runtime_loop",
        lambda coro, timeout=10: (
            ThreadPoolExecutor(1).submit(asyncio.run, coro).result(timeout)
        ),
    )
    return TestClient(app), acsi_client


def answer(value):
    async def call(*args, **kwargs):
        return value

    return call


def test_an_association_is_an_event(plugin, so):
    _, acsi_client = so
    acsi_client.runtime.connected_callback({"associateId": "cp2"})
    assert plugin.wait() == [Associated("cp2")]


def test_a_report_is_an_event(plugin, so):
    _, acsi_client = so
    data = [{"dataRef": "LD0/MMXU1.TotW", "value": 3}]
    acsi_client.runtime.report_callback("rpt1", "LD0/LLN0.DS1", data)
    assert plugin.wait() == [ReportReceived("rpt1", "LD0/LLN0.DS1", data)]


def test_a_read_is_an_event(plugin, so, monkeypatch):
    client, acsi_client = so
    monkeypatch.setattr(acsi_client, "read_value", answer({"value": 3.0}))
    response = client.post(
        "/api/readvalue",
        json={"objRef": "LD0/MMXU1.TotW.mag.f", "fc": "MX", "cp": "cp1"},
    )
    assert response.status_code == 200, response.text
    assert plugin.wait() == [ValueRead("LD0/MMXU1.TotW.mag.f", 3.0)]


def test_a_failed_read_is_an_event(plugin, so, monkeypatch):
    client, acsi_client = so
    monkeypatch.setattr(acsi_client, "read_value", answer(None))
    client.post(
        "/api/readvalue",
        json={"objRef": "LD0/MMXU1.TotW.mag.f", "fc": "MX", "cp": "cp1"},
    )
    assert plugin.wait() == [ValueRead("LD0/MMXU1.TotW.mag.f", None, ok=False)]


def test_a_write_is_one_event(plugin, so, monkeypatch):
    client, acsi_client = so
    monkeypatch.setattr(
        acsi_client, "write_value", answer({"objRef": "LD0/DWMX1.WMaxSpt", "value": 7})
    )
    response = client.post(
        "/api/writevalue",
        json={
            "objRef": "LD0/DWMX1.WMaxSpt",
            "fc": "SP",
            "value": 7,
            "dataType": "int32",
            "cp": "cp1",
        },
    )
    assert response.status_code == 200, response.text
    assert plugin.wait() == [ValueWritten("LD0/DWMX1.WMaxSpt", 7)]
    acsi_client.runtime.write_callback("LD0/DWMX1.WMaxSpt", 7, "SP", "int32", True)
    assert plugin.events == [ValueWritten("LD0/DWMX1.WMaxSpt", 7)]


def test_a_refused_write_is_an_event(plugin, so, monkeypatch):
    client, acsi_client = so
    monkeypatch.setattr(
        acsi_client,
        "write_value",
        answer(
            {"objRef": "LD0/DWMX1.WMaxSpt", "value": None, "error": "accessViolation"}
        ),
    )
    client.post(
        "/api/writevalue",
        json={
            "objRef": "LD0/DWMX1.WMaxSpt",
            "fc": "SP",
            "value": 7,
            "dataType": "int32",
            "cp": "cp1",
        },
    )
    assert plugin.wait() == [ValueWritten("LD0/DWMX1.WMaxSpt", 7, ok=False)]


@pytest.mark.parametrize(
    ("result", "success", "cause"),
    [
        (True, True, None),
        ("blockedByInterlocking", False, "blockedByInterlocking"),
        (None, False, None),
    ],
)
def test_an_operate_answer_is_an_event(plugin, so, monkeypatch, result, success, cause):
    client, acsi_client = so
    monkeypatch.setattr(
        acsi_client,
        "operate",
        answer({"objRef": "LD0/DWMX1.WMaxSpt", "result": result}),
    )
    client.post(
        "/api/operate",
        json={
            "objRef": "LD0/DWMX1.WMaxSpt",
            "value": 5,
            "value_type": "int32",
            "cp": "cp1",
        },
    )
    [event] = plugin.wait()
    assert event == OperateResponse(
        success=success,
        add_cause=cause,
        obj_ref="LD0/DWMX1.WMaxSpt",
        value=5,
        data={"objRef": "LD0/DWMX1.WMaxSpt", "result": result},
    )


# ==================== The app ====================


@pytest.fixture
def app_client(monkeypatch, tmp_path):
    monkeypatch.setenv("SO_LISTEN_ON_START", "false")
    monkeypatch.setattr(
        be,
        "plugin_service",
        be.PluginService(
            be.plugin_host, storage=tmp_path / "plugins", allowed_sources=[]
        ),
    )
    with TestClient(be.create_fastapi_app(tmp_path)) as client:
        yield client


def test_the_app_lists_its_plugins(app_client):
    assert app_client.get("/api/plugins").json() == {"plugins": [], "failed": {}}


@pytest.mark.parametrize(
    "path", ["/api/io/leds", "/api/io-plugin/connect", "/api/io-client"]
)
def test_the_old_io_paths_are_not_served(app_client, path):
    assert app_client.post(path, json={}, follow_redirects=False).status_code == 404


def test_no_io_plugin_code_is_left_in_the_so():
    with open(be.__file__, encoding="utf-8") as f:
        text = f.read()
    for name in (
        "_use_io_client",
        "load_io_plugin_modules",
        "IO_PLUGIN_REQUIRED_FILES",
        "blink_led_task",
        "write_to_lcd",
    ):
        assert name not in text, name
