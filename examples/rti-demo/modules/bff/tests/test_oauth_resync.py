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

"""Unit tests for keeping stored OAuth settings across SO restarts.

Same mechanism as test_tls_resync.py: the SO holds OAuth only in memory, so
after a container restart it accepts unauthenticated FSPs while
connections.json still says OAuth is on. ConnectionManager re-applies the
stored OAuth block via the SO's /reconfig-oauth - after TLS, never
concurrently with it, since each restarts the SO's listener.
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
from bff.ConnectionManager import ConnectionManager  # noqa: E402

pytestmark = pytest.mark.unit

STORED_OAUTH = {
    "enable_oauth": True,
    "idp_server": "IDP",
    "realm": "iec61850-test",
    "certificate_endpoint": "http://keycloak:8080/realms/iec61850-test/protocol/openid-connect/certs",
    "token_issuer": "http://localhost:8080/realms/iec61850-test",
    "auth_server_ca": "CA-PEM",
}


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class _FakeSO:
    """Serves the SO's runtime TLS/OAuth state and records reconfig POSTs."""

    def __init__(self, oauth_enabled, tls_enabled=False, reconfig_status=200):
        self.oauth_enabled = oauth_enabled
        self.tls_enabled = tls_enabled
        self.reconfig_status = reconfig_status
        self.posts = []

    async def get(self, url, **kwargs):
        if url == "http://rti-so:5002/api/oauth-status":
            return _Response({"ok": True, "enable_oauth": self.oauth_enabled})
        assert url == "http://rti-so:5002/api/tls-config"
        return _Response(
            {
                "ok": True,
                "enable_tls": self.tls_enabled,
                "tls_version": "1.3",
                "server_cert": "CERT-PEM" if self.tls_enabled else None,
            }
        )

    async def post(self, url, json=None, **kwargs):
        self.posts.append((url.rsplit("/", 1)[-1], json))
        ok = self.reconfig_status < 400
        return _Response({"ok": ok}, status_code=self.reconfig_status)


def _manager(tmp_path):
    return ConnectionManager(
        bff_clients={},
        connections_file=str(tmp_path / "connections.json"),
        logger=bff_server.logger,
    )


def _so(oauth=STORED_OAUTH, tls=None, status="connected"):
    con = {
        "name": "SO",
        "host": "rti-so",
        "port": 5002,
        "type": "RTI-SO",
        "ws_mode": "passive",
        "status": status,
        "OAuth": dict(oauth) if oauth is not None else None,
    }
    if tls is not None:
        con["TLS"] = tls
    return con


async def test_reapplies_stored_oauth_after_so_restart(tmp_path):
    so = _FakeSO(oauth_enabled=False)

    await _manager(tmp_path).sync_runtime_oauth(_so(), so)

    assert so.posts == [
        (
            "reconfig-oauth",
            {
                "connection_name": "SO",
                "enable_oauth": True,
                "ws_mode": "passive",
                "certificate_endpoint_url": STORED_OAUTH["certificate_endpoint"],
                "token_issuer_url": STORED_OAUTH["token_issuer"],
                "ca_certificate": "CA-PEM",
            },
        )
    ]


async def test_leaves_matching_oauth_alone(tmp_path):
    so = _FakeSO(oauth_enabled=True)

    await _manager(tmp_path).sync_runtime_oauth(_so(), so)

    assert so.posts == []


async def test_ignores_fsps_disconnected_sos_and_missing_oauth(tmp_path):
    manager = _manager(tmp_path)
    so = _FakeSO(oauth_enabled=False)

    await manager.sync_runtime_oauth(_so(oauth=None), so)
    await manager.sync_runtime_oauth(_so(status="disconnected"), so)
    fsp = {**_so(), "name": "FSP01", "type": "RTI-FSP", "ws_mode": "active"}
    await manager.sync_runtime_oauth(fsp, so)

    assert so.posts == []


async def test_backs_off_after_a_failed_oauth_reapply(tmp_path):
    manager = _manager(tmp_path)
    so = _FakeSO(oauth_enabled=False, reconfig_status=500)

    await manager.sync_runtime_oauth(_so(), so)
    await manager.sync_runtime_oauth(_so(), so)

    assert len(so.posts) == 1


async def test_tls_backoff_does_not_block_oauth(tmp_path):
    # Separate backoffs: a failing TLS re-apply mustn't also hold back OAuth.
    manager = _manager(tmp_path)
    tls = {"enable_tls": True, "tls_version": "TLSv1_3", "server_cert": "CERT-PEM"}
    failing = _FakeSO(oauth_enabled=False, reconfig_status=500)

    await manager.sync_runtime_tls(_so(tls=tls), failing)
    so = _FakeSO(oauth_enabled=False)
    await manager.sync_runtime_oauth(_so(tls=tls), so)

    assert [name for name, _ in so.posts] == ["reconfig-oauth"]


async def test_monitor_reapplies_tls_then_oauth(tmp_path):
    manager = _manager(tmp_path)
    tls = {"enable_tls": True, "tls_version": "TLSv1_3", "server_cert": "CERT-PEM"}
    manager.connections = [_so(tls=tls)]
    so = _FakeSO(oauth_enabled=False, tls_enabled=False)
    manager._client = so

    await manager.sync_all_runtime_security()

    assert [name for name, _ in so.posts] == ["reconfig-connection", "reconfig-oauth"]
