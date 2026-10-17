# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The IO server serves no plugin files: the FSP and SO connect to it over
HTTP as a plugin, at /plugin (decision 0029), and load no code from it."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from rpi_io.server.api_endpoint import create_fastapi_app
from rpi_io.server.io_controller import IOController

IO = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.unit


@pytest.fixture
def app():
    return create_fastapi_app(IOController())


def test_it_has_no_io_plugin_routes(app):
    paths = TestClient(app).get("/openapi.json").json()["paths"]
    assert "/api/io/health" in paths
    assert [p for p in paths if p.startswith("/api/io-plugin")] == []


@pytest.mark.parametrize(
    "path", ["/api/io-plugin/files", "/api/io-plugin/files/router.py"]
)
def test_the_plugin_files_are_not_served(app, path):
    assert TestClient(app).get(path).status_code == 404


def test_its_plugin_is_an_api_not_files_to_download():
    plugin = IO / "src" / "rpi_io" / "plugin"
    assert not (plugin / "plugin.json").exists()
    assert not (IO / "src" / "rpi_io" / "server" / "plugin_files.py").exists()
