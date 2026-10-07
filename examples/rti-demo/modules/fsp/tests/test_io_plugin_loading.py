# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The FSP loads the IO plugin's files and finds what it uses from them."""

import asyncio
import shutil
import sys
from pathlib import Path

import pytest
from fsp import bff_endpoint as be

pytestmark = pytest.mark.unit

# The plugin files the IO server serves, as they are in the repository.
PLUGIN_SRC = Path(__file__).resolve().parents[2] / "io" / "rti_io" / "plugin"

ROUTER_FUNCTIONS = ("create_io_router", "get_io_client", "get_mapping_manager")
UTILS_FUNCTIONS = ("sync_to_io_device", "write_to_lcd", "blink_led_task")


@pytest.fixture
def plugin_dir(tmp_path, monkeypatch):
    """The plugin files, as a download would leave them."""
    for name in be.IO_PLUGIN_REQUIRED_FILES:
        shutil.copy(PLUGIN_SRC / name, tmp_path / name)
    monkeypatch.setattr(be, "IO_PLUGIN_DYNAMIC_DIR", tmp_path)
    yield tmp_path
    be.clear_io_plugin_modules()


def test_the_repository_has_every_required_file():
    missing = [n for n in be.IO_PLUGIN_REQUIRED_FILES if not (PLUGIN_SRC / n).is_file()]
    assert not missing


def test_loads_the_plugin(plugin_dir):
    assert be.load_io_plugin_modules() is True
    for name in ROUTER_FUNCTIONS:
        assert callable(getattr(be._io_plugin_module, name)), name
    for name in UTILS_FUNCTIONS:
        assert callable(getattr(be._io_utils_module, name)), name
    assert be._io_plugin_module.create_io_router() is not None


def test_a_missing_file_fails_the_load(plugin_dir):
    (plugin_dir / be.IO_PLUGIN_REQUIRED_FILES[0]).unlink()
    assert be.load_io_plugin_modules() is False


def _plugin_modules():
    return sorted(n for n in sys.modules if n.split(".")[0] == be.IO_PLUGIN_PACKAGE)


def test_loads_as_one_package(plugin_dir):
    assert be.load_io_plugin_modules() is True
    assert "rti_io_plugin.router" in _plugin_modules()
    for bare in ("async_client_io", "io_router", "io_utils", "mapping_manager"):
        assert bare not in sys.modules


def test_reload_replaces_the_plugin_modules(plugin_dir):
    assert be.load_io_plugin_modules() is True
    first = be._io_plugin_module
    be.clear_io_plugin_modules()
    assert _plugin_modules() == []
    assert be.load_io_plugin_modules() is True
    assert be._io_plugin_module is not first


def test_failed_load_leaves_no_plugin_modules(plugin_dir):
    (plugin_dir / "utils.py").write_text(
        "raise RuntimeError('broken')\n", encoding="utf-8"
    )
    assert be.load_io_plugin_modules() is False
    assert _plugin_modules() == []


def test_files_endpoint_finds_every_required_file(plugin_dir, tmp_path_factory):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    model_dir = tmp_path_factory.mktemp("model")
    (model_dir / "model.py").write_text(
        "from ws61850.iec61850.data_model.ied_model import IedModel\n"
        "ied = IedModel(name='TestIED')\n",
        encoding="utf-8",
    )
    app = FastAPI()
    router, _ = be.create_bff_router(model_dir)
    app.include_router(router)
    body = TestClient(app).get("/api/io-plugin/files").json()
    assert body["missing_files"] == []
    assert body["required_files_present"] is True


def test_loading_again_without_a_clear_picks_up_changed_files(plugin_dir):
    assert be.load_io_plugin_modules() is True
    with (plugin_dir / "utils.py").open("a", encoding="utf-8") as f:
        f.write("\n\ndef added_after_first_load():\n    return 'new'\n")
    assert be.load_io_plugin_modules() is True
    assert be._io_utils_module.added_after_first_load() == "new"


def _io_server(monkeypatch, handler):
    """Route the module's httpx calls to `handler` instead of a real IO server."""
    real_client = be.httpx.AsyncClient
    transport = be.httpx.MockTransport(handler)
    monkeypatch.setattr(
        be.httpx,
        "AsyncClient",
        lambda *args, **kwargs: real_client(*args, transport=transport, **kwargs),
    )


def test_a_renamed_file_is_not_retried_and_says_why(monkeypatch, tmp_path):
    monkeypatch.setattr(be, "IO_PLUGIN_DYNAMIC_DIR", tmp_path)
    calls = []

    def handler(request):
        calls.append(request.url.path)
        detail = "'io_router.py' was renamed (decision 0018). Run the FSP or SO from the same version as this IO server."
        return be.httpx.Response(410, json={"detail": detail})

    _io_server(monkeypatch, handler)
    result = asyncio.run(
        be.download_io_plugin_files("http://io.test", files=["io_router.py"])
    )
    assert calls == ["/api/io-plugin/files/io_router.py"]
    assert "same version" in result["errors"]["io_router.py"]


def test_health_check_reports_the_plugin_files(monkeypatch):
    def handler(request):
        if request.url.path == "/api/io/health":
            return be.httpx.Response(
                200,
                json={
                    "status": "ok",
                    "service": "IO Device Control",
                    "version": "2.0.0",
                },
            )
        if request.url.path == "/api/io-plugin/health":
            return be.httpx.Response(
                200,
                json={"status": "healthy", "files_available": True, "files_count": 6},
            )
        return be.httpx.Response(404)

    _io_server(monkeypatch, handler)
    health = asyncio.run(be.check_io_server_health("http://io.test"))
    assert health["healthy"] is True
    assert health["files_available"] is True
    assert health["files_count"] == 6
