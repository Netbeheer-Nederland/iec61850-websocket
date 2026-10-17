# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The sample plugin sim_leds installs like any downloaded plugin and shows
events on its two simulated LEDs (modules/plugins/GETTING_STARTED.md in
examples/rti-demo)."""

import asyncio
from pathlib import Path

import httpx2 as httpx
import pytest
from acsi_plugins import (
    Associated,
    OperateResponse,
    PluginHost,
    ServerStopped,
    ValueRead,
    ValueWritten,
    loader,
)
from acsi_plugins.web import PluginService, attach
from fastapi import FastAPI

pytestmark = pytest.mark.unit

SAMPLE = Path(__file__).resolve().parents[1]
SOURCE = "http://dev.test:8099"


def serve_sample():
    """The sample folder, as `python -m http.server` would serve it."""

    def handler(request):
        path = SAMPLE / request.url.path.lstrip("/")
        if path.parent == SAMPLE and path.is_file():
            return httpx.Response(200, content=path.read_bytes())
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture
async def setup(tmp_path):
    host = PluginHost(role="fsp")
    host.bind_loop(asyncio.get_running_loop())
    service = PluginService(
        host,
        storage=tmp_path,
        allowed_sources=[SOURCE],
        client_factory=serve_sample,
    )
    app = FastAPI(lifespan=service.lifespan)
    attach(app, service)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://fsp"
    )
    response = await client.post(
        "/api/plugins",
        json={
            "name": "sim_leds",
            "source_url": SOURCE,
            "settings": {"blink_seconds": 0.05},
        },
    )
    assert response.status_code == 200, response.text
    yield host, client
    await client.aclose()
    for name in host.names():
        await host.remove(name)
    loader.unload_modules("sim_leds")


async def deliver(host, event):
    for future in host.emit(event):
        await asyncio.wrap_future(future)


async def leds(client):
    return (await client.get("/api/plugins/sim_leds/leds")).json()["leds"]


async def test_the_sample_installs_from_a_plain_file_server(setup):
    _, client = setup
    body = (await client.get("/api/plugins/sim_leds")).json()
    assert body["version"] == "1.0.0"
    assert body["healthy"] is True
    assert await leds(client) == {"red": False, "green": False}


async def test_an_association_turns_green_on_and_a_stop_turns_it_off(setup):
    host, client = setup
    await deliver(host, Associated("cp1"))
    assert await leds(client) == {"red": False, "green": True}
    await deliver(host, ServerStopped())
    assert await leds(client) == {"red": False, "green": False}


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


async def test_an_led_can_be_set_and_reset_by_hand(setup):
    _, client = setup
    await client.post("/api/plugins/sim_leds/leds/red", json={"on": True})
    assert (await leds(client))["red"] is True
    await client.post("/api/plugins/sim_leds/leds/reset")
    assert await leds(client) == {"red": False, "green": False}
    response = await client.post("/api/plugins/sim_leds/leds/blue", json={"on": True})
    assert response.status_code == 404
