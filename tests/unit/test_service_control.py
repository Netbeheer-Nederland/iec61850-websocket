# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for ControlService."""
import pytest
from unittest.mock import MagicMock

from ws61850.iec61850.services.control_service import ControlService
from ws61850.iec61850.server.control_handling import ControlHandlerResult
from ws61850.iec61850.server.server_control_object import ServerControlObject
from ws61850.iec61850.data_model.ied_model import (
    DataAttribute,
    DataAttributeType,
    DataObject,
    FunctionalConstraint,
    LogicalDevice,
    LogicalNode,
    IedModel,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def control_ied():
    """IED with a controllable DO: LD0/CSWI1.Pos (FC=co, Oper/ctlVal bool, Oper/ctlNum int)."""
    ied = IedModel(name="CtrlIED")
    ld = LogicalDevice(name="LD0", ldName="LD0")
    ied.add_logicalDevice(ld)

    ln = LogicalNode(name="CSWI1")
    ld.add_logical_node(ln)

    pos = DataObject(name="Pos", cdc="")
    pos.parent = ln

    oper = DataAttribute(name="Oper", attr_type=DataAttributeType.structure, fc=FunctionalConstraint.co)
    oper.parent = pos

    ctl_val = DataAttribute(name="ctlVal", attr_type=DataAttributeType.boolean, fc=FunctionalConstraint.co, mms_value=False)
    ctl_val.parent = oper
    ctl_num = DataAttribute(name="ctlNum", attr_type=DataAttributeType.int32, fc=FunctionalConstraint.co, mms_value=0)
    ctl_num.parent = oper
    oper.add_data_attribute(ctl_val)
    oper.add_data_attribute(ctl_num)
    pos.add_do_or_da(oper)
    ln.add_dataObject(pos)

    return ied


@pytest.fixture
def control_objects(control_ied):
    pos = control_ied.logical_devices[0].logical_nodes[0].data_objects[0]
    sco = ServerControlObject(pos)
    return [sco]


def _ok_handler(obj_ref, ctl_val, param):
    return ControlHandlerResult.OK, None


def _svc_tuple(service_name, **fields):
    return ("request", {"invokeId": 1, "associateId": 0, "service": (service_name, fields)})


def _select_msg(ref="LD0/CSWI1.Pos.Oper"):
    # extract_operate_or_select_ref returns service[1]["ref"] directly;
    # find_object_in_tree expects a plain string path.
    return _svc_tuple("select", ref=ref)


def _operate_msg(ref="LD0/CSWI1.Pos.Oper", ctl_val=True):
    # ctlVal must match the format extract_ctlVal_from_operate_request returns
    # and that assign_da_item expects: ("boolean", value)
    return _svc_tuple("operate", ref=ref, ctlVal=("boolean", ctl_val))


# ---------------------------------------------------------------------------
# select
# ---------------------------------------------------------------------------

def test_select_ok(control_ied, control_objects):
    svc = ControlService(control_ied, control_objects, lambda: (_ok_handler, None))
    result, _ = svc.select(1, 0, _select_msg())
    assert "instanceNotAvailable" not in str(result)
    assert control_objects[0].is_selected is True


def test_select_already_selected(control_ied, control_objects):
    svc = ControlService(control_ied, control_objects, lambda: (_ok_handler, None))
    svc.select(1, 0, _select_msg())
    result, _ = svc.select(1, 0, _select_msg())
    assert "objectAlreadySelected" in str(result)


def test_select_unknown_ref_returns_error(control_ied, control_objects):
    svc = ControlService(control_ied, control_objects, lambda: (_ok_handler, None))
    # Use a path that resolves to None gracefully (no sub-segment after missing DO)
    result, _ = svc.select(1, 0, _select_msg("LD0/CSWI1.MISSING"))
    # extract_operate_or_select_ref returns "LD0/CSWI1.MISSING"; find_object_in_tree
    # returns None → server_control_obj lookup fails → instanceNotAvailable
    assert "instanceNotAvailable" in str(result)


# ---------------------------------------------------------------------------
# operate
# ---------------------------------------------------------------------------

def test_operate_requires_select_first(control_ied, control_objects):
    svc = ControlService(control_ied, control_objects, lambda: (_ok_handler, None))
    result, quality_do = svc.operate(1, 0, _operate_msg())
    assert "controlMustBeSelected" in str(result)
    assert quality_do is None


def test_operate_ok_after_select(control_ied, control_objects):
    svc = ControlService(control_ied, control_objects, lambda: (_ok_handler, None))
    svc.select(1, 0, _select_msg())
    result, quality_do = svc.operate(1, 0, _operate_msg())
    assert "instanceNotAvailable" not in str(result)
    assert "controlMustBeSelected" not in str(result)


def test_operate_unknown_ref_returns_error(control_ied, control_objects):
    svc = ControlService(control_ied, control_objects, lambda: (_ok_handler, None))
    # "LD0/CSWI1.MISSING" → find_object_in_tree returns None → instanceNotAvailable
    result, quality_do = svc.operate(1, 0, _operate_msg("LD0/CSWI1.MISSING"))
    assert "instanceNotAvailable" in str(result)


def test_operate_no_handler_returns_error(control_ied, control_objects):
    svc = ControlService(control_ied, control_objects, lambda: None)
    control_objects[0].is_selected = True
    result, quality_do = svc.operate(1, 0, _operate_msg())
    assert "failedDueToServerConstraint" in str(result)


def test_operate_handler_failure_returns_error(control_ied, control_objects):
    def _fail_handler(ref, val, param):
        return ControlHandlerResult.FAILED, None

    svc = ControlService(control_ied, control_objects, lambda: (_fail_handler, None))
    control_objects[0].is_selected = True
    result, quality_do = svc.operate(1, 0, _operate_msg())
    assert "failedDueToServerConstraint" in str(result)


def test_operate_increments_ctl_num(control_ied, control_objects):
    svc = ControlService(control_ied, control_objects, lambda: (_ok_handler, None))
    control_objects[0].is_selected = True
    pos = control_ied.logical_devices[0].logical_nodes[0].data_objects[0]
    oper_da = next(da for da in pos.do_or_da if da.name == "Oper")
    ctl_num = next(da for da in oper_da.data_attributes if da.name == "ctlNum")
    initial = ctl_num.mmsValue
    svc.operate(1, 0, _operate_msg())
    assert ctl_num.mmsValue == initial + 1
