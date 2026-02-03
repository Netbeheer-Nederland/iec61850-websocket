import json
from dataclasses import asdict

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
    DataObject,
    DataSet,
    DataSetEntry,
    FunctionalConstraint,
    IedModel,
    LogicalDevice,
    LogicalNode,
    OptFldsRCB,
    ReportControl,
)


def build_model1():
    # Create IED Model once at startup
    ied = IedModel(name="IED1")

    # Create LD and LogicalNodes
    ld = LogicalDevice(name="LD0", ldName="LD_INST")
    lln0 = LogicalNode(name="LLN0", parent=ld)
    lphd1 = LogicalNode(name="LPHD1", parent=ld)
    dwmx1 = LogicalNode(name="DWMX1", parent=ld)
    dgen1 = LogicalNode(name="DGEN1", parent=ld)
    mmxu1 = LogicalNode(name="MMXU1", parent=ld)

    def add_do(parent_ln, factory, name):
        parent_ln.add_dataObject(factory(name, parent=parent_ln))

    def add_data_objects(parent_ln, definitions):
        for name, factory in definitions:
            add_do(parent_ln, factory, name)

    def add_dataset(parent_ln, ld_name, dataset_name, dataset_index, entries):
        dataset = DataSet(parent_ln, ld_name, dataset_name, dataset_index)
        for path, constraint in entries:
            dataset.dataSet_addEntry(DataSetEntry(ld_name, False, path, -1, None, None, constraint))
        parent_ln.add_dataSet(dataset)

    # For MMXU1
    add_do(mmxu1, create_ens_do, "Beh")
    add_data_objects(
        mmxu1,
        [
            ("TotW", create_mv_do),
            ("TotVAr", create_mv_do),
            ("PhV", create_wye_do),
            ("PPV", create_del_do),
            ("A", create_wye_do),
            ("AvWPhs", create_mv_do),
            ("MaxWPhs", create_mv_do),
            ("MinWPhs", create_mv_do),
        ],
    )

    # For LLN0
    add_data_objects(
        lln0,
        [
            ("Mod", create_enc_do),
            ("NamPlt", create_lpl_do),
            ("Beh", create_ens_do),
            ("Health", create_ens_do),
        ],
    )

    # For LPHD1
    add_data_objects(
        lphd1,
        [
            ("PhyNam", create_dpl_do),
            ("PhyHealth", create_ens_do),
            ("Proxy", create_sps_do),
            ("PwrUp", create_sps_do),
        ],
    )

    # For DWMX1
    add_data_objects(
        dwmx1,
        [
            ("NamPlt", create_lpl_do),
            ("Beh", create_ens_do),
            ("WMaxSptPct", create_apc_do),
            ("WMaxSpt", create_apc_do),
            ("WMaxSetPct", create_asg_do),
            ("WMaxSet", create_asg_do),
            ("WMaxFto", create_ing_do),
            ("SptReas", create_inc_do),
        ],
    )

    # For DGEN1
    add_data_objects(
        dgen1,
        [
            ("NamPlt", create_lpl_do),
            ("Beh", create_ens_do),
            ("DEROpSt", create_ens_do),
        ],
    )

    quality = {
        # 'detailQual' omitted (OPTIONAL)
        "validity": "good",  # must provide a value; choose from: 'good', 'invalid', 'questionable'
        "source": "process",  # choose from: 'process', 'substituted'
        "test": False,
        "operatorBlock": False,
    }

    timestamp = {
        "secondSinceEpoch": 1720458123,  # Example: some UTC time in seconds
        "fractionOfSecond": 1234567,  # Example: partial seconds (e.g., microseconds * 10)
        "timeQuality": {
            "leapSecondKnown": False,
            "clockFailure": False,
            "clockNotSynchronized": False,
            "timeAccuracy": 3,  # e.g., ±1 ms, depending on definition
        },
    }

    # Add LNs to LD
    ld.add_logical_node(lln0)
    ld.add_logical_node(lphd1)
    ld.add_logical_node(dwmx1)
    ld.add_logical_node(dgen1)
    ld.add_logical_node(mmxu1)

    ## DataSet

    add_dataset(
        lln0,
        "LD0",
        "DataSetMinMaxAvg",
        3,
        [
            ("LD0/MMXU1.MinWPhs", FunctionalConstraint.mx),
            ("LD0/MMXU1.MaxWPhs", FunctionalConstraint.mx),
            ("LD0/MMXU1.AvWPhs", FunctionalConstraint.mx),
        ],
    )

    add_dataset(
        lln0,
        "LD0",
        "DataSetSetpoints",
        1,
        [
            ("LD0/DWMX1.SptReas", FunctionalConstraint.st),
            ("LD0/DWMX1.WMaxFto.setVal", FunctionalConstraint.sp),
            ("LD0/DWMX1.WMaxSet.setMag.f", FunctionalConstraint.sp),
            ("LD0/DWMX1.WMaxSetPct.setMag.f", FunctionalConstraint.sp),
            ("LD0/DWMX1.WMaxSpt", FunctionalConstraint.mx),
            ("LD0/DWMX1.WMaxSptPct", FunctionalConstraint.mx),
            ("LD0/DGEN1.DEROpSt", FunctionalConstraint.st),
        ],
    )

    add_dataset(
        lln0,
        "LD0",
        "DataSetActualValues",
        1,
        [
            ("LD0/MMXU1.TotW", FunctionalConstraint.mx),
            ("LD0/MMXU1.TotVAr", FunctionalConstraint.mx),
            ("LD0/MMXU1.PhV.phsA", FunctionalConstraint.mx),
            ("LD0/MMXU1.PhV.phsB", FunctionalConstraint.mx),
            ("LD0/MMXU1.PhV.phsC", FunctionalConstraint.mx),
            ("LD0/MMXU1.PPV.phsAB", FunctionalConstraint.mx),
            ("LD0/MMXU1.PPV.phsBC", FunctionalConstraint.mx),
            ("LD0/MMXU1.PPV.phsCA", FunctionalConstraint.mx),
            ("LD0/MMXU1.A.phsA", FunctionalConstraint.mx),
            ("LD0/MMXU1.A.phsB", FunctionalConstraint.mx),
            ("LD0/MMXU1.A.phsC", FunctionalConstraint.mx),
        ],
    )

    # TODO: is RptEna needed in ReportControl class?
    ##BRCB
    optFields = asdict(OptFldsRCB(False, True, True, True, False, True, False, False))
    # trgOpts = asdict(TrgOps(integrity=True))
    trgOpts = {
        "dchg": False,
        "qchg": False,
        "dupd": False,
        "integrity": True,
        "gi": False,
    }

    brcb = ReportControl(
        "LD0/LLN0.rcbMinMaxAvg",
        lln0,
        "rcbMinMaxAvg",
        "MinMaxAvg",
        True,
        "LD0/LLN0.DataSetMinMaxAvg",
        1,
        trgOpts,
        optFields,
        "None",
        2000,
        None,
        False,
    )

    lln0.add_reportControl(brcb)

    # URCB
    optFields = asdict(
        OptFldsRCB(
            seqNum=False,
            timeStamp=True,
            dataSet=False,
            reasonCode=True,
            dataRef=False,
            entryID=False,
            configRef=False,
            bufOvfl=False,
        )
    )
    # trgOpts = asdict(TrgOps(integrity=True))
    trgOpts = {
        "dchg": True,
        "qchg": False,
        "dupd": False,
        "integrity": True,
        "gi": True,
    }

    urcb = ReportControl(
        "LD0/LLN0.rcbSetpoints",
        lln0,
        "rcbSetpoints",
        "Setpoints",
        False,
        "LD0/LLN0.DataSetSetpoints",
        1,
        trgOpts,
        optFields,
        100,
        1000,
        None,
        False,
    )

    lln0.add_reportControl(urcb)

    # URCB
    optFields = asdict(
        OptFldsRCB(
            seqNum=False,
            timeStamp=True,
            dataSet=False,
            reasonCode=True,
            dataRef=False,
            entryID=False,
            configRef=True,
            bufOvfl=False,
        )
    )
    # trgOpts = asdict(TrgOps(integrity=True))
    trgOpts = {
        "dchg": True,
        "qchg": True,
        "dupd": False,
        "integrity": False,
        "gi": True,
    }

    urcb = ReportControl(
        "LD0/LLN0.rcbActualValues",
        lln0,
        "rcbActualValues",
        "DataSetActualValues",
        False,
        "LD0/LLN0.DataSetActualValues",
        1,
        trgOpts,
        optFields,
        1000,
        1000,
        None,
        False,
    )

    lln0.add_reportControl(urcb)

    # Add LD to IED
    ied.add_logicalDevice(ld)

    return ied


def build_model2():
    # Create IED Model once at startup
    ied = IedModel(name="IED2")

    # Create LD and LogicalNodes
    ld = LogicalDevice(name="LD0", ldName="LD_INST")
    ld_1 = LogicalDevice(name="LD1", ldName="LD_INST")
    ln_lln0 = LogicalNode(name="LLN0", parent=ld)
    # ln2 = LogicalNode(name="LPHD1", parent=ld)
    ln_dwmx1 = LogicalNode(name="DWMX1", parent=ld)
    ln_dgen1 = LogicalNode(name="DGEN1", parent=ld)
    ln_mmxu1 = LogicalNode(name="MMXU1", parent=ld)

    def add_do(parent_ln, name=None, factory=None, data_object=None):
        if data_object is None:
            data_object = factory(name, parent=parent_ln)
        parent_ln.add_dataObject(data_object)
        return data_object

    # For LN = DWMX1 (ln_dwmx1)
    add_do(ln_dwmx1, "NamPlt", create_lpl_do)
    add_do(ln_dwmx1, "Beh", create_ens_do)
    add_do(ln_dwmx1, "WMaxSptPct", create_apc_do)
    add_do(ln_dwmx1, "WMaxSpt", create_apc_do)
    add_do(ln_dwmx1, "WMaxSetPct", lambda n, parent: create_asg_do_custom(n, parent))
    add_do(ln_dwmx1, "WMaxSet", lambda n, parent: create_asg_do_custom(n, parent))
    add_do(ln_dwmx1, data_object=DataObject("WMaxFto", 0, -1, cdc="ing", parent=ln_dwmx1))
    add_do(ln_dwmx1, data_object=DataObject("SptReas", 0, -1, cdc="inc", parent=ln_dwmx1))

    # For LN = DGEN1 (ln_dgen1)
    add_do(ln_dgen1, "NamPlt", create_lpl_do)
    add_do(ln_dgen1, "Beh", create_ens_do)
    add_do(ln_dgen1, "DEROpSt", create_ens_do)

    # For MMXU1 (ln_mmxu1)
    add_do(ln_mmxu1, "Beh", create_ens_do)
    add_do(ln_mmxu1, "TotW", create_mv_do)
    add_do(ln_mmxu1, "TotVAr", create_mv_do)
    add_do(ln_mmxu1, "PhV", create_wye_do)
    add_do(ln_mmxu1, "PPV", create_del_do)
    add_do(ln_mmxu1, "A", create_wye_do)
    add_do(ln_mmxu1, "AvWPhs", create_mv_do)
    add_do(ln_mmxu1, "MaxWPhs", create_mv_do)
    add_do(ln_mmxu1, "MinWPhs", create_mv_do)

    QUALITY_DEFAULT = {
        # 'detailQual' omitted (OPTIONAL)
        "validity": "good",  # must provide a value; choose from: 'good', 'invalid', 'questionable'
        "source": "process",  # choose from: 'process', 'substituted'
        "test": False,
        "operatorBlock": False,
    }
    TIMESTAMP_DEFAULT = {
        "secondSinceEpoch": 1720458123,  # Example: some UTC time in seconds
        "fractionOfSecond": 1234567,  # Example: partial seconds (e.g., microseconds * 10)
        "timeQuality": {
            "leapSecondKnown": False,
            "clockFailure": False,
            "clockNotSynchronized": False,
            "timeAccuracy": 3,  # e.g., ±1 ms, depending on definition
        },
    }
    quality = QUALITY_DEFAULT
    timestamp = TIMESTAMP_DEFAULT

    # Add LNs to LD
    ld.add_logical_node(ln_lln0)
    # ld.add_logical_node(ln2)
    ld.add_logical_node(ln_dwmx1)
    ld.add_logical_node(ln_dgen1)
    ld.add_logical_node(ln_mmxu1)

    ## DataSet
    dataset_min_max_avg = DataSet(ln_lln0, "LD0", "DataSetMinMaxAvg", 3)

    data_entry_1 = DataSetEntry("LD0", False, "LD0/MMXU1.MinWPhs", -1, None, None, FunctionalConstraint.mx)
    data_entry_2 = DataSetEntry("LD0", False, "LD0/MMXU1.MaxWPhs", -1, None, None, FunctionalConstraint.mx)
    data_entry_3 = DataSetEntry("LD0", False, "LD0/MMXU1.AvWPhs", -1, None, None, FunctionalConstraint.mx)

    dataset_min_max_avg.dataSet_addEntry(data_entry_1)
    dataset_min_max_avg.dataSet_addEntry(data_entry_2)
    dataset_min_max_avg.dataSet_addEntry(data_entry_3)

    ln_lln0.add_dataSet(dataset_min_max_avg)

    dataset_set_setpoints = DataSet(ln_lln0, "LD0", "DataSetSetpoints", 1)

    data_entry_1 = DataSetEntry("LD0", False, "LD0/DGEN1.DEROpSt", -1, None, None, FunctionalConstraint.st)
    data_entry_2 = DataSetEntry("LD0", False, "LD0/DWMX1.WMaxSptPct", -1, None, None, FunctionalConstraint.mx)

    dataset_set_setpoints.dataSet_addEntry(data_entry_1)
    dataset_set_setpoints.dataSet_addEntry(data_entry_2)
    # dataset_min_max_avg.dataSet_addEntry(data_entry_3)

    ln_lln0.add_dataSet(dataset_set_setpoints)

    ##BRCB
    optFields = asdict(OptFldsRCB(False, True, True, True, False, True, False, False))
    trgOpts = {
        "dchg": False,
        "qchg": False,
        "dupd": False,
        "integrity": True,
        "gi": False,
    }

    brcb = ReportControl(
        "LD0/LLN0.rcbMinMaxAvg",
        ln_lln0,
        "rcbMinMaxAvg",
        "MinMaxAvg",
        True,
        "DataSetMinMaxAvg",
        1,
        trgOpts,
        optFields,
        "None",
        2,
        None,
        False,
    )

    ln_lln0.add_reportControl(brcb)

    # URCB
    optFields = asdict(
        OptFldsRCB(
            seqNum=False,
            timeStamp=True,
            dataSet=False,
            reasonCode=True,
            dataRef=False,
            entryID=False,
            configRef=False,
            bufOvfl=False,
        )
    )
    # trgOpts = asdict(TrgOps(integrity=True))
    trgOpts = {
        "dchg": True,
        "qchg": False,
        "dupd": False,
        "integrity": True,
        "gi": True,
    }

    urcb = ReportControl(
        "LD0/LLN0.rcbSetpoints",
        ln_lln0,
        "rcbSetpoints",
        "Setpoints",
        False,
        "DataSetSetpoints",
        1,
        trgOpts,
        optFields,
        100,
        900000,
        None,
        False,
    )

    ln_lln0.add_reportControl(urcb)

    # Add LD to IED
    ied.add_logicalDevice(ld)
    ied.add_logicalDevice(ld_1)

    return ied
