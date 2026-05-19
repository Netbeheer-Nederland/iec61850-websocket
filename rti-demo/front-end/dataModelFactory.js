// dataModelFactory.js
// Converts SCL files (XML) into a Python module (model.py).

const SCL_NS = 'http://www.iec.ch/61850/2003/SCL';

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
  FLOAT64: 'float32',
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

function pyString(value) {
  return `'${String(value).replace(/\\/g, '\\\\').replace(/'/g, "\\'")}'`;
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
    return pyString(value);
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

  const items = entries.map(([k, v]) => `${nextPad}${pyString(k)}: ${toPythonLiteral(v, indent + 4)}`);
  return `{\n${items.join(',\n')}\n${pad}}`;
}

function parseXmlFromFileText(xmlText) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(xmlText, 'application/xml');
  const parseError = doc.querySelector('parsererror');
  if (parseError) {
    throw new Error('Invalid XML/SCL file.');
  }
  return doc;
}

function getAttribute(node, name) {
  return node.getAttribute(name) || '';
}

function getChildrenByTagName(node, tagName) {
  return Array.from(node.getElementsByTagNameNS(SCL_NS, tagName));
}

function getDirectChildrenByTagName(node, tagName) {
  return Array.from(node.children || []).filter((child) => child.localName === tagName);
}

function parseDataTypeTemplatesFromDoc(doc) {
  const dtt = doc.querySelector('DataTypeTemplates');
  if (!dtt) {
    throw new Error('DataTypeTemplates section not found in SCL file.');
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
        // Get <val> if present
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
        // Get <val> if present
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

// Recursively parse DOI/SDOI/DAI/SDAI tree for <Val> in IED section
export function parseIedValOverrides(iedNode) {
  const overrides = {};
  function walk(node, path = []) {
    // DOI/SDOI/DAI/SDAI
    const tag = node.localName;
    let name = getAttribute(node, 'name');
    if (!name) return;
    const newPath = [...path, name];
    // DAI/SDAI may have <Val>
    if (tag === 'DAI' || tag === 'SDAI') {
      const valEl = node.querySelector('Val');
      if (valEl) {
        overrides[newPath.join('.')]= valEl.textContent.trim();
      }
    }
    // Recurse into SDOI/DAI/SDAI children
    Array.from(node.children || []).forEach((child) => {
      if (["SDOI", "DAI", "SDAI"].includes(child.localName)) {
        walk(child, newPath);
      }
    });
  }
  // Start from each DOI under LN/LN0
  const lns = getChildrenByTagName(iedNode, 'LN').concat(getChildrenByTagName(iedNode, 'LN0'));
  lns.forEach((ln) => {
    getDirectChildrenByTagName(ln, 'DOI').forEach((doi) => {
      walk(doi, []);
    });
  });
  return overrides;
}

// Helper to resolve value for a DA/BDA path
function resolveDaValue(pathArr, iedOverrides, dttVal) {
  // pathArr: [DO, SDO..., DA, SDA...]
  // Try IED override first
  const pathStr = pathArr.join('.');
  if (iedOverrides && iedOverrides.hasOwnProperty(pathStr)) {
    return iedOverrides[pathStr];
  }
  // Fallback to DataTypeTemplates <val>
  if (dttVal !== undefined && dttVal !== null) {
    return dttVal;
  }
  return null;
}

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

function buildLogicalNodeName(lnClass, inst, prefix) {
  if (!lnClass) {
    return 'LN';
  }
  return `${prefix || ''}${lnClass}${inst || ''}`;
}

function normalizeTypeRef(typeRef) {
  if (!typeRef) {
    return '';
  }
  return String(typeRef).split('/')[0];
}

function safeIdentifier(value) {
  const raw = String(value || 'x');
  const cleaned = raw.replace(/[^a-zA-Z0-9_]/g, '_').replace(/^_+|_+$/g, '');
  return cleaned || 'x';
}

function parseLnDataSets(lnNode, fallbackLdInst) {
  const dataSetNodes = getDirectChildrenByTagName(lnNode, 'DataSet');
  return dataSetNodes.map((dsNode) => {
    const dataSetName = getAttribute(dsNode, 'name') || 'DataSet';
    const fcdaNodes = getDirectChildrenByTagName(dsNode, 'FCDA');
    const entries = fcdaNodes.map((fcdaNode) => {
      const ldInst = getAttribute(fcdaNode, 'ldInst') || fallbackLdInst || '';
      const prefix = getAttribute(fcdaNode, 'prefix');
      const lnClass = getAttribute(fcdaNode, 'lnClass');
      const lnInst = getAttribute(fcdaNode, 'lnInst');
      const lnName = buildLogicalNodeName(lnClass, lnInst, prefix);
      const doName = getAttribute(fcdaNode, 'doName');
      const daName = getAttribute(fcdaNode, 'daName');
      const doPath = daName ? `${doName}.${daName}` : doName;
      const variableName = doPath ? `${ldInst}/${lnName}.${doPath}` : `${ldInst}/${lnName}`;
      const fc = getAttribute(fcdaNode, 'fc');
      return {
        logicalDeviceName: ldInst,
        variableName,
        fc,
        fcEnum: FC_TO_ENUM_NAME[String(fc || '').toUpperCase()] || null
      };
    });

    return {
      name: dataSetName,
      logicalDeviceName: fallbackLdInst || '',
      entries
    };
  });
}

function parseBoolAttr(value, defaultValue = false) {
  if (value === undefined || value === null || value === '') {
    return defaultValue;
  }
  return ['1', 'true', 'yes'].includes(String(value).toLowerCase());
}

function parseIntAttr(value, defaultValue) {
  if (value === undefined || value === null || value === '') {
    return defaultValue;
  }
  const parsed = Number.parseInt(String(value), 10);
  return Number.isNaN(parsed) ? defaultValue : parsed;
}

function parseLnReportControls(lnNode, fallbackLdInst, lnNameForPath, dataSets) {
  const reportNodes = getDirectChildrenByTagName(lnNode, 'ReportControl');
  return reportNodes.map((rcNode) => {
    const name = getAttribute(rcNode, 'name') || 'ReportControl';
    const confRev = parseIntAttr(getAttribute(rcNode, 'confRev'), 1);
    const rptId = getAttribute(rcNode, 'rptID') || name;
    const datSet = getAttribute(rcNode, 'datSet');
    const defaultDataSetName = Array.isArray(dataSets) && dataSets.length > 0 ? dataSets[0].name : '';
    const dataSetName = datSet || defaultDataSetName;
    const datasetPath = dataSetName ? `${fallbackLdInst}/${lnNameForPath}.${dataSetName}` : '';
    const buffered = parseBoolAttr(getAttribute(rcNode, 'buffered'), false);
    const indexed = parseBoolAttr(getAttribute(rcNode, 'indexed'), false);
    const bufferedTime = parseIntAttr(getAttribute(rcNode, 'bufTime'), 0);
    const intPeriod = parseIntAttr(getAttribute(rcNode, 'intgPd'), 1000);

    const trgOpsNode = getDirectChildrenByTagName(rcNode, 'TrgOps')[0] || null;
    const trgOps = trgOpsNode
      ? {
          dchg: parseBoolAttr(getAttribute(trgOpsNode, 'dchg'), false),
          dupd: parseBoolAttr(getAttribute(trgOpsNode, 'dupd'), false),
          gi: parseBoolAttr(getAttribute(trgOpsNode, 'gi'), false),
          integrity: parseBoolAttr(getAttribute(trgOpsNode, 'period'), false),
          qchg: parseBoolAttr(getAttribute(trgOpsNode, 'qchg'), false)
        }
      : {};

    const optFieldsNode = getDirectChildrenByTagName(rcNode, 'OptFields')[0] || null;
    const optFlds = optFieldsNode
      ? {
          seqNum: parseBoolAttr(getAttribute(optFieldsNode, 'seqNum'), false),
          timeStamp: parseBoolAttr(getAttribute(optFieldsNode, 'timeStamp'), false),
          dataSet: parseBoolAttr(getAttribute(optFieldsNode, 'dataSet'), false),
          reasonCode: parseBoolAttr(getAttribute(optFieldsNode, 'reasonCode'), false),
          dataRef: parseBoolAttr(getAttribute(optFieldsNode, 'dataRef'), false),
          entryID: parseBoolAttr(getAttribute(optFieldsNode, 'entryID'), false),
          configRef: parseBoolAttr(getAttribute(optFieldsNode, 'configRef'), false),
          bufOvfl: parseBoolAttr(getAttribute(optFieldsNode, 'bufOvfl'), false)
        }
      : {};

    return {
      name,
      confRev,
      rptId,
      datasetPath,
      buffered,
      indexed,
      bufferedTime,
      intPeriod,
      trgOps,
      optFlds
    };
  });
}

function daDefaultMmsLiteral(daType) {
  switch (daType) {
    case 'boolean':
      return 'False';
    case 'int8':
    case 'int16':
    case 'int24':
    case 'int32':
    case 'int64':
    case 'int8u':
    case 'int16u':
    case 'int24u':
    case 'int32u':
    case 'enumerated':
      return '0';
    case 'float32':
      return '0.0';
    case 'quality':
      return '{"validity": "good", "source": "process", "test": False, "operatorBlock": False}';
    case 'timeStamp':
      return '{"secondSinceEpoch": 0, "fractionOfSecond": 0, "timeQuality": {"leapSecondsKown": False, "clockFailure": False, "clockNotSynchronized": False, "timeAccuracy": 0}}';
    case 'visString64':
    case 'visString129':
    case 'visString255':
      return '""';
    case 'octetString':
      return 'bytes()';
    case 'check':
      return '{"synchroCheck": False, "interlockCheck": False}';
    case 'structure':
      return '[]';
    default:
      return 'None';
  }
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
      let resolvedVal = resolveDaValue(bdaPath, iedOverrides, bda.val);

      if (isStructRef) {
        const childFnSuffix = safeIdentifier(normalizeTypeRef(bda.typeRef));
        lines.push(`    ${bdaVar} = _create_da_${childFnSuffix}(${pyString(bda.name || 'BDA')}, fc, da)`);
      } else {
        const bdaType = bda.dataAttributeType || 'structure';
        const bdaTypeExpr = `DataAttributeType.${bdaType}`;
        let valueLiteral = resolvedVal !== null ? toPythonLiteral(resolvedVal) : daDefaultMmsLiteral(bdaType);
        lines.push(`    ${bdaVar} = DataAttribute(${pyString(bda.name || 'BDA')}, ${bdaTypeExpr}, fc, ${valueLiteral}, da)`);
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
    lines.push(`    do = DataObject(name, ${pyString(String(doTypeDef.cdc || '').toLowerCase())}, parent=parent)`);

    (doTypeDef.das || []).forEach((da, index) => {
      const fcExpr = da.fcEnum ? `FunctionalConstraint.${da.fcEnum}` : 'None';
      const daVar = `_da_${safeIdentifier(String(da.name || 'da').toLowerCase())}_${index + 1}`;
      const isStructRef = String(da.bType || '').toLowerCase() === 'struct' && Boolean(templates.daTypes[da.typeRef]);
      const daPath = [doTypeDef.cdc, da.name]; // Simplified path; can be improved for nested
      let resolvedVal = resolveDaValue(daPath, iedOverrides, da.val);

      if (isStructRef) {
        const childFnSuffix = safeIdentifier(normalizeTypeRef(da.typeRef));
        lines.push(`    ${daVar} = _create_da_${childFnSuffix}(${pyString(da.name || 'DA')}, ${fcExpr}, do)`);
      } else {
        const daType = da.dataAttributeType || 'structure';
        const daTypeExpr = `DataAttributeType.${daType}`;
        let valueLiteral = resolvedVal !== null ? toPythonLiteral(resolvedVal) : daDefaultMmsLiteral(daType);
        lines.push(`    ${daVar} = DataAttribute(${pyString(da.name || 'DA')}, ${daTypeExpr}, ${fcExpr}, ${valueLiteral}, do)`);
      }

      lines.push(`    do.add_do_or_da(${daVar})`);
    });

    (doTypeDef.sdos || []).forEach((sdo, index) => {
      const childTypeDef = templates.doTypes[sdo.typeRef] || null;
      const childCdc = childTypeDef && childTypeDef.cdc ? childTypeDef.cdc : '';
      const sdoVar = `_sdo_${safeIdentifier(String(sdo.name || 'sdo').toLowerCase())}_${index + 1}`;
      lines.push(`    ${sdoVar} = _create_do_by_typeref(${pyString(sdo.name || 'SDO')}, ${pyString(normalizeTypeRef(sdo.typeRef))}, ${pyString(childCdc)}, do)`);
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
    lines.push(`        ${pyString(entry.typeRef)}: ${entry.fnName},`);
  });
  lines.push('    }');
  lines.push('    fn = _dispatcher.get(type_ref)');
  lines.push('    if fn:');
  lines.push('        return fn(name, parent)');
  lines.push('    return _create_do_by_cdc(name, cdc, parent)');
  lines.push('');
}

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
      const dataSets = parseLnDataSets(lnNode, inst);
      const reportControls = parseLnReportControls(lnNode, inst, lnName, dataSets);
      return {
        lnClass,
        inst: instValue,
        prefix: prefixValue,
        lnType: getAttribute(lnNode, 'lnType'),
        dataSets,
        reportControls
      };
    });
    const lnNodes = getDirectChildrenByTagName(ldNode, 'LN').map((lnNode) => {
      const lnClass = getAttribute(lnNode, 'lnClass');
      const instValue = getAttribute(lnNode, 'inst');
      const prefixValue = getAttribute(lnNode, 'prefix');
      const lnName = buildLogicalNodeName(lnClass, instValue, prefixValue);
      const dataSets = parseLnDataSets(lnNode, inst);
      const reportControls = parseLnReportControls(lnNode, inst, lnName, dataSets);
      return {
        lnClass,
        inst: instValue,
        prefix: prefixValue,
        lnType: getAttribute(lnNode, 'lnType'),
        dataSets,
        reportControls
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

export async function parseSclFile(file) {
  const xmlText = await file.text();
  const doc = parseXmlFromFileText(xmlText);
  return parseDataTypeTemplatesFromDoc(doc);
}

export async function generatePythonModelFromScl(file, sourceFileText, selectedIedName, selectedApName) {
  const xmlText = await file.text();
  const doc = parseXmlFromFileText(xmlText);
  const templates = parseDataTypeTemplatesFromDoc(doc);
  // Parse IED section for value overrides
  const iedNodes = getChildrenByTagName(doc.documentElement, 'IED');
  let selectedIed = null;
  if (selectedIedName) {
    selectedIed = iedNodes.find((node) => getAttribute(node, 'name') === selectedIedName) || null;
  }
  if (!selectedIed) {
    selectedIed = iedNodes[0] || null;
  }
  const iedOverrides = selectedIed ? parseIedValOverrides(selectedIed) : {};
  const runtimeModel = parseRuntimeModelFromDoc(doc, selectedIedName, selectedApName);

  const sourceCandidate = sourceFileText
    || file?.path
    || file?.webkitRelativePath
    || file?.name
    || 'unknown';
  const sourceText = String(sourceCandidate).replace(/\\/g, '/');

  const lines = [];
  lines.push('"""Auto-generated model script from SCL DataTypeTemplates and IED section.');
  lines.push('');
  lines.push(`Source file: ${sourceText}`);
  lines.push('Generated by: generate_mode_from_scl.py');
  lines.push('"""');
  lines.push('');
  lines.push('from __future__ import annotations');
  lines.push('');
  lines.push('from dataclasses import asdict');
  lines.push('from typing import Optional');
  lines.push('');
  lines.push('from ws61850.iec61850.data_model import *');
  lines.push('');
  lines.push(`BTYPE_TO_DA_ENUM_NAME = ${toPythonLiteral(BTYPE_TO_DA_ENUM_NAME)}`);
  lines.push(`FC_TO_ENUM_NAME = ${toPythonLiteral(FC_TO_ENUM_NAME)}`);
  lines.push('');

  emitDaTypeFunctions(lines, templates, iedOverrides);

  emitDoTypeFunctions(lines, templates, iedOverrides);

  lines.push('def build_ied_model() -> IedModel:');
  lines.push(`    ied = IedModel(name=${pyString(runtimeModel.iedName)})`);
  lines.push('');

  runtimeModel.ldevices.forEach((ld, ldIndex) => {
    const ldVar = `ld${ldIndex + 1}`;
    lines.push(`    ${ldVar} = LogicalDevice(name=${pyString(ld.inst)}, ldName=${pyString(ld.ldName)})`);
    lines.push('');

    ld.logicalNodes.forEach((ln, lnIndex) => {
      const lnVar = `ln${ldIndex + 1}_${lnIndex + 1}`;
      const lnName = buildLogicalNodeName(ln.lnClass, ln.inst, ln.prefix);
      lines.push(`    ${lnVar} = LogicalNode(name=${pyString(lnName)}, parent=${ldVar})`);

      const lnTypeDef = templates.lnTypes[ln.lnType] || null;
      if (lnTypeDef && Array.isArray(lnTypeDef.dos)) {
        lnTypeDef.dos.forEach((lnDo, doIndex) => {
          const doTypeDef = templates.doTypes[lnDo.typeRef] || null;
          const cdc = doTypeDef && doTypeDef.cdc ? doTypeDef.cdc : '';
          const doVar = `do_${safeIdentifier(String(lnDo.name || 'do').toLowerCase())}_${doIndex + 1}`;
          const typeRefNorm = normalizeTypeRef(lnDo.typeRef);
          lines.push(`    ${doVar} = _create_do_by_typeref(${pyString(lnDo.name)}, ${pyString(typeRefNorm)}, ${pyString(cdc)}, ${lnVar})`);
          lines.push(`    ${lnVar}.add_data_object(${doVar})`);
        });
      }

      if (Array.isArray(ln.dataSets) && ln.dataSets.length > 0) {
        ln.dataSets.forEach((dataSet, dsIndex) => {
          const dsVar = `dataset_${ldIndex + 1}_${lnIndex + 1}_${dsIndex + 1}`;
          const dsLogicalDeviceName = dataSet.logicalDeviceName || ld.inst;
          lines.push(`    ${dsVar} = DataSet(${lnVar}, ${pyString(dsLogicalDeviceName)}, ${pyString(dataSet.name)})`);

          (dataSet.entries || []).forEach((entry, entryIndex) => {
            if (!entry.fcEnum) {
              return;
            }
            const entryVar = `data_entry_${ldIndex + 1}_${lnIndex + 1}_${dsIndex + 1}_${entryIndex + 1}`;
            lines.push(`    ${entryVar} = DataSetEntry(${pyString(entry.logicalDeviceName)}, ${pyString(entry.variableName)}, FunctionalConstraint.${entry.fcEnum})`);
            lines.push(`    ${dsVar}.add_entry(${entryVar})`);
          });

          lines.push(`    ${lnVar}.add_data_set(${dsVar})`);
        });
      }

      if (Array.isArray(ln.reportControls) && ln.reportControls.length > 0) {
        ln.reportControls.forEach((rc, rcIndex) => {
          const rcVar = `rcb_${ldIndex + 1}_${lnIndex + 1}_${rcIndex + 1}`;
          lines.push(`    ${rcVar} = ReportControl(`);
          lines.push(`        ${pyString(rc.name)},`);
          lines.push(`        buffered=${rc.buffered ? 'True' : 'False'},`);
          lines.push(`        dataset_name=${pyString(rc.datasetPath)},`);
          lines.push(`        rpt_id=${pyString(rc.rptId)},`);
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
  lines.push('');

  const pythonCode = `${lines.join('\n')}\n`;

  const blob = new Blob([pythonCode], { type: 'text/plain' });
  const link = document.createElement('a');
  const objectUrl = URL.createObjectURL(blob);
  link.href = objectUrl;
  link.download = 'model.py';
  link.click();
  URL.revokeObjectURL(objectUrl);
}