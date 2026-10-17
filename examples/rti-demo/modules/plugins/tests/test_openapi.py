# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""openapi.yaml, the contract for third-party plugins, says what the code does."""

import dataclasses
from pathlib import Path

import pytest
import yaml
from acsi_plugins import PluginHost, contract, loader
from acsi_plugins.web import PluginService, create_plugins_router

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SPEC = yaml.safe_load((ROOT / "openapi.yaml").read_text(encoding="utf-8"))
SCHEMAS = SPEC["components"]["schemas"]
METHODS = {"get", "post", "put", "patch", "delete"}


def spec_routes(prefix):
    return {
        (path, method.upper())
        for path, item in SPEC["paths"].items()
        if path.startswith(prefix)
        for method in item
        if method in METHODS
    }


def test_management_routes_match_the_router(tmp_path):
    router = create_plugins_router(
        PluginService(PluginHost(role="fsp"), storage=tmp_path, allowed_sources=[])
    )
    in_code = {
        (route.path.replace("{path:path}", "{path}"), method)
        for route in router.routes
        for method in route.methods
    }
    assert spec_routes("/api/plugins") == in_code


def test_api_version():
    assert (
        SCHEMAS["PluginManifest"]["properties"]["api"]["const"] == contract.API_VERSION
    )


def test_name_and_file_patterns_are_the_loaders():
    assert SCHEMAS["PluginName"]["pattern"] == loader._NAME.pattern
    assert SCHEMAS["PluginFileName"]["pattern"] == loader._FILE.pattern


async def test_status_fields_are_the_hosts():
    class Demo(contract.AcsiPlugin):
        pass

    host = PluginHost(role="fsp")
    await host.add("demo", Demo())
    status = host.status("demo")
    assert set(status) == set(SCHEMAS["PluginStatus"]["required"])
    assert set(status) == set(SCHEMAS["PluginStatus"]["properties"])


def test_the_manifest_example_is_a_valid_manifest():
    example = SPEC["paths"]["/plugin.json"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["example"]
    loader.Manifest.parse(example)


@pytest.mark.parametrize(
    "cls",
    [
        contract.Associated,
        contract.OperateReceived,
        contract.OperateResponse,
        contract.ValueWritten,
        contract.ValueRead,
        contract.ReportReceived,
        contract.ServerStopped,
    ],
)
def test_event_fields_are_the_dataclasses(cls):
    schema = SCHEMAS[cls.__name__]
    assert {"$ref": f"#/components/schemas/{cls.__name__}"} in SCHEMAS["Event"]["oneOf"]
    fields = {f.name for f in dataclasses.fields(cls)}
    assert set(schema["properties"]) - {"event_type"} == fields
    required = {
        f.name
        for f in dataclasses.fields(cls)
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
    }
    assert set(schema["required"]) - {"event_type"} <= fields
    assert required <= set(schema["required"])


def test_control_result_and_context_fields():
    assert set(SCHEMAS["ControlResult"]["properties"]) == {
        f.name for f in dataclasses.fields(contract.ControlResult)
    }
    assert set(SCHEMAS["PluginContext"]["properties"]) | {"logger"} == {
        f.name for f in dataclasses.fields(contract.PluginContext)
    }
