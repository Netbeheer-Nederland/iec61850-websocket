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

from ws61850.iec61850.data_model.helper import (
    create_apc_do,
    create_asg_do,
    create_del_do,
    create_dpl_do,
    create_enc_do,
    create_ens_do,
    create_inc_do,
    create_ing_do,
    create_lpl_do,
    create_mv_do,
    create_sps_do,
    create_wye_do,
)
from ws61850.iec61850.data_model.ied_model import (
    DataSet,
    DataSetEntry,
    FunctionalConstraint,
    IedModel,
    LogicalDevice,
    LogicalNode,
    ReportControl,
)
from ws61850.protocol.types import OptFlds, TrgOps


def make_ied_model1():
    ied = IedModel(name="IED1")

    ld = LogicalDevice(name="LD0", ldName="LD_INST")
    ln2 = LogicalNode(name="LLN0")
    ln3 = LogicalNode(name="LPHD1")
    ln4 = LogicalNode(name="DWMX1")
    ln5 = LogicalNode(name="DGEN1")
    ln1 = LogicalNode(name="MMXU1")

    # MMXU1
    for name, factory in [
        ("Beh", create_ens_do),
        ("TotW", create_mv_do),
        ("TotVAr", create_mv_do),
        ("PhV", create_wye_do),
        ("PPV", create_del_do),
        ("A", create_wye_do),
        ("AvWPhs", create_mv_do),
        ("MaxWPhs", create_mv_do),
        ("MinWPhs", create_mv_do),
    ]:
        ln1.add_data_object(factory(name, ln1))

    # LLN0
    for name, factory in [
        ("Mod", create_enc_do),
        ("NamPlt", create_lpl_do),
        ("Beh", create_ens_do),
        ("Health", create_ens_do),
    ]:
        ln2.add_data_object(factory(name, ln2))

    # LPHD1
    for name, factory in [
        ("PhyNam", create_dpl_do),
        ("PhyHealth", create_ens_do),
        ("Proxy", create_sps_do),
        ("PwrUp", create_sps_do),
    ]:
        ln3.add_data_object(factory(name, ln3))

    # DWMX1
    for name, factory in [
        ("NamPlt", create_lpl_do),
        ("Beh", create_ens_do),
        ("WMaxSptPct", create_apc_do),
        ("WMaxSpt", create_apc_do),
        ("WMaxSetPct", create_asg_do),
        ("WMaxSet", create_asg_do),
        ("WMaxFto", create_ing_do),
        ("SptReas", create_inc_do),
    ]:
        ln4.add_data_object(factory(name, ln4))

    # DGEN1
    for name, factory in [
        ("NamPlt", create_lpl_do),
        ("Beh", create_ens_do),
        ("DEROpSt", create_ens_do),
    ]:
        ln5.add_data_object(factory(name, ln5))

    ld.add_logical_node(ln2)
    ld.add_logical_node(ln3)
    ld.add_logical_node(ln4)
    ld.add_logical_node(ln5)
    ld.add_logical_node(ln1)

    # DataSets
    ds_minmax = DataSet(ln2, "LD0", "DataSetMinMaxAvg", [
        DataSetEntry("LD0", "LD0/MMXU1.MinWPhs", FunctionalConstraint.mx),
        DataSetEntry("LD0", "LD0/MMXU1.MaxWPhs", FunctionalConstraint.mx),
        DataSetEntry("LD0", "LD0/MMXU1.AvWPhs", FunctionalConstraint.mx),
    ])
    ln2.add_data_set(ds_minmax)

    ds_setpoints = DataSet(ln2, "LD0", "DataSetSetpoints", [
        DataSetEntry("LD0", "LD0/DWMX1.SptReas", FunctionalConstraint.st),
        DataSetEntry("LD0", "LD0/DWMX1.WMaxFto.setVal", FunctionalConstraint.sp),
        DataSetEntry("LD0", "LD0/DWMX1.WMaxSet.setMag.f", FunctionalConstraint.sp),
        DataSetEntry("LD0", "LD0/DWMX1.WMaxSetPct.setMag.f", FunctionalConstraint.sp),
        DataSetEntry("LD0", "LD0/DWMX1.WMaxSpt", FunctionalConstraint.mx),
        DataSetEntry("LD0", "LD0/DWMX1.WMaxSptPct", FunctionalConstraint.mx),
        DataSetEntry("LD0", "LD0/DGEN1.DEROpSt", FunctionalConstraint.st),
    ])
    ln2.add_data_set(ds_setpoints)

    ds_actual = DataSet(ln2, "LD0", "DataSetActualValues", [
        DataSetEntry("LD0", "LD0/MMXU1.TotW", FunctionalConstraint.mx),
        DataSetEntry("LD0", "LD0/MMXU1.TotVAr", FunctionalConstraint.mx),
        DataSetEntry("LD0", "LD0/MMXU1.PhV.phsA", FunctionalConstraint.mx),
        DataSetEntry("LD0", "LD0/MMXU1.PhV.phsB", FunctionalConstraint.mx),
        DataSetEntry("LD0", "LD0/MMXU1.PhV.phsC", FunctionalConstraint.mx),
        DataSetEntry("LD0", "LD0/MMXU1.PPV.phsAB", FunctionalConstraint.mx),
        DataSetEntry("LD0", "LD0/MMXU1.PPV.phsBC", FunctionalConstraint.mx),
        DataSetEntry("LD0", "LD0/MMXU1.PPV.phsCA", FunctionalConstraint.mx),
        DataSetEntry("LD0", "LD0/MMXU1.A.phsA", FunctionalConstraint.mx),
        DataSetEntry("LD0", "LD0/MMXU1.A.phsB", FunctionalConstraint.mx),
        DataSetEntry("LD0", "LD0/MMXU1.A.phsC", FunctionalConstraint.mx),
    ])
    ln2.add_data_set(ds_actual)

    # BRCB
    brcb = ReportControl(
        "rcbMinMaxAvg",
        buffered=True,
        dataset_name="LD0/LLN0.DataSetMinMaxAvg",
        trg_ops=TrgOps(integrity=True).to_wire(),
        opt_flds=OptFlds(timeStamp=True, dataSet=True, bufOvfl=True, entryID=True).to_wire(),
        buffered_time="None",
        int_period=2000,
    )
    ln2.add_report_control(brcb)

    # URCB — setpoints
    urcb_sp = ReportControl(
        "rcbSetpoints",
        buffered=False,
        dataset_name="LD0/LLN0.DataSetSetpoints",
        trg_ops=TrgOps(dchg=True, integrity=True, gi=True).to_wire(),
        opt_flds=OptFlds(timeStamp=True, reasonCode=True).to_wire(),
        buffered_time=100,
        int_period=1000,
    )
    ln2.add_report_control(urcb_sp)

    # URCB — actual values
    urcb_av = ReportControl(
        "rcbActualValues",
        buffered=False,
        dataset_name="LD0/LLN0.DataSetActualValues",
        trg_ops=TrgOps(dchg=True, qchg=True, gi=True).to_wire(),
        opt_flds=OptFlds(timeStamp=True, reasonCode=True, configRef=True).to_wire(),
        buffered_time=1000,
        int_period=1000,
    )
    ln2.add_report_control(urcb_av)

    ied.add_logical_device(ld)
    return ied
