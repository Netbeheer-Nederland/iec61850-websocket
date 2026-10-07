# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The IO server serves the IO plugin's files (GET /api/io-plugin/files)."""

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

IO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(IO))

from rti_io.server.plugin_files import create_plugin_files_router  # noqa: E402

PLUGIN_FILES = {
    "__init__.py",
    "async_client_io.py",
    "io_router.py",
    "io_utils.py",
    "mapping_manager.py",
    "io_mapping.json",
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("IO_CLIENT_FILES_DIR", raising=False)
    app = FastAPI()
    app.include_router(create_plugin_files_router())
    return TestClient(app)


def test_lists_the_plugin_files(client):
    names = {f["name"] for f in client.get("/api/io-plugin/files").json()["files"]}
    assert PLUGIN_FILES <= names


def test_serves_a_plugin_file(client):
    body = client.get("/api/io-plugin/files/io_router.py").json()
    assert body["ok"] is True
    assert "def create_io_router" in body["content"]
