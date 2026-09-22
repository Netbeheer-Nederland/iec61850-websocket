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

"""Unit tests for so.acsi_client's ACSIClient controller.

Covers the pure/synchronous pieces of ACSIClient that don't require a live
WebSocket connection or event loop thread: cp-list/model-info bookkeeping,
parameter validation, value conversion, message-meta parsing, and the
action/message logs.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from so.acsi_client import ACSIClient

from ws61850.iec61850.client.iec61850_client import IEC61850Client

pytestmark = pytest.mark.unit


@pytest.fixture
def client():
    return ACSIClient()


def _add_client(client, cp, connected):
    """Append a fake associated/unassociated client for `cp` to client_list."""
    c = IEC61850Client(cp)
    c.is_connected = connected
    client.runtime.client_list.append(c)
    return c


class TestGetCpList:
    def test_empty_when_no_clients(self, client):
        assert client.get_cp_list() == []

    def test_excludes_unconnected_cps(self, client):
        # client_list holds every configured access point, connected or
        # not - get_cp_list only surfaces ones with an established
        # association (see the comment on get_cp_list itself).
        _add_client(client, "cp1", connected=True)
        _add_client(client, "cp2", connected=False)

        assert client.get_cp_list() == ["cp1"]

    def test_includes_all_when_all_connected(self, client):
        _add_client(client, "cp1", connected=True)
        _add_client(client, "cp2", connected=True)

        assert client.get_cp_list() == ["cp1", "cp2"]

    def test_empty_when_none_connected(self, client):
        _add_client(client, "cp1", connected=False)
        _add_client(client, "cp2", connected=False)

        assert client.get_cp_list() == []


class TestGetIec61850Client:
    def test_finds_by_cp(self, client):
        target = _add_client(client, "cp1", connected=True)
        _add_client(client, "cp2", connected=False)

        assert client.get_iec61850_client("cp1") is target

    def test_returns_none_when_not_found(self, client):
        assert client.get_iec61850_client("cp1") is None

    def test_ignores_connection_state(self, client):
        # Unlike get_cp_list, this is a raw client_list lookup - it's used
        # to find the association object itself regardless of whether it's
        # currently connected.
        target = _add_client(client, "cp1", connected=False)

        assert client.get_iec61850_client("cp1") is target


class TestModelInfo:
    def test_starts_empty(self, client):
        assert client.model_info_list == []

    def test_get_model_info_creates_and_caches(self, client):
        info = client.get_model_info("cp1")

        assert info.cp == "cp1"
        assert client.get_model_info("cp1") is info

    def test_update_model_info_dict_adds_new_clients(self, client):
        _add_client(client, "cp1", connected=True)
        _add_client(client, "cp2", connected=False)
        client._update_model_info_dict()

        # Unlike get_cp_list, model tracking isn't filtered by connection
        # state - every configured cp gets a ModelInfo entry.
        assert {info.cp for info in client.model_info_list} == {"cp1", "cp2"}

    def test_update_model_info_dict_removes_gone_clients(self, client):
        c1 = _add_client(client, "cp1", connected=True)
        client._update_model_info_dict()

        client.runtime.client_list.remove(c1)
        client._update_model_info_dict()

        assert client.model_info_list == []


class TestValidateConnectionParams:
    @pytest.mark.parametrize("port", [0, -1, 65536, 100000])
    def test_rejects_out_of_range_port(self, client, port):
        with pytest.raises(ValueError):
            client._validate_connection_params("localhost", port)

    @pytest.mark.parametrize("port", [1, 8765, 65535])
    def test_accepts_in_range_port(self, client, port):
        client._validate_connection_params("localhost", port)  # no raise


class TestConvertOperateValToItsType:
    def test_boolean(self, client):
        assert client._convert_operate_val_to_its_type("true", "boolean") is True
        assert client._convert_operate_val_to_its_type("", "boolean") is False

    def test_int32(self, client):
        assert client._convert_operate_val_to_its_type("42", "int32") == 42

    def test_float32(self, client):
        assert client._convert_operate_val_to_its_type("3.5", "float32") == 3.5

    def test_string(self, client):
        assert client._convert_operate_val_to_its_type(123, "string") == "123"

    def test_unsupported_type_raises(self, client):
        with pytest.raises(ValueError):
            client._convert_operate_val_to_its_type("x", "unknown")


class TestExtractMessageMeta:
    def test_request_message(self, client):
        raw = '{"request": {"associateId": "cp1", "service": {"read": {}}}}'

        meta = client._extract_message_meta(raw)

        assert meta == {"service_type": "read", "category": "request", "cp": "cp1"}

    def test_response_message(self, client):
        raw = '{"response": {"associateId": "cp1", "service": {"read": {}}}}'

        meta = client._extract_message_meta(raw)

        assert meta == {"service_type": "read", "category": "response", "cp": "cp1"}

    def test_associate_request(self, client):
        raw = '{"associate": {"service": {"associateRequest": {"calledAP": "cp1"}}}}'

        meta = client._extract_message_meta(raw)

        assert meta == {
            "service_type": "associateRequest",
            "category": "associate",
            "cp": "cp1",
        }

    def test_associate_response(self, client):
        raw = (
            '{"associate": {"service": {"associateResponse": {"associateId": "cp1"}}}}'
        )

        meta = client._extract_message_meta(raw)

        assert meta == {
            "service_type": "associateResponse",
            "category": "associate",
            "cp": "cp1",
        }

    def test_unrecognized_shape_returns_unknowns(self, client):
        raw = '{"somethingElse": {}}'

        meta = client._extract_message_meta(raw)

        assert meta == {"service_type": "unknown", "category": "unknown", "cp": ""}

    def test_invalid_json_returns_parse_error(self, client):
        meta = client._extract_message_meta("not json")

        assert meta == {
            "service_type": "parse-error",
            "category": "parse-error",
            "cp": "",
        }

    def test_non_dict_json_returns_unknowns(self, client):
        meta = client._extract_message_meta("[1, 2, 3]")

        assert meta == {"service_type": "unknown", "category": "unknown", "cp": ""}


class TestActionsAndMessagesLog:
    def test_log_action_appends_and_get_actions_returns_it(self, client):
        # ACSIClient.__init__ already logs its own "Connection initiated"
        # action (it starts listening on 0.0.0.0:8765 immediately on
        # construction), so the log isn't empty beforehand - only assert on
        # what this call itself appended.
        before = len(client.get_actions())

        client._log_action("did something", detail={"x": 1})

        actions = client.get_actions()
        assert len(actions) == before + 1
        assert actions[-1]["message"] == "did something"
        assert actions[-1]["detail"] == {"x": 1}

    def test_clear_actions_empties_log(self, client):
        client._log_action("did something")

        client.clear_actions()

        assert client.get_actions() == []

    def test_log_message_appends_and_get_messages_returns_it(self, client):
        client._log_message(
            "recv", '{"request": {"associateId": "cp1", "service": {"read": {}}}}', None
        )

        messages = client.get_messages()

        assert len(messages) == 1
        assert messages[0]["direction"] == "recv"
        assert messages[0]["service_type"] == "read"
        assert messages[0]["cp"] == "cp1"

    def test_clear_messages_empties_log(self, client):
        client._log_message("recv", "hello", None)

        client.clear_messages()

        assert client.get_messages() == []


class TestInitDoesNotClobberConnectStatus:
    def test_init_does_not_overwrite_status_set_by_connect(self):
        # Regression test: __init__ used to call self.connect(...) - which
        # already sets runtime.status = "connecting" itself, synchronously,
        # before spawning a background thread that eventually flips it to
        # "connected" - and then unconditionally set
        # self.runtime.status = "connecting" again right after. connect()'s
        # background thread can (and, per real container logs, reliably
        # does) win that race and already reach "connected" before that
        # extra line ran, silently clobbering it back to "connecting"
        # forever - nothing was left to ever correct it, even though the WS
        # server was genuinely up and accepting associations the whole
        # time. Mocking connect() to land on "connected" synchronously
        # reproduces exactly that race outcome without real threads/sockets.
        def fake_connect(self, host, port):
            self.runtime.status = "connected"

        with patch.object(ACSIClient, "connect", fake_connect):
            client = ACSIClient()

        assert client.runtime.status == "connected"
