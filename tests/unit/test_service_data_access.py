# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for DataAccessService."""
import pytest

from ws61850.iec61850.services.data_access_service import DataAccessService
from ws61850.iec61850.data_model.ied_model import FunctionalConstraint


def _svc_tuple(service_name, **fields):
    return ("request", {"invokeId": 1, "associateId": 0, "service": (service_name, fields)})


# ---------------------------------------------------------------------------
# getDataValues
# ---------------------------------------------------------------------------

def test_get_data_values_da_ok(simple_ied):
    svc = DataAccessService(simple_ied)
    msg = _svc_tuple(
        "getDataValues",
        ref={"ref": "LD0/LLN0.Health.stVal", "fc": "st"},
        includeElementName=True,
    )
    result = svc.get_data_values(1, 0, msg)
    flat = str(result)
    assert "instanceNotAvailable" not in flat


def test_get_data_values_do_ok(simple_ied):
    svc = DataAccessService(simple_ied)
    msg = _svc_tuple(
        "getDataValues",
        ref={"ref": "LD0/LLN0.Health", "fc": "st"},
        includeElementName=True,
    )
    result = svc.get_data_values(1, 0, msg)
    flat = str(result)
    assert "instanceNotAvailable" not in flat


def test_get_data_values_missing_ref(simple_ied):
    svc = DataAccessService(simple_ied)
    # Use top-level missing DO — find_object_in_tree returns None gracefully when
    # there is no sub-segment after the unknown name.
    msg = _svc_tuple(
        "getDataValues",
        ref={"ref": "LD0/LLN0.MISSING", "fc": "st"},
        includeElementName=True,
    )
    result = svc.get_data_values(1, 0, msg)
    flat = str(result)
    assert "instanceNotAvailable" in flat


# ---------------------------------------------------------------------------
# setDataValues
# ---------------------------------------------------------------------------

def test_set_data_values_da_ok(simple_ied):
    svc = DataAccessService(simple_ied)
    # assign_da_item expects value as ("type_name", actual_value) tuple
    msg = _svc_tuple(
        "setDataValues",
        ref={"ref": "LD0/LLN0.Health.stVal", "fc": "st"},
        dataAttrVal=[{"data": ("boolean", True)}],
    )
    result = svc.set_data_values(1, 0, msg)
    flat = str(result)
    assert "ok" in flat


def test_set_data_values_fc_co_returns_access_violation(simple_ied):
    svc = DataAccessService(simple_ied)
    msg = _svc_tuple(
        "setDataValues",
        ref={"ref": "LD0/LLN0.Health.stVal", "fc": "co"},
        dataAttrVal=[{"data": True}],
    )
    result = svc.set_data_values(1, 0, msg)
    flat = str(result)
    assert "accessViolation" in flat


def test_set_data_values_missing_ref(simple_ied):
    svc = DataAccessService(simple_ied)
    # Top-level missing DO: find_object_in_tree returns None gracefully.
    msg = _svc_tuple(
        "setDataValues",
        ref={"ref": "LD0/LLN0.NOPE", "fc": "st"},
        dataAttrVal=[{"data": ("boolean", True)}],
    )
    result = svc.set_data_values(1, 0, msg)
    flat = str(result)
    assert "instanceNotAvailable" in flat


def test_set_data_values_wrong_fc_returns_error(simple_ied):
    svc = DataAccessService(simple_ied)
    # Health.stVal is FunctionalConstraint.st; writing with "mx" should fail
    msg = _svc_tuple(
        "setDataValues",
        ref={"ref": "LD0/LLN0.Health.stVal", "fc": "mx"},
        dataAttrVal=[{"data": True}],
    )
    result = svc.set_data_values(1, 0, msg)
    flat = str(result)
    assert "instanceNotAvailable" in flat


# ---------------------------------------------------------------------------
# getDatasetValues
# ---------------------------------------------------------------------------

def test_get_dataset_values_with_dataset(simple_ied):
    from ws61850.iec61850.data_model.ied_model import DataSet, DataSetEntry

    lln0 = simple_ied.logical_devices[0].logical_nodes[0]
    ds = DataSet(parent=lln0, logical_device_name="LD0", name="DS2")
    entry = DataSetEntry(
        logical_device_name="LD0",
        variable_name="LD0/LLN0.Health.stVal",
        fc=FunctionalConstraint.st,
    )
    ds.dataSet_addEntry(entry)
    lln0.add_dataSet(ds)

    svc = DataAccessService(simple_ied)
    msg = _svc_tuple("getDatasetValues", dsRef="LD0/LLN0.DS2")

    result = svc.get_dataset_values(1, 0, msg, find_ds_in_tree=None)
    flat = str(result)
    assert "instanceNotAvailable" not in flat


def test_get_dataset_values_missing_ln(simple_ied):
    svc = DataAccessService(simple_ied)
    msg = _svc_tuple("getDatasetValues", dsRef="LD0/MISSING.DS1")
    result = svc.get_dataset_values(1, 0, msg, find_ds_in_tree=None)
    flat = str(result)
    assert "instanceNotAvailable" in flat
