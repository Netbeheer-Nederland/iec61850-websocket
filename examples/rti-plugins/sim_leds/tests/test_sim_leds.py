# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The sample plugin sim_leds is an HTTP service on the plugin API: an FSP
connects to it from its plugin configuration and its LEDs show the events
(decision 0029; modules/plugins/GETTING_STARTED.md in examples/rti-demo).

Copy this file next to your own plugin: it runs the FSP's plugin service
against the plugin's app, with no FSP, SO or network."""

import asyncio

import httpx2 as httpx
import pytest
from acsi_plugins import (
    Associated,
    OperateResponse,
    PluginEntry,
    PluginHost,
    ServerStopped,
    ValueRead,
    ValueWritten,
)
from acsi_plugins.web import PluginService, attach
from fastapi import FastAPI
from sim_leds.plugin import plugin
from sim_leds.server.app import create_app

pytestmark = pytest.mark.unit

URL = "http://sim-leds.test/plugin"
POS = "LD0/CSWI1.Pos.Oper.ctlVal"


@pytest.fixture
async def setup(monkeypatch):
    monkeypatch.setenv("SIM_LEDS_CLAIMS", POS)
    plugin_app = create_app()

    def plugin_client():
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=plugin_app),
            base_url="http://sim-leds.test",
        )

    host = PluginHost(role="fsp", host_url="http://fsp.test:5001")
    service = PluginService(
        host,
        configured=[PluginEntry("sim_leds", URL, {"blink_seconds": 0.05})],
        client_factory=plugin_client,
        retry_seconds=0,
    )
    app = FastAPI()
    attach(app, service)
    await service.startup()
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://fsp"
    )
    assert service.failed == {}
    yield host, client
    await client.aclose()
    await service.shutdown()


async def deliver(host, event):
    for future in host.emit(event):
        await asyncio.wrap_future(future)


async def leds(client):
    return (await client.get("/api/plugins/sim_leds/leds")).json()["leds"]


async def test_the_fsp_connects_to_it(setup):
    _, client = setup
    body = (await client.get("/api/plugins/sim_leds")).json()
    # From the package metadata: "" here, where sim-leds isn't installed.
    assert body["version"] == plugin._version()
    assert body["claims"] == [POS]
    assert body["healthy"] is True
    assert await leds(client) == {"red": False, "green": False}


async def test_an_association_turns_green_on_and_a_disconnect_turns_it_off(setup):
    host, client = setup
    await deliver(host, Associated("cp1"))
    assert await leds(client) == {"red": False, "green": True}
    await deliver(host, ServerStopped())
    assert await leds(client) == {"red": False, "green": False}
    history = (await client.get("/api/plugins/sim_leds/leds")).json()["history"]
    assert history[-1]["reason"] == "disconnected"


async def test_a_failed_operate_turns_red_on_until_a_good_one(setup):
    host, client = setup
    await deliver(host, OperateResponse(success=False, add_cause="blockedByMode"))
    assert (await leds(client))["red"] is True
    history = (await client.get("/api/plugins/sim_leds/leds")).json()["history"]
    assert history[-1]["reason"] == "operate failed: blockedByMode"
    await deliver(host, OperateResponse(success=True))
    assert (await leds(client))["red"] is False


async def test_a_good_write_blinks_green(setup):
    host, client = setup
    await deliver(host, ValueWritten("LD0/MMXU1.TotW.mag.f", 1.5))
    assert (await leds(client))["green"] is True
    await asyncio.sleep(0.15)
    assert (await leds(client))["green"] is False


@pytest.mark.parametrize(
    "event",
    [ValueWritten("LD0/X.Y", 1, ok=False), ValueRead("LD0/X.Y", None, ok=False)],
)
async def test_a_failed_write_or_read_turns_red_on(setup, event):
    host, client = setup
    await deliver(host, event)
    assert (await leds(client))["red"] is True


async def test_an_operate_is_refused_while_red_is_on(setup):
    host, client = setup
    assert await asyncio.to_thread(host.handle_control, POS, {}) is None
    await client.post("/api/plugins/sim_leds/leds/red", json={"on": True})
    answer = await asyncio.to_thread(host.handle_control, POS, {})
    assert (answer.ok, answer.add_cause) == (False, "blockedByInterlocking")


async def test_an_led_can_be_set_and_reset_by_hand(setup):
    _, client = setup
    await client.post("/api/plugins/sim_leds/leds/red", json={"on": True})
    assert (await leds(client))["red"] is True
    await client.post("/api/plugins/sim_leds/leds/reset")
    assert await leds(client) == {"red": False, "green": False}
    response = await client.post("/api/plugins/sim_leds/leds/blue", json={"on": True})
    assert response.status_code == 404


async def test_the_fsp_lists_its_two_leds_as_attached(setup):
    host, client = setup
    await deliver(host, Associated("cp1"))

    [status] = (await client.get("/api/plugins")).json()["plugins"]

    [item] = status["attached"]
    assert item["label"] == "Simulated LEDs"
    assert item["live"] == [
        {
            "type": "indicators",
            "items": [
                {"name": "red", "on": False, "color": "red"},
                {"name": "green", "on": True, "color": "green"},
            ],
        }
    ]
