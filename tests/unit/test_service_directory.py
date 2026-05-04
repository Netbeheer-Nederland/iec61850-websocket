# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for DirectoryService."""
import pytest

from ws61850.iec61850.services.directory_service import DirectoryService
from ws61850.iec61850.data_model.ied_model import DataSet, DataSetEntry, FunctionalConstraint


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _svc_tuple(service_name, **fields):
    return ("request", {"invokeId": 1, "associateId": 0, "service": (service_name, fields)})


# ---------------------------------------------------------------------------
# getServerDirectory
# ---------------------------------------------------------------------------

def test_get_server_directory_returns_ld_names(simple_ied):
    svc = DirectoryService(simple_ied)
    result = svc.get_server_directory(invoke_id=1, associate_id=0)
    # result is a TPAA tuple — check it is a tuple/list
    assert result is not None
    # The LD name should appear somewhere in the nested structure
    import json
    flat = str(result)
    assert "LD0" in flat


# ---------------------------------------------------------------------------
# getLogicalDeviceDirectory
# ---------------------------------------------------------------------------

def test_get_ld_directory_returns_ln_names(simple_ied):
    svc = DirectoryService(simple_ied)
    msg = _svc_tuple("getLogicalDeviceDirectory", ldName="LD0")
    result = svc.get_logical_device_directory(1, 0, msg)
    flat = str(result)
    assert "LLN0" in flat
    assert "GGIO1" in flat


def test_get_ld_directory_unknown_ld_returns_error(simple_ied):
    svc = DirectoryService(simple_ied)
    msg = _svc_tuple("getLogicalDeviceDirectory", ldName="MISSING")
    result = svc.get_logical_device_directory(1, 0, msg)
    flat = str(result)
    assert "instanceNotAvailable" in flat


# ---------------------------------------------------------------------------
# getLogicalNodeDirectory
# ---------------------------------------------------------------------------

def test_get_ln_directory_data_objects(simple_ied):
    svc = DirectoryService(simple_ied)
    msg = _svc_tuple("getLogicalNodeDirectory", lnRef="LD0/LLN0", aCSIClass="dataObject")
    result = svc.get_logical_node_directory(1, 0, msg)
    flat = str(result)
    assert "Health" in flat


def test_get_ln_directory_unknown_ln_returns_error(simple_ied):
    svc = DirectoryService(simple_ied)
    msg = _svc_tuple("getLogicalNodeDirectory", lnRef="LD0/MISSING", aCSIClass="dataObject")
    result = svc.get_logical_node_directory(1, 0, msg)
    flat = str(result)
    assert "instanceNotAvailable" in flat


# ---------------------------------------------------------------------------
# getDataDirectory
# ---------------------------------------------------------------------------

def test_get_data_directory_returns_da_names(simple_ied):
    svc = DirectoryService(simple_ied)
    msg = _svc_tuple("getDataDirectory", dataRef="LD0/LLN0.Health")
    result = svc.get_data_directory(1, 0, msg)
    flat = str(result)
    assert "stVal" in flat


def test_get_data_directory_unknown_ref_returns_error(simple_ied):
    svc = DirectoryService(simple_ied)
    msg = _svc_tuple("getDataDirectory", dataRef="LD0/LLN0.MISSING")
    result = svc.get_data_directory(1, 0, msg)
    flat = str(result)
    assert "instanceNotAvailable" in flat


# ---------------------------------------------------------------------------
# getDataDefinition
# ---------------------------------------------------------------------------

def test_get_data_definition_ok(simple_ied):
    svc = DirectoryService(simple_ied)
    msg = _svc_tuple("getDataDefinition", dataRef="LD0/LLN0.Health")
    result = svc.get_data_definition(1, 0, msg)
    assert result is not None


def test_get_data_definition_unknown_returns_error(simple_ied):
    svc = DirectoryService(simple_ied)
    msg = _svc_tuple("getDataDefinition", dataRef="LD0/LLN0.NOPE")
    result = svc.get_data_definition(1, 0, msg)
    flat = str(result)
    assert "instanceNotAvailable" in flat


# ---------------------------------------------------------------------------
# getDataSetDirectory
# ---------------------------------------------------------------------------

def test_get_ds_directory_ok(simple_ied):
    from ws61850.iec61850.data_model.ied_model import DataSet, DataSetEntry

    lln0 = simple_ied.logical_devices[0].logical_nodes[0]
    ds = DataSet(parent=lln0, logical_device_name="LD0", name="DS1")
    entry = DataSetEntry(
        logical_device_name="LD0",
        variable_name="LD0/LLN0.Health.stVal",
        fc=FunctionalConstraint.st,
    )
    ds.dataSet_addEntry(entry)
    lln0.add_dataSet(ds)

    svc = DirectoryService(simple_ied)
    msg = _svc_tuple("getDataSetDirectory", dsRef="LD0/LLN0.DS1")
    result = svc.get_data_set_directory(1, 0, msg)
    assert result is not None
    assert "instanceNotAvailable" not in str(result)


def test_get_ds_directory_missing_returns_error(simple_ied):
    svc = DirectoryService(simple_ied)
    msg = _svc_tuple("getDataSetDirectory", dsRef="LD0/LLN0.NONE")
    result = svc.get_data_set_directory(1, 0, msg)
    flat = str(result)
    assert "instanceNotAvailable" in flat
