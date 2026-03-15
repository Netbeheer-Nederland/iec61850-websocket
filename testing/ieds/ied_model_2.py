from dataclasses import asdict

from ws61850.iec61850.data_model.helper import (
    create_apc_do,
    create_asg_do_custom,
    create_del_do,
    create_ens_do,
    create_lpl_do,
    create_mv_do,
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


def make_ied_model2():
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

    # For LLN0 (ln_lln0)
    # do_Mod = DataObject("Mod", 0, -1, cdc="enc", parent=ln1)
    # ln1.add_dataObject(do_Mod)
    #
    # do_NamPlt = DataObject("NamPlt", 0, -1, cdc="lpl", parent=ln1)
    # ln1.add_dataObject(do_NamPlt)
    #
    # do_Beh = DataObject("Beh", 0, -1, cdc="ens", parent=ln1)
    # ln1.add_dataObject(do_Beh)
    #
    # do_Health = DataObject("Health", 0, -1, cdc="ens", parent=ln1)
    # ln1.add_dataObject(do_Health)
    #
    # # For LPHD1 (ln2)
    # do_PhyNam = DataObject("PhyNam", 0, -1, cdc="dpl", parent=ln2)
    # ln2.add_dataObject(do_PhyNam)
    #
    # do_PhyHealth = DataObject("PhyHealth", 0, -1, cdc="ens", parent=ln2)
    # ln2.add_dataObject(do_PhyHealth)
    #
    # do_Proxy = DataObject("Proxy", 0, -1, cdc="sps", parent=ln2)
    # ln2.add_dataObject(do_Proxy)
    #
    # do_PwrUp = DataObject("PwrUp", 0, -1, cdc="ens", parent=ln2)
    # ln2.add_dataObject(do_PwrUp)

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

    ##DAs PhV
    # do_phsA = DataObject(name="phsA", parent=do_PhV, type_="cmv")
    #
    # da_cVal = DataAttribute('cVal',0,-1,DataAttributeType.structure, FunctionalConstraint.mx, 0,[], 0, do_phsA)
    # da_mag = DataAttribute('mag',0,-1,DataAttributeType.structure, FunctionalConstraint.mx, 0,[], 0, da_cVal)
    # da_f = DataAttribute('f',0,-1,DataAttributeType.float32, FunctionalConstraint.mx, 0,None, 0, da_mag)
    # da_quality = DataAttribute('q',0,-1,DataAttributeType.quality, FunctionalConstraint.mx, 0,None, 0, do_phsA)
    # da_time_stamp = DataAttribute('t',0,-1,DataAttributeType.timeStamp, FunctionalConstraint.mx, 0,None, 0, do_phsA)
    #
    # da_units = DataAttribute('units',0,-1,DataAttributeType.structure, FunctionalConstraint.cf, 0,[], 0, do_phsA)
    # da_siUnit = DataAttribute('SIUnit',0,-1,DataAttributeType.enumerated, FunctionalConstraint.cf, 0,None, 0, da_units)
    # da_multiplier = DataAttribute('multiplier',0,-1,DataAttributeType.enumerated, FunctionalConstraint.cf, 0,None, 0, da_units)
    #
    # da_units.add_dataAttribute(da_siUnit)
    # da_units.add_dataAttribute(da_multiplier)
    #
    # da_mag.add_dataAttribute(da_f)
    # da_cVal.add_dataAttribute(da_mag)
    # do_phsA.add_dataAttribute(da_quality)
    # do_phsA.add_dataAttribute(da_time_stamp)
    # do_phsA.add_dataAttribute(da_units)
    # do_phsA.add_dataAttribute(da_cVal)
    # do_PhV.add_subDataObject(do_phsA)

    ##DAs MaxWPhs

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
            "leapSecondsKown": False,
            "clockFailure": False,
            "clockNotSynchronized": False,
            "timeAccuracy": 3,  # e.g., ±1 ms, depending on definition
        },
    }
    quality = QUALITY_DEFAULT
    timestamp = TIMESTAMP_DEFAULT

    # da_mag = DataAttribute('mag',0,-1,DataAttributeType.structure, FunctionalConstraint.mx, 0,[], 0, do_MaxWPhs)
    # da_f = DataAttribute('f',0,-1,DataAttributeType.float32, FunctionalConstraint.mx, 0,12.54, 0, da_mag)
    # da_quality = DataAttribute('q',0,-1,DataAttributeType.quality, FunctionalConstraint.mx, 0, quality, 0, do_MaxWPhs)
    # da_time_stamp = DataAttribute('t',0,-1,DataAttributeType.timeStamp, FunctionalConstraint.mx, 0,timestamp, 0, do_MaxWPhs)
    #
    # da_units = DataAttribute('units',0,-1,DataAttributeType.structure, FunctionalConstraint.cf, 0,[], 0, do_MaxWPhs)
    # da_siUnit = DataAttribute('SIUnit',0,-1,DataAttributeType.enumerated, FunctionalConstraint.cf, 0,0, 0, da_units)
    # da_multiplier = DataAttribute('multiplier',0,-1,DataAttributeType.enumerated, FunctionalConstraint.cf, 0,0, 0, da_units)
    #
    # da_units.add_dataAttribute(da_siUnit)
    # da_units.add_dataAttribute(da_multiplier)
    #
    # da_mag.add_dataAttribute(da_f)
    # do_MaxWPhs.add_dataAttribute(da_mag)
    # do_MaxWPhs.add_dataAttribute(da_quality)
    # do_MaxWPhs.add_dataAttribute(da_time_stamp)
    # do_MaxWPhs.add_dataAttribute(da_units)

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

    i = 7
