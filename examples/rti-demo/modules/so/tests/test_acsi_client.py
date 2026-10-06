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

import json
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
        assert client._convert_operate_val_to_its_type("false", "boolean") is False
        assert client._convert_operate_val_to_its_type("off", "boolean") is False
        assert client._convert_operate_val_to_its_type(True, "boolean") is True

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

        assert meta == {
            "service_type": "read",
            "category": "request",
            "cp": "cp1",
            "invoke_id": None,
        }

    def test_response_message(self, client):
        raw = '{"response": {"associateId": "cp1", "service": {"read": {}}}}'

        meta = client._extract_message_meta(raw)

        assert meta == {
            "service_type": "read",
            "category": "response",
            "cp": "cp1",
            "invoke_id": None,
        }

    def test_request_carries_invoke_id(self, client):
        raw = '{"request": {"associateId": "cp1", "invokeId": 7, "service": {"getDataValues": {}}}}'

        assert client._extract_message_meta(raw)["invoke_id"] == 7

    def test_associate_request(self, client):
        raw = '{"associate": {"service": {"associateRequest": {"calledAP": "cp1"}}}}'

        meta = client._extract_message_meta(raw)

        assert meta == {
            "service_type": "associateRequest",
            "category": "associate",
            "cp": "cp1",
            "invoke_id": None,
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
            "invoke_id": None,
        }

    def test_report_carries_its_cp(self, client):
        raw = '{"unconfirmed": {"associateId": "cp2", "service": {"report": {"rptID": "ActualValues"}}}}'

        meta = client._extract_message_meta(raw)

        assert meta == {
            "service_type": "report",
            "category": "unconfirmed",
            "cp": "cp2",
            "invoke_id": None,
        }

    def test_unrecognized_shape_returns_unknowns(self, client):
        raw = '{"somethingElse": {}}'

        meta = client._extract_message_meta(raw)

        assert meta == {
            "service_type": "unknown",
            "category": "unknown",
            "cp": "",
            "invoke_id": None,
        }

    def test_invalid_json_returns_parse_error(self, client):
        meta = client._extract_message_meta("not json")

        assert meta == {
            "service_type": "parse-error",
            "category": "parse-error",
            "cp": "",
            "invoke_id": None,
        }

    def test_non_dict_json_returns_unknowns(self, client):
        meta = client._extract_message_meta("[1, 2, 3]")

        assert meta == {
            "service_type": "unknown",
            "category": "unknown",
            "cp": "",
            "invoke_id": None,
        }


class TestActionsAndMessagesLog:
    def test_log_action_appends_and_get_actions_returns_it(self, client):
        # ACSIClient.__init__ already logs its own "Connection initiated"
        # action (it starts listening on 0.0.0.0:8765 immediately on
        # construction), so the log isn't empty beforehand - only assert on
        # what this call itself appended.
        before = len(client.get_actions())

        client._log_action("did something", detail={"x": 1}, kind="system")

        actions = client.get_actions()
        assert len(actions) == before + 1
        assert actions[-1]["message"] == "did something"
        assert actions[-1]["detail"] == {"x": 1}
        assert actions[-1]["kind"] == "system"

    def test_log_action_requires_a_known_kind(self, client):
        with pytest.raises(TypeError):
            client._log_action("no kind")  # kind is a required keyword
        with pytest.raises(ValueError):
            client._log_action("bad kind", kind="websocket")

    def test_log_action_records_acsi_fields(self, client):
        client._log_action(
            "GetDataValues",
            kind="acsi",
            cp="cp1",
            service="getDataValues",
            correlation={"cp": "cp1", "invokeId": 3, "messageSeqFrom": 10},
        )

        entry = client.get_actions()[-1]
        assert entry["kind"] == "acsi"
        assert entry["cp"] == "cp1"
        assert entry["service"] == "getDataValues"
        assert entry["correlation"] == {
            "cp": "cp1",
            "invokeId": 3,
            "messageSeqFrom": 10,
        }

    def test_clear_actions_empties_log(self, client):
        client._log_action("did something", kind="system")

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
        assert messages[0]["kind"] == "websocket"
        assert messages[0]["level"] == "info"
        assert messages[0]["service"] == "read"

    def test_log_message_marks_service_error_responses_as_errors(self, client):
        client._log_message(
            "recv",
            '{"response": {"associateId": "cp1", "invokeId": 4, "service": {"serviceError": "instanceNotAvailable"}}}',
            None,
        )

        message = client.get_messages()[-1]
        assert message["level"] == "error"
        assert message["invokeId"] == 4

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


class TestInvokeAcsi:
    """ACSIClient._invoke_acsi: one kind "acsi" entry per call, linked to the
    frames logged while it ran."""

    @staticmethod
    def _frames(client, *frames):
        async def call():
            for direction, raw in frames:
                client._log_message(direction, raw, None)
            return "the-result"

        return call

    @staticmethod
    def _req(cp, invoke_id, service="getDataValues"):
        return f'{{"request": {{"associateId": "{cp}", "invokeId": {invoke_id}, "service": {{"{service}": {{}}}}}}}}'

    @staticmethod
    def _resp(cp, invoke_id, service="getDataValues"):
        return f'{{"response": {{"associateId": "{cp}", "invokeId": {invoke_id}, "service": {{"{service}": {{}}}}}}}}'

    async def test_logs_one_linked_entry_for_an_ok_call(self, client):
        client._log_message("recv", self._resp("cp1", 1), None)  # earlier, unrelated
        info = type("WSInfo", (), {"invoke_id": 4})()

        result = await client._invoke_acsi(
            service="getDataValues",
            summary="GetDataValues LD0/LLN0.Mod.stVal [ST]",
            cp="cp1",
            websocket_info=info,
            detail={"objRef": "LD0/LLN0.Mod.stVal"},
            call=self._frames(
                client, ("send", self._req("cp1", 4)), ("recv", self._resp("cp1", 4))
            ),
        )

        assert result == "the-result"
        entry = client.get_actions()[-1]
        assert entry["kind"] == "acsi"
        assert entry["level"] == "info"
        assert entry["message"] == "GetDataValues LD0/LLN0.Mod.stVal [ST] - ok"
        assert entry["service"] == "getDataValues"
        assert entry["cp"] == "cp1"
        assert entry["detail"]["objRef"] == "LD0/LLN0.Mod.stVal"
        assert entry["detail"]["result"] == "the-result"
        frame_ids = [m["id"] for m in client.get_messages()]
        assert entry["correlation"] == {
            "cp": "cp1",
            "invokeId": 4,
            "messageSeqFrom": frame_ids[1],
            "messageSeqTo": frame_ids[2],
        }

    async def test_service_error_response_is_an_error(self, client):
        await client._invoke_acsi(
            service="setDataValues",
            summary="SetDataValues x",
            cp="cp1",
            websocket_info=None,
            call=self._frames(
                client,
                ("send", self._req("cp1", 0, "setDataValues")),
                ("recv", self._resp("cp1", 0, "serviceError")),
            ),
        )

        entry = client.get_actions()[-1]
        assert entry["level"] == "error"
        assert entry["message"].startswith("SetDataValues x - failed")

    async def test_no_response_on_this_cp_is_a_warning(self, client):
        # A response on another cp, and a report, don't count as this call's.
        await client._invoke_acsi(
            service="getDataValues",
            summary="GetDataValues x",
            cp="cp1",
            websocket_info=None,
            call=self._frames(
                client,
                ("send", self._req("cp1", 0)),
                ("recv", self._resp("cp2", 0)),
                (
                    "recv",
                    '{"unconfirmed": {"associateId": "cp1", "service": {"report": {}}}}',
                ),
            ),
        )

        entry = client.get_actions()[-1]
        assert entry["level"] == "warn"
        assert entry["message"] == "GetDataValues x - no response"


class TestReportCallback:
    """_on_recv_message hands a received report's values to the report callback."""

    @staticmethod
    def _received(client, report):
        calls = []
        client.install_report_callback(
            lambda rpt_id, data_set, data: calls.append((rpt_id, data_set, data))
        )
        client._on_recv_message(
            json.dumps(
                {"unconfirmed": {"associateId": "cp1", "service": {"report": report}}}
            ),
            None,
        )
        return calls

    def test_reads_entry_data_under_entry(self, client):
        value = [{"data": {"float32": 42.5}}]
        calls = self._received(
            client,
            {
                "rptID": "ActualValues",
                "dataSet": "LD0/LLN0.DataSetActualValues",
                "entry": {
                    "entryID": "1",
                    "entryData": [{"dataRef": "LD0/MMXU1.TotW.mag.f", "value": value}],
                },
            },
        )

        assert calls == [
            (
                "ActualValues",
                "LD0/LLN0.DataSetActualValues",
                [{"dataRef": "LD0/MMXU1.TotW.mag.f", "value": value}],
            )
        ]

    def test_still_reads_a_top_level_entry_data(self, client):
        calls = self._received(
            client,
            {
                "rptID": "R",
                "dataSet": "DS",
                "entryData": [{"dataRef": "LD0/A", "value": 1}],
            },
        )

        assert calls[0][2] == [{"dataRef": "LD0/A", "value": 1}]

    def test_accepts_a_single_entry(self, client):
        calls = self._received(
            client,
            {
                "rptID": "R",
                "dataSet": "DS",
                "entry": {"entryData": {"dataRef": "LD0/A", "value": 1}},
            },
        )

        assert calls[0][2] == [{"dataRef": "LD0/A", "value": 1}]


class TestOperateRequestContents:
    """What ACSIClient.operate sends: the caller's ctlNum, origin and test,
    timed now - not a fixed test-mode operate."""

    def test_originator_maps_categories(self):
        from so.acsi_client import originator

        assert originator({"orCat": 1, "orIdent": "HMI"}) == {
            "orCat": "bayControl",
            "orIdent": b"HMI",
        }
        assert originator({"orCat": "3", "orIdent": "0"}) == {
            "orCat": "remoteControl",
            "orIdent": b"0",
        }
        assert originator({"orCat": "automaticBay", "orIdent": b"x"}) == {
            "orCat": "automaticBay",
            "orIdent": b"x",
        }
        assert originator(None) == {
            "orCat": "stationControl",
            "orIdent": b"ORIGIN_ID_1234567890",
        }
        assert len(originator({"orCat": 2, "orIdent": "x" * 80})["orIdent"]) == 64

    @pytest.mark.parametrize("bad", [9, -1, "fieldControl"])
    def test_originator_rejects_unknown_categories(self, bad):
        from so.acsi_client import originator

        with pytest.raises(ValueError):
            originator({"orCat": bad, "orIdent": "x"})

    def test_operate_sends_the_callers_values_timed_now(self, client):
        import asyncio
        import time as _time
        from types import SimpleNamespace

        sent = []

        async def fake_operate(oper_val, websocket_info, callback, parameter):
            sent.append(oper_val)
            return True

        async def run_call(**kwargs):
            return await kwargs["call"]()

        client.get_iec61850_client = lambda cp: SimpleNamespace(operate=fake_operate)
        client.runtime.endpoint = SimpleNamespace(
            get_websocket_info=lambda c: SimpleNamespace()
        )
        client._invoke_acsi = run_call

        result = asyncio.run(
            client.operate(
                "GenericIO/GGIO1.SPCSO1",
                True,
                "boolean",
                "cp2",
                ctl_num=7,
                origin={"orCat": 1, "orIdent": "HMI"},
                test=False,
            )
        )

        assert result == {"objRef": "GenericIO/GGIO1.SPCSO1", "result": True}
        oper = sent[0]
        assert oper["ctlNum"] == 7
        assert oper["test"] is False
        assert oper["origin"] == {"orCat": "bayControl", "orIdent": b"HMI"}
        assert abs(oper["t"]["secondSinceEpoch"] - _time.time()) < 5

    def test_operate_defaults_to_a_real_operate(self, client):
        import asyncio
        from types import SimpleNamespace

        sent = []

        async def fake_operate(oper_val, *args):
            sent.append(oper_val)
            return True

        async def run_call(**kwargs):
            return await kwargs["call"]()

        client.get_iec61850_client = lambda cp: SimpleNamespace(operate=fake_operate)
        client.runtime.endpoint = SimpleNamespace(
            get_websocket_info=lambda c: SimpleNamespace()
        )
        client._invoke_acsi = run_call

        asyncio.run(client.operate("LD0/DWMX1.WMaxSpt", "50", "float32", "cp1"))
        assert sent[0]["test"] is False
        assert sent[0]["ctlNum"] == 0


class TestEnumeratedOperateValue:
    """ENG/ENC operates send value_type "enumerated" - ACSI INTEGER (0..255)."""

    def test_converts_to_an_integer(self, client):
        assert client._convert_operate_val_to_its_type("3", "enumerated") == 3
        assert client._convert_operate_val_to_its_type(0, "enumerated") == 0

    @pytest.mark.parametrize("bad", ["on", "", 256, -1, None])
    def test_rejects_what_is_not_0_to_255(self, client, bad):
        with pytest.raises(ValueError):
            client._convert_operate_val_to_its_type(bad, "enumerated")
