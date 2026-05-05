# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for ReportService."""
import pytest
from unittest.mock import MagicMock

from ws61850.iec61850.services.report_service import ReportService
from ws61850.iec61850.data_model.ied_model import ReportControl
from ws61850.iec61850.server.server_report_control import ServerReportControl


def _make_rcb(name, ln, buffered=True):
    rcb = ReportControl(
        name,
        buffered=buffered,
        dataset_name="LD0/LLN0.DS1",
        rpt_id=name,
        conf_rev=1,
        trg_ops={"gi": True, "dchg": True},
        opt_flds={},
        buffered_time=0,
        int_period=0,
        indexed=False,
    )
    ln.add_report_control(rcb)
    return rcb


def _make_server_rc(rcb):
    src = ServerReportControl(rcb)
    return src


def _svc_tuple(service_name, **fields):
    return ("request", {"invokeId": 1, "associateId": 0, "service": (service_name, fields)})


@pytest.fixture
def brcb_control(simple_ied):
    lln0 = simple_ied.logical_devices[0].logical_nodes[0]
    rcb = _make_rcb("BR$rcb01", lln0, buffered=True)
    src = _make_server_rc(rcb)
    return src


@pytest.fixture
def urcb_control(simple_ied):
    lln0 = simple_ied.logical_devices[0].logical_nodes[0]
    rcb = _make_rcb("RP$rcb01", lln0, buffered=False)
    src = _make_server_rc(rcb)
    return src


# ---------------------------------------------------------------------------
# getBRCBValues
# ---------------------------------------------------------------------------

def test_get_brcb_values_ok(brcb_control):
    svc = ReportService([brcb_control])
    msg = _svc_tuple("getBRCBValues", brcbRef="LD0/LLN0.BR$rcb01")
    result, trigger = svc.get_brcb_values(1, 0, msg)
    assert trigger is None
    assert "instanceNotAvailable" not in str(result)


def test_get_brcb_values_missing_ref(brcb_control):
    svc = ReportService([brcb_control])
    msg = _svc_tuple("getBRCBValues", brcbRef="LD0/LLN0.MISSING")
    result, trigger = svc.get_brcb_values(1, 0, msg)
    assert "instanceNotAvailable" in str(result)


def test_get_brcb_values_rejects_unbuffered(urcb_control):
    svc = ReportService([urcb_control])
    msg = _svc_tuple("getBRCBValues", brcbRef="LD0/LLN0.RP$rcb01")
    result, trigger = svc.get_brcb_values(1, 0, msg)
    assert "instanceNotAvailable" in str(result)


# ---------------------------------------------------------------------------
# getURCBValues
# ---------------------------------------------------------------------------

def test_get_urcb_values_ok(urcb_control):
    svc = ReportService([urcb_control])
    msg = _svc_tuple("getURCBValues", urcbRef="LD0/LLN0.RP$rcb01")
    result, trigger = svc.get_urcb_values(1, 0, msg)
    assert trigger is None
    assert "instanceNotAvailable" not in str(result)


def test_get_urcb_values_missing_ref(urcb_control):
    svc = ReportService([urcb_control])
    msg = _svc_tuple("getURCBValues", urcbRef="LD0/LLN0.MISSING")
    result, trigger = svc.get_urcb_values(1, 0, msg)
    assert "instanceNotAvailable" in str(result)


def test_get_urcb_values_rejects_buffered(brcb_control):
    svc = ReportService([brcb_control])
    msg = _svc_tuple("getURCBValues", urcbRef="LD0/LLN0.BR$rcb01")
    result, trigger = svc.get_urcb_values(1, 0, msg)
    assert "instanceNotAvailable" in str(result)
