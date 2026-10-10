# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""/api/plugins: install, list, reload and remove plugins, and reach their routes (decision 0021)."""

import json

import httpx2 as httpx
import pytest
from acsi_plugins import PluginHost, loader
from acsi_plugins.web import PluginService, attach
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

SOURCE = "http://io.test/plugins/demo"
MANIFEST = {
    "name": "demo",
    "version": "1.0.0",
    "api": 1,
    "entry": "plugin:DemoPlugin",
    "files": ["__init__.py", "plugin.py"],
}
PLUGIN_PY = """
from fastapi import APIRouter, Request
from acsi_plugins import AcsiPlugin

VERSION = "{version}"

class DemoPlugin(AcsiPlugin):
    def claims(self):
        return {claims!r}

    async def start(self, ctx):
        self.settings = ctx.settings

    def router(self):
        router = APIRouter()

        @router.get("/hello")
        def hello(who: str = "world"):
            return {{"hello": who, "version": VERSION, "settings": self.settings}}

        @router.post("/echo")
        async def echo(request: Request):
            return {{"body": await request.json()}}

        return router
"""


class Server:
    """The plugin source: a plain file server."""

    def __init__(self, version="1.0.0", claims=()):
        self.set(version, claims)
        self.calls = 0

    def set(self, version, claims=()):
        self.files = {
            "plugin.json": json.dumps({**MANIFEST, "version": version}),
            "__init__.py": "",
            "plugin.py": PLUGIN_PY.format(version=version, claims=list(claims)),
        }

    def client(self):
        def handler(request):
            self.calls += 1
            name = request.url.path.rsplit("/", 1)[-1]
            if name in self.files:
                return httpx.Response(200, text=self.files[name])
            return httpx.Response(404)

        return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture
def server():
    return Server()


@pytest.fixture
def service(tmp_path, server):
    service = PluginService(
        PluginHost(role="fsp"),
        storage=tmp_path / "plugins",
        allowed_sources=["http://io.test"],
        client_factory=server.client,
    )
    yield service
    loader.unload_modules("demo")


@pytest.fixture
def client(service):
    app = FastAPI(lifespan=service.lifespan)
    attach(app, service)
    with TestClient(app) as client:
        yield client


def install(client, **extra):
    return client.post(
        "/api/plugins", json={"name": "demo", "source_url": SOURCE, **extra}
    )


def test_install_downloads_loads_and_lists_the_plugin(client):
    response = install(client, settings={"io_url": "http://io.test"})
    assert response.status_code == 200, response.text
    assert response.json()["plugin"]["name"] == "demo"
    [entry] = client.get("/api/plugins").json()["plugins"]
    assert (entry["name"], entry["version"], entry["source"]) == (
        "demo",
        "1.0.0",
        SOURCE,
    )
    assert entry["routes"] is True


def test_a_plugin_s_routes_are_under_its_name(client):
    install(client, settings={"io_url": "http://io.test"})
    body = client.get("/api/plugins/demo/hello", params={"who": "fsp"}).json()
    assert body == {
        "hello": "fsp",
        "version": "1.0.0",
        "settings": {"io_url": "http://io.test"},
    }
    assert client.post("/api/plugins/demo/echo", json={"a": 1}).json() == {
        "body": {"a": 1}
    }


def test_an_unknown_plugin_has_no_routes(client):
    assert client.get("/api/plugins/nothing/hello").status_code == 404


def test_a_source_that_is_not_allowed_is_refused(client, server):
    response = client.post(
        "/api/plugins", json={"name": "demo", "source_url": "http://evil.test/files"}
    )
    assert response.status_code == 403
    assert "PLUGIN_ALLOWED_SOURCES" in response.json()["detail"]
    assert server.calls == 0


def test_a_plugin_that_fails_to_load_is_reported(client, service, server):
    server.files["plugin.py"] = "raise RuntimeError('broken')\n"
    response = install(client)
    assert response.status_code == 422
    assert "broken" in response.json()["detail"]
    assert client.get("/api/plugins").json()["plugins"] == []
    assert loader.stored(service.storage) == []


def test_an_objref_conflict_is_reported(client, service, server):
    from acsi_plugins import AcsiPlugin

    class Owner(AcsiPlugin):
        def claims(self):
            return ["LD0/CSWI1.Pos"]

    client.portal.call(service.host.add, "owner", Owner())
    server.set("1.0.0", claims=["LD0/CSWI1.Pos"])
    response = install(client)
    assert response.status_code == 409
    assert "owner" in response.json()["detail"]


def test_reload_downloads_again_and_keeps_the_settings(client, server):
    install(client, settings={"io_url": "http://io.test"})
    server.set("1.1.0")
    response = client.post("/api/plugins/demo/reload")
    assert response.status_code == 200, response.text
    body = client.get("/api/plugins/demo/hello").json()
    assert body["version"] == "1.1.0"
    assert body["settings"] == {"io_url": "http://io.test"}


def test_remove_unloads_the_plugin_and_its_files(client, service):
    install(client)
    assert client.delete("/api/plugins/demo").status_code == 200
    assert client.get("/api/plugins").json()["plugins"] == []
    assert client.get("/api/plugins/demo/hello").status_code == 404
    assert loader.stored(service.storage) == []
    assert client.delete("/api/plugins/demo").status_code == 404


def test_a_stored_plugin_is_loaded_at_startup(tmp_path, server):
    def make_service():
        return PluginService(
            PluginHost(role="fsp"),
            storage=tmp_path / "plugins",
            allowed_sources=["http://io.test"],
            client_factory=server.client,
        )

    svc = make_service()
    first = FastAPI(lifespan=svc.lifespan)
    attach(first, svc)
    with TestClient(first) as c:
        install(c, settings={"io_url": "http://io.test"})
    loader.unload_modules("demo")

    svc = make_service()
    second = FastAPI(lifespan=svc.lifespan)
    attach(second, svc)
    with TestClient(second) as c:
        body = c.get("/api/plugins/demo/hello").json()
    assert body["settings"] == {"io_url": "http://io.test"}
    loader.unload_modules("demo")


def test_a_reloaded_plugin_keeps_its_source_and_settings_after_a_restart(
    tmp_path, server
):
    def make_app():
        svc = PluginService(
            PluginHost(role="fsp"),
            storage=tmp_path / "plugins",
            allowed_sources=["http://io.test"],
            client_factory=server.client,
        )
        app = FastAPI(lifespan=svc.lifespan)
        attach(app, svc)
        return app

    with TestClient(make_app()) as c:
        install(c, settings={"io_url": "http://io.test"})
        assert c.post("/api/plugins/demo/reload").status_code == 200
    loader.unload_modules("demo")

    with TestClient(make_app()) as c:
        assert c.get("/api/plugins/demo").json()["source"] == SOURCE
        assert c.get("/api/plugins/demo/hello").json()["settings"] == {
            "io_url": "http://io.test"
        }
    loader.unload_modules("demo")


def test_a_configured_plugin_is_installed_at_startup(tmp_path, server):
    service = PluginService(
        PluginHost(role="so"),
        storage=tmp_path / "plugins",
        allowed_sources=["http://io.test"],
        configured=[{"name": "demo", "source": SOURCE, "settings": {"x": 1}}],
        client_factory=server.client,
    )
    app = FastAPI(lifespan=service.lifespan)
    attach(app, service)
    with TestClient(app) as c:
        assert c.get("/api/plugins/demo/hello").json()["settings"] == {"x": 1}
    loader.unload_modules("demo")


def test_a_startup_failure_is_listed_not_raised(tmp_path, server):
    service = PluginService(
        PluginHost(role="so"),
        storage=tmp_path / "plugins",
        allowed_sources=[],
        configured=[{"name": "demo", "source": SOURCE}],
        client_factory=server.client,
    )
    app = FastAPI(lifespan=service.lifespan)
    attach(app, service)
    with TestClient(app) as c:
        body = c.get("/api/plugins").json()
    assert body["plugins"] == []
    assert "not allowed" in body["failed"]["demo"]


# ==================== No old paths ====================


@pytest.mark.parametrize(
    "path",
    ["/api/io/leds", "/api/io-plugin", "/api/io-plugin/connect", "/api/io-client"],
)
def test_the_io_plugin_s_old_paths_are_not_served(client, path):
    assert client.post(path, json={}, follow_redirects=False).status_code == 404


# ==================== Settings from the environment ====================


def test_from_env_reads_storage_sources_and_configured_plugins(monkeypatch, tmp_path):
    monkeypatch.setenv("PLUGIN_STORAGE", str(tmp_path))
    monkeypatch.setenv(
        "PLUGIN_ALLOWED_SOURCES", "http://rti-io:9000, http://localhost:9000"
    )
    monkeypatch.setenv(
        "PLUGINS",
        json.dumps([{"name": "demo", "source": "http://localhost:8099"}]),
    )
    service = PluginService.from_env(PluginHost(role="fsp"))
    assert service.storage == tmp_path
    assert service.allowed_sources == ["http://rti-io:9000", "http://localhost:9000"]
    assert service.configured == [{"name": "demo", "source": "http://localhost:8099"}]


def test_from_env_ignores_io_plugin_storage(monkeypatch, tmp_path):
    monkeypatch.delenv("PLUGIN_STORAGE", raising=False)
    monkeypatch.setenv("IO_PLUGIN_STORAGE", str(tmp_path))
    monkeypatch.delenv("PLUGIN_ALLOWED_SOURCES", raising=False)
    monkeypatch.delenv("PLUGINS", raising=False)
    service = PluginService.from_env(PluginHost(role="fsp"))
    assert service.storage != tmp_path
    assert service.allowed_sources == []
    assert service.configured == []
