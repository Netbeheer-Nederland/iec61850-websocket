import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { executeApiCall, buildTargetValue } from '../services/apiService';
import ControlModal from './ControlModal';

const CONTROLLABLE_CDCS = ['SPC', 'DPC', 'APC', 'INC', 'ENC', 'BSC', 'ING', 'ASG', 'CTE', 'ENG'];

/**
 * DataAccessPanel - A reusable component for reading and writing data from ACSI endpoints
 * 
 * Features:
 * - Dropdown to select connected endpoint
 * - Cascading dropdowns for LD (Logical Devices), LN (Logical Nodes), DO (Data Objects), DA (Data Attributes)
 * - Read button to fetch data value
 * - Write button to write data value
 * - Operate button to open ControlModal for controllable DO/SDO
 * - Displays results of operations
 * - Manual cp entry box (shown only for WebSocket Passive endpoints), used wherever cp is needed
 * 
 * @param {Object} props
 * @param {Object[]} props.connections - Array of connection objects with host, port, name, type, status
 * @param {Function} props.getModel - Function to retrieve cached model by endpoint target
 * @param {Object} props.settings - BFF settings with bffHost and bffPort
 * @param {string} props.cp - The control point/access point identifier
 */
function DataAccessPanel({ connections, getModel, updateModel, settings, cp = 'cp1' }) {
  // State for selections
  const [selectedTarget, setSelectedTarget] = useState('');
  const [selectedLD, setSelectedLD] = useState('');
  const [selectedLN, setSelectedLN] = useState('');
  const [selectedDO, setSelectedDO] = useState('');
  const [selectedFC, setSelectedFC] = useState('');
  
  // State for available options (populated from model)
  const [availableLDs, setAvailableLDs] = useState([]);
  const [availableLNs, setAvailableLNs] = useState([]);
  const [availableDOs, setAvailableDOs] = useState([]);

  // State for complex structures
  const [doChildren, setDoChildren] = useState([]);
  const [attributePath, setAttributePath] = useState([]);
  const dataDefinitionCacheRef = useRef({});

  // Tracks the previously-selected target so the dropdown-populate effect can
  // tell "target actually changed" apart from "getModel/extractHierarchyFromModel
  // got a new function identity from a parent re-render".
  const prevTargetRef = useRef('');
  
  // State for data operations
  const [readResult, setReadResult] = useState(null);
  const [writeResult, setWriteResult] = useState(null);
  const [writeValue, setWriteValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [modelFetched, setModelFetched] = useState(false);
  const [fetchingModel, setFetchingModel] = useState(false);

  // Manual cp entry, shown next to "Fetch Model" for WebSocket Passive endpoints.
  // Its value takes priority over selectedConnection?.cp / the cp prop wherever
  // effectiveCp is computed in this file.
  const [manualCp, setManualCp] = useState('');

  // The cp value that the currently-loaded model (for the selected target) was
  // fetched with. getModel/updateModel are keyed only by target (host:port), not
  // cp, so this local tracker is what lets us tell "model loaded for cp1" apart
  // from "model loaded for cp2" and re-enable Fetch Model when cp changes.
  const [fetchedCp, setFetchedCp] = useState(null);

  // ControlModal state
  const [showControlModal, setShowControlModal] = useState(false);
  const [controlModalTarget, setControlModalTarget] = useState({ ref: '', name: '', cdc: '', endpoint: null, cp: null });
  const [operateResult, setOperateResult] = useState(null); // { success: boolean, message: string } | null

  // Get connected endpoints (excluding IDP-Server type)
  const connectedEndpoints = useMemo(() => {
    return connections.filter(conn => conn.status === 'connected' && conn.type !== 'IDP-Server');
  }, [connections]);

  // Currently selected connection object
  const selectedConnection = useMemo (() => {
    return connectedEndpoints.find(conn => buildTargetValue(conn.host, conn.port) === selectedTarget);
  }, [connectedEndpoints, selectedTarget]);

  // Derive ACSI role from the connection type
  const getAcsiRole = (conn) => {
    if (!conn) return null;
    if (conn.acsi === 'client' || conn.acsi === 'server') return conn.acsi;
    const t = (conn.type || '').toUpperCase();
    if (t.includes('SO')) return 'client';
    if (t.includes('FSP')) return 'server';
    return null;
  };

  // FSP endpoints have no write restriction; SO endpoints only allows CF/SP
  const isServerEndpoint = useMemo(() => {
    return getAcsiRole(selectedConnection) === 'server';
  }, [selectedConnection]);

  // Check if this is a TRUE ACSI Server (has acsi='server'), not just FSP
  const isTrueAcsiServer = useMemo(() => {
    return selectedConnection?.acsi === 'server';
  }, [selectedConnection]);

  // True for "passive" websocket endpoints (e.g. RTI-SO). These need cp entered
  // manually here rather than inferred from a client-side connection object.
  // NOTE: adjust this check if your connection `type` strings differ from "RTI-SO",
  // or if another connection type also happens to contain "SO" as a substring.
  const isWebsocketPassiveEndpoint = useMemo(() => {
    const t = (selectedConnection?.type || '').toUpperCase();
    return t.includes('SO');
  }, [selectedConnection]);

  // Compute effective cp - used for all endpoint types
  const effectiveCp = useMemo(() => {
    return (isWebsocketPassiveEndpoint && manualCp) || selectedConnection?.cp || cp || 'cp1';
  }, [isWebsocketPassiveEndpoint, manualCp, selectedConnection, cp]);

  // Effective writable check
  const canWriteFc = useCallback((fc) => {
    if (isServerEndpoint) return true;
    return isWritableFc(fc);
  }, [isServerEndpoint]);

  // Look up the selected DO/SDO's own `cdc` field directly from the model.
  // Unlike doChildren (which holds the DO's *children*, not the DO itself),
  // this walks the same two model shapes extractDoDefinitionFromModel handles,
  // but returns the DO node's cdc instead of its attribute definitions.
  const getDoCdc = (modelData, ldName, lnName, doPath) => {
    try {
      let data = modelData;
      if (data?.result?.model?.server?.logicalDevices) data = data.result.model;
      else if (data?.result?.server?.logicalDevices) data = data.result;
      else if (data?.model?.server?.logicalDevices) data = data.model;

      const pathParts = doPath.split('.');
      const doName = pathParts[0];
      const sdoParts = pathParts.slice(1);

      // Shape 1: logicalDeviceMap / logicalNodeDetails (ACSI Client model-tree)
      const logicalNodeDetails = data?.logicalNodeDetails || {};
      const lnRef = `${ldName}/${lnName}`;
      const details = logicalNodeDetails[lnRef] || {};
      const dataObjects = details.dataObjects || [];
      const doObj = dataObjects.find(obj => (typeof obj === 'object' ? obj.name : String(obj)) === doName);

      if (doObj && typeof doObj === 'object') {
        if (sdoParts.length === 0) return doObj.cdc || '';
        // Navigate nested SDOs for an SDO path
        let current = doObj;
        for (const part of sdoParts) {
          const sdo = (current.subDataObjects || current.sub_data_objects || []).find(item =>
            (typeof item === 'object' ? item.name : String(item)) === part
          );
          if (!sdo) return '';
          current = sdo;
        }
        return current.cdc || '';
      }

      // Shape 2: tree-structured model (kind/name/children)
      const tree = data?.tree?.children ? data.tree : (data?.children ? data : null);
      if (tree) {
        const ldNode = tree.children?.find(n => n.name === ldName || n.kind === ldName);
        const lnNode = ldNode?.children?.find(n => (n.name || n.kind) === lnName);
        let current = lnNode?.children?.find(n => n.name === doName);
        for (const part of sdoParts) {
          current = current?.children?.find(n => n.name === part);
        }
        return current?.cdc || '';
      }

      return '';
    } catch (e) {
      return '';
    }
  };

  // Resolve the currently selected DO's own cdc for the Operate-button check.
  const selectedDoCdc = useMemo(() => {
    if (!selectedTarget || !selectedLD || !selectedLN || !selectedDO || !getModel) return '';
    const modelData = getModel(selectedTarget);
    return getDoCdc(modelData, selectedLD, selectedLN, selectedDO);
  }, [selectedTarget, selectedLD, selectedLN, selectedDO, getModel]);

  // Check if Operate button should be shown
  const showOperateButton = useMemo(() => {
    if (!selectedTarget || !selectedConnection || !selectedDO || !selectedLD || !selectedLN) return false;
    const isAcsiClient = getAcsiRole(selectedConnection) === 'client';
    if (!isAcsiClient) return false;

    return CONTROLLABLE_CDCS.includes((selectedDoCdc || '').toUpperCase());
  }, [selectedTarget, selectedConnection, selectedDO, selectedLD, selectedLN, selectedDoCdc]);

  // Handle Operate button click
  const handleOperateClick = useCallback(() => {
    if (!selectedLD || !selectedLN || !selectedDO || !selectedConnection || !effectiveCp) return;
    setOperateResult(null); // clear any stale result from a previous operate
    const doRef = `${selectedLD}/${selectedLN}.${selectedDO}`;
    setControlModalTarget({
      ref: doRef,
      name: selectedDO,
      cdc: selectedDoCdc || '',
      endpoint: selectedConnection,
      cp: effectiveCp
    });
    setShowControlModal(true);
  }, [selectedLD, selectedLN, selectedDO, selectedConnection, effectiveCp, selectedDoCdc]);

  // Recursively parse a nested structure DA
  const buildSdaNode = (sda, parentRef, fc) => {
    const name = sda.cmpName || sda.name || 'SDA';
    const ref = `${parentRef}.${name}`;
    const bType = Array.isArray(sda.cmpType) ? sda.cmpType[0] : (sda.bType || '');
    const nestedSda = Array.isArray(sda.cmpType) && sda.cmpType[0] === 'structure' && Array.isArray(sda.cmpType[1])
      ? sda.cmpType[1] : [];
    return { name, type: 'SDA', ref, fc, bType, children: nestedSda.map(c => buildSdaNode(c, ref, fc))};
  };

  // Parse a DA
  const buildDaNode = (da, parentRef) => {
    const name = da.name || da.daRef?.split('.').pop() || 'DA';
    const ref = `${parentRef}.${name}`;
    const fc = da.fc || da.Fc || da.FC || '';
    const bType = Array.isArray(da.daType) ? da.daType[0] : (da.bType || '');
    const nestedSda = Array.isArray(da.daType) && da.daType[0] === 'structure' && Array.isArray(da.daType[1])
      ? da.daType[1] : (da.subDataAttributes || da.sub_attributes || da.sda || []);
    return { name, type: 'DA', ref, fc, bType, children: nestedSda.map(c => buildSdaNode(c, ref, fc)) };
  };

  // Parse an SDO
  const buildSdoNode = (sdo, parentRef) => {
    const name = sdo.name || 'SDO';
    const ref = `${parentRef}.${name}`;
    const inlineDas = sdo.dataAttributes || sdo.data_attributes || [];
    const children = inlineDas.length > 0 ? inlineDas.map(da => buildDaNode(da, ref)) : [];
    return {name, type: 'SDO', ref, cdc: sdo.cdc || '', fc: null, bType: null, children};
  };

  // Top-level children of a DO
  const buildDoChildren = (parentRef, definitionValue) => {
    const dataAttributes = definitionValue?.dataAttributeDefinition || [];
    const subDataObjects = definitionValue?.subDataDefinition || [];
    return [
        ...dataAttributes.map(da => buildDaNode(da, parentRef)),
        ...subDataObjects.map(sdo => buildSdoNode(sdo, parentRef)),
    ];
  };

  //fetchDAsForDO but return the whole value object
  const extractDataDefinitionValue = (payload) => {
    if (payload.result?.value?.dataAttributeDefinition || payload.result?.value?.subDataDefinition) return payload.result.value;
    if (payload.value?.dataAttributeDefinition || payload.value?.subDataDefinition) return payload.value;
    if (payload.dataAttributeDefinition || payload.subDataDefinition) return payload;
    if (payload.result?.dataAttributeDefintion || payload.result?.sudDataDefinition) return payload.result;
    if (payload.data?.dataAttributeDefinition || payload.data?.subDataDefinition) return payload.data;
    return payload.result?.value || payload.value || payload.result || payload;
  };

  // Extract DO/SDO definition from already-loaded server model
  const extractDoDefinitionFromModel = (modelData, ldName, lnName, doPath) => {
    try {
      let data = modelData;
      
      // Normalize to the actual model object
      if (data?.result?.model?.server?.logicalDevices) {
        data = data.result.model;
      } else if (data?.result?.server?.logicalDevices) {
        data = data.result;
      } else if (data?.model?.server?.logicalDevices) {
        data = data.model;
      }
      
      // Try to extract from logicalDeviceMap/logicalNodeDetails structure (model-tree format)
      const logicalDeviceMap = data.logicalDeviceMap || {};
      const logicalNodeDetails = data.logicalNodeDetails || {};
      const lnRef = `${ldName}/${lnName}`;
      const details = logicalNodeDetails[lnRef] || {};
      const dataObjects = details.dataObjects || [];
      
      if (dataObjects.length > 0) {
        // Find the DO (or parent DO for SDO paths)
        // doPath can be "DOName" for a DO, or "DOName.SDOName" for an SDO
        const pathParts = doPath.split('.');
        const doName = pathParts[0];
        const sdoPath = pathParts.slice(1).join('.');
        
        const doObj = dataObjects.find(obj => {
          const objName = typeof obj === 'object' ? obj.name : String(obj);
          return objName === doName;
        });
        
        if (doObj) {
          // If it's an SDO path, navigate to the nested SDO
          if (sdoPath && doObj.subDataObjects) {
            let current = doObj;
            const sdoParts = sdoPath.split('.');
            
            for (const part of sdoParts) {
              const sdoObj = (current.subDataObjects || []).find(item => {
                const itemName = typeof item === 'object' ? item.name : String(item);
                return itemName === part;
              });
              if (!sdoObj) return null;
              current = sdoObj;
            }
            
            // Return SDO's definition
            const dataAttributes = current.dataAttributes || current.data_attributes || [];
            const subDataObjects = current.subDataObjects || current.sub_data_objects || [];
            
            return {
              dataAttributeDefinition: dataAttributes,
              subDataDefinition: subDataObjects
            };
          }
          
          // For regular DOs, return their definition
          const dataAttributes = doObj.data_attributes || doObj.dataAttributes || doObj.da || [];
          const subDataObjects = doObj.subDataObjects || doObj.sub_data_objects || [];
          
          return {
            dataAttributeDefinition: dataAttributes,
            subDataDefinition: subDataObjects
          };
        }
      }
      
      // Try to extract from tree structure (Server model format)
      if (data?.tree?.children) {
        return extractDoDefinitionFromTree(data.tree, ldName, lnName, doPath);
      }
      
      if (data?.children) {
        return extractDoDefinitionFromTree(data, ldName, lnName, doPath);
      }
      
      return null;
    } catch (error) {
      console.error('Failed to extract DO definition from model:', error);
      return null;
    }
  };

  // Helper to extract DO definition from tree-structured model
  const extractDoDefinitionFromTree = (tree, ldName, lnName, doPath) => {
    try {
      const lnRef = `${ldName}/${lnName}`;
      const doName = doPath.split('.')[0];
      
      // Find the LD in the tree
      const ldNode = tree.children?.find(node => node.name === ldName || node.kind === ldName);
      if (!ldNode) return null;
      
      // Find the LN under the LD
      const lnNode = ldNode.children?.find(node => {
        const nodeName = node.name || node.kind;
        return nodeName === lnName || nodeName === lnRef;
      });
      if (!lnNode) return null;
      
      // Find the DO under the LN
      const doNode = lnNode.children?.find(node => node.name === doName);
      if (!doNode) return null;
      
      // For SDO paths, navigate deeper
      const pathParts = doPath.split('.');
      let current = doNode;
      for (let i = 1; i < pathParts.length; i++) {
        const part = pathParts[i];
        current = current.children?.find(node => node.name === part);
        if (!current) return null;
      }
      
      // Extract DAs and SDOs from the current node
      const dataAttributes = [];
      const subDataObjects = [];
      
      if (current.children) {
        current.children.forEach(child => {
          if (child.kind === 'DA' || child.kind === 'DataAttribute' || child.type === 'DA' || child.type === 'DataAttribute') {
            dataAttributes.push(child);
          } else if (child.kind === 'SDO' || child.kind === 'SubDataObject' || child.type === 'SDO' || child.type === 'SubDataObject') {
            subDataObjects.push(child);
          }
        });
      }
      
      return {
        dataAttributeDefinition: dataAttributes,
        subDataDefinition: subDataObjects
      };
    } catch (error) {
      console.error('Failed to extract DO definition from tree:', error);
      return null;
    }
  };

  // Walk a path of selected names down the tree to find the node at that depth
  const findNodeAtPath = (nodes, path) => {
    let currentNodes = nodes, node = null;
    for (const name of path) {
      node = currentNodes.find(n => n.name === name);
      if (!node) return null;
      currentNodes = node.children || [];
    }
    return node;
  };

  const setChildrenAtPath = (nodes, path, newChildren) => {
    if (path.length === 0) return nodes;
    const [name, ...rest] = path;
    return nodes.map(n => {
      if (n.name !== name) return n;
      if (rest.length === 0) return { ...n, children: newChildren };
      return { ...n, children: setChildrenAtPath(n.children || [], rest, newChildren) };
    });
  };

  // FC helper
  const WRITABLE_FCS = ['CF', 'SP'];
  const isWritableFc =(fc) => WRITABLE_FCS.includes((fc || '').toUpperCase());

  const parsePythonDictString = useCallback((pythonStr) => {
    if (!pythonStr || typeof pythonStr !== 'string') return pythonStr;
    try {
      const jsonStr = pythonStr
          .replace(/'/g, '"')
          .replace(/True/g, 'true')
          .replace(/False/g, 'false')
          .replace(/None/g, 'null')
          .replace(/""+/g, '"');
      return JSON.parse(jsonStr);
    } catch (e) {
      return pythonStr;
    }
  }, []);

  // Extract hierarchy from model data
  const extractHierarchyFromModel = useCallback((modelData) => {
    const hierarchy = { lds: [], lns: {}, dos: {}, das: {} };
    
    if (!modelData) return hierarchy;
    
    try {
      // Handle different model structures - normalize to the actual model object
      let data = modelData;
      
      // The stored model could be:
      // 1. Full API response: { ok: true, result: { server: {...}, logicalDeviceMap: {...}, logicalNodeDetails: {...} } }
      // 2. Just the result: { server: {...}, logicalDeviceMap: {...}, logicalNodeDetails: {...} }
      // 3. Tree structure: { tree: {...} } or { kind: 'Server', children: [...] }
      
      // Try to get to the actual model data
      if (data?.result?.server?.logicalDevices) {
        data = data.result;
      } else if (data?.result?.model?.server?.logicalDevices) {
        data = data.result.model;
      } else if (data?.result?.tree?.children) {
        data = data.result;
      } else if (data?.result?.model) {
        data = data.result.model;
      } else if (data?.model?.server?.logicalDevices) {
        data = data.model;
      } else if (data?.model?.tree?.children) {
        data = data.model;
      } else if (data?.model) {
        data = data.model;
      }
      
      // Extract from model.tree structure (ACSIServer format with kind/name/children)
      // This is the most complete format with full hierarchy including DAs
      if (data?.tree?.children) {
        // Extract from tree structure
        const tree = data.tree;
        if (tree.kind === 'IED' || tree.kind === 'Server' || tree.kind === 'server') {
          // Tree root is IED or Server, children are LDs
          tree.children.forEach(node => {
            if (node.kind === 'LD' || node.kind === 'LDevice') {
              hierarchy.lds.push(node.name);
              extractFromKindTree(node, node.name, 'LD', hierarchy);
            }
          });
        } else if (tree.kind === 'LD' || tree.kind === 'LDevice') {
          hierarchy.lds.push(tree.name);
          extractFromKindTree(tree, tree.name, 'LD', hierarchy);
        }
        return hierarchy;
      }
      
      // Also check if tree is at the root level (not under model)
      if (data?.children && (data.kind === 'IED' || data.kind === 'Server' || data.kind === 'server')) {
        data.children.forEach(node => {
          if (node.kind === 'LD' || node.kind === 'LDevice') {
            hierarchy.lds.push(node.name);
            extractFromKindTree(node, node.name, 'LD', hierarchy);
          }
        });
        return hierarchy;
      }
      
      // Extract from server.logicalDevices structure (ACSI Client model-tree)
      if (data?.server?.logicalDevices) {
        const lds = data.server.logicalDevices || [];
        const logicalDeviceMap = data.logicalDeviceMap || {};
        const logicalNodeDetails = data.logicalNodeDetails || {};
        
        hierarchy.lds = lds.map(ld => typeof ld === 'object' ? ld.name : String(ld));
        
        // Build LN, DO, DA maps
        lds.forEach(ld => {
          const ldName = typeof ld === 'object' ? ld.name : String(ld);
          const lns = logicalDeviceMap[ldName] || [];
          hierarchy.lns[ldName] = lns.map(ln => typeof ln === 'object' ? ln.name : String(ln));
          
          lns.forEach(ln => {
            const lnName = typeof ln === 'object' ? ln.name : String(ln);
            const lnRef = `${ldName}/${lnName}`;
            const details = logicalNodeDetails[lnRef] || {};
            
            // Get DOs from dataObjects
            const dos = details.dataObjects || ln.dataObjects || ln.do || [];
            hierarchy.dos[lnRef] = dos.map(doObj => typeof doObj === 'object' ? doObj.name : String(doObj));
            
            // Try to get DAs from dataAttributes array (if available)
            const daList = details.dataAttributes || [];
            if (daList.length > 0) {
              // dataAttributes is an array of strings like "DOName.DAName"
              const daByDo = {};
              daList.forEach(daRef => {
                const parts = String(daRef).split('.');
                if (parts.length >= 2) {
                  const doName = parts[0];
                  const daName = parts.slice(1).join('.');
                  if (!daByDo[doName]) daByDo[doName] = [];
                  daByDo[doName].push(daName);
                }
              });
              
              // Store DAs by DO
              dos.forEach(doObj => {
                const doName = typeof doObj === 'object' ? doObj.name : String(doObj);
                const doRef = `${lnRef}.${doName}`;
                hierarchy.das[doRef] = daByDo[doName] || [];
              });
            } else {
              // Fallback: try to extract from dataObjects if they have da/daList
              dos.forEach(doObj => {
                const doName = typeof doObj === 'object' ? doObj.name : String(doObj);
                const doRef = `${lnRef}.${doName}`;
                const das = (doObj.data_attributes || doObj.dataAttributes || doObj.da || []).map(da => 
                  typeof da === 'object' ? da.name : String(da)
                );
                hierarchy.das[doRef] = das;
              });
            }
          });
        });
      }
      // Extract from tree structure (if model was transformed to tree with type/name/children)
      else if (data?.children) {
        data.children.forEach(node => {
          const nodeKind = node.kind || node.type;
          const nodeType = node.type || node.kind;
          
          if (nodeKind === 'LDevice' || nodeKind === 'LD' || nodeType === 'LDevice' || nodeType === 'server' || nodeType === 'Server') {
            // Handle root server node
            if (nodeType === 'server' || nodeType === 'Server' || nodeKind === 'Server') {
              node.children?.forEach(child => {
                const childKind = child.kind || child.type;
                const childType = child.type || child.kind;
                if (childKind === 'LDevice' || childKind === 'LD' || childType === 'LDevice') {
                  hierarchy.lds.push(child.name);
                  extractChildrenFromTree(child, child.name, 'LD', hierarchy);
                }
              });
            } else {
              hierarchy.lds.push(node.name);
              extractChildrenFromTree(node, node.name, 'LD', hierarchy);
            }
          } else if (nodeKind === 'IED' || nodeKind === 'Server' || nodeType === 'IED' || nodeType === 'Server') {
            // Also check for IED type nodes
            if (node.name && !hierarchy.lds.includes(node.name)) {
              hierarchy.lds.push(node.name);
            }
            // Extract children as LNs
            if (node.children) {
              node.children.forEach(child => {
                const childKind = child.kind || child.type;
                const childType = child.type || child.kind;
                if (childKind === 'LDevice' || childKind === 'LD' || childType === 'LDevice' || childType === 'LN' || childType === 'LogicalNode') {
                  const lnName = child.name || '';
                  if (lnName && !hierarchy.lns[node.name]) {
                    hierarchy.lns[node.name] = [];
                  }
                  if (lnName) {
                    hierarchy.lns[node.name].push(lnName);
                  }
                  extractChildrenFromTree(child, `${node.name}/${lnName}`, 'LN', hierarchy);
                }
              });
            }
          }
        });
      }
      // Extract from iedName/accessPoints structure
      else if (data?.accessPoints) {
        data.accessPoints.forEach(ap => {
          const apName = typeof ap === 'object' ? ap.name : String(ap);
          hierarchy.lds.push(apName);
          // Check for ldevices in access point
          if (ap.ldevices) {
            ap.ldevices.forEach(ld => {
              const ldName = typeof ld === 'object' ? ld.name : String(ld);
              // Add LNs if available
              if (ld.lnodes || ld.LN) {
                const lns = ld.lnodes || ld.LN || [];
                hierarchy.lns[ldName] = lns.map(ln => {
                  const lnName = typeof ln === 'object' ? ln.name : String(ln);
                  // Extract DOs and DAs from LNode
                  if (ln.dataObjects || ln.do || ln.DO) {
                    const lnRef = `${ldName}/${lnName}`;
                    const dos = (ln.dataObjects || ln.do || ln.DO || []).map(doObj => {
                      const doName = typeof doObj === 'object' ? doObj.name : String(doObj);
                      return doName;
                    });
                    hierarchy.dos[lnRef] = dos;
                    
                    dos.forEach((doName, idx) => {
                      const doObj = (ln.dataObjects || ln.do || ln.DO || [])[idx];
                      const doRef = `${lnRef}.${doName}`;
                      const das = (doObj.data_attributes || doObj.dataAttributes || doObj.da || []).map(da => 
                        typeof da === 'object' ? da.name : String(da)
                      );
                      hierarchy.das[doRef] = das;
                    });
                  }
                  return lnName;
                });
              }
            });
          }
        });
      }
      // Also try to extract from result.model.server structure (BFF response)
      else if (data?.result?.model?.server?.logicalDevices) {
        data = data.result.model;
        // Recursively process
        return extractHierarchyFromModel(data);
      }
    } catch (e) {
      // Silent error handling - model structure not recognized
    }
    
    return hierarchy;
  }, []);

  // Helper to extract from tree structure with kind/name/children (Server format)
  const extractFromKindTree = useCallback((node, parentRef, parentType, hierarchy) => {
    if (!node.children) return;
    
    node.children.forEach(child => {
      if (!child.name) return;
      
      const childRef = parentType === 'LD' ? `${parentRef}/${child.name}` : parentRef;
      
      if (child.kind === 'LN' || child.kind === 'LogicalNode') {
        // Add LN under parent (which should be LD)
        if (!hierarchy.lns[parentRef]) {
          hierarchy.lns[parentRef] = [];
        }
        if (!hierarchy.lns[parentRef].includes(child.name)) {
          hierarchy.lns[parentRef].push(child.name);
        }
        
        // Extract DOs and DAs from LN children
        const lnRef = parentType === 'LD' ? `${parentRef}/${child.name}` : parentRef;
        child.children?.forEach(doNode => {
          if (doNode.kind === 'DO' || doNode.kind === 'DataObject' || doNode.kind === 'SDO') {
            // Store DO under LN
            if (!hierarchy.dos[lnRef]) {
              hierarchy.dos[lnRef] = [];
            }
            if (!hierarchy.dos[lnRef].includes(doNode.name)) {
              hierarchy.dos[lnRef].push(doNode.name);
            }
            
            // Extract DAs from DO children
            const doRef = `${lnRef}.${doNode.name}`;
            const das = [];
            doNode.children?.forEach(daNode => {
              if (daNode.kind === 'DA' || daNode.kind === 'DataAttribute' || daNode.kind === 'SDA') {
                das.push(daNode.name);
              }
            });
            hierarchy.das[doRef] = das;
          }
        });
        
        // Recurse into LN
        extractFromKindTree(child, lnRef, 'LN', hierarchy);
      }
      else if (child.kind === 'LD' || child.kind === 'LDevice') {
        // Handle nested LDs
        if (!hierarchy.lds.includes(child.name)) {
          hierarchy.lds.push(child.name);
        }
        extractFromKindTree(child, child.name, 'LD', hierarchy);
      }
    });
  }, []);

  // Helper to extract children from tree nodes
  const extractChildrenFromTree = useCallback((node, parentRef, parentType, hierarchy) => {
    if (!node.children) return;
    
    node.children.forEach(child => {
      if (!child.name) return;
      
      const childType = child.type || child.kind;
      const childKind = child.kind || child.type;
      
      // Handle LogicalNode
      if (childType === 'LogicalNode' || childType === 'LN' || childKind === 'LN' || childKind === 'LogicalNode') {
        // Add to LNs under current LD
        if (!hierarchy.lns[parentRef]) {
          hierarchy.lns[parentRef] = [];
        }
        hierarchy.lns[parentRef].push(child.name);
        extractChildrenFromTree(child, `${parentRef}/${child.name}`, 'LN', hierarchy);
      }
      // Handle LDevice (can be nested under Server)
      else if (childType === 'LDevice' || childKind === 'LDevice' || childKind === 'LD') {
        // Add to LDs
        if (!hierarchy.lds.includes(child.name)) {
          hierarchy.lds.push(child.name);
        }
        // Extract children for this LD
        extractChildrenFromTree(child, child.name, 'LD', hierarchy);
      }
      // Handle DO, DataObject, SDO
      else if (childType === 'DO' || childType === 'DataObject' || childType === 'SDO' || childKind === 'DO' || childKind === 'DataObject' || childKind === 'SDO') {
        // Determine the parent reference for storing DOs
        // parentRef should be LD/LN for DO under LN, or LD for DO under LD
        const doParentRef = parentType === 'LN' ? parentRef : (parentType === 'LD' ? parentRef : parentRef);
        
        if (!hierarchy.dos[doParentRef]) {
          hierarchy.dos[doParentRef] = [];
        }
        hierarchy.dos[doParentRef].push(child.name);
        
        // For DO reference, use dot notation: LD/LN.DO or LD.DO
        const currentRef = parentType === 'LN' ? `${parentRef}.${child.name}` : `${parentRef}.${child.name}`;
        extractChildrenFromTree(child, currentRef, 'DO', hierarchy);
      }
      // Handle DA, DataAttribute, SDA
      else if (childType === 'DA' || childType === 'DataAttribute' || childType === 'SDA' || childKind === 'DA' || childKind === 'DataAttribute' || childKind === 'SDA') {
        // Store DAs under the DO reference (parentRef)
        const doRef = parentRef || '';
        if (!hierarchy.das[doRef]) {
          hierarchy.das[doRef] = [];
        }
        hierarchy.das[doRef].push(child.name);
      }
      // Handle Group nodes - recurse but keep parent type
      else if (childType === 'Group' || childType === 'DataSet' || childType === 'ReportControl' || childKind === 'Group' || childKind === 'DataSet' || childKind === 'ReportControl') {
        extractChildrenFromTree(child, parentRef, parentType, hierarchy);
      }
      // For other types (Server, etc.) - recurse with appropriate type
      else {
        // If it's a server node with children, extract LDs
        if (childType === 'Server' || childType === 'server' || childKind === 'Server' || childKind === 'server') {
          child.children?.forEach(c => {
            const cType = c.type || c.kind;
            const cKind = c.kind || c.type;
            if (cType === 'LDevice' || cKind === 'LDevice' || cKind === 'LD') {
              if (!hierarchy.lds.includes(c.name)) {
                hierarchy.lds.push(c.name);
              }
              extractChildrenFromTree(c, c.name, 'LD', hierarchy);
            }
          });
        }
        extractChildrenFromTree(child, parentRef, parentType, hierarchy);
      }
    });
  }, []);

  const handleFetchModel = useCallback(async () => {
    if (!selectedTarget || !selectedConnection || !updateModel) return;

    if (isWebsocketPassiveEndpoint && !manualCp.trim()) {
      setError('Please enter a cp value for this WebSocket Passive endpoint');
      return;
    }

    setFetchingModel(true);
    setError(null);

    try {
      if (getAcsiRole(selectedConnection) === 'client') {
        // ACSI Client endpoint = same call as ACSIClient.jsx's loadClientTree
        const result = await executeApiCall('model-tree', selectedTarget, {cp: effectiveCp});
        if (result?.ok) {
          updateModel(selectedTarget, result.payload);
          const hierarchy = extractHierarchyFromModel(result.payload);
          setAvailableLDs(hierarchy.lds);
          setSelectedLD(''); setSelectedLN(''); setSelectedDO('');
          setDoChildren([]); setAttributePath([]);
          setModelFetched(true);
          setFetchedCp(effectiveCp);
        } else {
          setError(result?.payload?.error || result?.rawText || 'Failed to fetch model');
        }
      } else {
        // ACSI Server endpoint - same normalization as ACSIServer.jsx's loadServerModel
        const result = await executeApiCall('model', selectedTarget, {cp: effectiveCp});
        if (result?.ok) {
          let modelData = result.payload;

          if (modelData?.result?.model) modelData = modelData.result.model;
          else if (modelData?.model) modelData = modelData.model;

          if (modelData?.tree) modelData = modelData.tree;

          if (typeof modelData === 'string') {
            try {
              modelData = JSON.parse(modelData);
            } catch (e) {
              modelData = parsePythonDictString(modelData);
            }
          }

          if (modelData === result.payload && modelData?.result) modelData = modelData.result;

          if (modelData?.accessPoints && !modelData.children && !modelData.ieds && !modelData.kind) {
            modelData = {
              iedName: modelData.iedName || selectedConnection.name || 'Server',
              accessPoints: modelData.accessPoints.map(apName => ({ name: apName, ldevices: [] })),
            };
          }

          if (modelData && Object.keys(modelData).length > 0) {
            updateModel(selectedTarget, modelData);
            const hierarchy = extractHierarchyFromModel(modelData);
            setAvailableLDs(hierarchy.lds);
            setSelectedLD(''); setSelectedLN(''); setSelectedDO('');
            setDoChildren([]); setAttributePath([]);
            setModelFetched(true);
            setFetchedCp(effectiveCp);
          } else {
            setError('No model data found in response');
          }
        } else {
          setError(result?.payload?.error || result?.rawText || 'Failed to fetch model');
        }
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setFetchingModel(false);
    }
  }, [selectedTarget, selectedConnection, cp, updateModel, extractHierarchyFromModel, parsePythonDictString, manualCp, isWebsocketPassiveEndpoint, effectiveCp]);

  // Populate dropdowns when endpoint or parent selection changes
  useEffect(() => {
    const targetChanged = prevTargetRef.current !== selectedTarget;
    prevTargetRef.current = selectedTarget;

    if (!selectedTarget) {
      setAvailableLDs([]);
      setAvailableLNs([]);
      setAvailableDOs([]);
      setDoChildren([]);
      setAttributePath([]);
      setModelFetched(false);
      if (targetChanged) {
        setManualCp('');
        setFetchedCp(null);
      }
      return;
    }

    // Get model for this endpoint
    const modelData = getModel ? getModel(selectedTarget) : null;
    setModelFetched(!!modelData);

    const hierarchy = extractHierarchyFromModel(modelData);
    setAvailableLDs(hierarchy.lds);

    // Only reset selections/cp when the endpoint actually changed - not when
    // this effect re-runs because getModel/extractHierarchyFromModel got new
    // identities from a parent re-render (e.g. after picking LD/LN/DO).
    if (targetChanged) {
      setSelectedLD('');
      setSelectedLN('');
      setSelectedDO('');
      setDoChildren([]);
      setAttributePath([]);
      setManualCp('');
      setFetchedCp(null);
    }
  }, [selectedTarget, getModel, extractHierarchyFromModel]);

  // Invalidate model state when effective cp changes
  useEffect(() => {
    if (fetchedCp === null) return;  // No model fetched yet for this target
    if (effectiveCp === fetchedCp) return;  // Still matches what's loaded

    // cp changed - invalidate model state
    setModelFetched(false);
    setAvailableLDs([]);
    setSelectedLD('');
    setSelectedLN('');
    setSelectedDO('');
    setDoChildren([]);
    setAttributePath([]);
  }, [effectiveCp, fetchedCp]);

  // Update LN dropdown when LD changes
  useEffect(() => {
    if (!selectedLD || !selectedTarget) {
      setAvailableLNs([]);
      setSelectedLN('');
      setSelectedDO('');
      setDoChildren([]);
      setAttributePath([]);
      return;
    }
    
    const modelData = getModel ? getModel(selectedTarget) : null;
    const hierarchy = extractHierarchyFromModel(modelData);
    
    setAvailableLNs(hierarchy.lns[selectedLD] || []);
  }, [selectedLD, selectedTarget, getModel, extractHierarchyFromModel]);

  // Update DO dropdown when LN changes
  useEffect(() => {
    if (!selectedLN || !selectedLD || !selectedTarget) {
      setAvailableDOs([]);
      setSelectedDO('');
      setDoChildren([]);
      setAttributePath([]);
      return;
    }
    
    const lnRef = `${selectedLD}/${selectedLN}`;
    const modelData = getModel ? getModel(selectedTarget) : null;
    const hierarchy = extractHierarchyFromModel(modelData);
    
    setAvailableDOs(hierarchy.dos[lnRef] || []);
  }, [selectedLN, selectedLD, selectedTarget, getModel, extractHierarchyFromModel]);

  // Update DA dropdown when DO changes
  useEffect(() => {
    if (!selectedDO || !selectedLN || !selectedLD || !selectedTarget) {
      setDoChildren([]);
      setAttributePath([]);
      return;
    }
    
    const doRef = `${selectedLD}/${selectedLN}.${selectedDO}`;
    setAttributePath([]);

    if (dataDefinitionCacheRef.current[doRef]) {
      setDoChildren(dataDefinitionCacheRef.current[doRef]);
      return;
    }

    const fetchDoDefinition = async () => {
      try {
        const lnRef = `${selectedLD}/${selectedLN}`;

        // For ACSI Client endpoints (SO), use data-definition API
        // For Server endpoints (FSP, true ACSI Server), extract from model
        if (getAcsiRole(selectedConnection) === 'client') {
          const result = await executeApiCall('data-definition', selectedTarget, {
            cp: effectiveCp,
            ld_inst: selectedLD,
            ln_inst: selectedLN,
            do_path: selectedDO,
          });

          if (result?.ok && result.payload) {
            const value = extractDataDefinitionValue(result.payload);
            const children = buildDoChildren(doRef, value);
            dataDefinitionCacheRef.current[doRef] = children;
            setDoChildren(children);
            return;
          }
        }

        // For Server endpoints (FSP, true ACSI Server), extract from the already-loaded model
        if (getAcsiRole(selectedConnection) === 'server' && getModel) {
          const modelData = getModel(selectedTarget);
          if (modelData) {
            const definitionValue = extractDoDefinitionFromModel(modelData, selectedLD, selectedLN, selectedDO);
            if (definitionValue) {
              const children = buildDoChildren(doRef, definitionValue);
              dataDefinitionCacheRef.current[doRef] = children;
              setDoChildren(children);
              return;
            }
          }
        }

        setDoChildren([]);
      } catch (error) {
        setDoChildren([]);
      }
    };

    fetchDoDefinition();
  }, [selectedDO, selectedLN, selectedLD, selectedTarget, cp, connectedEndpoints, manualCp, isWebsocketPassiveEndpoint]);

  const selectedNode = useMemo(() => {
    if (!attributePath.length) return null;
    return findNodeAtPath(doChildren, attributePath);
  }, [doChildren, attributePath]);

  // If the currently selected node is an SDO whose children haven't been fetched yet, fetch them
  useEffect(() => {
    if (!selectedNode || selectedNode.type !== 'SDO' || selectedNode.children !== null) return;

    const doPath = [selectedDO, ...attributePath].join('.');
    const definitionPath = `${selectedLD}/${selectedLN}.${doPath}`;

    if (dataDefinitionCacheRef.current[definitionPath]) {
      setDoChildren(prev => setChildrenAtPath(prev, attributePath, dataDefinitionCacheRef.current[definitionPath]));
      return;
    }

    const fetchSdoDefinition = async () => {
      try {
        const lnRef = `${selectedLD}/${selectedLN}`;

        // For ACSI Client endpoints, use data-definition API
        // For Server endpoints (FSP, true ACSI Server), extract from model
        if (getAcsiRole(selectedConnection) === 'client') {
          const result = await executeApiCall('data-definition', selectedTarget, {
            cp: effectiveCp,
            ld_inst: selectedLD,
            ln_inst: selectedLN,
            do_path: doPath,
          });

          if (result?.ok && result.payload) {
            const value = extractDataDefinitionValue(result.payload);
            const children = buildDoChildren(selectedNode.ref, value);
            dataDefinitionCacheRef.current[definitionPath] = children;
            setDoChildren(prev => setChildrenAtPath(prev, attributePath, children));
            return;
          }
        }

        // For Server endpoints (FSP, true ACSI Server), extract from the already-loaded model
        if (getAcsiRole(selectedConnection) === 'server' && getModel) {
          const modelData = getModel(selectedTarget);
          if (modelData) {
            // For SDOs, we need to find the nested path
            const definitionValue = extractDoDefinitionFromModel(modelData, selectedLD, selectedLN, doPath);
            if (definitionValue) {
              const children = buildDoChildren(selectedNode.ref, definitionValue);
              dataDefinitionCacheRef.current[definitionPath] = children;
              setDoChildren(prev => setChildrenAtPath(prev, attributePath, children));
              return;
            }
          }
        }

        setDoChildren(prev => setChildrenAtPath(prev, attributePath, []));
      } catch (error) {
        setDoChildren(prev => setChildrenAtPath(prev, attributePath, []));
      }
    };

    fetchSdoDefinition();
  }, [selectedNode, attributePath, selectedLD, selectedLN, selectedDO, selectedTarget, cp, connectedEndpoints, manualCp, isWebsocketPassiveEndpoint]);

  useEffect(() => {
    setSelectedFC(selectedNode?.fc ? String(selectedNode.fc).toUpperCase() : '');
  }, [selectedNode]);

  const handleAttributeLevelSelect = useCallback((depth, name) => {
    setAttributePath(prev => {
      const next = prev.slice(0, depth);
      if (name) next.push(name);
      return next;
    });
  }, []);

  // Format values for display
  const formatValuesForDisplay = useCallback((result) => {
    if (!result) return null;
    
    // Extract values from various possible locations
    let values = result?.result?.values || result?.values || result?.payload?.result?.values || result?.payload?.values;
    
    if (!values || !Array.isArray(values)) {
      // If it's not an array, try to display it as-is
      if (result?.result?.value !== undefined) {
        return { type: typeof result.result.value, value: result.result.value };
      }
      if (result?.result?.values !== undefined) {
        return { type: result.result.values.type, value: result.result.values.value };
      }
      return result;
    }
    
    // If there's only one value, return it directly
    if (values.length === 1) {
      return values[0];
    }
    
    // If multiple values, return the array
    return values;
  }, []);

  // Build object reference from selections
  const buildObjectRef = useCallback(() => {
    if (!selectedLD || !selectedLN || !selectedDO || !selectedNode) return '';
    if (selectedNode.type !== 'DA' && selectedNode.type !== 'SDA') return '';
    if (selectedNode.children && selectedNode.children.length > 0) return '';
    return selectedNode.ref;
  }, [selectedLD, selectedLN, selectedDO, selectedNode]);

  // Handle read operation
  const handleRead = useCallback(async () => {
    if (!selectedTarget) {
      setError('Please select an endpoint first');
      return;
    }
    
    const objRef = buildObjectRef();
    if (!objRef) {
      setError('Please select LD, LN, DO, and DA first');
      return;
    }
    
    setLoading(true);
    setError(null);
    setReadResult(null);
    
    try {
      // Add cp to body for ACSI client endpoints and WebSocket Passive endpoints
      const isAcsiClient = getAcsiRole(selectedConnection) === 'client';
      const body = {
        objRef: objRef,
        fc: selectedFC.toLowerCase() || 'st'
      };
      if (isAcsiClient || isWebsocketPassiveEndpoint) {
        body.cp = effectiveCp;
      }
      
      const result = await executeApiCall('read', selectedTarget, body);
      
      if (result?.ok) {
        setReadResult(result.payload);
      } else {
        setError(result?.payload?.error || result?.rawText || 'Failed to read value');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [selectedTarget, buildObjectRef, selectedFC, connections, cp, manualCp, isWebsocketPassiveEndpoint, effectiveCp]);

  // Handle write operation
  const handleWrite = useCallback(async () => {
    if (!selectedTarget) {
      setError('Please select an endpoint first');
      return;
    }

    if (!canWriteFc(selectedFC)) {
      setError(`Writing not allowed for FC "${selectedFC || 'unknown'}". Only CF and SP are writable.`);
      return;
    }
    
    const objRef = buildObjectRef();
    if (!objRef) {
      setError('Please select LD, LN, DO, and DA first');
      return;
    }
    
    if (!writeValue) {
      setError('Please enter a value to write');
      return;
    }
    
    setLoading(true);
    setError(null);
    setWriteResult(null);
    
    try {
      // Add cp to body for ACSI client endpoints and WebSocket Passive endpoints
      const isAcsiClient = getAcsiRole(selectedConnection) === 'client';
      
      // Get the daType for the selected DA
      const valueType = selectedNode?.bType || null;
      
      const body = {
        objRef: objRef,
        value: writeValue,
        fc: selectedFC.toLowerCase() || 'st'
      };
      if (valueType) {
        body.dataType = valueType;
      }
      if (isAcsiClient || isWebsocketPassiveEndpoint) {
        body.cp = effectiveCp;
      }
      
      const result = await executeApiCall('write', selectedTarget, body);
      
      if (result?.ok) {
        setWriteResult(result.payload);
      } else {
        setError(result?.payload?.error || result?.rawText || 'Failed to write value');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [selectedTarget, buildObjectRef, writeValue, selectedFC, connections, cp, selectedNode, manualCp, isWebsocketPassiveEndpoint, effectiveCp]);

  // Reset selections and results
  const handleReset = useCallback(() => {
    setSelectedTarget('');
    setSelectedLD('');
    setSelectedLN('');
    setSelectedDO('');
    setDoChildren([]);
    setAttributePath([]);
    setWriteValue('');
    setReadResult(null);
    setWriteResult(null);
    setError(null);
    setManualCp('');
    setFetchedCp(null);
    setOperateResult(null);
  }, []);

  return (
    <div style={{ 
      border: '1px solid var(--border-color)', 
      borderRadius: '8px', 
      padding: '16px',
      background: 'var(--bg-card)'
    }}>
      <h3 style={{ margin: 0, marginBottom: '16px', color: 'var(--text-secondary)' }}>
        {getAcsiRole(selectedConnection) === 'client'
            ? 'ACSI Client - Read or write to ACSI Server'
            : 'Read or write to ACSI Server' }
      </h3>
      
      {/* Endpoint Selection */}
      <div style={{ marginBottom: '12px' }}>
        <label style={{ display: 'block', marginBottom: '4px', fontSize: '12px', color: 'var(--text-muted)' }}>
          Endpoint
        </label>
        <select
          value={selectedTarget}
          onChange={(e) => setSelectedTarget(e.target.value)}
          style={{ width: '100%', padding: '8px', borderRadius: '4px', background: 'var(--bg-hover)', border: '1px solid var(--border-color)' }}
          disabled={connectedEndpoints.length === 0}
        >
          <option value="">Select connected endpoint...</option>
          {connectedEndpoints.map(conn => (
            <option key={buildTargetValue(conn.host, conn.port)} value={buildTargetValue(conn.host, conn.port)}>
              {conn.name || `${conn.host}:${conn.port}`} ({conn.type})
            </option>
          ))}
        </select>
        {selectedTarget && (
          <div style={{ 
            marginTop: '4px', 
            fontSize: '11px', 
            color: 'var(--text-muted)',
            fontStyle: 'italic'
          }}>
            ACSI: {getAcsiRole(selectedConnection) || 'Unknown'}
          </div>
        )}
      </div>

      {selectedTarget && (
          <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
            <button
              onClick={handleFetchModel}
              disabled={modelFetched || fetchingModel || (isWebsocketPassiveEndpoint && !manualCp.trim())}
              className="btn-secondary"
              style={{ flex: 1 }}
            >
              {fetchingModel ? 'Fetching Model...' : modelFetched ? 'Model Loaded ✓' : 'Fetch Model'}
            </button>
            {isWebsocketPassiveEndpoint && (
              <input
                type="text"
                value={manualCp}
                onChange={(e) => {
                  const newCp = e.target.value;
                  setManualCp(newCp);
                  // Typing a new cp invalidates whatever model was loaded for the old one
                  if (modelFetched) {
                    setModelFetched(false);
                    setAvailableLDs([]);
                    setSelectedLD('');
                    setSelectedLN('');
                    setSelectedDO('');
                    setDoChildren([]);
                    setAttributePath([]);
                  }
                }}
                placeholder="cp (e.g. cp1)"
                title="Connection point (cp) — required for WebSocket Passive endpoints"
                style={{
                  width: '110px',
                  padding: '8px',
                  borderRadius: '4px',
                  background: 'var(--bg-hover)',
                  border: manualCp.trim() ? '1px solid var(--border-color)' : '1px solid var(--danger-color)'
                }}
              />
            )}
          </div>
      )}

      {/* Cascading Selection Row */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', marginBottom: '12px'}}>
        <div style={{ minWidth: '160px', flex: '1 1 160px' }}>
          <label style={{ display: 'block', marginBottom: '4px', fontSize:'12px', color: 'var(--text-muted)'}}>
            LD (Logical Device)
          </label>
          <select
            value={selectedLD}
            onChange={(e) => setSelectedLD(e.target.value)}
            style={{ width: '100%', padding: '8px', borderRadius: '4px', background: 'var(--bg-hover)', border: '1px solid var(--border-color)'}}
            disabled={!selectedTarget || availableLDs.length === 0}
          >
            <option value="">Select LD...</option>
            {availableLDs.map(ld => <option key={String(ld)} value={ld}>{ld}</option>)}
          </select>
        </div>

        <div style={{ minWidth: '160px', flex: '1 1 160px' }}>
          <label style={{ display: 'block', marginBottom: '4px', fontSize: '12px', color: 'var(--text-muted)' }}>
            LN (Logical Node)
          </label>
          <select
            value={selectedLN}
            onChange={(e) => setSelectedLN(e.target.value)}
            style={{ width: '100%', padding: '8px', borderRadius: '4px', background: 'var(--bg-hover)', border: '1px solid var(--border-color)' }}
            disabled={!selectedLD || availableLNs.length === 0}
          >
            <option value="">Select LN...</option>
            {availableLNs.map(ln => <option key={String(ln)} value={ln}>{ln}</option>)}
          </select>
        </div>

         <div style={{ minWidth: '160px', flex: '1 1 160px' }}>
          <label style={{ display: 'block', marginBottom: '4px', fontSize: '12px', color: 'var(--text-muted)' }}>
            DO (Data Object)
          </label>
          <select
            value={selectedDO}
            onChange={(e) => setSelectedDO(e.target.value)}
            style={{ width: '100%', padding: '8px', borderRadius: '4px', background: 'var(--bg-hover)', border: '1px solid var(--border-color)' }}
            disabled={!selectedLN || availableDOs.length === 0}
          >
            <option value="">Select DO...</option>
            {availableDOs.map(doObj => <option key={String(doObj)} value={doObj}>{doObj}</option>)}
          </select>
        </div>

        {selectedDO && (() => {
          const levels = [];
          let nodes = doChildren;
          for (let depth = 0; depth <= attributePath.length; depth++) {
            levels.push({depth, nodes});
            const name = attributePath[depth];
            if (!name) break;
            const chosen = nodes.find(n => n.name === name);
            if (!chosen) break;
            if (chosen.children === null) {
              levels.push({depth: depth + 1, nodes: null});
              break;
            }
            nodes = chosen.children;
            if (nodes.length === 0) break;
          }
          return levels.map(({depth, nodes: levelNodes}) => (
              <div key={depth} style={{ minWidth: '160px', flex: '1 1 160px'}}>
                <label style={{ display: 'block', marginBottom: '4px', fontSize: '12px', color: 'var(--text-muted)'}}>
                  {depth === 0 ? 'DA / SDO' : 'DA / SDA'}
                </label>
                <select
                  value={attributePath[depth] || ''}
                  onChange={(e) => handleAttributeLevelSelect(depth, e.target.value)}
                  style={{ width: '100%', padding: '8px', borderRadius: '4px', background: 'var(--bg-hover)', border: '1px solid var(--border-color)'}}
                  disabled={levelNodes === null || levelNodes.length === 0}
                >
                  <option value="">{levelNodes === null ? 'Loading...' : 'Select...'}</option>
                  {levelNodes?.map(n => (
                      <option key={n.ref} value={n.name}>
                        {n.name} [{n.type}{n.fc ? `, ${n.fc.toUpperCase()}` : ''}]
                      </option>
                  ))}
                </select>
              </div>
          ));
        })()}
      </div>

      {/* Object Reference Display */}
      {selectedLD && selectedLN && selectedDO && buildObjectRef() && (
        <div style={{ 
          marginBottom: '16px', 
          padding: '8px 12px', 
          background: 'var(--bg-hover)', 
          borderRadius: '4px',
          fontFamily: 'monospace',
          fontSize: '13px',
          color: 'var(--text-secondary)'
        }}>
          Object Reference: {buildObjectRef()}
          {selectedFC && (
              <span style={{ marginLeft: '8px', color: 'var(--text-muted)' }}>
                [{selectedFC}]
                {isServerEndpoint ? (
                    <span style={{ color: 'var(--success-color)', marginLeft: '6px' }}>
                      (unrestricted - ACSI Server)
                    </span>
                ) : !isWritableFc(selectedFC) ? (
                    <span style={{ color: 'var(--text-muted)', marginLeft: '6px' }}>
                      (read-only - ACSI Client)
                    </span>
                ) : null}
              </span>
          )}
        </div>
      )}
      
      {/* Write Value Input - only for writable FCs */}
      {buildObjectRef() && canWriteFc(selectedFC) && (
        <div style={{ marginBottom: '16px' }}>
          <label style={{ display: 'block', marginBottom: '4px', fontSize: '12px', color: 'var(--text-muted)' }}>
            Value to Write
          </label>
          <input
            type="text"
            value={writeValue}
            onChange={(e) => setWriteValue(e.target.value)}
            placeholder="Enter value (e.g., true, 100, 'text')"
            style={{
              width: '100%',
              padding: '8px',
              borderRadius: '4px',
              background: 'var(--bg-hover)',
              border: '1px solid var(--border-color)'
            }}
          />
        </div>
      )}
      {buildObjectRef() && !canWriteFc(selectedFC) && (
          <div style={{ marginBottom: '16px', fontSize: '12px', color: 'var(--text-muted)', fontStyle: 'italic'}}>
            Read-only attribute (FC: {selectedFC || 'unknown'}) - writing is only enabled for CF/SP.
          </div>
      )}

      {/* Operate Button - shown for ACSI Client endpoints with controllable DO/SDO */}
      {showOperateButton && (
        <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
          <button
            onClick={handleOperateClick}
            className="btn-primary"
            style={{ flex: 1 }}
            title="Operate on controllable DO/SDO"
          >
            Operate
          </button>
        </div>
      )}

      {/* Action Buttons */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
        <button
          onClick={handleRead}
          disabled={!buildObjectRef() || loading}
          className="btn-primary"
          style={{ flex: 1 }}
        >
          {loading ? 'Reading...' : 'Read'}
        </button>
        <button
          onClick={handleWrite}
          disabled={!buildObjectRef() || !writeValue || loading || !canWriteFc(selectedFC)}
          className="btn-secondary"
          style={{ flex: 1 }}
        >
          {loading ? 'Writing...' : 'Write'}
        </button>
        <button
          onClick={handleReset}
          disabled={loading}
          className="btn-secondary"
          style={{ padding: '8px 12px' }}
          title="Clear selections"
        >
          <i className="fas fa-times"></i>
        </button>
      </div>
      
      {/* Results Display */}
      {error && (
        <div style={{ 
          padding: '12px', 
          background: 'var(--danger-bg)', 
          color: 'var(--danger-color)', 
          borderRadius: '4px',
          marginBottom: '12px',
          fontSize: '13px'
        }}>
          <i className="fas fa-exclamation-circle" style={{ marginRight: '8px' }}></i>
          {error}
        </div>
      )}
      
      {readResult && (
        <div style={{ 
          padding: '12px', 
          background: 'var(--info-bg)', 
          color: 'var(--info-color)', 
          borderRadius: '4px',
          marginBottom: '12px'
        }}>
          <strong style={{ display: 'block', marginBottom: '4px' }}>Read Result:</strong>
          <div style={{ fontFamily: 'monospace', fontSize: '12px' }}>
            {(() => {
              const formatted = formatValuesForDisplay(readResult);
              if (!formatted) return null;
              
              if (Array.isArray(formatted)) {
                return formatted.map((v, i) => (
                  <div key={i} style={{ marginBottom: '4px' }}>
                    Type: <strong>{v.type}</strong>, Value: <strong>{JSON.stringify(v.value)}</strong>
                  </div>
                ));
              }
              
              // Single value object
              return <div>
                Type: <strong>{formatted.type}</strong>, Value: <strong>{JSON.stringify(formatted.value)}</strong>
              </div>;
            })()}
          </div>
        </div>
      )}
      
      {writeResult && (
        <div style={{ 
          padding: '12px', 
          background: 'var(--success-bg)', 
          color: 'var(--success-color)', 
          borderRadius: '4px',
          marginBottom: '12px'
        }}>
          <strong style={{ display: 'block', marginBottom: '4px' }}>Write Result:</strong>
          <div style={{ fontFamily: 'monospace', fontSize: '12px' }}>
            {(() => {
              const success = writeResult?.result?.success ?? writeResult?.payload?.result?.success ?? writeResult?.success;
              const value = writeResult?.result?.value ?? writeResult?.payload?.result?.value ?? writeResult?.value;
              return <div>
                Status: <strong style={{ color: success ? 'var(--success-color)' : 'var(--danger-color)' }}>
                  {success ? 'Success' : 'Failed'}
                </strong>
                {value !== undefined && <>, Value: <strong>{JSON.stringify(value)}</strong></>}
              </div>;
            })()}
          </div>
        </div>
      )}

      {operateResult && (
        <div style={{
          padding: '12px',
          background: operateResult.success ? 'var(--success-bg)' : 'var(--danger-bg)',
          color: operateResult.success ? 'var(--success-color)' : 'var(--danger-color)',
          borderRadius: '4px',
          marginBottom: '12px'
        }}>
          <i className={`fas fa-${operateResult.success ? 'check-circle' : 'exclamation-circle'}`} style={{ marginRight: '8px' }}></i>
          {operateResult.message}
        </div>
      )}

      {/* ControlModal for DO/SDO operations */}
      {showControlModal && (
        <ControlModal
          objRef={controlModalTarget.ref}
          objName={controlModalTarget.name}
          cdc={controlModalTarget.cdc}
          endpoint={controlModalTarget.endpoint}
          cp={controlModalTarget.cp}
          onClose={() => {
            setShowControlModal(false);
            setControlModalTarget({ ref: '', name: '', cdc: '', endpoint: null, cp: null });
          }}
          onSuccess={(payload) => {
            const deviceMsg = payload?.result?.message || payload?.message;
            setOperateResult({
              success: true,
              message: deviceMsg
                ? `Operate succeeded on ${controlModalTarget.name}: ${deviceMsg}`
                : `Operate succeeded on ${controlModalTarget.name}`
            });
            setShowControlModal(false);
            setControlModalTarget({ ref: '', name: '', cdc: '', endpoint: null, cp: null });
          }}
          onError={(errMsg) => {
            setOperateResult({
              success: false,
              message: `Operate failed on ${controlModalTarget.name}: ${errMsg}`
            });
            // Leave the modal open on failure, same as ControlModal's own
            // inline error behavior, so the user can adjust and retry.
          }}
        />
      )}
      </div>
  );
}

export default DataAccessPanel;
