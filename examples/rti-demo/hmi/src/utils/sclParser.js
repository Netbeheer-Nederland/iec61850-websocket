/**
 * SCL Parser Utility
 * Standalone SCL parsing for React components
 * Based on dataModelFactory.js logic
 */

const SCL_NS = 'http://www.iec.ch/61850/2003/SCL';

// Type mappings from dataModelFactory.js
const BTYPE_TO_DA_ENUM_NAME = {
  BOOLEAN: 'boolean',
  INT8: 'int8',
  INT16: 'int16',
  INT24: 'int24',
  INT32: 'int32',
  INT64: 'int64',
  INT8U: 'int8u',
  INT16U: 'int16u',
  INT24U: 'int24u',
  INT32U: 'int32u',
  FLOAT32: 'float32',
  FLOAT64: 'float64',
  Enum: 'enumerated',
  Quality: 'quality',
  Timestamp: 'timeStamp',
  Check: 'check',
  Struct: 'structure',
  VisString64: 'visString64',
  VisString129: 'visString129',
  VisString255: 'visString255',
  Octet64: 'octetString',
  OctetString: 'octetString',
  ObjRef: 'visString255',
  Dbpos: 'enumerated',
  Tcmd: 'enumerated',
  Unicode255: 'visString255',
  PhyComAddr: 'octetString'
};

const FC_TO_ENUM_NAME = {
  ST: 'st',
  MX: 'mx',
  SP: 'sp',
  SV: 'sv',
  CF: 'cf',
  DC: 'dc',
  SG: 'sg',
  SE: 'se',
  SR: 'sr',
  OR: 'or_',
  BL: 'bl',
  EX: 'ex',
  LG: 'lg',
  CO: 'co'
};

// Helper functions for XML parsing
function getAttribute(node, name) {
  return node.getAttribute(name) || '';
}

function getChildrenByTagName(node, tagName) {
  return Array.from(node.getElementsByTagNameNS(SCL_NS, tagName));
}

function getDirectChildrenByTagName(node, tagName) {
  return Array.from(node.children || []).filter((child) => child.localName === tagName);
}

/**
 * Parse DataTypeTemplates section from SCL document
 */
function parseDataTypeTemplatesFromDoc(doc) {
  const dtt = doc.querySelector('DataTypeTemplates');
  if (!dtt) {
    return { enumTypes: {}, daTypes: {}, doTypes: {}, lnTypes: {} };
  }

  const enumTypes = {};
  const daTypes = {};
  const doTypes = {};
  const lnTypes = {};

  getChildrenByTagName(dtt, 'EnumType').forEach((enumEl) => {
    const id = getAttribute(enumEl, 'id');
    if (!id) return;
    enumTypes[id] = {
      values: getChildrenByTagName(enumEl, 'EnumVal').map((valEl) => ({
        name: valEl.textContent.trim(),
        ord: getAttribute(valEl, 'ord') === '' ? null : Number.parseInt(getAttribute(valEl, 'ord'), 10),
        desc: getAttribute(valEl, 'desc')
      }))
    };
  });

  getChildrenByTagName(dtt, 'DAType').forEach((daTypeEl) => {
    const id = getAttribute(daTypeEl, 'id');
    if (!id) return;
    daTypes[id] = {
      iedType: getAttribute(daTypeEl, 'iedType'),
      bdas: getChildrenByTagName(daTypeEl, 'BDA').map((bdaEl) => {
        const bType = getAttribute(bdaEl, 'bType');
        let val = null;
        const valEl = bdaEl.querySelector('Val');
        if (valEl) val = valEl.textContent.trim();
        return {
          name: getAttribute(bdaEl, 'name'),
          bType,
          typeRef: getAttribute(bdaEl, 'type'),
          desc: getAttribute(bdaEl, 'desc'),
          dataAttributeType: BTYPE_TO_DA_ENUM_NAME[bType] || null,
          val
        };
      })
    };
  });

  getChildrenByTagName(dtt, 'DOType').forEach((doTypeEl) => {
    const id = getAttribute(doTypeEl, 'id');
    if (!id) return;
    doTypes[id] = {
      cdc: getAttribute(doTypeEl, 'cdc'),
      desc: getAttribute(doTypeEl, 'desc'),
      das: getChildrenByTagName(doTypeEl, 'DA').map((daEl) => {
        const bType = getAttribute(daEl, 'bType');
        const fc = getAttribute(daEl, 'fc');
        let val = null;
        const valEl = daEl.querySelector('Val');
        if (valEl) val = valEl.textContent.trim();
        return {
          name: getAttribute(daEl, 'name'),
          bType,
          typeRef: getAttribute(daEl, 'type'),
          fc,
          fcEnum: FC_TO_ENUM_NAME[String(fc || '').toUpperCase()] || null,
          dchg: getAttribute(daEl, 'dchg'),
          dupd: getAttribute(daEl, 'dupd'),
          qchg: getAttribute(daEl, 'qchg'),
          valKind: getAttribute(daEl, 'valKind'),
          dataAttributeType: BTYPE_TO_DA_ENUM_NAME[bType] || null,
          val
        };
      }),
      sdos: getChildrenByTagName(doTypeEl, 'SDO').map((sdoEl) => ({
        name: getAttribute(sdoEl, 'name'),
        typeRef: getAttribute(sdoEl, 'type')
      }))
    };
  });

  getChildrenByTagName(dtt, 'LNodeType').forEach((lnTypeEl) => {
    const id = getAttribute(lnTypeEl, 'id');
    if (!id) return;
    lnTypes[id] = {
      lnClass: getAttribute(lnTypeEl, 'lnClass'),
      desc: getAttribute(lnTypeEl, 'desc'),
      dos: getChildrenByTagName(lnTypeEl, 'DO').map((doEl) => ({
        name: getAttribute(doEl, 'name'),
        typeRef: getAttribute(doEl, 'type'),
        transient: getAttribute(doEl, 'transient'),
        desc: getAttribute(doEl, 'desc')
      }))
    };
  });

  return { enumTypes, daTypes, doTypes, lnTypes };
}

/**
 * Parse IED section for value overrides
 */
function parseIedValOverrides(iedNode, templates) {
  const overrides = {};

  function addOverride(pathArr, value) {
    const path = normalizeRefPath(pathArr);
    overrides[path] = value;
  }

  function walk(node, path = []) {
    const tag = node.localName;
    const name = getAttribute(node, 'name');
    if (!name) return;

    const newPath = [...path, name];
    if (tag === 'DAI' || tag === 'SDAI') {
      const valEl = node.querySelector('Val');
      if (valEl) {
        addOverride(newPath, valEl.textContent.trim());
      }
    }

    Array.from(node.children || []).forEach((child) => {
      if (['SDOI', 'DAI', 'SDAI'].includes(child.localName)) {
        walk(child, newPath);
      }
    });
  }

  const lns = getChildrenByTagName(iedNode, 'LN').concat(getChildrenByTagName(iedNode, 'LN0'));
  lns.forEach((ln) => {
    const doNameToCdc = {};
    const lnType = getAttribute(ln, 'lnType');
    const lnTypeDef = templates && templates.lnTypes ? templates.lnTypes[lnType] : null;
    if (lnTypeDef && Array.isArray(lnTypeDef.dos)) {
      lnTypeDef.dos.forEach((lnDo) => {
        const doTypeDef = templates.doTypes ? templates.doTypes[lnDo.typeRef] : null;
        if (lnDo.name && doTypeDef && doTypeDef.cdc) {
          doNameToCdc[lnDo.name] = doTypeDef.cdc;
        }
      });
    }

    getDirectChildrenByTagName(ln, 'DOI').forEach((doi) => {
      walk(doi, [], doNameToCdc);
    });
  });

  return overrides;
}

/**
 * Parse DataSet elements from LN/LN0 node
 */
function parseDataSets(lnNode) {
  const dataSetNodes = getDirectChildrenByTagName(lnNode, 'DataSet');
  if (dataSetNodes.length === 0) {
    return [];
  }

  return dataSetNodes.map((dsNode) => {
    const name = getAttribute(dsNode, 'name');
    const desc = getAttribute(dsNode, 'desc');
    
    const fcdas = getDirectChildrenByTagName(dsNode, 'FCDA').map((fcda) => ({
      ldInst: getAttribute(fcda, 'ldInst'),
      prefix: getAttribute(fcda, 'prefix'),
      lnClass: getAttribute(fcda, 'lnClass'),
      lnInst: getAttribute(fcda, 'lnInst'),
      doName: getAttribute(fcda, 'doName'),
      daName: getAttribute(fcda, 'daName'),
      fc: getAttribute(fcda, 'fc'),
      fcEnum: FC_TO_ENUM_NAME[String(getAttribute(fcda, 'fc') || '').toUpperCase()] || null,
      ix: getAttribute(fcda, 'ix')
    }));

    return {
      name,
      desc,
      entries: fcdas
    };
  });
}

/**
 * Parse ReportControl elements from LN/LN0 node
 */
function parseReportControls(lnNode) {
  const rcNodes = getDirectChildrenByTagName(lnNode, 'ReportControl');
  if (rcNodes.length === 0) {
    return [];
  }

  return rcNodes.map((rcNode) => {
    const name = getAttribute(rcNode, 'name');
    const buffered = getAttribute(rcNode, 'buffered') === 'true';
    const rptId = getAttribute(rcNode, 'rptID');
    const indexed = getAttribute(rcNode, 'indexed') === 'true';
    const bufTime = getAttribute(rcNode, 'bufTime');
    const intPeriod = getAttribute(rcNode, 'intgPd');
    const confRev = Number.parseInt(getAttribute(rcNode, 'confRev'), 10) || 1;
    const datSet = getAttribute(rcNode, 'datSet');

    // Parse TrgOps - defaults to false for all if not present
    const trgOpsNode = getDirectChildrenByTagName(rcNode, 'TrgOps')[0];
    const trgOps = trgOpsNode ? {
      dchg: getAttribute(trgOpsNode, 'dchg') === 'true',
      qchg: getAttribute(trgOpsNode, 'qchg') === 'true',
      dupd: getAttribute(trgOpsNode, 'dupd') === 'true',
      period: getAttribute(trgOpsNode, 'period') === 'true',
      gi: getAttribute(trgOpsNode, 'gi') === 'true'
    } : {
      dchg: false,
      qchg: false,
      dupd: false,
      period: false,
      gi: false
    };

    // Parse OptFields - defaults to false for all if not present
    const optFieldsNode = getDirectChildrenByTagName(rcNode, 'OptFields')[0];
    const optFlds = optFieldsNode ? {
      seqNum: getAttribute(optFieldsNode, 'seqNum') === 'true',
      timeStamp: getAttribute(optFieldsNode, 'timeStamp') === 'true',
      dataSet: getAttribute(optFieldsNode, 'dataSet') === 'true',
      reasonCode: getAttribute(optFieldsNode, 'reasonCode') === 'true',
      dataRef: getAttribute(optFieldsNode, 'dataRef') === 'true',
      entryID: getAttribute(optFieldsNode, 'entryID') === 'true',
      configRef: getAttribute(optFieldsNode, 'configRef') === 'true',
      bufOvfl: getAttribute(optFieldsNode, 'bufOvfl') === 'true'
    } : {
      seqNum: false,
      timeStamp: false,
      dataSet: false,
      reasonCode: false,
      dataRef: false,
      entryID: false,
      configRef: false,
      bufOvfl: false
    };

    return {
      name,
      buffered,
      rptId,
      indexed,
      bufferedTime: bufTime ? Number.parseInt(bufTime, 10) : 0,
      intPeriod: intPeriod ? Number.parseInt(intPeriod, 10) : 0,
      confRev,
      datasetPath: datSet || '',
      trgOps,
      optFlds
    };
  });
}

/**
 * Parse runtime model from SCL document
 */
function parseRuntimeModelFromDoc(doc, selectedIedName, selectedApName) {
  const iedNodes = getChildrenByTagName(doc.documentElement, 'IED');
  if (iedNodes.length === 0) {
    throw new Error('No IED found in SCL file.');
  }

  let selectedIed = null;
  if (selectedIedName) {
    selectedIed = iedNodes.find((node) => getAttribute(node, 'name') === selectedIedName) || null;
  }
  if (!selectedIed) {
    selectedIed = iedNodes[0] || null;
  }
  if (!selectedIed) {
    throw new Error('Unable to select IED from SCL file.');
  }

  const iedName = getAttribute(selectedIed, 'name') || 'IED';
  const apNodes = getDirectChildrenByTagName(selectedIed, 'AccessPoint');
  if (apNodes.length === 0) {
    throw new Error(`IED '${iedName}' has no AccessPoint.`);
  }

  let selectedAp = null;
  if (selectedApName) {
    selectedAp = apNodes.find((node) => getAttribute(node, 'name') === selectedApName) || null;
  }
  if (!selectedAp) {
    selectedAp = apNodes[0] || null;
  }
  if (!selectedAp) {
    throw new Error(`Unable to select AccessPoint for IED '${iedName}'.`);
  }

  const serverNode = getDirectChildrenByTagName(selectedAp, 'Server')[0] || null;
  if (!serverNode) {
    throw new Error(`AccessPoint '${getAttribute(selectedAp, 'name') || ''}' has no Server section.`);
  }

  const ldevices = getDirectChildrenByTagName(serverNode, 'LDevice').map((ldNode) => {
    const inst = getAttribute(ldNode, 'inst') || 'LD';
    const ldName = getAttribute(ldNode, 'ldName') || inst;
    const ln0Nodes = getDirectChildrenByTagName(ldNode, 'LN0').map((lnNode) => {
      const lnClass = getAttribute(lnNode, 'lnClass') || 'LLN0';
      const instValue = getAttribute(lnNode, 'inst');
      const prefixValue = getAttribute(lnNode, 'prefix');
      const lnName = buildLogicalNodeName(lnClass, instValue, prefixValue);
      return {
        lnClass,
        inst: instValue,
        prefix: prefixValue,
        lnType: getAttribute(lnNode, 'lnType'),
        dataSets: parseDataSets(lnNode),
        reportControls: parseReportControls(lnNode)
      };
    });
    const lnNodes = getDirectChildrenByTagName(ldNode, 'LN').map((lnNode) => {
      const lnClass = getAttribute(lnNode, 'lnClass');
      const instValue = getAttribute(lnNode, 'inst');
      const prefixValue = getAttribute(lnNode, 'prefix');
      const lnName = buildLogicalNodeName(lnClass, instValue, prefixValue);
      return {
        lnClass,
        inst: instValue,
        prefix: prefixValue,
        lnType: getAttribute(lnNode, 'lnType'),
        dataSets: parseDataSets(lnNode),
        reportControls: parseReportControls(lnNode)
      };
    });
    return {
      inst,
      ldName,
      logicalNodes: [...ln0Nodes, ...lnNodes]
    };
  });

  return {
    iedName,
    ldevices
  };
}

function buildLogicalNodeName(lnClass, inst, prefix) {
  if (!lnClass) {
    return 'LN';
  }
  return `${prefix || ''}${lnClass}${inst || ''}`;
}

/**
 * Parse SCL file content and extract all metadata
 * @param {string} sclContent - The SCL/XML file content
 * @returns {Object} - Parsed SCL metadata
 */
export function parseSclContent(sclContent) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(sclContent, 'application/xml');
  
  const parseError = doc.querySelector('parsererror');
  if (parseError) {
    throw new Error('Invalid XML/SCL file: ' + parseError.textContent);
  }

  // Extract all IEDs
  const iedNodes = getChildrenByTagName(doc.documentElement, 'IED');
  const iedNames = iedNodes.map(node => getAttribute(node, 'name') || 'Unnamed');

  // Extract AccessPoints
  const iedAccessPoints = {};
  iedNodes.forEach((iedNode, index) => {
    const iedName = iedNames[index];
    const apNodes = getDirectChildrenByTagName(iedNode, 'AccessPoint');
    iedAccessPoints[iedName] = apNodes.map(node => getAttribute(node, 'name') || 'cp1');
  });

  // Parse DataTypeTemplates
  let templates = {};
  try {
    templates = parseDataTypeTemplatesFromDoc(doc);
  } catch (error) {
    console.warn('Could not parse DataTypeTemplates:', error);
    templates = { enumTypes: {}, daTypes: {}, doTypes: {}, lnTypes: {} };
  }

  return {
    doc,
    iedNames,
    iedAccessPoints,
    templates
  };
}

/**
 * Extract IED and AP selection from SCL
 * @param {string} sclContent - SCL file content
 * @param {string} selectedIedName - Selected IED name
 * @param {string} selectedApName - Selected Access Point name
 * @returns {Object} - Runtime model structure
 */
export function extractRuntimeModel(sclContent, selectedIedName = null, selectedApName = null) {
  const { doc, iedNames, templates } = parseSclContent(sclContent);
  
  const iedNodes = getChildrenByTagName(doc.documentElement, 'IED');
  
  // Find selected IED or use first
  let selectedIed = null;
  if (selectedIedName) {
    selectedIed = iedNodes.find(node => getAttribute(node, 'name') === selectedIedName) || null;
  }
  if (!selectedIed && iedNodes.length > 0) {
    selectedIed = iedNodes[0];
  }
  
  if (!selectedIed) {
    throw new Error('No IED found in SCL file');
  }

  const iedName = getAttribute(selectedIed, 'name') || 'UnknownIED';
  
  // Get AccessPoints
  const apNodes = getDirectChildrenByTagName(selectedIed, 'AccessPoint');
  let selectedAp = null;
  if (selectedApName) {
    selectedAp = apNodes.find(node => getAttribute(node, 'name') === selectedApName) || null;
  }
  if (!selectedAp && apNodes.length > 0) {
    selectedAp = apNodes[0];
  }
  
  if (!selectedAp) {
    throw new Error(`No AccessPoint found for IED '${iedName}'`);
  }

  const apName = getAttribute(selectedAp, 'name') || 'cp1';

  // Parse IED overrides
  const iedOverrides = parseIedValOverrides(selectedIed, templates);

  // Parse runtime model
  const runtimeModel = parseRuntimeModelFromDoc(doc, selectedIedName, selectedApName);

  return {
    iedName,
    apName,
    templates,
    iedOverrides,
    runtimeModel,
    allIedNames: iedNames
  };
}

/**
 * Generate Python model code from SCL content
 * @param {string} sclContent - SCL file content
 * @param {string} selectedIedName - Selected IED name
 * @param {string} selectedApName - Selected Access Point name
 * @param {string} sourceFileName - Original file name
 * @returns {string} - Generated Python model code
 */
export function generateModelPyCode(sclContent, selectedIedName = null, selectedApName = null, sourceFileName = 'model.scl') {
  const { templates, iedOverrides, runtimeModel, iedName, apName } = extractRuntimeModel(
    sclContent, selectedIedName, selectedApName
  );

  // Use the same logic as dataModelFactory.js but return the code instead of downloading
  const lines = [];
  lines.push('"""Auto-generated model script from SCL DataTypeTemplates and IED section.');
  lines.push(`Source file: ${sourceFileName}`);
  lines.push('Generated by: SCL Model Factory"""');
  lines.push('');
  lines.push('from __future__ import annotations');
  lines.push('');
  lines.push('from dataclasses import asdict');
  lines.push('from typing import Optional');
  lines.push('');
  lines.push('from ws61850.iec61850.data_model import *');
  lines.push('from ws61850.protocol.types import OptFlds');
  lines.push('');
  lines.push(`BTYPE_TO_DA_ENUM_NAME = ${JSON.stringify(BTYPE_TO_DA_ENUM_NAME)}`);
  lines.push(`FC_TO_ENUM_NAME = ${JSON.stringify(FC_TO_ENUM_NAME)}`);
  lines.push('');

  // Emit DA type functions
  emitDaTypeFunctions(lines, templates, iedOverrides);
  
  // Emit DO type functions
  emitDoTypeFunctions(lines, templates, iedOverrides);

  // Build IED
  lines.push('');
  lines.push('def build_ied_model() -> IedModel:');
  lines.push(`    ied = IedModel(name="${iedName}")`);
  lines.push('');

  // Add logical devices from runtime model
  runtimeModel.ldevices.forEach((ld, ldIndex) => {
    const ldVar = `ld${ldIndex + 1}`;
    lines.push(`    ${ldVar} = LogicalDevice(name="${ld.inst}", ldName="${ld.ldName}")`);
    lines.push('');

    ld.logicalNodes.forEach((ln, lnIndex) => {
      const lnVar = `ln${ldIndex + 1}_${lnIndex + 1}`;
      const lnName = ln.lnClass + (ln.inst || '');
      lines.push(`    ${lnVar} = LogicalNode(name="${lnName}", parent=${ldVar})`);

      // Add data objects from lnType
      const lnTypeDef = templates.lnTypes[ln.lnType] || null;
      if (lnTypeDef && Array.isArray(lnTypeDef.dos)) {
        lnTypeDef.dos.forEach((lnDo, doIndex) => {
          const doTypeDef = templates.doTypes[lnDo.typeRef] || null;
          const cdc = doTypeDef && doTypeDef.cdc ? doTypeDef.cdc : '';
          const doVar = `do_${safeIdentifier(lnDo.name || 'do').toLowerCase()}_${doIndex + 1}`;
          const typeRefNorm = normalizeTypeRef(lnDo.typeRef);
          lines.push(`    ${doVar} = _create_do_by_typeref("${lnDo.name}", "${typeRefNorm}", "${cdc}", ${lnVar})`);
          lines.push(`    ${lnVar}.add_data_object(${doVar})`);
        });
      }

      // Add data sets
      if (Array.isArray(ln.dataSets) && ln.dataSets.length > 0) {
        ln.dataSets.forEach((dataSet, dsIndex) => {
          const dsVar = `dataset_${ldIndex + 1}_${lnIndex + 1}_${dsIndex + 1}`;
          const dsLogicalDeviceName = ld.inst;
          lines.push(`    ${dsVar} = DataSet(${lnVar}, "${dsLogicalDeviceName}", "${dataSet.name}")`);

          (dataSet.entries || []).forEach((entry, entryIndex) => {
            if (!entry.fcEnum) return;
            const entryVar = `data_entry_${ldIndex + 1}_${lnIndex + 1}_${dsIndex + 1}_${entryIndex + 1}`;
            
            // Construct variable name from FCDA attributes
            // Format: {ldInst}/{prefix}{lnClass}{lnInst}.{doName}[.{daName}]
            const ldInst = entry.ldInst || ld.inst;
            const prefix = entry.prefix || '';
            const lnClass = entry.lnClass || '';
            const lnInst = entry.lnInst || '';
            const doName = entry.doName || '';
            const daName = entry.daName || '';
            
            const lnPath = `${prefix}${lnClass}${lnInst}`;
            let variableName = `${ldInst}/${lnPath}.${doName}`;
            if (daName) {
              variableName += `.${daName}`;
            }
            
            lines.push(`    ${entryVar} = DataSetEntry("${ldInst}", "${variableName}", FunctionalConstraint.${entry.fcEnum})`);
            lines.push(`    ${dsVar}.add_entry(${entryVar})`);
          });

          lines.push(`    ${lnVar}.add_data_set(${dsVar})`);
        });
      }

      // Add report controls
      if (Array.isArray(ln.reportControls) && ln.reportControls.length > 0) {
        ln.reportControls.forEach((rc, rcIndex) => {
          const rcVar = `rcb_${ldIndex + 1}_${lnIndex + 1}_${rcIndex + 1}`;
          lines.push(`    ${rcVar} = ReportControl(`);
          lines.push(`        name="${rc.name}",`);
          lines.push(`        buffered=${rc.buffered ? 'True' : 'False'},`);
          lines.push(`        dataset_name="${rc.datasetPath}",`);
          lines.push(`        rpt_id="${rc.rptId}",`);
          lines.push(`        conf_rev=${rc.confRev},`);
          lines.push(`        trg_ops=${toPythonLiteral(rc.trgOps, 8)},`);
          lines.push(`        opt_flds=${toPythonLiteral(rc.optFlds, 8)},`);
          lines.push(`        buffered_time=${rc.bufferedTime},`);
          lines.push(`        int_period=${rc.intPeriod},`);
          lines.push(`        indexed=${rc.indexed ? 'True' : 'False'},`);
          lines.push('    )');
          lines.push(`    ${lnVar}.add_report_control(${rcVar})`);
        });
      }

      lines.push(`    ${ldVar}.add_logical_node(${lnVar})`);
    });

    lines.push('');
    lines.push(`    ied.add_logical_device(${ldVar})`);
    lines.push('');
  });

  lines.push('    return ied');
  lines.push('');
  lines.push('');
  lines.push('ied = build_ied_model()');

  return lines.join('\n');
}

// Helper functions (copied from dataModelFactory.js for standalone use)
function safeIdentifier(value) {
  const raw = String(value || 'x');
  const cleaned = raw.replace(/[^a-zA-Z0-9_]/g, '_').replace(/^_+|_+$/g, '');
  return cleaned || 'x';
}

function normalizeTypeRef(typeRef) {
  if (!typeRef) return '';
  return String(typeRef).split('/')[0];
}

function normalizeRefPath(pathOrParts) {
  const parts = Array.isArray(pathOrParts)
    ? pathOrParts
    : String(pathOrParts || '').split('.');

  return parts
    .filter((part) => part !== undefined && part !== null && String(part).trim() !== '')
    .map((part) => String(part).trim().toLowerCase())
    .join('.');
}

function toPythonLiteral(value, indent = 0) {
  const pad = ' '.repeat(indent);
  const nextPad = ' '.repeat(indent + 4);

  if (value === null || value === undefined) {
    return 'None';
  }

  if (typeof value === 'boolean') {
    return value ? 'True' : 'False';
  }

  if (typeof value === 'number') {
    return Number.isFinite(value) ? String(value) : 'None';
  }

  if (typeof value === 'string') {
    return `'${String(value).replace(/\\/g, '\\\\').replace(/'/g, "\\'")}'`;
  }

  if (Array.isArray(value)) {
    if (value.length === 0) {
      return '[]';
    }
    const items = value.map((item) => `${nextPad}${toPythonLiteral(item, indent + 4)}`);
    return `[\n${items.join(',\n')}\n${pad}]`;
  }

  const entries = Object.entries(value);
  if (entries.length === 0) {
    return '{}';
  }

  const items = entries.map(([k, v]) => `${nextPad}'${k}': ${toPythonLiteral(v, indent + 4)}`);
  return `{\n${items.join(',\n')}\n${pad}}`;
}

function emitDaTypeFunctions(lines, templates, iedOverrides, parentPath = []) {
  Object.entries(templates.daTypes).forEach(([daTypeId, daTypeDef]) => {
    const fnSuffix = safeIdentifier(normalizeTypeRef(daTypeId));
    const fnName = `_create_da_${fnSuffix}`;

    lines.push(`def ${fnName}(name, fc, parent):`);
    lines.push('    da = DataAttribute(name, DataAttributeType.structure, fc, [], parent)');

    (daTypeDef.bdas || []).forEach((bda, index) => {
      const bdaVar = `_bda_${safeIdentifier(String(bda.name || 'bda').toLowerCase())}_${index + 1}`;
      const isStructRef = String(bda.bType || '').toLowerCase() === 'struct' && Boolean(templates.daTypes[bda.typeRef]);
      const bdaPath = [...parentPath, bda.name];
      const resolvedVal = resolveDaValue(bdaPath, iedOverrides, bda.val);

      if (isStructRef) {
        const childFnSuffix = safeIdentifier(normalizeTypeRef(bda.typeRef));
        lines.push(`    ${bdaVar} = _create_da_${childFnSuffix}(${toPythonLiteral(bda.name || 'BDA')}, fc, da)`);
      } else {
        const bdaType = bda.dataAttributeType || 'structure';
        const bdaTypeExpr = `DataAttributeType.${bdaType}`;
        let valueLiteral = resolvedVal !== null ? toPythonLiteral(resolvedVal) : 'None';
        lines.push(`    ${bdaVar} = DataAttribute(${toPythonLiteral(bda.name || 'BDA')}, ${bdaTypeExpr}, fc, ${valueLiteral}, da)`);
      }

      lines.push(`    da.add_data_attribute(${bdaVar})`);
    });

    lines.push('    return da');
    lines.push('');
  });
}

function emitDoTypeFunctions(lines, templates, iedOverrides) {
  const dispatcherEntries = [];

  Object.entries(templates.doTypes).forEach(([doTypeId, doTypeDef]) => {
    const normalizedTypeRef = normalizeTypeRef(doTypeId);
    const fnSuffix = safeIdentifier(normalizedTypeRef);
    const fnName = `_create_do_${fnSuffix}`;
    dispatcherEntries.push({ typeRef: normalizedTypeRef, fnName });

    lines.push(`def ${fnName}(name, parent):`);
    lines.push(`    do = DataObject(name, "${String(doTypeDef.cdc || '').toLowerCase()}", parent=parent)`);

    (doTypeDef.das || []).forEach((da, index) => {
      const fcExpr = da.fcEnum ? `FunctionalConstraint.${da.fcEnum}` : 'None';
      const daVar = `_da_${safeIdentifier(String(da.name || 'da').toLowerCase())}_${index + 1}`;
      const isStructRef = String(da.bType || '').toLowerCase() === 'struct' && Boolean(templates.daTypes[da.typeRef]);
      const daPath = [doTypeDef.cdc, da.name];
      const resolvedVal = resolveDaValue(daPath, iedOverrides, da.val);

      if (isStructRef) {
        const childFnSuffix = safeIdentifier(normalizeTypeRef(da.typeRef));
        lines.push(`    ${daVar} = _create_da_${childFnSuffix}(${toPythonLiteral(da.name || 'DA')}, ${fcExpr}, do)`);
      } else {
        const daType = da.dataAttributeType || 'structure';
        const daTypeExpr = `DataAttributeType.${daType}`;
        let valueLiteral = resolvedVal !== null ? toPythonLiteral(resolvedVal) : 'None';
        lines.push(`    ${daVar} = DataAttribute(${toPythonLiteral(da.name || 'DA')}, ${daTypeExpr}, ${fcExpr}, ${valueLiteral}, do)`);
      }

      lines.push(`    do.add_do_or_da(${daVar})`);
    });

    (doTypeDef.sdos || []).forEach((sdo, index) => {
      const childTypeDef = templates.doTypes[sdo.typeRef] || null;
      const childCdc = childTypeDef && childTypeDef.cdc ? childTypeDef.cdc : '';
      const sdoVar = `_sdo_${safeIdentifier(String(sdo.name || 'sdo').toLowerCase())}_${index + 1}`;
      lines.push(`    ${sdoVar} = _create_do_by_typeref(${toPythonLiteral(sdo.name || 'SDO')}, ${toPythonLiteral(normalizeTypeRef(sdo.typeRef))}, ${toPythonLiteral(childCdc)}, do)`);
      lines.push(`    do.add_do_or_da(${sdoVar})`);
    });

    lines.push('    return do');
    lines.push('');
  });

  lines.push('def _create_do_by_cdc(name: str, cdc: Optional[str], parent):');
  lines.push("    cdc_norm = (cdc or '').lower()");
  lines.push('    return DataObject(name, cdc_norm, parent=parent)');
  lines.push('');

  lines.push('def _create_do_by_typeref(name: str, type_ref, cdc, parent):');
  lines.push('    _dispatcher = {');
  dispatcherEntries.forEach((entry) => {
    lines.push(`        ${toPythonLiteral(entry.typeRef)}: ${entry.fnName},`);
  });
  lines.push('    }');
  lines.push('    fn = _dispatcher.get(type_ref)');
  lines.push('    if fn:');
  lines.push('        return fn(name, parent)');
  lines.push('    return _create_do_by_cdc(name, cdc, parent)');
  lines.push('');
}

function resolveDaValue(pathArr, iedOverrides, dttVal) {
  const pathStr = normalizeRefPath(pathArr);
  if (iedOverrides && Object.prototype.hasOwnProperty.call(iedOverrides, pathStr)) {
    return iedOverrides[pathStr];
  }

  if (dttVal !== undefined && dttVal !== null) {
    return dttVal;
  }

  return null;
}

export default {
  parseSclContent,
  extractRuntimeModel,
  generateModelPyCode
};
