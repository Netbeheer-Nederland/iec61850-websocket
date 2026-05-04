# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""Shared pytest fixtures for unit tests."""
import pytest

from ws61850.iec61850.data_model.ied_model import (
    DataAttribute,
    DataAttributeType,
    DataObject,
    DataSet,
    DataSetEntry,
    FunctionalConstraint,
    IedModel,
    LogicalDevice,
    LogicalNode,
)


def _make_da(name, fc, type_=DataAttributeType.boolean, value=False, parent=None):
    da = DataAttribute(name=name, fc=fc, type_=type_, mmsValue=value, parent=parent)
    return da


def _make_do(name, parent=None):
    return DataObject(name=name, parent=parent)


@pytest.fixture
def simple_ied():
    """
    Minimal IED:
      LD0
        LLN0
          Health (st: stVal bool, q quality)
          Mod   (cf: ctlVal enum)
        GGIO1
          Ind1  (st: stVal bool)
    """
    ied = IedModel(name="TestIED")
    ld = LogicalDevice(name="LD0", ldName="LD0")
    ied.add_logicalDevice(ld)

    lln0 = LogicalNode(name="LLN0")
    ld.add_logical_node(lln0)

    # Health DO
    health = _make_do("Health")
    health.parent = lln0
    st_val = _make_da("stVal", FunctionalConstraint.st, DataAttributeType.boolean, False)
    st_val.parent = health
    q = _make_da("q", FunctionalConstraint.st, DataAttributeType.quality, 0)
    q.parent = health
    health.add_do_or_da(st_val)
    health.add_do_or_da(q)
    lln0.add_dataObject(health)

    # Mod DO (CF)
    mod = _make_do("Mod")
    mod.parent = lln0
    ctl_val = _make_da("ctlVal", FunctionalConstraint.cf, DataAttributeType.int32, 1)
    ctl_val.parent = mod
    mod.add_do_or_da(ctl_val)
    lln0.add_dataObject(mod)

    ggio1 = LogicalNode(name="GGIO1")
    ld.add_logical_node(ggio1)

    ind1 = _make_do("Ind1")
    ind1.parent = ggio1
    ind_st = _make_da("stVal", FunctionalConstraint.st, DataAttributeType.boolean, False)
    ind_st.parent = ind1
    ind1.add_do_or_da(ind_st)
    ggio1.add_dataObject(ind1)

    return ied
