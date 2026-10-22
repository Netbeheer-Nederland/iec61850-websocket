# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""/api/plugins and the plugin service: configured plugins are connected at
startup, unreachable ones retried, and their routes reached (decision 0029)."""

import asyncio
import json

import pytest
from acsi_plugins import Associated, PluginEntry, PluginHost
from acsi_plugins.web import PluginService, attach
from fastapi import FastAPI
from fastapi.testclient import TestClient

from .fake_plugin import URL, FakePlugin

pytestmark = pytest.mark.unit

ALLOWED = ["http://plugin.test"]


def make_app(fake, configured=(), retry_seconds=0.0, allowed=ALLOWED):
    host = PluginHost(role="fsp", host_url="http://fsp.test:5001")
    service = PluginService(
        host,
        configured=list(configured),
        allowed_sources=list(allowed),
        client_factory=fake.client,
        retry_seconds=retry_seconds,
    )
    app = FastAPI(lifespan=service.lifespan)
    attach(app, service)
    return app, service


@pytest.fixture
def fake():
    return FakePlugin()


@pytest.fixture
def client(fake):
    app, _ = make_app(fake)
    with TestClient(app) as client:
        yield client


def test_a_configured_plugin_is_connected_at_startup(fake):
    app, _ = make_app(fake, [PluginEntry("demo", URL, {"a": 1})])
    with TestClient(app) as client:
        [status] = client.get("/api/plugins").json()["plugins"]
    assert status["name"] == "demo"
    assert status["url"] == URL
    assert status["version"] == "1.0.0"
    assert status["routes"] is True
    start = fake.calls[0]
    assert start == (
        "start",
        {
            "name": "demo",
            "role": "fsp",
            "host_url": "http://fsp.test:5001",
            "settings": {"a": 1},
        },
    )
    # Stopped with the app.
    assert fake.calls[-1][0] == "stop"


def test_an_unreachable_plugin_is_listed_and_the_app_starts(fake):
    fake.up = False
    app, _ = make_app(fake, [PluginEntry("demo", URL)])
    with TestClient(app) as client:
        body = client.get("/api/plugins").json()
    assert body["plugins"] == []
    assert "Can't reach" in body["failed"]["demo"]


def test_an_unreachable_plugin_is_tried_again(fake):
    fake.up = False
    app, service = make_app(fake, [PluginEntry("demo", URL)], retry_seconds=0.05)
    with TestClient(app) as client:
        fake.up = True
        for _ in range(100):
            if service.host.names():
                break
            client.portal.call(asyncio.sleep, 0.02)
        body = client.get("/api/plugins").json()
    assert [p["name"] for p in body["plugins"]] == ["demo"]
    assert body["failed"] == {}


def test_a_plugin_with_another_name_is_refused(fake):
    app, _ = make_app(fake, [PluginEntry("other", URL)])
    with TestClient(app) as client:
        failed = client.get("/api/plugins").json()["failed"]
    assert "is plugin 'demo', not 'other'" in failed["other"]


def test_events_reach_the_plugin(fake):
    app, service = make_app(fake, [PluginEntry("demo", URL)])
    with TestClient(app) as client:
        futures = service.host.emit(Associated("cp1"))
        for f in futures:
            f.result(5)
        assert client.get("/api/plugins/demo").json()["healthy"] is True
    assert fake.events() == [{"type": "Associated", "associate_id": "cp1"}]


def test_add_through_the_api(client, fake):
    response = client.post(
        "/api/plugins", json={"name": "demo", "url": URL, "settings": {"b": 2}}
    )
    assert response.status_code == 200, response.text
    assert response.json()["plugin"]["name"] == "demo"
    assert fake.calls[0][1]["settings"] == {"b": 2}


def test_a_url_that_is_not_allowed_is_refused(fake):
    app, _ = make_app(fake, allowed=[])
    with TestClient(app) as client:
        response = client.post("/api/plugins", json={"name": "demo", "url": URL})
    assert response.status_code == 403
    assert fake.calls == []


def test_a_plugin_that_cannot_be_reached_is_422(client, fake):
    fake.up = False
    response = client.post("/api/plugins", json={"name": "demo", "url": URL})
    assert response.status_code == 422
    assert "Can't reach" in response.json()["detail"]


def test_a_name_is_added_once(client):
    client.post("/api/plugins", json={"name": "demo", "url": URL})
    response = client.post("/api/plugins", json={"name": "demo", "url": URL})
    assert response.status_code == 409


def test_an_objref_conflict_is_409(fake):
    fake.description["claims"] = ["LD0/CSWI1.Pos"]
    other = FakePlugin("other", claims=["LD0/CSWI1.Pos"])
    app, service = make_app(fake)
    with TestClient(app) as client:
        assert (
            client.post("/api/plugins", json={"name": "demo", "url": URL}).status_code
            == 200
        )
        service.client_factory = other.client
        response = client.post("/api/plugins", json={"name": "other", "url": URL})
    assert response.status_code == 409
    assert "owned by 'demo'" in response.json()["detail"]


def test_reload_starts_the_plugin_again_with_its_settings(client, fake):
    client.post("/api/plugins", json={"name": "demo", "url": URL, "settings": {"b": 2}})
    fake.description["version"] = "1.1.0"
    response = client.post("/api/plugins/demo/reload")
    assert response.status_code == 200
    assert response.json()["plugin"]["version"] == "1.1.0"
    assert [c[0] for c in fake.calls] == ["start", "stop", "start"]
    assert fake.calls[-1][1]["settings"] == {"b": 2}


def test_remove_stops_the_plugin(client, fake):
    client.post("/api/plugins", json={"name": "demo", "url": URL})
    assert client.delete("/api/plugins/demo").json() == {"ok": True}
    assert fake.calls[-1][0] == "stop"
    assert client.get("/api/plugins").json()["plugins"] == []
    assert client.delete("/api/plugins/demo").status_code == 404


def test_a_plugin_s_routes_are_under_its_name(client):
    client.post("/api/plugins", json={"name": "demo", "url": URL})
    assert client.get("/api/plugins/demo/hello", params={"who": "fsp"}).json() == {
        "hello": "fsp"
    }
    assert client.post("/api/plugins/demo/echo", json={"x": 1}).json() == {
        "body": {"x": 1}
    }


def test_an_unknown_plugin_has_no_routes(client):
    assert client.get("/api/plugins/nope/hello").status_code == 404


def test_a_plugin_without_routes_has_none(fake):
    fake.description.pop("routes")
    app, _ = make_app(fake, [PluginEntry("demo", URL)])
    with TestClient(app) as client:
        assert client.get("/api/plugins/demo").json()["routes"] is False
        assert client.get("/api/plugins/demo/hello").status_code == 404


@pytest.mark.parametrize(
    "path",
    ["/api/io/leds", "/api/io-plugin", "/api/io-plugin/connect", "/api/io-client"],
)
def test_the_io_plugin_s_old_paths_are_not_served(client, path):
    assert client.get(path).status_code == 404


def test_from_env_reads_the_file_inline_plugins_and_host_url(monkeypatch, tmp_path):
    path = tmp_path / "plugins.json"
    path.write_text(
        json.dumps(
            {
                "host_url": "http://from-file:5001",
                "plugins": [{"name": "io", "url": "http://rpi-io:9000/plugin"}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("PLUGINS_FILE", str(path))
    monkeypatch.setenv(
        "PLUGINS",
        json.dumps([{"name": "sim_leds", "url": "http://localhost:8099/plugin"}]),
    )
    monkeypatch.setenv("PLUGIN_HOST_URL", "http://from-env:5001")
    monkeypatch.setenv("PLUGIN_ALLOWED_SOURCES", "http://a.test, http://b.test")
    monkeypatch.setenv("PLUGIN_RETRY_SECONDS", "3")
    host = PluginHost(role="so")
    service = PluginService.from_env(host)
    assert [p.name for p in service.configured] == ["io", "sim_leds"]
    assert host.host_url == "http://from-env:5001"
    assert service.allowed_sources == ["http://a.test", "http://b.test"]
    assert service.retry_seconds == 3


def test_from_env_ignores_a_bad_configuration(monkeypatch):
    monkeypatch.delenv("PLUGINS_FILE", raising=False)
    monkeypatch.setenv("PLUGINS", "not json")
    service = PluginService.from_env(PluginHost(role="fsp"))
    assert service.configured == []


def test_from_env_without_settings_has_no_plugins(monkeypatch):
    for var in ("PLUGINS_FILE", "PLUGINS", "PLUGIN_HOST_URL", "PLUGIN_ALLOWED_SOURCES"):
        monkeypatch.delenv(var, raising=False)
    host = PluginHost(role="fsp")
    service = PluginService.from_env(host)
    assert service.configured == []
    assert service.allowed_sources == []
    assert host.host_url is None
