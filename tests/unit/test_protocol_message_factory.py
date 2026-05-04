# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
import pytest

from ws61850.protocol.message_factory import TpaaMessageFactory


@pytest.fixture
def factory():
    return TpaaMessageFactory()


# ---------------------------------------------------------------------------
# Association lifecycle
# ---------------------------------------------------------------------------

def test_associate_request_structure(factory):
    msg = factory.associate_request("calledAP", 65536)
    assert msg[0] == "associate"
    _, svc = msg
    assert svc[0] == "service"
    req_type, payload = svc[1]
    assert req_type == "associateRequest"
    assert payload["calledAP"] == "calledAP"
    assert payload["maxMessageSize"] == 65536


def test_associate_response_minimal(factory):
    msg = factory.associate_response(65536, associate_id=1)
    _, svc = msg
    _, payload = svc[1]
    assert payload["associateId"] == 1
    assert payload["maxMessageSize"] == 65536
    assert "maxOutstandingCalls" not in payload


def test_associate_response_with_outstanding_calls(factory):
    msg = factory.associate_response(65536, associate_id=2, max_outstanding_calls=10)
    _, svc = msg
    _, payload = svc[1]
    assert payload["maxOutstandingCalls"] == 10


def test_release_request(factory):
    msg = factory.release_request(invoke_id=3, associate_id=1)
    _, svc = msg
    req_type, payload = svc[1]
    assert req_type == "releaseRequest"
    assert payload["invokeId"] == 3
    assert payload["associateId"] == 1


def test_abort_request(factory):
    msg = factory.abort_request(invoke_id=5, associate_id=2)
    _, svc = msg
    req_type, payload = svc[1]
    assert req_type == "abortRequest"


def test_token_refresh(factory):
    msg = factory.token_refresh(associate_id=1, token="tok123")
    _, svc = msg
    req_type, payload = svc[1]
    assert req_type == "refreshToken"
    assert payload["token"] == "tok123"


# ---------------------------------------------------------------------------
# Generic request / response
# ---------------------------------------------------------------------------

def test_generic_request(factory):
    msg = factory.request("someService", invoke_id=1, associate_id=0, foo="bar")
    assert msg[0] == "request"
    body = msg[1]
    assert body["invokeId"] == 1
    svc_name, svc_payload = body["service"]
    assert svc_name == "someService"
    assert svc_payload["foo"] == "bar"


def test_generic_response(factory):
    msg = factory.response("someService", invoke_id=2, associate_id=0, result="ok")
    assert msg[0] == "response"


def test_service_error(factory):
    msg = factory.service_error(invoke_id=3, associate_id=0, error="instanceNotAvailable")
    assert msg[0] == "response"
    assert msg[1]["serviceError"] == "instanceNotAvailable"


# ---------------------------------------------------------------------------
# Named request builders
# ---------------------------------------------------------------------------

def test_get_server_directory(factory):
    msg = factory.get_server_directory(invoke_id=1, associate_id=0)
    svc_name, payload = msg[1]["service"]
    assert svc_name == "getServerDirectory"
    assert payload["objectClass"] == "logicalDevice"


def test_get_logical_device_directory(factory):
    msg = factory.get_logical_device_directory(1, 0, "LD0")
    svc_name, payload = msg[1]["service"]
    assert svc_name == "getLogicalDeviceDirectory"
    assert payload["ldName"] == "LD0"


def test_get_logical_node_directory(factory):
    msg = factory.get_logical_node_directory(1, 0, "LD0/LLN0", "dataObject")
    svc_name, payload = msg[1]["service"]
    assert svc_name == "getLogicalNodeDirectory"
    assert payload["lnRef"] == "LD0/LLN0"
    assert payload["aCSIClass"] == "dataObject"


def test_get_data_set_directory(factory):
    msg = factory.get_data_set_directory(1, 0, "LD0/LLN0.DS1")
    svc_name, payload = msg[1]["service"]
    assert svc_name == "getDataSetDirectory"
    assert payload["dsRef"] == "LD0/LLN0.DS1"


def test_get_data_directory(factory):
    msg = factory.get_data_directory(1, 0, "LD0/LLN0.Health")
    svc_name, payload = msg[1]["service"]
    assert svc_name == "getDataDirectory"
    assert payload["dataRef"] == "LD0/LLN0.Health"


def test_get_data_values(factory):
    ref = {"ref": "LD0/LLN0.Health.stVal", "fc": "st"}
    msg = factory.get_data_values(1, 0, ref, include_element_name=True)
    svc_name, payload = msg[1]["service"]
    assert svc_name == "getDataValues"
    assert payload["ref"] == ref
    assert payload["includeElementName"] is True


def test_get_brcb_values(factory):
    msg = factory.get_brcb_values(1, 0, "LD0/LLN0.BR.rcb01")
    svc_name, payload = msg[1]["service"]
    assert svc_name == "getBRCBValues"
    assert payload["brcbRef"] == "LD0/LLN0.BR.rcb01"


def test_get_urcb_values(factory):
    msg = factory.get_urcb_values(1, 0, "LD0/LLN0.RP.rcb01")
    svc_name, payload = msg[1]["service"]
    assert svc_name == "getURCBValues"
    assert payload["urcbRef"] == "LD0/LLN0.RP.rcb01"


def test_select(factory):
    msg = factory.select(1, 0, "LD0/CSWI1.Pos.Oper")
    svc_name, payload = msg[1]["service"]
    assert svc_name == "select"
    assert payload["ref"] == "LD0/CSWI1.Pos.Oper"
