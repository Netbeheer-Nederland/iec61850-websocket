<?xml version="1.0" encoding="UTF-8"?>
<SCL xmlns="http://www.iec.ch/61850/2003/SCL" xmlns:sxy="http://www.iec.ch/61850/2003/SCLcoordinates" revision="B" version="2007" xmlns:compas="https://www.lfenergy.org/compas/extension/v1">
  <Private type="compas_scl">
    <compas:Labels />
  </Private>
  <Header id="DER" nameStructure="IEDName" revision="R000" toolID="" version="RTI_V1.0" />
  <Communication>
    <SubNetwork name="CUS_DSO" type="8-MMS" Name="CUS_DSO">
      <ConnectedAP apName="AP1" iedName="IED_2">
        <Address>
          <P type="IP">10.10.1.1</P>
          <P type="IP-SUBNET">255.255.255.0</P>
          <P type="IP-GATEWAY">10.10.0.1</P>
          <P type="OSI-PSEL">00000001</P>
          <P type="OSI-SSEL">0001</P>
          <P type="OSI-TSEL">0001</P>
        </Address>
      </ConnectedAP>
    </SubNetwork>
  </Communication>
  <IED configVersion="RTI_V1.0.0" manufacturer="NBNL" type="ied" name="IED_2" originalSclVersion="2007" originalSclRevision="B">
    <Services nameLength="64">
      <DynAssociation max="1" />
      <GetDirectory />
      <GetDataObjectDefinition />
      <DataObjectDirectory />
      <GetDataSetValue />
      <DataSetDirectory />
      <ConfDataSet max="3" maxAttributes="50" modify="true" />
      <ReadWrite />
      <ConfReportControl max="16" bufConf="true" bufMode="both" />
      <GetCBValues />
      <ReportSettings cbName="Conf" datSet="Conf" bufTime="Dyn" intgPd="Dyn" optFields="Dyn" resvTms="true" rptID="Dyn" trgOps="Dyn" />
      <ConfLNs fixLnInst="false" fixPrefix="false" />
      <ClientServices>
        <TimeSyncProt sntp="true" />
      </ClientServices>
      <ConfLdName />
    </Services>
    <AccessPoint name="AP1">
      <Server>
        <Authentication none="true" />
        <LDevice inst="LD0" ldName="RTIserver1_0_0">
          <LN0 lnType="lln0_7_4_B2007" inst="" lnClass="LLN0">
            <DataSet name="DataSetSetpoints">
              <FCDA ldInst="LD0" prefix="" lnClass="DWMX" lnInst="1" doName="SptReas" fc="ST" />
              <FCDA ldInst="LD0" prefix="" lnClass="DWMX" lnInst="1" doName="WMaxFto" daName="setVal" fc="SP" />
              <FCDA ldInst="LD0" prefix="" lnClass="DWMX" lnInst="1" doName="WMaxSet" daName="setMag.f" fc="SP" />
              <FCDA ldInst="LD0" prefix="" lnClass="DWMX" lnInst="1" doName="WMaxSetPct" daName="setMag.f" fc="SP" />
              <FCDA ldInst="LD0" prefix="" lnClass="DWMX" lnInst="1" doName="WMaxSpt" fc="MX" />
              <FCDA ldInst="LD0" prefix="" lnClass="DWMX" lnInst="1" doName="WMaxSptPct" fc="MX" />
              <FCDA ldInst="LD0" prefix="" lnClass="DGEN" lnInst="1" doName="DEROpSt" fc="ST" />
            </DataSet>
            <DataSet name="DataSetActualValues">
              <FCDA ldInst="LD0" prefix="" lnClass="MMXU" lnInst="1" doName="TotW" fc="MX" />
              <FCDA ldInst="LD0" prefix="" lnClass="MMXU" lnInst="1" doName="TotVAr" fc="MX" />
              <FCDA ldInst="LD0" prefix="" lnClass="MMXU" lnInst="1" doName="PhV.phsA" fc="MX" />
              <FCDA ldInst="LD0" prefix="" lnClass="MMXU" lnInst="1" doName="PhV.phsB" fc="MX" />
              <FCDA ldInst="LD0" prefix="" lnClass="MMXU" lnInst="1" doName="PhV.phsC" fc="MX" />
              <FCDA ldInst="LD0" prefix="" lnClass="MMXU" lnInst="1" doName="PPV.phsAB" fc="MX" />
              <FCDA ldInst="LD0" prefix="" lnClass="MMXU" lnInst="1" doName="PPV.phsBC" fc="MX" />
              <FCDA ldInst="LD0" prefix="" lnClass="MMXU" lnInst="1" doName="PPV.phsCA" fc="MX" />
              <FCDA ldInst="LD0" prefix="" lnClass="MMXU" lnInst="1" doName="A.phsA" fc="MX" />
              <FCDA ldInst="LD0" prefix="" lnClass="MMXU" lnInst="1" doName="A.phsB" fc="MX" />
              <FCDA ldInst="LD0" prefix="" lnClass="MMXU" lnInst="1" doName="A.phsC" fc="MX" />
            </DataSet>
            <DataSet name="DataSetMinMaxAvg" desc="MinMaxAvg">
              <FCDA ldInst="LD0" prefix="" lnClass="MMXU" lnInst="1" doName="MinWPhs" fc="MX" />
              <FCDA ldInst="LD0" prefix="" lnClass="MMXU" lnInst="1" doName="MaxWPhs" fc="MX" />
              <FCDA ldInst="LD0" prefix="" lnClass="MMXU" lnInst="1" doName="AvWPhs" fc="MX" />
            </DataSet>
            <ReportControl name="rcbSetpoints" buffered="false" rptID="Setpoints" indexed="false" bufTime="100" confRev="1" datSet="DataSetSetpoints">
              <TrgOps dchg="true" qchg="false" dupd="false" period="false" gi="true" />
              <OptFields seqNum="false" timeStamp="true" dataSet="false" reasonCode="true" dataRef="false" entryID="false" configRef="true" bufOvfl="false" />
              <RptEnabled max="1" />
            </ReportControl>
            <ReportControl name="rcbActualValues" buffered="false" rptID="ActualValues" indexed="false" bufTime="1000" intgPd="1000" confRev="1" datSet="DataSetActualValues">
              <TrgOps dchg="true" qchg="true" dupd="false" period="false" gi="true" />
              <OptFields seqNum="false" timeStamp="true" dataSet="false" reasonCode="true" dataRef="false" entryID="false" configRef="true" bufOvfl="false" />
              <RptEnabled max="1" />
            </ReportControl>
            <ReportControl name="rcbMinMaxAvg" buffered="true" rptID="MinMaxAvg" indexed="false" intgPd="900000" confRev="1" datSet="DataSetMinMaxAvg">
              <TrgOps dchg="false" qchg="false" dupd="false" period="true" gi="false" />
              <OptFields seqNum="false" timeStamp="true" dataSet="false" reasonCode="false" dataRef="false" entryID="true" configRef="false" bufOvfl="true" />
              <RptEnabled max="1" />
            </ReportControl>
          </LN0>
          <LN lnType="lphd_7_4_B2007" inst="1" lnClass="LPHD" />
          <LN lnType="dwmx_IEC_61850-7-420" inst="1" lnClass="DWMX">
            <DOI name="WMaxFto">
              <SDI name="units">
                <DAI name="SIUnit">
                  <Val>s</Val>
                </DAI>
              </SDI>
            </DOI>
            <DOI name="WMaxSet">
              <SDI name="units">
                <DAI name="SIUnit">
                  <Val>W</Val>
                </DAI>
                <DAI name="multiplier">
                  <Val>M</Val>
                </DAI>
              </SDI>
            </DOI>
            <DOI name="WMaxSpt">
              <SDI name="units">
                <DAI name="SIUnit">
                  <Val>W</Val>
                </DAI>
                <DAI name="multiplier">
                  <Val>M</Val>
                </DAI>
              </SDI>
            </DOI>
          </LN>
          <LN lnType="dgen_7_420_B2007" inst="1" lnClass="DGEN" />
          <LN lnType="mmxu_7_4_B2007" inst="1" lnClass="MMXU">
            <DOI name="PPV">
              <SDI name="phsAB">
                <SDI name="units">
                  <DAI name="multiplier">
                    <Val>k</Val>
                  </DAI>
                  <DAI name="SIUnit">
                    <Val>V</Val>
                  </DAI>
                </SDI>
              </SDI>
              <SDI name="phsBC">
                <SDI name="units">
                  <DAI name="SIUnit">
                    <Val>V</Val>
                  </DAI>
                  <DAI name="multiplier">
                    <Val>k</Val>
                  </DAI>
                </SDI>
              </SDI>
              <SDI name="phsCA">
                <SDI name="units">
                  <DAI name="multiplier">
                    <Val>k</Val>
                  </DAI>
                  <DAI name="SIUnit">
                    <Val>V</Val>
                  </DAI>
                </SDI>
              </SDI>
            </DOI>
            <DOI name="TotW">
              <SDI name="units">
                <DAI name="SIUnit">
                  <Val>W</Val>
                </DAI>
                <DAI name="multiplier">
                  <Val>M</Val>
                </DAI>
              </SDI>
            </DOI>
            <DOI name="TotVAr">
              <SDI name="units">
                <DAI name="SIUnit">
                  <Val>VAr</Val>
                </DAI>
                <DAI name="multiplier">
                  <Val>M</Val>
                </DAI>
              </SDI>
            </DOI>
            <DOI name="PhV">
              <SDI name="phsA">
                <SDI name="units">
                  <DAI name="SIUnit">
                    <Val>V</Val>
                  </DAI>
                  <DAI name="multiplier">
                    <Val>k</Val>
                  </DAI>
                </SDI>
              </SDI>
              <SDI name="phsB">
                <SDI name="units">
                  <DAI name="SIUnit">
                    <Val>V</Val>
                  </DAI>
                  <DAI name="multiplier">
                    <Val>k</Val>
                  </DAI>
                </SDI>
              </SDI>
              <SDI name="phsC">
                <SDI name="units">
                  <DAI name="SIUnit">
                    <Val>V</Val>
                  </DAI>
                  <DAI name="multiplier">
                    <Val>k</Val>
                  </DAI>
                </SDI>
              </SDI>
            </DOI>
            <DOI name="A">
              <SDI name="phsA">
                <SDI name="units">
                  <DAI name="SIUnit">
                    <Val>A</Val>
                  </DAI>
                </SDI>
              </SDI>
              <SDI name="phsB">
                <SDI name="units">
                  <DAI name="SIUnit">
                    <Val>A</Val>
                  </DAI>
                </SDI>
              </SDI>
              <SDI name="phsC">
                <SDI name="units">
                  <DAI name="SIUnit">
                    <Val>A</Val>
                  </DAI>
                </SDI>
              </SDI>
            </DOI>
            <DOI name="AvWPhs">
              <SDI name="units">
                <DAI name="SIUnit">
                  <Val>W</Val>
                </DAI>
                <DAI name="multiplier">
                  <Val>M</Val>
                </DAI>
              </SDI>
            </DOI>
            <DOI name="MaxWPhs">
              <SDI name="units">
                <DAI name="SIUnit">
                  <Val>W</Val>
                </DAI>
                <DAI name="multiplier">
                  <Val>M</Val>
                </DAI>
              </SDI>
            </DOI>
            <DOI name="MinWPhs">
              <SDI name="units">
                <DAI name="SIUnit">
                  <Val>W</Val>
                </DAI>
                <DAI name="multiplier">
                  <Val>M</Val>
                </DAI>
              </SDI>
            </DOI>
          </LN>
        </LDevice>
      </Server>
    </AccessPoint>
  </IED>
  <DataTypeTemplates>
    <LNodeType id="lphd_7_4_B2007" lnClass="LPHD">
      <DO desc="IEC61850_7_4.LNGroupL::LPHD.PhyNam.desc" name="PhyNam" type="DPL" transient="false" />
      <DO desc="IEC61850_7_4.LNGroupL::LPHD.PhyHealth.desc" name="PhyHealth" type="ens_HealthKind" transient="false" />
      <DO desc="IEC61850_7_4.LNGroupL::LPHD.Proxy.desc" name="Proxy" type="SPS" transient="false" />
      <DO desc="IEC61850_7_4.LNGroupL::LPHD.PwrUp.desc" name="PwrUp" type="SPS" transient="true" />
    </LNodeType>
    <LNodeType id="mmxu_7_4_B2007" lnClass="MMXU">
      <DO desc="IEC61850_7_4.AbstractLNsCommon::DomainLN.Beh.desc" name="Beh" type="ens_BehaviourModeKind" transient="false" />
      <DO desc="IEC61850_7_4.LNGroupM::MMXU.TotW.desc" name="TotW" type="MV" transient="false" />
      <DO desc="IEC61850_7_4.LNGroupM::MMXU.TotVAr.desc" name="TotVAr" type="MV" transient="false" />
      <DO desc="IEC61850_7_4.LNGroupM::MMXU.PhV.desc" name="PhV" type="WYE" transient="false" />
      <DO desc="IEC61850_7_4.LNGroupM::MMXU.PhV.desc" name="PPV" type="DEL" transient="false" />
      <DO desc="IEC61850_7_4.LNGroupM::MMXU.A.desc" name="A" type="WYE" transient="false" />
      <DO desc="IEC61850_7_4.LNGroupM::MMXU.AvWPhs.desc" name="AvWPhs" type="MV" transient="false" />
      <DO desc="IEC61850_7_4.LNGroupM::MMXU.MaxWPhs.desc" name="MaxWPhs" type="MV" transient="false" />
      <DO desc="IEC61850_7_4.LNGroupM::MMXU.MinWPhs.desc" name="MinWPhs" type="MV" transient="false" />
    </LNodeType>
    <LNodeType desc="DER unit generator" id="dgen_7_420_B2007" lnClass="DGEN">
      <DO desc="IEC61850_7_4.AbstractLNsCommon::DomainLN.NamPlt.desc" name="NamPlt" type="LPL_420" transient="false" />
      <DO desc="IEC61850_7_4.AbstractLNsCommon::DomainLN.Beh.desc" name="Beh" type="ens_BehaviourModeKind" transient="false" />
      <DO desc="IEC61850_7_420.DERGeneratorLNs::DGEN.DEROpSt.desc" name="DEROpSt" type="DERStateKind_ENS" transient="false" />
    </LNodeType>
    <LNodeType id="lln0_7_4_B2007" lnClass="LLN0">
      <DO desc="IEC61850_7_4.AbstractLNsCommon::DomainLN.Mod.desc" name="Mod" type="enc_BehaviourModeKind" transient="false" />
      <DO desc="IEC61850_7_4.LNGroupL::LLN0.NamPlt.desc" name="NamPlt" type="LPL" transient="false" />
      <DO desc="IEC61850_7_4.LNGroupL::LLN0.Beh.desc" name="Beh" type="ens_BehaviourModeKind" transient="false" />
      <DO desc="IEC61850_7_4.LNGroupL::LLN0.Health.desc" name="Health" type="ens_HealthKind" transient="false" />
    </LNodeType>
    <LNodeType id="dwmx_IEC_61850-7-420" lnClass="DWMX">
      <DO desc="IEC61850_7_4.AbstractLNsCommon::DomainLN.NamPlt.desc" name="NamPlt" type="LPL_420" transient="false" />
      <DO desc="IEC61850_7_4.LNGroupL::LLN0.Beh.desc" name="Beh" type="ens_BehaviourModeKind" transient="false" />
      <DO desc="IEC61850_7_420.ActivePowerLNs::DWMX.WMaxSptPct.desc" name="WMaxSptPct" type="APC" transient="false" />
      <DO desc="IEC61850_7_420.ActivePowerLNs::DWMX.WMaxSpt.desc" name="WMaxSpt" type="APC" transient="false" />
      <DO desc="IEC61850_7_420.ActivePowerLNs::DWMX.WMaxSetPct.desc" name="WMaxSetPct" type="ASG" transient="false" />
      <DO desc="IEC61850_7_420.ActivePowerLNs::DWMX.WMaxSet.desc" name="WMaxSet" type="ASG" transient="false" />
      <DO desc="IEC61850_7_420.ActivePowerLNs::DWMX.WMaxFto.desc" name="WMaxFto" type="ING" transient="false" />
      <DO desc="Setpoint reason" name="SptReas" type="INC" transient="false" />
      <DO name="DERAvail" type="DERAvail" />
    </LNodeType>
    <DOType id="ING" cdc="ING">
      <DA bType="INT32" name="setVal" dchg="false" dupd="false" fc="SP" qchg="false" />
      <DA bType="Struct" name="units" type="Unit" dchg="false" dupd="false" fc="CF" qchg="false" />
      <DA bType="VisString255" name="dataNs" dchg="false" dupd="false" fc="EX" qchg="false" />
    </DOType>
    <DOType id="ASG" cdc="ASG">
      <DA bType="Struct" type="AnalogueValue" name="setMag" dchg="false" dupd="false" fc="SP" qchg="false" />
      <DA bType="Struct" name="units" type="Unit" dchg="false" dupd="false" fc="CF" qchg="false" />
      <DA bType="VisString255" name="dataNs" dchg="false" dupd="false" fc="EX" qchg="false" />
    </DOType>
    <DOType id="DERStateKind_ENS" cdc="ENS">
      <DA bType="Enum" name="stVal" type="DERStateKind" dchg="false" dupd="false" fc="ST" qchg="false" />
      <DA bType="Quality" name="q" dchg="false" dupd="false" fc="ST" qchg="false" />
      <DA bType="Timestamp" name="t" dchg="false" dupd="false" fc="ST" qchg="false" />
    </DOType>
    <DOType id="ens_HealthKind" cdc="ENS">
      <DA bType="Enum" name="stVal" type="HealthKind" dchg="false" dupd="false" fc="ST" qchg="false" />
      <DA bType="Quality" name="q" dchg="false" dupd="false" fc="ST" qchg="false" />
      <DA bType="Timestamp" name="t" dchg="false" dupd="false" fc="ST" qchg="false" />
    </DOType>
    <DOType id="DPL" cdc="DPL">
      <DA bType="VisString255" name="vendor" dchg="false" dupd="false" fc="DC" qchg="false" />
      <DA bType="VisString255" name="hwRev" dchg="false" dupd="false" fc="DC" qchg="false" />
      <DA bType="VisString255" name="swRev" dchg="false" dupd="false" fc="DC" qchg="false" />
      <DA bType="VisString255" name="serNum" dchg="false" dupd="false" fc="DC" qchg="false" />
      <DA bType="VisString255" name="model" dchg="false" dupd="false" fc="DC" qchg="false" />
      <DA bType="VisString255" name="location" dchg="false" dupd="false" fc="DC" qchg="false" />
    </DOType>
    <DOType id="SPS" cdc="SPS">
      <DA bType="BOOLEAN" name="stVal" dchg="false" dupd="false" fc="ST" qchg="false" />
      <DA bType="Quality" name="q" dchg="false" dupd="false" fc="ST" qchg="false" />
      <DA bType="Timestamp" name="t" dchg="false" dupd="false" fc="ST" qchg="false" />
    </DOType>
    <DOType id="ens_BehaviourModeKind" cdc="ENS">
      <DA bType="Enum" name="stVal" type="BehaviourModeKind" dchg="false" dupd="false" fc="ST" qchg="false" />
      <DA bType="Quality" name="q" dchg="false" dupd="false" fc="ST" qchg="false" />
      <DA bType="Timestamp" name="t" dchg="false" dupd="false" fc="ST" qchg="false" />
    </DOType>
    <DOType id="enc_BehaviourModeKind" cdc="ENC">
      <DA bType="Enum" name="stVal" type="BehaviourModeKind" dchg="false" dupd="false" fc="ST" qchg="false" />
      <DA bType="Quality" name="q" dchg="false" dupd="false" fc="ST" qchg="false" />
      <DA bType="Timestamp" name="t" dchg="false" dupd="false" fc="ST" qchg="false" />
      <DA bType="Enum" name="ctlModel" type="CtlModelKind" dchg="false" dupd="false" fc="CF" qchg="false">
        <Val>status-only</Val>
      </DA>
    </DOType>
    <DOType id="LPL" cdc="LPL">
      <DA bType="VisString255" name="vendor" dchg="false" dupd="false" fc="DC" qchg="false" />
      <DA bType="VisString255" name="swRev" dchg="false" dupd="false" fc="DC" qchg="false" />
      <DA bType="VisString255" name="configRev" dchg="false" dupd="false" fc="DC" qchg="false" />
      <DA bType="VisString255" name="ldNs" dchg="false" dupd="false" fc="EX" qchg="false">
        <Val>IEC 61850-7-4:2007A</Val>
      </DA>
      <DA bType="VisString255" name="lnNs" dchg="false" dupd="false" fc="EX" qchg="false">
        <Val>IEC 61850-7-4:2007A</Val>
      </DA>
    </DOType>
    <DOType id="LPL_420" cdc="LPL">
      <DA bType="VisString255" name="vendor" dchg="false" dupd="false" fc="DC" qchg="false" />
      <DA bType="VisString255" name="swRev" dchg="false" dupd="false" fc="DC" qchg="false" />
      <DA bType="VisString255" name="configRev" dchg="false" dupd="false" fc="DC" qchg="false" />
      <DA bType="VisString255" name="lnNs" dchg="false" dupd="false" fc="EX" qchg="false">
        <Val>IEC 61850-7-420:2019</Val>
      </DA>
    </DOType>
    <DOType id="MV" cdc="MV">
      <DA bType="Struct" name="mag" type="AnalogueValue" dchg="true" dupd="false" fc="MX" qchg="false" />
      <DA bType="Quality" name="q" dchg="false" dupd="false" fc="MX" qchg="false" />
      <DA bType="Timestamp" name="t" dchg="false" dupd="false" fc="MX" qchg="false" />
      <DA bType="Struct" name="units" type="Unit" dchg="false" dupd="false" fc="CF" qchg="false" />
    </DOType>
    <DOType id="CMV" cdc="CMV">
      <DA bType="Struct" name="cVal" type="Vector" dchg="true" dupd="false" fc="MX" qchg="false" />
      <DA bType="Quality" name="q" dchg="false" dupd="false" fc="MX" qchg="false" />
      <DA bType="Timestamp" name="t" dchg="false" dupd="false" fc="MX" qchg="false" />
      <DA bType="Struct" name="units" type="Unit" dchg="false" dupd="false" fc="CF" qchg="false" />
    </DOType>
    <DOType id="WYE" cdc="WYE">
      <SDO type="CMV" name="phsA" />
      <SDO type="CMV" name="phsB" />
      <SDO type="CMV" name="phsC" />
    </DOType>
    <DOType id="DEL" cdc="DEL">
      <SDO type="CMV" name="phsAB" />
      <SDO type="CMV" name="phsBC" />
      <SDO type="CMV" name="phsCA" />
    </DOType>
    <DOType desc="Controllable analogue process value" id="APC" cdc="APC">
      <DA bType="Struct" name="Oper" type="OperAnalog" dchg="false" dupd="false" fc="CO" qchg="false" />
      <DA bType="Struct" name="mxVal" type="AnalogueValue" dchg="true" dupd="false" fc="MX" qchg="false" />
      <DA bType="Quality" name="q" dchg="false" dupd="false" fc="MX" qchg="false" />
      <DA bType="Timestamp" name="t" dchg="false" dupd="false" fc="MX" qchg="false" />
      <DA bType="Struct" name="units" type="Unit" dchg="false" dupd="false" fc="CF" qchg="false" />
      <DA bType="Enum" name="ctlModel" type="CtlModelKind" dchg="true" dupd="false" fc="CF" qchg="false">
        <Val>direct-with-normal-security</Val>
      </DA>
    </DOType>
    <DOType desc="Controllable integer status" id="INC" cdc="INC">
      <DA bType="Struct" name="Oper" type="OperINT32" dchg="false" dupd="false" fc="CO" qchg="false" />
      <DA bType="INT32" name="stVal" dchg="false" dupd="false" fc="ST" qchg="false" />
      <DA bType="Quality" name="q" dchg="false" dupd="false" fc="ST" qchg="false" />
      <DA bType="Timestamp" name="t" dchg="false" dupd="false" fc="ST" qchg="false" />
      <DA bType="Enum" name="ctlModel" type="CtlModelKind" dchg="false" dupd="false" fc="CF" qchg="false">
        <Val>direct-with-normal-security</Val>
      </DA>
      <DA name="dataNs" bType="VisString255" valKind="RO" fc="EX">
        <Val>NBNL_RTI_version1</Val>
      </DA>
    </DOType>
    <DOType cdc="SPS" id="DERAvail" desc="">
      <DA name="stVal" bType="BOOLEAN" type="" fc="ST" dchg="true" />
      <DA name="q" bType="Quality" type="" fc="ST" qchg="true" />
      <DA name="t" bType="Timestamp" type="" fc="ST" />
      <DA name="subEna" bType="BOOLEAN" type="" fc="SV" />
      <DA name="subVal" bType="BOOLEAN" type="" fc="SV" />
      <DA name="subQ" bType="Quality" type="" fc="SV" />
      <DA name="subID" bType="VisString64" type="" fc="SV" />
      <DA name="blkEna" bType="BOOLEAN" type="" fc="BL" />
      <DA name="d" bType="VisString255" type="" fc="DC" />
      <DA name="dU" bType="Unicode255" type="" fc="DC" />
      <DA name="cdcName" bType="VisString255" type="" fc="EX" />
      <DA name="dataNs" bType="VisString255" type="" fc="EX" />
    </DOType>
    <DAType id="Originator" iedType="">
      <BDA desc="IEC61850_7_2.DomainTypesGeneral::S_Originator.orCat.desc" bType="Enum" name="orCat" type="OriginatorCategoryKind" />
      <BDA desc="IEC61850_7_2.DomainTypesGeneral::S_Originator.orIdent.desc" bType="Octet64" name="orIdent" />
    </DAType>
    <DAType id="OperINT32" iedType="">
      <BDA desc="IEC 61850-8-1:2003.ctlVal" bType="INT32" name="ctlVal" />
      <BDA desc="IEC 61850-8-1:2003.origin" bType="Struct" name="origin" type="Originator" />
      <BDA desc="IEC 61850-8-1:2003.ctlNum" bType="INT8U" name="ctlNum" />
      <BDA desc="IEC 61850-8-1:2003.T" bType="Timestamp" name="T" />
      <BDA desc="IEC 61850-8-1:2003.Test" bType="BOOLEAN" name="Test" />
      <BDA desc="IEC 61850-8-1:2003.Check" bType="Check" name="Check" />
      <ProtNs type="8-MMS">IEC 61850-8-1:2003</ProtNs>
    </DAType>
    <DAType id="Unit" iedType="">
      <BDA desc="IEC61850_7_3.ConstructedDAs::Unit.SIUnit.desc" bType="Enum" name="SIUnit" type="SIUnitKind" />
      <BDA desc="IEC61850_7_3.ConstructedDAs::Unit.multiplier.desc" bType="Enum" name="multiplier" type="MultiplierKind" />
    </DAType>
    <DAType id="OperAnalog">
      <BDA name="ctlVal" bType="Struct" type="AnalogueValue" />
      <BDA name="origin" bType="Struct" type="Originator" />
      <BDA name="ctlNum" bType="INT8U" />
      <BDA name="T" bType="Timestamp" />
      <BDA name="Test" bType="BOOLEAN" />
      <BDA name="Check" bType="Check" />
      <ProtNs type="8-MMS">IEC 61850-8-1:2003</ProtNs>
    </DAType>
    <DAType id="AnalogueValue" iedType="">
      <BDA desc="IEC61850_7_3.AnalogueValue::AnalogueValue.f.desc" bType="FLOAT32" name="f" />
    </DAType>
    <DAType id="Vector" iedType="">
      <BDA desc="IEC61850_7_3.ConstructedDAs::Vector.mag.desc" bType="Struct" name="mag" type="AnalogueValue" />
    </DAType>
    <EnumType id="CtlModelKind">
      <EnumVal desc="status-only" ord="0">status-only</EnumVal>
      <EnumVal desc="direct-with-normal-security" ord="1">direct-with-normal-security</EnumVal>
      <EnumVal desc="sbo-with-normal-security" ord="2">sbo-with-normal-security</EnumVal>
      <EnumVal desc="direct-with-enhanced-security" ord="3">direct-with-enhanced-security</EnumVal>
      <EnumVal desc="sbo-with-enhanced-security" ord="4">sbo-with-enhanced-security</EnumVal>
    </EnumType>
    <EnumType id="HealthKind">
      <EnumVal desc="Ok" ord="1">Ok</EnumVal>
      <EnumVal desc="Warning" ord="2">Warning</EnumVal>
      <EnumVal desc="Alarm" ord="3">Alarm</EnumVal>
    </EnumType>
    <EnumType id="DERStateKind">
      <EnumVal ord="1">on but disconnected and not ready</EnumVal>
      <EnumVal ord="2">starting up</EnumVal>
      <EnumVal ord="3">disconnected and available</EnumVal>
      <EnumVal ord="4">disconnected and authorized</EnumVal>
      <EnumVal ord="5">synchronizing</EnumVal>
      <EnumVal ord="6">running</EnumVal>
      <EnumVal ord="7">stopping and disconnecting under emergency conditions</EnumVal>
      <EnumVal ord="8">stopping</EnumVal>
      <EnumVal ord="9">disconnected and blocked</EnumVal>
      <EnumVal ord="10">disconnected and in maintenance</EnumVal>
      <EnumVal ord="11">failed</EnumVal>
      <EnumVal ord="98">Not applicable or not known</EnumVal>
    </EnumType>
    <EnumType id="OriginatorCategoryKind">
      <EnumVal desc="not-supported" ord="0">not-supported</EnumVal>
      <EnumVal desc="bay-control" ord="1">bay-control</EnumVal>
      <EnumVal desc="station-control" ord="2">station-control</EnumVal>
      <EnumVal desc="remote-control" ord="3">remote-control</EnumVal>
      <EnumVal desc="automatic-bay" ord="4">automatic-bay</EnumVal>
      <EnumVal desc="automatic-station" ord="5">automatic-station</EnumVal>
      <EnumVal desc="automatic-remote" ord="6">automatic-remote</EnumVal>
      <EnumVal desc="maintenance" ord="7">maintenance</EnumVal>
      <EnumVal desc="process" ord="8">process</EnumVal>
    </EnumType>
    <EnumType id="MultiplierKind">
      <EnumVal desc="y" ord="-24">y</EnumVal>
      <EnumVal desc="z" ord="-21">z</EnumVal>
      <EnumVal desc="a" ord="-18">a</EnumVal>
      <EnumVal desc="f" ord="-15">f</EnumVal>
      <EnumVal desc="p" ord="-12">p</EnumVal>
      <EnumVal desc="n" ord="-9">n</EnumVal>
      <EnumVal desc="µ" ord="-6">µ</EnumVal>
      <EnumVal desc="m" ord="-3">m</EnumVal>
      <EnumVal desc="c" ord="-2">c</EnumVal>
      <EnumVal desc="d" ord="-1">d</EnumVal>
      <EnumVal desc="" ord="0" />
      <EnumVal desc="da" ord="1">da</EnumVal>
      <EnumVal desc="h" ord="2">h</EnumVal>
      <EnumVal desc="k" ord="3">k</EnumVal>
      <EnumVal desc="M" ord="6">M</EnumVal>
      <EnumVal desc="G" ord="9">G</EnumVal>
      <EnumVal desc="T" ord="12">T</EnumVal>
      <EnumVal desc="P" ord="15">P</EnumVal>
      <EnumVal desc="E" ord="18">E</EnumVal>
      <EnumVal desc="Z" ord="21">Z</EnumVal>
      <EnumVal desc="Y" ord="24">Y</EnumVal>
    </EnumType>
    <EnumType id="SIUnitKind">
      <EnumVal desc="" ord="1" />
      <EnumVal desc="m" ord="2">m</EnumVal>
      <EnumVal desc="kg" ord="3">kg</EnumVal>
      <EnumVal desc="s" ord="4">s</EnumVal>
      <EnumVal desc="A" ord="5">A</EnumVal>
      <EnumVal desc="K" ord="6">K</EnumVal>
      <EnumVal desc="mol" ord="7">mol</EnumVal>
      <EnumVal desc="cd" ord="8">cd</EnumVal>
      <EnumVal desc="deg" ord="9">deg</EnumVal>
      <EnumVal desc="rad" ord="10">rad</EnumVal>
      <EnumVal desc="sr" ord="11">sr</EnumVal>
      <EnumVal desc="Gy" ord="21">Gy</EnumVal>
      <EnumVal desc="Bq" ord="22">Bq</EnumVal>
      <EnumVal desc="°C" ord="23">°C</EnumVal>
      <EnumVal desc="Sv" ord="24">Sv</EnumVal>
      <EnumVal desc="F" ord="25">F</EnumVal>
      <EnumVal desc="C" ord="26">C</EnumVal>
      <EnumVal desc="S" ord="27">S</EnumVal>
      <EnumVal desc="H" ord="28">H</EnumVal>
      <EnumVal desc="V" ord="29">V</EnumVal>
      <EnumVal desc="ohm" ord="30">ohm</EnumVal>
      <EnumVal desc="J" ord="31">J</EnumVal>
      <EnumVal desc="N" ord="32">N</EnumVal>
      <EnumVal desc="Hz" ord="33">Hz</EnumVal>
      <EnumVal desc="lx" ord="34">lx</EnumVal>
      <EnumVal desc="Lm" ord="35">Lm</EnumVal>
      <EnumVal desc="Wb" ord="36">Wb</EnumVal>
      <EnumVal desc="T" ord="37">T</EnumVal>
      <EnumVal desc="W" ord="38">W</EnumVal>
      <EnumVal desc="Pa" ord="39">Pa</EnumVal>
      <EnumVal desc="m²" ord="41">m²</EnumVal>
      <EnumVal desc="m³" ord="42">m³</EnumVal>
      <EnumVal desc="m/s" ord="43">m/s</EnumVal>
      <EnumVal desc="m/s²" ord="44">m/s²</EnumVal>
      <EnumVal desc="m³/s" ord="45">m³/s</EnumVal>
      <EnumVal desc="m/m³" ord="46">m/m³</EnumVal>
      <EnumVal desc="M" ord="47">M</EnumVal>
      <EnumVal desc="kg/m³" ord="48">kg/m³</EnumVal>
      <EnumVal desc="m²/s" ord="49">m²/s</EnumVal>
      <EnumVal desc="W/m K" ord="50">W/m K</EnumVal>
      <EnumVal desc="J/K" ord="51">J/K</EnumVal>
      <EnumVal desc="ppm" ord="52">ppm</EnumVal>
      <EnumVal desc="1/s" ord="53">1/s</EnumVal>
      <EnumVal desc="rad/s" ord="54">rad/s</EnumVal>
      <EnumVal desc="W/m²" ord="55">W/m²</EnumVal>
      <EnumVal desc="J/m²" ord="56">J/m²</EnumVal>
      <EnumVal desc="S/m" ord="57">S/m</EnumVal>
      <EnumVal desc="K/s" ord="58">K/s</EnumVal>
      <EnumVal desc="Pa/s" ord="59">Pa/s</EnumVal>
      <EnumVal desc="J/kg K" ord="60">J/kg K</EnumVal>
      <EnumVal desc="VA" ord="61">VA</EnumVal>
      <EnumVal desc="Watts" ord="62">Watts</EnumVal>
      <EnumVal desc="VAr" ord="63">VAr</EnumVal>
      <EnumVal desc="phi" ord="64">phi</EnumVal>
      <EnumVal desc="cos(phi)" ord="65">cos(phi)</EnumVal>
      <EnumVal desc="Vs" ord="66">Vs</EnumVal>
      <EnumVal desc="V²" ord="67">V²</EnumVal>
      <EnumVal desc="As" ord="68">As</EnumVal>
      <EnumVal desc="A²" ord="69">A²</EnumVal>
      <EnumVal desc="A²t" ord="70">A²t</EnumVal>
      <EnumVal desc="VAh" ord="71">VAh</EnumVal>
      <EnumVal desc="Wh" ord="72">Wh</EnumVal>
      <EnumVal desc="VArh" ord="73">VArh</EnumVal>
      <EnumVal desc="V/Hz" ord="74">V/Hz</EnumVal>
      <EnumVal desc="Hz/s" ord="75">Hz/s</EnumVal>
      <EnumVal desc="char" ord="76">char</EnumVal>
      <EnumVal desc="char/s" ord="77">char/s</EnumVal>
      <EnumVal desc="kgm²" ord="78">kgm²</EnumVal>
      <EnumVal desc="dB" ord="79">dB</EnumVal>
      <EnumVal desc="J/Wh" ord="80">J/Wh</EnumVal>
      <EnumVal desc="W/s" ord="81">W/s</EnumVal>
      <EnumVal desc="l/s" ord="82">l/s</EnumVal>
      <EnumVal desc="dBm" ord="83">dBm</EnumVal>
      <EnumVal desc="h" ord="84">h</EnumVal>
      <EnumVal desc="min" ord="85">min</EnumVal>
    </EnumType>
    <EnumType id="BehaviourModeKind">
      <EnumVal desc="on" ord="1">on</EnumVal>
      <EnumVal desc="blocked" ord="2">blocked</EnumVal>
      <EnumVal desc="test" ord="3">test</EnumVal>
      <EnumVal desc="test/blocked" ord="4">test/blocked</EnumVal>
      <EnumVal desc="off" ord="5">off</EnumVal>
    </EnumType>
  </DataTypeTemplates>
</SCL>