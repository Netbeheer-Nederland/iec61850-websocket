# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""openapi.yaml, the contract for third-party plugins, says what the code does
(decisions 0027, 0029)."""

import asyncio
import dataclasses
import logging
from pathlib import Path

import pytest
import yaml
from acsi_plugins import (
    EVENT_TYPES,
    PluginContext,
    PluginHost,
    PluginsConfig,
    RemotePlugin,
    contract,
    event_json,
    remote,
)
from acsi_plugins.web import PluginService, create_plugins_router

from .fake_plugin import URL, FakePlugin

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SPEC = yaml.safe_load((ROOT / "openapi.yaml").read_text(encoding="utf-8"))
SCHEMAS = SPEC["components"]["schemas"]
METHODS = {"get", "post", "put", "patch", "delete"}


def spec_routes(tag):
    return {
        (path, method.upper())
        for path, item in SPEC["paths"].items()
        for method, op in item.items()
        if method in METHODS and tag in op.get("tags", [])
    }


def example(path, method="get", status="200"):
    op = SPEC["paths"][path][method]
    if status is None:
        return op["requestBody"]["content"]["application/json"]["example"]
    return op["responses"][status]["content"]["application/json"]["example"]


def test_management_routes_match_the_router():
    router = create_plugins_router(PluginService(PluginHost(role="fsp")))
    in_code = {
        (route.path.replace("{path:path}", "{path}"), method)
        for route in router.routes
        for method in route.methods
    }
    assert spec_routes("Plugin management") | spec_routes("Plugin routes") == in_code


async def test_the_plugin_api_is_what_the_host_calls():
    fake = FakePlugin(answer={"ok": True})
    seen = set()

    async def record(request):
        seen.add((request.url.path.removeprefix("/plugin") or "/", request.method))

    def client():
        c = fake.client()
        c.event_hooks["request"].append(record)
        return c

    plugin = RemotePlugin(URL, client_factory=client)
    await plugin.describe()
    ctx = PluginContext("demo", "fsp", {}, None, logging.getLogger("test"))
    await plugin.start(ctx)
    await plugin.on_event(contract.Associated("cp1"))
    await asyncio.to_thread(plugin.handle_control, "LD0/X", {})
    await plugin.stop()
    assert spec_routes("Plugin API") == seen


def test_api_version():
    api = SCHEMAS["PluginDescription"]["properties"]["api"]["const"]
    assert api == contract.API_VERSION
    assert SPEC["info"]["version"] == str(contract.API_VERSION)


def test_the_name_pattern_is_the_host_s():
    assert SCHEMAS["PluginName"]["pattern"] == remote.NAME.pattern


async def test_status_fields_are_the_host_s():
    host = PluginHost(role="fsp")
    await host.add("demo", contract.AcsiPlugin())
    status = host.status("demo")
    assert set(status) == set(SCHEMAS["PluginStatus"]["required"])
    assert set(status) == set(SCHEMAS["PluginStatus"]["properties"])


def test_the_examples_are_valid():
    remote.Description.parse(example("/"), URL)
    PluginsConfig.parse(SCHEMAS["PluginsConfig"]["example"])
    event = example("/events", "post", None)["event"]
    fields = {k: v for k, v in event.items() if k != "type"}
    assert event_json(EVENT_TYPES[event["type"]](**fields)) == event


@pytest.mark.parametrize("name", list(EVENT_TYPES))
def test_event_fields_are_what_the_host_sends(name):
    schema = SCHEMAS[name]
    assert schema["properties"]["type"] == {"const": name}
    fields = {f.name for f in dataclasses.fields(EVENT_TYPES[name])}
    assert set(schema["properties"]) == fields | {"type"}
    # event_json always sends every field.
    assert set(schema["required"]) == fields | {"type"}


def test_every_event_is_in_the_spec():
    listed = {r["$ref"].rsplit("/", 1)[1] for r in SCHEMAS["Event"]["oneOf"]}
    assert listed == set(EVENT_TYPES)


def test_control_result_fields():
    assert set(SCHEMAS["ControlResult"]["properties"]) == {
        f.name for f in dataclasses.fields(contract.ControlResult)
    }


async def test_the_host_fields_are_what_the_host_sends():
    fake = FakePlugin()
    plugin = RemotePlugin(URL, client_factory=fake.client)
    ctx = PluginContext("demo", "so", {}, "http://so.test:5000", logging.getLogger("t"))
    await plugin.start(ctx)
    await plugin.stop()
    assert set(SCHEMAS["Host"]["properties"]) == set(fake.calls[-1][1])
