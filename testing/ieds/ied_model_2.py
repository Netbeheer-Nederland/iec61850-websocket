from dataclasses import asdict

from ws61850.iec61850.data_model.helper import create_apc_do, create_asg_do_custom, create_lpl_do, create_ens_do, \
    create_mv_do, create_wye_do, create_del_do
from ws61850.iec61850.data_model.ied_model import IedModel, LogicalDevice, LogicalNode, DataObject, DataSet, \
    DataSetEntry, OptFldsRCB, ReportControl, FunctionalConstraint


def make_ied_model2():
    # Create IED Model once at startup
    ied = IedModel(name="IED2")

    # Create LD and LogicalNodes
    ld = LogicalDevice(name="LD0", ldName="LD_INST")
    ld_1 = LogicalDevice(name="LD1", ldName="LD_INST")
    ln1 = LogicalNode(name="LLN0", parent=ld)
    # ln2 = LogicalNode(name="LPHD1", parent=ld)
    ln3 = LogicalNode(name="DWMX1", parent=ld)
    ln4 = LogicalNode(name="DGEN1", parent=ld)
    ln5 = LogicalNode(name="MMXU1", parent=ld)

    # For LLN0 (ln1)
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

    # For LN = DWMX1 (ln3)
    do_NamPlt = DataObject("NamPlt", 0, -1, cdc="lpl", parent=ln3)
    ln3.add_dataObject(do_NamPlt)

    do_Beh = DataObject("Beh", 0, -1, cdc="ens", parent=ln3)
    ln3.add_dataObject(do_Beh)

    # do_WMaxSptPct = DataObject("WMaxSptPct", 0, -1, cdc="apc", parent=ln3)
    do_WMaxSptPct = create_apc_do("WMaxSptPct", parent=ln3)
    ln3.add_dataObject(do_WMaxSptPct)

    # do_WMaxSpt = DataObject("WMaxSpt", 0, -1, cdc="apc", parent=ln3)
    do_WMaxSpt = create_apc_do("WMaxSpt", parent=ln3)
    ln3.add_dataObject(do_WMaxSpt)

    # do_WMaxSetPct = DataObject("WMaxSetPct", 0, -1, cdc="asg", parent=ln3)
    do_WMaxSetPct = create_asg_do_custom("WMaxSetPct", ln3)
    ln3.add_dataObject(do_WMaxSetPct)

    # do_WMaxSet = DataObject("WMaxSet", 0, -1, cdc="asg", parent=ln3)
    do_WMaxSet = create_asg_do_custom("WMaxSet", ln3)
    ln3.add_dataObject(do_WMaxSet)

    do_WMaxFto = DataObject("WMaxFto", 0, -1, cdc="ing", parent=ln3)
    ln3.add_dataObject(do_WMaxFto)

    do_SptReas = DataObject("SptReas", 0, -1, cdc="inc", parent=ln3)
    ln3.add_dataObject(do_SptReas)

    # For LN = DGEN1 (ln4)
    # do_NamPlt = DataObject("NamPlt", 0, -1, cdc="lpl", parent=ln4)
    do_NamPlt = create_lpl_do("NamPlt", ln4)
    ln4.add_dataObject(do_NamPlt)

    # do_Beh = DataObject("Beh", 0, -1, cdc="ens", parent=ln4)
    do_Beh = create_ens_do("Beh", ln4)
    ln4.add_dataObject(do_Beh)

    # do_DEROpSt = DataObject("DEROpSt", 0, -1, cdc="ens", parent=ln4)
    do_DEROpSt = create_ens_do("DEROpSt", ln4)
    ln4.add_dataObject(do_DEROpSt)
    # For MMXU1 (ln5)
    # do_Beh = DataObject("Beh", 0, -1, type_="ens", parent=ln5)
    do_Beh = create_ens_do("Beh", ln5)
    ln5.add_dataObject(do_Beh)

    # do_TotW = DataObject("TotW", 0, -1, type_="mv", parent=ln5)
    do_TotW = create_mv_do("TotW", ln5)
    ln5.add_dataObject(do_TotW)

    # do_TotVAr = DataObject("TotVAr", 0, -1, type_="mv", parent=ln5)
    do_TotVAr = create_mv_do("TotVAr", ln5)
    ln5.add_dataObject(do_TotVAr)

    # do_PhV = DataObject("PhV", 0, -1, type_="wye", parent=ln5)
    # do_PhV = DataObject("PhV", 0, -1, type_="wye", parent=ln5)
    do_PhV = create_wye_do("PhV", ln5)
    ln5.add_dataObject(do_PhV)

    # do_PPV = DataObject("PPV", 0, -1, cdc="del", parent=ln5)
    do_PPV = create_del_do("PPV", ln5)
    ln5.add_dataObject(do_PPV)

    # do_A = DataObject("A", 0, -1, cdc="wye", parent=ln5)
    do_A = create_wye_do("A", parent=ln5)
    ln5.add_dataObject(do_A)

    # do_AvWPhs = DataObject("AvWPhs", 0, -1, type_="mv", parent=ln5)
    do_AvWPhs = create_mv_do("AvWPhs", parent=ln5)
    ln5.add_dataObject(do_AvWPhs)

    # do_MaxWPhs = DataObject("MaxWPhs", 0, -1, type_="mv", parent=ln5)
    do_MaxWPhs = create_mv_do("MaxWPhs", parent=ln5)
    ln5.add_dataObject(do_MaxWPhs)

    # do_MinWPhs = DataObject("MinWPhs", 0, -1, type_="mv", parent=ln5)
    do_MinWPhs = create_mv_do("MinWPhs", parent=ln5)
    ln5.add_dataObject(do_MinWPhs)

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

    quality = {
        # 'detailQual' omitted (OPTIONAL)
        'validity': 'good',  # must provide a value; choose from: 'good', 'invalid', 'questionable'
        'source': 'process',  # choose from: 'process', 'substituted'
        'test': False,
        'operatorBlock': False
    }
    timestamp = {
        "secondSinceEpoch": 1720458123,  # Example: some UTC time in seconds
        "fractionOfSecond": 1234567,  # Example: partial seconds (e.g., microseconds * 10)
        "timeQuality": {
            "leapSecondKnown": False,
            "clockFailure": False,
            "clockNotSynchronized": False,
            "timeAccuracy": 3  # e.g., ±1 ms, depending on definition
        }
    }

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
    ld.add_logical_node(ln1)
    # ld.add_logical_node(ln2)
    ld.add_logical_node(ln3)
    ld.add_logical_node(ln4)
    ld.add_logical_node(ln5)

    ## DataSet

    dataset_min_max_avg = DataSet(ln1, "LD0", "DataSetMinMaxAvg", 3)

    data_entry_1 = DataSetEntry("LD0", False, "LD0/MMXU1.MinWPhs", -1, None, None, FunctionalConstraint.mx)
    data_entry_2 = DataSetEntry("LD0", False, "LD0/MMXU1.MaxWPhs", -1, None, None, FunctionalConstraint.mx)
    data_entry_3 = DataSetEntry("LD0", False, "LD0/MMXU1.AvWPhs", -1, None, None, FunctionalConstraint.mx)

    dataset_min_max_avg.dataSet_addEntry(data_entry_1)
    dataset_min_max_avg.dataSet_addEntry(data_entry_2)
    dataset_min_max_avg.dataSet_addEntry(data_entry_3)

    ln1.add_dataSet(dataset_min_max_avg)

    dataset_set_setpoints = DataSet(ln1, "LD0", "DataSetSetpoints", 1)

    data_entry_1 = DataSetEntry("LD0", False, "LD0/DGEN1.DEROpSt", -1, None, None, FunctionalConstraint.st)
    data_entry_2 = DataSetEntry("LD0", False, "LD0/DWMX1.WMaxSptPct", -1, None, None, FunctionalConstraint.mx)

    dataset_set_setpoints.dataSet_addEntry(data_entry_1)
    dataset_set_setpoints.dataSet_addEntry(data_entry_2)
    # dataset_min_max_avg.dataSet_addEntry(data_entry_3)

    ln1.add_dataSet(dataset_set_setpoints)

    ##BRCB
    optFields = asdict(OptFldsRCB(False, True, True, True, False, True, False, False))
    trgOpts = {"dchg": False, "qchg": False, "dupd": False, "integrity": True, "gi": False}

    brcb = ReportControl("LD0/LLN0.rcbMinMaxAvg", ln1, "rcbMinMaxAvg", "MinMaxAvg", True,
                         "DataSetMinMaxAvg", 1, trgOpts, optFields, "None", 2, None, False)

    ln1.add_reportControl(brcb)

    # URCB
    optFields = asdict(
        OptFldsRCB(seqNum=False, timeStamp=True, dataSet=False, reasonCode=True, dataRef=False, entryID=False,
                   configRef=False, bufOvfl=False))
    # trgOpts = asdict(TrgOps(integrity=True))
    trgOpts = {"dchg": True, "qchg": False, "dupd": False, "integrity": True, "gi": True}

    urcb = ReportControl("LD0/LLN0.rcbSetpoints", ln1, "rcbSetpoints", "Setpoints", False,
                         "DataSetSetpoints", 1, trgOpts, optFields, 100, 900000, None, False)

    ln1.add_reportControl(urcb)

    # Add LD to IED
    ied.add_logicalDevice(ld)
    ied.add_logicalDevice(ld_1)

    i = 7
