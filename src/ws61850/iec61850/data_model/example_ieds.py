from ws61850.iec61850.data_model.helper import (
    create_apc_do,
    create_asg_do,
    create_asg_do_custom,
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


def build_model1():
    ied = IedModel(name="IED1")

    ld = LogicalDevice(name="LD0", ldName="LD_INST")
    lln0 = LogicalNode(name="LLN0")
    lphd1 = LogicalNode(name="LPHD1")
    dwmx1 = LogicalNode(name="DWMX1")
    dgen1 = LogicalNode(name="DGEN1")
    mmxu1 = LogicalNode(name="MMXU1")

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
        mmxu1.add_data_object(factory(name, mmxu1))

    for name, factory in [
        ("Mod", create_enc_do),
        ("NamPlt", create_lpl_do),
        ("Beh", create_ens_do),
        ("Health", create_ens_do),
    ]:
        lln0.add_data_object(factory(name, lln0))

    for name, factory in [
        ("PhyNam", create_dpl_do),
        ("PhyHealth", create_ens_do),
        ("Proxy", create_sps_do),
        ("PwrUp", create_sps_do),
    ]:
        lphd1.add_data_object(factory(name, lphd1))

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
        dwmx1.add_data_object(factory(name, dwmx1))

    for name, factory in [
        ("NamPlt", create_lpl_do),
        ("Beh", create_ens_do),
        ("DEROpSt", create_ens_do),
    ]:
        dgen1.add_data_object(factory(name, dgen1))

    ld.add_logical_node(lln0)
    ld.add_logical_node(lphd1)
    ld.add_logical_node(dwmx1)
    ld.add_logical_node(dgen1)
    ld.add_logical_node(mmxu1)

    # DataSets
    ds_minmax = DataSet(lln0, "LD0", "DataSetMinMaxAvg", [
        DataSetEntry("LD0", "LD0/MMXU1.MinWPhs", FunctionalConstraint.mx),
        DataSetEntry("LD0", "LD0/MMXU1.MaxWPhs", FunctionalConstraint.mx),
        DataSetEntry("LD0", "LD0/MMXU1.AvWPhs", FunctionalConstraint.mx),
    ])
    lln0.add_data_set(ds_minmax)

    ds_setpoints = DataSet(lln0, "LD0", "DataSetSetpoints", [
        DataSetEntry("LD0", "LD0/DWMX1.SptReas", FunctionalConstraint.st),
        DataSetEntry("LD0", "LD0/DWMX1.WMaxFto.setVal", FunctionalConstraint.sp),
        DataSetEntry("LD0", "LD0/DWMX1.WMaxSet.setMag.f", FunctionalConstraint.sp),
        DataSetEntry("LD0", "LD0/DWMX1.WMaxSetPct.setMag.f", FunctionalConstraint.sp),
        DataSetEntry("LD0", "LD0/DWMX1.WMaxSpt", FunctionalConstraint.mx),
        DataSetEntry("LD0", "LD0/DWMX1.WMaxSptPct", FunctionalConstraint.mx),
        DataSetEntry("LD0", "LD0/DGEN1.DEROpSt", FunctionalConstraint.st),
    ])
    lln0.add_data_set(ds_setpoints)

    ds_actual = DataSet(lln0, "LD0", "DataSetActualValues", [
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
    lln0.add_data_set(ds_actual)

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
    lln0.add_report_control(brcb)

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
    lln0.add_report_control(urcb_sp)

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
    lln0.add_report_control(urcb_av)

    ied.add_logical_device(ld)
    return ied


def build_model2():
    ied = IedModel(name="IED2")

    ld = LogicalDevice(name="LD0", ldName="LD_INST")
    ld_1 = LogicalDevice(name="LD1", ldName="LD_INST")
    ln_lln0 = LogicalNode(name="LLN0")
    ln_dwmx1 = LogicalNode(name="DWMX1")
    ln_dgen1 = LogicalNode(name="DGEN1")
    ln_mmxu1 = LogicalNode(name="MMXU1")

    for name, factory in [
        ("NamPlt", create_lpl_do),
        ("Beh", create_ens_do),
        ("WMaxSptPct", create_apc_do),
        ("WMaxSpt", create_apc_do),
        ("WMaxSetPct", create_asg_do_custom),
        ("WMaxSet", create_asg_do_custom),
        ("WMaxFto", create_ing_do),
        ("SptReas", create_inc_do),
    ]:
        ln_dwmx1.add_data_object(factory(name, ln_dwmx1))

    for name, factory in [
        ("NamPlt", create_lpl_do),
        ("Beh", create_ens_do),
        ("DEROpSt", create_ens_do),
    ]:
        ln_dgen1.add_data_object(factory(name, ln_dgen1))

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
        ln_mmxu1.add_data_object(factory(name, ln_mmxu1))

    ld.add_logical_node(ln_lln0)
    ld.add_logical_node(ln_dwmx1)
    ld.add_logical_node(ln_dgen1)
    ld.add_logical_node(ln_mmxu1)

    # DataSets
    ds_minmax = DataSet(ln_lln0, "LD0", "DataSetMinMaxAvg", [
        DataSetEntry("LD0", "LD0/MMXU1.MinWPhs", FunctionalConstraint.mx),
        DataSetEntry("LD0", "LD0/MMXU1.MaxWPhs", FunctionalConstraint.mx),
        DataSetEntry("LD0", "LD0/MMXU1.AvWPhs", FunctionalConstraint.mx),
    ])
    ln_lln0.add_data_set(ds_minmax)

    ds_setpoints = DataSet(ln_lln0, "LD0", "DataSetSetpoints", [
        DataSetEntry("LD0", "LD0/DGEN1.DEROpSt", FunctionalConstraint.st),
        DataSetEntry("LD0", "LD0/DWMX1.WMaxSptPct", FunctionalConstraint.mx),
    ])
    ln_lln0.add_data_set(ds_setpoints)

    # BRCB
    brcb = ReportControl(
        "rcbMinMaxAvg",
        buffered=True,
        dataset_name="LD0/LLN0.DataSetMinMaxAvg",
        trg_ops=TrgOps(integrity=True).to_wire(),
        opt_flds=OptFlds(timeStamp=True, dataSet=True, bufOvfl=True, entryID=True).to_wire(),
        buffered_time="None",
        int_period=2,
    )
    ln_lln0.add_report_control(brcb)

    # URCB
    urcb = ReportControl(
        "rcbSetpoints",
        buffered=False,
        dataset_name="LD0/LLN0.DataSetSetpoints",
        trg_ops=TrgOps(dchg=True, integrity=True, gi=True).to_wire(),
        opt_flds=OptFlds(timeStamp=True, reasonCode=True).to_wire(),
        buffered_time=100,
        int_period=900000,
    )
    ln_lln0.add_report_control(urcb)

    ied.add_logical_device(ld)
    ied.add_logical_device(ld_1)
    return ied
