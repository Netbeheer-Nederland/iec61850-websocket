# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""IEC61850Server.handle_request logs the one-time GI report it sends when an
RCB is enabled - not the request's response a second time."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ws61850.iec61850.server import iec61850_server as server_module
from ws61850.iec61850.server.iec61850_server import IEC61850Server


@pytest.fixture
def stubbed(monkeypatch):
    # Encoding is the identity, so the logged frames can be told apart.
    monkeypatch.setattr(server_module, "decode_tpaa_message", lambda message, ber: ("request", message))
    monkeypatch.setattr(server_module, "extract_invoke_id", lambda decoded: 7)
    monkeypatch.setattr(server_module, "encode_tpaa_message", lambda tpaa, ber: tpaa)
    monkeypatch.setattr(server_module, "create_data_attribute_list_from_dataset", lambda *a: [])
    monkeypatch.setattr(server_module, "create_tpaa_report", lambda *a: "REPORT")
    monkeypatch.setattr(server_module, "get_now_time", lambda: 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("service", ["setBRCBValues", "setURCBValues"])
async def test_gi_report_is_logged_as_sent(stubbed, monkeypatch, service):
    monkeypatch.setattr(server_module, "extract_service_name", lambda decoded: service)
    rcb_socket = SimpleNamespace(send=AsyncMock())
    gi_rcb = SimpleNamespace(
        rcb=SimpleNamespace(dataset_name="LD0/LLN0.DS1", gi=True,
                            client_connection=SimpleNamespace(websocket=rcb_socket, associate_id="cp1")),
        time_of_entry=None,
    )
    server = object.__new__(IEC61850Server)
    server._report_service = SimpleNamespace(
        set_brcb_values=AsyncMock(return_value=("RESPONSE", gi_rcb)),
        set_urcb_values=AsyncMock(return_value=("RESPONSE", gi_rcb)),
    )
    server.ied_model = None
    server.find_ds_in_tree = lambda name: object()
    logged = []
    server.send_msg_callback = lambda message, ts: logged.append(message)
    websocket_info = SimpleNamespace(websocket=SimpleNamespace(send=AsyncMock()), is_ber_protocol=False)

    await server.handle_request("raw", "cp1", websocket_info)

    rcb_socket.send.assert_awaited_once_with("REPORT")
    websocket_info.websocket.send.assert_awaited_once_with("RESPONSE")
    assert logged == ["REPORT", "RESPONSE"]
    assert gi_rcb.rcb.gi is False
