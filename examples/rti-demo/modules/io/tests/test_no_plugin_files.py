# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The IO server serves no plugin files: the IO plugin is installed with the
FSP and SO (decision 0022)."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

IO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(IO))

from rti_io.server.api_endpoint import create_fastapi_app  # noqa: E402
from rti_io.server.io_controller import IOController  # noqa: E402

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


def test_it_has_no_plugin_code():
    assert not (IO / "rti_io" / "plugin").exists()
    assert not (IO / "rti_io" / "server" / "plugin_files.py").exists()
