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

pytestmark = pytest.mark.unit

PLUGIN_FILES = {
    "__init__.py",
    "client.py",
    "router.py",
    "mapping.py",
    "utils.py",
    "io_mapping.json",
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("IO_PLUGIN_FILES_DIR", raising=False)
    monkeypatch.delenv("IO_CLIENT_FILES_DIR", raising=False)
    app = FastAPI()
    app.include_router(create_plugin_files_router())
    return TestClient(app)


def test_lists_the_plugin_files(client):
    names = {f["name"] for f in client.get("/api/io-plugin/files").json()["files"]}
    assert PLUGIN_FILES <= names


def test_serves_a_plugin_file(client):
    body = client.get("/api/io-plugin/files/router.py").json()
    assert body["ok"] is True
    assert "def create_io_router" in body["content"]


def test_old_file_names_are_gone(client):
    response = client.get("/api/io-plugin/files/async_client_io.py")
    assert response.status_code == 410
    assert "same version" in response.json()["detail"]


def test_old_files_dir_variable_still_works(monkeypatch, tmp_path):
    (tmp_path / "router.py").write_text("# test\n", encoding="utf-8")
    monkeypatch.delenv("IO_PLUGIN_FILES_DIR", raising=False)
    monkeypatch.setenv("IO_CLIENT_FILES_DIR", str(tmp_path))
    app = FastAPI()
    app.include_router(create_plugin_files_router())
    names = {
        f["name"] for f in TestClient(app).get("/api/io-plugin/files").json()["files"]
    }
    assert names == {"router.py"}


# Requests for files outside the plugin folder (decision 0019): a step up,
# an absolute path, and an encoded step up into a sibling folder.
OUTSIDE_REQUESTS = [
    "..%2Fserver%2Fio_config.json",
    "%2Fetc%2Fhostname",
    "%2E%2E%2Fserver%2Fmain.py",
    "sub%2F..%2F..%2Fserver%2Fmain.py",
]


@pytest.mark.parametrize("name", OUTSIDE_REQUESTS)
def test_serves_nothing_outside_the_plugin_folder(client, name):
    response = client.get(f"/api/io-plugin/files/{name}")
    assert response.status_code == 404
    assert "content" not in response.json()


def test_serves_no_subfolder(client, monkeypatch, tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "x.py").write_text("# x\n", encoding="utf-8")
    monkeypatch.setenv("IO_PLUGIN_FILES_DIR", str(tmp_path))
    app = FastAPI()
    app.include_router(create_plugin_files_router())
    assert TestClient(app).get("/api/io-plugin/files/sub%2Fx.py").status_code == 404


def test_serves_no_symlink_out_of_the_folder(monkeypatch, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("secret\n", encoding="utf-8")
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (plugin / "router.py").symlink_to(secret)
    monkeypatch.setenv("IO_PLUGIN_FILES_DIR", str(plugin))
    app = FastAPI()
    app.include_router(create_plugin_files_router())
    assert TestClient(app).get("/api/io-plugin/files/router.py").status_code == 404
