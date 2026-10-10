# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The IO plugin's client module."""

import asyncio
import sys
from pathlib import Path

import pytest

IO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(IO))

from rti_io.plugin import client as plugin_client  # noqa: E402
from rti_io.plugin import router as plugin_router  # noqa: E402

PLUGIN = IO / "rti_io" / "plugin"

pytestmark = pytest.mark.unit


def test_one_async_client():
    assert not hasattr(plugin_client, "AsyncDemoIOClient")
    assert plugin_router.AsyncIOClient is plugin_client.AsyncIOClient


def test_connection_failure_raises_io_connection_error():
    assert not hasattr(plugin_client, "ConnectionError")
    client = plugin_client.AsyncIOClient(base_url="http://127.0.0.1:9", max_retries=0)
    with pytest.raises(plugin_client.IOConnectionError):
        asyncio.run(client._request("GET", "/api/io/health"))


def test_the_router_imports_no_removed_package():
    assert "demo_IO" not in (PLUGIN / "router.py").read_text(encoding="utf-8")


@pytest.mark.parametrize("state", [True, False])
def test_the_sync_client_sets_an_led(state):
    client = plugin_client.DemoIOClient(base_url="http://io.test")
    calls = []

    async def request(method, endpoint, **kwargs):
        calls.append((method, endpoint, kwargs.get("json")))
        return {"ok": True}

    client._async_client._request = request
    assert client.set_led("led1", state) == {"ok": True}
    assert calls == [("POST", "/devices/led1/set", {"state": state})]


def _public_methods(cls):
    return {
        name
        for name, member in vars(cls).items()
        if callable(member) and not name.startswith("_")
    }


def test_every_sync_method_has_its_async_counterpart():
    # DemoIOClient runs AsyncIOClient's coroutine of the same name; only
    # close() differs (aclose() on the async client).
    missing = (
        _public_methods(plugin_client.DemoIOClient)
        - {"close"}
        - set(dir(plugin_client.AsyncIOClient))
    )
    assert missing == set()


def _recording(client):
    calls = []

    async def request(method, endpoint, **kwargs):
        calls.append((method, endpoint, kwargs.get("json")))
        return {"ok": True}

    client._request = request
    return calls


def test_clear_lcd_uses_the_lcd_control_route():
    client = plugin_client.AsyncIOClient(base_url="http://io.test")
    calls = _recording(client)
    asyncio.run(client.clear_lcd("lcd1"))
    assert calls == [("POST", "/lcd/lcd1/control", {"clear": True})]


def test_the_sync_client_configures_a_button_like_the_async_one():
    client = plugin_client.DemoIOClient(base_url="http://io.test")
    calls = _recording(client._async_client)
    client.config_button("btn1", 17, "Button", debounce_time=0.1, pull_up=False)
    assert calls[0][2] == {
        "name": "btn1",
        "device_type": "button",
        "identifier": None,
        "description": "Button",
        "gpio_pin": 17,
        "debounce_time": 0.1,
        "pull_up": False,
    }
