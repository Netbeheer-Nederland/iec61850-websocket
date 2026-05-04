# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
import json

import pytest

from ws61850.shared.extractors import (
    extract_acsiType,
    extract_associate_request_type,
    extract_brcb_ref,
    extract_data_ref,
    extract_dataAttrVal,
    extract_ds_ref,
    extract_includeElementName,
    extract_invoke_id,
    extract_ln_ref,
    extract_ld_name,
    extract_ref,
    extract_service_name,
    extract_urcb_ref,
    retrieve_associate_id,
    retrieve_associate_id_from_decoded_msg,
    retrieve_max_outstanding_calls_from_decoded_msg,
)


# ---------------------------------------------------------------------------
# retrieve_associate_id (raw JSON)
# ---------------------------------------------------------------------------

def _raw_associate_response(associate_id):
    return json.dumps({
        "associate": {
            "service": {
                "associateResponse": {"associateId": associate_id}
            }
        }
    })


def test_retrieve_associate_id_ok():
    raw = _raw_associate_response(42)
    assert retrieve_associate_id(raw) == 42


def test_retrieve_associate_id_missing_key():
    with pytest.raises(ValueError):
        retrieve_associate_id(json.dumps({"associate": {}}))


# ---------------------------------------------------------------------------
# retrieve_associate_id_from_decoded_msg
# ---------------------------------------------------------------------------

def _decoded_assoc_response(assoc_id):
    return ("associate", ("service", ("associateResponse", {"associateId": assoc_id})))


def test_retrieve_associate_id_from_decoded_msg_ok():
    msg = _decoded_assoc_response(7)
    assert retrieve_associate_id_from_decoded_msg(msg) == 7


def test_retrieve_associate_id_from_decoded_msg_missing():
    with pytest.raises(ValueError):
        retrieve_associate_id_from_decoded_msg(("associate", ("service", ("associateResponse", {}))))


# ---------------------------------------------------------------------------
# retrieve_max_outstanding_calls_from_decoded_msg
# ---------------------------------------------------------------------------

def test_retrieve_max_outstanding_calls_present():
    msg = ("associate", ("service", ("associateResponse", {"associateId": 1, "maxOutstandingCalls": 10})))
    assert retrieve_max_outstanding_calls_from_decoded_msg(msg) == 10


def test_retrieve_max_outstanding_calls_missing_returns_zero():
    msg = ("associate", ("service", ("associateResponse", {"associateId": 1})))
    assert retrieve_max_outstanding_calls_from_decoded_msg(msg) == 0


# ---------------------------------------------------------------------------
# extract_associate_request_type
# ---------------------------------------------------------------------------

def _assoc_tuple(request_type, payload=None):
    return ("associate", ("service", (request_type, payload or {})))


def test_extract_associate_request_type_ok():
    tpaa = _assoc_tuple("associateRequest")
    assert extract_associate_request_type(tpaa) == "associateRequest"


def test_extract_associate_request_type_wrong_pdu():
    with pytest.raises(ValueError):
        extract_associate_request_type(("request", {}))


# ---------------------------------------------------------------------------
# extract_service_name / extract_invoke_id
# ---------------------------------------------------------------------------

def _request_tuple(service_name, invoke_id=1, associate_id=0, payload=None):
    return ("request", {"invokeId": invoke_id, "associateId": associate_id, "service": (service_name, payload or {})})


def test_extract_service_name_ok():
    tpaa = _request_tuple("getServerDirectory")
    assert extract_service_name(tpaa) == "getServerDirectory"


def test_extract_invoke_id_ok():
    tpaa = _request_tuple("getDataValues", invoke_id=5)
    assert extract_invoke_id(tpaa) == 5


def test_extract_service_name_bad_structure():
    with pytest.raises(ValueError):
        extract_service_name(("request", {"invokeId": 1}))


# ---------------------------------------------------------------------------
# Field extractors
# ---------------------------------------------------------------------------

def _svc_tuple(service_name, **fields):
    return ("request", {"invokeId": 1, "associateId": 0, "service": (service_name, fields)})


def test_extract_ld_name():
    tpaa = _svc_tuple("getLogicalDeviceDirectory", ldName="LD0")
    assert extract_ld_name(tpaa) == "LD0"


def test_extract_ln_ref():
    tpaa = _svc_tuple("getLogicalNodeDirectory", lnRef="LD0/LLN0")
    assert extract_ln_ref(tpaa) == "LD0/LLN0"


def test_extract_acsiType():
    tpaa = _svc_tuple("getLogicalNodeDirectory", lnRef="LD0/LLN0", aCSIClass="dataObject")
    assert extract_acsiType(tpaa) == "dataObject"


def test_extract_ds_ref():
    tpaa = _svc_tuple("getDataSetDirectory", dsRef="LD0/LLN0.DS1")
    assert extract_ds_ref(tpaa) == "LD0/LLN0.DS1"


def test_extract_data_ref():
    tpaa = _svc_tuple("getDataDirectory", dataRef="LD0/LLN0.Health")
    assert extract_data_ref(tpaa) == "LD0/LLN0.Health"


def test_extract_ref():
    tpaa = _svc_tuple("getDataValues", ref={"ref": "LD0/LLN0.Health.stVal", "fc": "st"})
    assert extract_ref(tpaa) == {"ref": "LD0/LLN0.Health.stVal", "fc": "st"}


def test_extract_dataAttrVal():
    tpaa = _svc_tuple("setDataValues", dataAttrVal=[{"data": True}])
    assert extract_dataAttrVal(tpaa) == [{"data": True}]


def test_extract_includeElementName():
    tpaa = _svc_tuple("getDataValues", includeElementName=True)
    assert extract_includeElementName(tpaa) is True


def test_extract_brcb_ref():
    tpaa = _svc_tuple("getBRCBValues", brcbRef="LD0/LLN0.BR.rcb01")
    assert extract_brcb_ref(tpaa) == "LD0/LLN0.BR.rcb01"


def test_extract_urcb_ref():
    tpaa = _svc_tuple("getURCBValues", urcbRef="LD0/LLN0.RP.rcb01")
    assert extract_urcb_ref(tpaa) == "LD0/LLN0.RP.rcb01"


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fn,tpaa", [
    (extract_ld_name, _svc_tuple("x")),
    (extract_ln_ref, _svc_tuple("x")),
    (extract_acsiType, _svc_tuple("x")),
    (extract_ds_ref, _svc_tuple("x")),
    (extract_data_ref, _svc_tuple("x")),
    (extract_ref, _svc_tuple("x")),
    (extract_dataAttrVal, _svc_tuple("x")),
    (extract_includeElementName, _svc_tuple("x")),
    (extract_brcb_ref, _svc_tuple("x")),
    (extract_urcb_ref, _svc_tuple("x")),
])
def test_field_extractor_missing_raises(fn, tpaa):
    with pytest.raises(ValueError):
        fn(tpaa)
