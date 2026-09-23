# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
#
# Copyright 2025 Netbeheer Nederland
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unit tests for the OAuth Config modal's BFF endpoints.

- POST /api/connections/oauth-config also keeps the IDP server and realm
  the modal's fields were derived from, so reopening it shows them again.
- GET /api/idp/discovery reads a realm's OIDC discovery document through the
  BFF (the browser can't reach e.g. http://keycloak:8080), so the modal gets
  the IDP's real issuer - with KC_HOSTNAME set, that differs from the
  address the IDP is reached on.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_tmp_connections_file = Path(tempfile.mkdtemp()) / "connections.json"
_tmp_connections_file.write_text("[]", encoding="utf-8")
os.environ.setdefault("BFF_CONNECTIONS_FILE", str(_tmp_connections_file))

from bff import bff_server  # noqa: E402 - must follow the env var default above
from fastapi.testclient import TestClient  # noqa: E402

pytestmark = pytest.mark.unit

IDP = {
    "name": "IDP",
    "host": "",
    "port": 5000,
    "type": "IDP-Server",
    "endpoint": "http://keycloak:8080",
}
SO = {
    "name": "SO",
    "host": "rti-so",
    "port": 5002,
    "type": "RTI-SO",
    "ws_mode": "passive",
}


@pytest.fixture(autouse=True)
def _isolated_connections(monkeypatch):
    monkeypatch.setattr(bff_server.conn_manager, "connections", [dict(IDP), dict(SO)])
    monkeypatch.setattr(bff_server.conn_manager, "save_connections", lambda: None)
    yield


def test_oauth_config_keeps_idp_server_and_realm():
    client = TestClient(bff_server.app)

    response = client.post(
        "/api/connections/oauth-config",
        json={
            "connection_name": "SO",
            "enable_oauth": True,
            "ws_mode": "passive",
            "idp_server": "IDP",
            "realm": "iec61850-test",
            "certificate_endpoint_url": "http://keycloak:8080/realms/iec61850-test/protocol/openid-connect/certs",
            "token_issuer_url": "http://localhost:8080/realms/iec61850-test",
        },
    )

    assert response.json()["ok"] is True
    stored = client.get(
        "/api/connections/oauth-config", params={"connection_name": "SO"}
    ).json()
    assert stored["idp_server"] == "IDP"
    assert stored["realm"] == "iec61850-test"
    assert stored["token_issuer_url"] == "http://localhost:8080/realms/iec61850-test"


def test_idp_discovery_returns_the_realms_real_endpoints(monkeypatch):
    fetched = []

    async def fake_fetch(url):
        fetched.append(url)
        return {
            "issuer": "http://localhost:8080/realms/iec61850-test",
            "jwks_uri": "http://keycloak:8080/realms/iec61850-test/protocol/openid-connect/certs",
            "token_endpoint": "http://keycloak:8080/realms/iec61850-test/protocol/openid-connect/token",
        }

    monkeypatch.setattr(bff_server, "_fetch_oidc_discovery", fake_fetch)

    body = (
        TestClient(bff_server.app)
        .get(
            "/api/idp/discovery", params={"idp_server": "IDP", "realm": "iec61850-test"}
        )
        .json()
    )

    assert fetched == [
        "http://keycloak:8080/realms/iec61850-test/.well-known/openid-configuration"
    ]
    assert body == {
        "ok": True,
        "issuer": "http://localhost:8080/realms/iec61850-test",
        "certificate_endpoint": "http://keycloak:8080/realms/iec61850-test/protocol/openid-connect/certs",
        "token_endpoint": "http://keycloak:8080/realms/iec61850-test/protocol/openid-connect/token",
    }


def test_idp_discovery_reports_an_unreachable_idp(monkeypatch):
    async def failing_fetch(url):
        raise OSError("connection refused")

    monkeypatch.setattr(bff_server, "_fetch_oidc_discovery", failing_fetch)

    body = (
        TestClient(bff_server.app)
        .get("/api/idp/discovery", params={"idp_server": "IDP", "realm": "nope"})
        .json()
    )

    assert body["ok"] is False
    assert "connection refused" in body["error"]


def test_idp_discovery_unknown_idp():
    body = (
        TestClient(bff_server.app)
        .get("/api/idp/discovery", params={"idp_server": "missing", "realm": "r"})
        .json()
    )

    assert body["ok"] is False
