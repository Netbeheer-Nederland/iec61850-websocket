// src/pages/ACSIClient.jsx
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import Tree from '../components/Tree';
import ContextMenu from '../components/ContextMenu';
import ControlModal from '../components/ControlModal';
import WriteValueModal from '../components/WriteValueModal';
import BrcbConfigModal from '../components/BrcbConfigModal';
import TLSConfigModal from '../components/TLSConfigModal';
import { executeApiCall, buildTargetValue, getApiById } from '../services/apiService';

const CONTROLLABLE_CDCS = ['SPC', 'DPC', 'APC', 'INC', 'ENC', 'BSC', 'ING', 'ASG', 'CTE', 'ENG'];

const ACSIClient = ({ updateModel, bffBaseUrl = 'http://localhost:5000', connections: propConnections = [] }) => {
  const location = useLocation();
  const endpoint = location.state?.endpoint;
  // Store the original API endpoint (BFF) - this is used for all API calls
  // WS host/port are only used in the body of connect/disconnect calls
  const apiTarget = endpoint ? `${endpoint.host}:${endpoint.port}` : null;
  const [wsHost, setWsHost] = useState('127.0.0.1');
  const [wsPort, setWsPort] = useState(8765);
  const [wsCp, setWsCp] = useState(endpoint?.cp || 'cp1');
  const [connected, setConnected] = useState(() => localStorage.getItem('acsi-connected') === 'true');
  const [clientTrees, setClientTrees] = useState({}); // cp -> tree object, keyed so each client keeps its own model
  const [clientLoading, setClientLoading] = useState({}); // cp -> boolean, tracks in-flight "Fetch Model" per client
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [statusInfo, setStatusInfo] = useState(null);
  const [protocolMessages, setProtocolMessages] = useState([]);
  const [isMonitoring, setIsMonitoring] = useState(false);
  const [contextMenu, setContextMenu] = useState({ visible: false, x: 0, y: 0 });
  const [contextMenuTarget, setContextMenuTarget] = useState(null);
  const [showControlModal, setShowControlModal] = useState(false);
  const [showWriteModal, setShowWriteModal] = useState(false);
  const [connections, setConnections] = useState([]);
  const [acsiClientList, setAcsiClientList] = useState([]);
  const [expandedClients, setExpandedClients] = useState({});
  const statusIntervalRef = useRef(null);
  const doDefinitionCacheRef = useRef({});

  // Fetch connections from BFF to get IDP-Server instances
  useEffect(() => {
    const fetchConnections = async () => {
      try {
        const url = `${bffBaseUrl}/api/connections`;
        const response = await fetch(url);
        if (response.ok) {
          const data = await response.json();
          setConnections(data.connections || []);
        }
      } catch (error) {
        console.error('Failed to fetch connections:', error);
      }
    };
    
    if (bffBaseUrl) {
      fetchConnections();
    }
  }, [bffBaseUrl]);

  // Fetch OAuth status from the SO server on page load
  useEffect(() => {
    const fetchOAuthStatus = async () => {
      if (!apiTarget) return;
      try {
        const result = await executeApiCall('oauth-status', apiTarget, {});
        if (result?.ok) {
          const enableOAuth = result.payload?.result?.enable_oauth ?? result.payload?.enable_oauth ?? false;
          setUseOAuth(enableOAuth);
        }
      } catch (error) {
        console.error('Failed to fetch OAuth status:', error);
      }
    };
    fetchOAuthStatus();
  }, [apiTarget]);

  // Fetch properties (includes acsi_client_list) on page load
  useEffect(() => {
    const fetchProperties = async () => {
      if (!apiTarget) return;
      try {
        const result = await executeApiCall('properties', apiTarget, {});
        if (result?.ok) {
          const clientList = result.payload?.result?.acsi_client_list || result.payload?.acsi_client_list || [];
          setAcsiClientList(Array.isArray(clientList) ? clientList : []);
        }
      } catch (error) {
        console.error('Failed to fetch properties:', error);
      }
    };
    fetchProperties();
  }, [apiTarget]);

  const [showBrcbConfigModal, setShowBrcbConfigModal] = useState(false);
  const [showTLSModal, setShowTLSModal] = useState(false);
  const [useOAuth, setUseOAuth] = useState(false);
  const [message, setMessage] = useState(null);
  const monitorIntervalRef = useRef(null);

  useEffect(() => {
    localStorage.setItem('acsi-connected', String(connected));
  }, [connected]);

  // Keep wsHost/wsPort in sync with the live status response — the user
  // can't edit these; they always reflect what the SO server reports.
  useEffect(() => {
    const liveHost = statusInfo?.result?.host;
    const livePort = statusInfo?.result?.port;
    if (liveHost !== undefined && liveHost !== null) setWsHost(liveHost);
    if (livePort !== undefined && livePort !== null) setWsPort(livePort);
  }, [statusInfo]);

  // apiTarget for WS connection display (can be edited by user)
  const wsEndpointTarget = `${wsHost}:${wsPort}`;

  const [writeModalTarget, setWriteModalTarget] = useState({ ref: '', fc: '', endpoint: null, cp: null });
  const [controlModalTarget, setControlModalTarget] = useState({ ref: '', name: '', cdc: '', endpoint: null, cp: null });
  const [brcbConfigTarget, setBrcbConfigTarget] = useState({ ref: '', rcbType: '', endpoint: null, cp: null });

  // Stop monitoring
  const stopMonitoring = useCallback(() => {
    if (monitorIntervalRef.current) {
      clearInterval(monitorIntervalRef.current);
      monitorIntervalRef.current = null;
    }
    setIsMonitoring(false);
  }, []);

    const [expandedNodesByClient, setExpandedNodesByClient] = useState({}); // cp -> { [nodeRef]: bool }

    const handleExpandToggle = useCallback((cp, nodeRef, isExpanded) => {
      setExpandedNodesByClient((prev) => ({
        ...prev,
        [cp]: { ...(prev[cp] || {}), [nodeRef]: isExpanded },
      }));
    }, []);

    const toggleClientExpanded = useCallback((cp) => {
      setExpandedClients((prev) => ({ ...prev, [cp]: !prev[cp] }));
    }, []);


  // Load status
  const loadStatus = useCallback(async () => {
    if (!apiTarget) return;
    try {
      const result = await executeApiCall('status', apiTarget, null);
      if (result?.ok) setStatusInfo(result.payload);
    } catch (error) {
      console.error('Failed to load status:', error);
    }
  }, [apiTarget]);

    // Auto-poll SO status when endpoint is available — same pattern as
    // ACSIServer.jsx, so the connection status and host/port stay fresh
    // without requiring a manual "Reload Status" click.
    useEffect(() => {
      if (!apiTarget) return;
      loadStatus(); // immediate fetch on mount / target change
      statusIntervalRef.current = setInterval(loadStatus, 10000);
      return () => {
        if (statusIntervalRef.current) {
          clearInterval(statusIntervalRef.current);
          statusIntervalRef.current = null;
        }
      };
    }, [apiTarget, loadStatus]);

  // Fetch action logs
  const fetchActionLogs = useCallback(async () => {
    if (!apiTarget) return;
    try {
      const result = await executeApiCall('actions-logs', apiTarget, {});
      if (result?.ok) {
        const actions = result.payload.result?.actions || result.payload.actions || [];
        if (Array.isArray(actions) && actions.length > 0) {
          setProtocolMessages((prev) => {
            const existingIds = new Set(prev.map((msg) => msg.id));
            const newMessages = actions
              .filter((msg) => msg && msg.id && !existingIds.has(msg.id))
              .map((msg) => ({ ...msg, timestamp: new Date().toLocaleTimeString() }));
            return [...newMessages, ...prev].slice(0, 30);
          });
        }
      }
    } catch (error) {
      console.error('Failed to fetch action logs:', error);
    }
  }, [apiTarget]);

  // Start monitoring
  const startMonitoring = useCallback(async () => {
    if (isMonitoring) return;
    if (!apiTarget) {
      setError('No API endpoint configured');
      return;
    }
    stopMonitoring();
    setIsMonitoring(true);
    await fetchActionLogs();
    monitorIntervalRef.current = setInterval(fetchActionLogs, 5000);
  }, [isMonitoring, apiTarget, fetchActionLogs, stopMonitoring]);

  // Clear messages
  const clearMessages = useCallback(async () => {
    if (!apiTarget) {
      setError('No API endpoint configured');
      return;
    }
    const result = await executeApiCall('clear-logs', apiTarget, {});
    if (result?.ok) setProtocolMessages([]);
    else setError(`Error clearing messages: ${result?.payload?.error || 'Unknown error'}`);
  }, [apiTarget]);

  // Load model tree
  // cpParam lets callers (accordion "Fetch Model" buttons) target a specific
  // cp; each cp's fetched tree is kept independently in clientTrees.
  const loadClientTree = useCallback(async (cpParam) => {
    if (!apiTarget) {
      setError('No API endpoint configured');
      return;
    }
    const cpToUse = cpParam || wsCp;
    setClientLoading((prev) => ({ ...prev, [cpToUse]: true }));
    setError(null);
    try {
      const result = await executeApiCall('model-tree', apiTarget, { cp: cpToUse });
      if (result?.ok) {
        const tree = transformTree(result.payload);
        setClientTrees((prev) => ({
          ...prev,
          [cpToUse]: tree.length > 0 ? { name: 'Server', type: 'server', children: tree } : null,
        }));
        if (updateModel) {
          updateModel(apiTarget, result.payload);
        }
      } else {
        setError(result?.payload?.error || result?.rawText || 'Failed to fetch model');
      }
    } catch (error) {
      setError(error.message);
    } finally {
      setClientLoading((prev) => ({ ...prev, [cpToUse]: false }));
    }
  }, [apiTarget, wsCp]);

  // Transform API response to tree structure
  const transformTree = (data) => {
  if (!data.result?.model?.server?.logicalDevices) return [];
  const lds = data.result.model.server.logicalDevices;
  const logicalDeviceMap = data.result.model.logicalDeviceMap || {};
  const logicalNodeDetails = data.result.model.logicalNodeDetails || {};
  return lds.map((ld) => {
    const ldName = typeof ld === 'object' ? ld.name : ld;
    const lns = logicalDeviceMap[ldName] || [];
    const children = lns.map((ln) => {
      const lnName = typeof ln === 'object' ? (ln.name || ln.ln_class) : ln;
      const lnRef = `${ldName}/${lnName}`;
      const details = logicalNodeDetails[lnRef] || {};
      const dataSets = details.dataSets || [];
      const reportControls = details.reportControlBlocks || [];
      const dataObjects = details.dataObjects || ln.dataObjects || ln.do || [];

      // Group DataSets
      const dsChildren = dataSets.map((ds) => ({
        name: typeof ds === 'object' ? ds.name : ds,
        type: 'DataSet',
        ref: `${lnRef}.${typeof ds === 'object' ? ds.name : ds}`,
        children: [],
      }));

      // Group ReportControls
      const rcChildren = reportControls.map((rcb) => ({
        name: typeof rcb === 'object' ? rcb.name : rcb,
        type: typeof rcb === 'object' ? rcb.type : 'ReportControl',
        ref: `${lnRef}.${typeof rcb === 'object' ? rcb.name : rcb}`,
        children: [],
        rcbType: typeof rcb === 'object' ? rcb.type : 'ReportControl',
      }));

      // Process DataObjects
      const doChildren = dataObjects.map((doObj) => {
        const doName = typeof doObj === 'object' ? doObj.name : doObj;
        const doRef = `${lnRef}.${doName}`;
        const das = (doObj.data_attributes || doObj.dataAttributes || doObj.da || []).map((da) => {
          const daName = typeof da === 'object' ? da.name : da;
          const daRef = `${doRef}.${daName}`;
          const subDas = (da.subDataAttributes || da.sub_attributes || da.sda || []).map((sda) => {
            const sdaName = typeof sda === 'object' ? sda.name : sda;
            const sdaRef = `${daRef}.${sdaName}`;
            return {
              name: sdaName,
              type: 'SDA',
              ref: sdaRef,
              fc: da.fc || doObj.fc || '',
              bType: sda.bType || '',
              children: [],
            };
          });
          return {
            name: daName,
            type: 'DA',
            ref: daRef,
            fc: da.fc || doObj.fc || '',
            bType: da.bType || '',
            children: subDas,
          };
        });

        // Process SDOs
        const sdoChildren = (doObj.subDataObjects || doObj.sub_data_objects || []).map((sdo) => {
          const sdoName = typeof sdo === 'object' ? sdo.name : sdo;
          const sdoRef = `${doRef}.${sdoName}`;
          const sdoDas = (sdo.dataAttributes || sdo.data_attributes || []).map((sdoDa) => {
            const sdoDaName = typeof sdoDa === 'object' ? sdoDa.name : sdoDa;
            const sdoDaRef = `${sdoRef}.${sdoDaName}`;
            return {
              name: sdoDaName,
              type: 'SDA',
              ref: sdoDaRef,
              fc: sdoDa.fc || doObj.fc || '',
              bType: sdoDa.bType || '',
              children: [],
            };
          });
          return {
            name: sdoName,
            type: 'SDO',
            ref: sdoRef,
            cdc: sdo.cdc || '',
            children: sdoDas,
          };
        });

        return {
          name: doName,
          type: 'DO',
          ref: doRef,
          fc: doObj.fc || '',
          cdc: doObj.cdc || '',
          children: [...das, ...sdoChildren],
        };
      });

      return {
        name: lnName,
        type: 'LogicalNode',
        ref: lnRef,
        children: [
          ...(dsChildren.length > 0 ? [{ name: 'DataSets', type: 'Group', children: dsChildren }] : []),
          ...(rcChildren.length > 0 ? [{ name: 'ReportControls', type: 'Group', children: rcChildren }] : []),
          ...doChildren,
        ],
      };
    });
    return {
      name: ldName,
      type: 'LDevice',
      ref: ldName,
      children,
    };
  });
};

  // Format value for display - matching the JS version logic
  const formatValueForDisplay = useCallback((valueData, isError = false) => {
    if (isError) {
      return { display: '✗ Error', color: '#c62828' };
    }

    function asn1TimeStampToISOString(ts) {
      if (!ts || typeof ts.secondSinceEpoch !== 'number') return '';
      const seconds = ts.secondSinceEpoch;
      let ms = 0;
      if (typeof ts.fractionOfSecond === 'number') {
        ms = Math.floor(ts.fractionOfSecond / 1000);
      }
      const date = new Date((seconds * 1000) + ms);
      return date.toISOString();
    }

    function extractActualValue(val) {
      if (Array.isArray(val) && val.length > 0 && val[0] && val[0].data) {
        const dataObj = val[0].data;
        if (typeof dataObj === 'object' && !Array.isArray(dataObj)) {
          const keys = Object.keys(dataObj);
          if (keys.length === 1) {
            return dataObj[keys[0]];
          }
        }
        return dataObj;
      }
      return val;
    }

    if (Array.isArray(valueData) && valueData.length > 0) {
      const firstItem = valueData[0];

      if (firstItem && firstItem.data && Array.isArray(firstItem.data)) {
        if (firstItem.data.length === 2 &&
            typeof firstItem.data[0] === 'string' &&
            firstItem.data[0] === 'structure') {
          return { display: '—', color: '#4caf50' };
        }

        if (firstItem.data.length === 2 && typeof firstItem.data[0] === 'string') {
          const value = firstItem.data[1];
          let displayValue = value;
          if (value && typeof value === 'object' && typeof value.secondSinceEpoch === 'number') {
            displayValue = asn1TimeStampToISOString(value) || JSON.stringify(value);
          } else if (typeof value === 'number') {
            displayValue = value.toFixed(2);
          } else if (typeof value === 'boolean') {
            displayValue = value ? 'true' : 'false';
          } else if (typeof value === 'object') {
            displayValue = JSON.stringify(value);
          }
          return { display: displayValue, color: '#4caf50' };
        }
      }
    }

    const actualValue = extractActualValue(valueData);
    return { display: JSON.stringify(actualValue), color: '#4caf50' };
  }, []);

  // Read data value
  const readDataValue = useCallback(
    async (objRef, fc, cpParam) => {
      if (!apiTarget) {
        setError('No endpoint configured');
        return;
      }
      const cpToUse = cpParam || wsCp;
      const applyToTree = (valueData, isError) => {
        setClientTrees((prevTrees) => {
          const tree = prevTrees[cpToUse];
          if (!tree) return prevTrees;
          const formatted = formatValueForDisplay(valueData, isError);
          const updateTreeWithValue = (nodes) =>
            nodes.map((node) =>
              node.ref === objRef ? { ...node, value: formatted.display, valueColor: formatted.color } :
              node.children ? { ...node, children: updateTreeWithValue(node.children) } : node
            );
          return { ...prevTrees, [cpToUse]: { ...tree, children: updateTreeWithValue(tree.children) } };
        });
      };
      try {
        const result = await executeApiCall('read', apiTarget, { objRef, fc, cp: cpToUse });
        if (result?.ok) {
          const valueData = result.payload?.result?.value;
          if (valueData) applyToTree(valueData, false);
        } else {
          applyToTree(result?.payload?.error || 'Unknown error', true);
        }
      } catch (error) {
        applyToTree(error.message, true);
      }
    },
    [apiTarget, wsCp, formatValueForDisplay]
  );

  // Write data value
  const writeDataValue = useCallback(
    async (objRef, fc, value, value_type, cpParam) => {
      if (!apiTarget) {
        setError('No endpoint configured');
        throw new Error('No endpoint configured');
      }
      const cpToUse = cpParam || wsCp;
      const applyToTree = (valueData, isError) => {
        setClientTrees((prevTrees) => {
          const tree = prevTrees[cpToUse];
          if (!tree) return prevTrees;
          const formatted = formatValueForDisplay(valueData, isError);
          const updateTreeWithValue = (nodes) =>
            nodes.map((node) =>
              node.ref === objRef ? { ...node, value: formatted.display, valueColor: formatted.color } :
              node.children ? { ...node, children: updateTreeWithValue(node.children) } : node
            );
          return { ...prevTrees, [cpToUse]: { ...tree, children: updateTreeWithValue(tree.children) } };
        });
      };
      try {
        const result = await executeApiCall('write', apiTarget, { objRef, fc, value, value_type, cp: cpToUse });
        if (result?.ok) {
          const valueData = result.payload?.result?.value || value;
          if (valueData) applyToTree(valueData, false);
          return result;
        } else {
          const errorMsg = result?.payload?.error || result?.rawText || 'Write failed';
          setError(`Write failed: ${errorMsg}`);
          throw new Error(errorMsg);
        }
      } catch (error) {
        applyToTree(error.message, true);
        setError(error.message);
        throw error;
      }
    },
    [apiTarget, wsCp, formatValueForDisplay]
  );

  // Cache of DO definitions used ONLY to decide context-menu availability.
  // Deliberately separate from clientTrees so checking it never expands a row.
  // Cache key includes cp since the same ref string can exist under different clients.
  const fetchDoDefinition = useCallback(
    async (ref, cpParam) => {
      const cpToUse = cpParam || wsCp;
      const cacheKey = `${cpToUse}::${ref}`;
      if (doDefinitionCacheRef.current[cacheKey]) {
        return doDefinitionCacheRef.current[cacheKey];
      }
      try {
        const ldName = ref.split('/')[0];
        const lnName = ref.split('/')[1].split('.')[0];
        const doPath = ref.split('/')[1].split('.').slice(1).join('.');
        const result = await executeApiCall('data-definition', apiTarget, {
          ld_inst: ldName,
          ln_inst: lnName,
          do_path: doPath,
          cp: cpToUse,
        });
        if (result?.ok) {
          const def = {
            dataAttributes: result.payload.result.value?.dataAttributeDefinition || [],
            subDataObjects: result.payload.result.value?.subDataDefinition || [],
          };
          doDefinitionCacheRef.current[cacheKey] = def;
          return def;
        }
      } catch (error) {
        console.error('Failed to fetch DO definition:', error);
      }
      return null;
    },
    [apiTarget, wsCp]
  );

  const hasOperInDef = (def) =>
    !!def?.dataAttributes?.some((da) => (da.name || da.daRef?.split('.').pop() || '').toLowerCase() === 'oper');

  // Handle context menu
  const handleContextMenu = useCallback(
    (e, nodeInfo) => {
      e.preventDefault();
      e.stopPropagation();
      const { clientX, clientY } = e;

      const cpToUse = nodeInfo.cp || wsCp;
      const cacheKey = `${cpToUse}::${nodeInfo.ref}`;
      const cachedDef = doDefinitionCacheRef.current[cacheKey];
      const isDO = nodeInfo.nodeType === 'DO';

      // Open right away with whatever we already know.
      setContextMenuTarget({
        ...nodeInfo,
        cp: cpToUse,
        hasOperDA: cachedDef ? hasOperInDef(cachedDef) : null, // null = not yet known
        operPending: isDO && !cachedDef,
      });
      setContextMenu({ visible: true, x: clientX, y: clientY });

      // If unknown, resolve in the background — no setClientTrees, no expand side-effect.
      if (isDO && !cachedDef) {
        fetchDoDefinition(nodeInfo.ref, cpToUse).then((def) => {
          setContextMenuTarget((prev) =>
            prev && prev.ref === nodeInfo.ref
              ? { ...prev, hasOperDA: hasOperInDef(def), operPending: false }
              : prev // menu target changed/closed since — ignore stale result
          );
        });
      }
    },
    [fetchDoDefinition, wsCp]
  );

  // Close context menu
  const closeContextMenu = useCallback(() => {
    setContextMenu({ visible: false, x: 0, y: 0 });
    setContextMenuTarget(null);
  }, []);

  // Handle node click (for expanding DOs/SDOs)
  // nodeInfo.cp identifies which client's tree/accordion this click came
  // from — each accordion's <Tree> forces this explicitly on every callback.
const handleNodeClick = useCallback(
  async (nodeInfo) => {
    const nodeRef = nodeInfo.ref;
    const cpToUse = nodeInfo.cp || wsCp;

     const shouldToggle = !['DO', 'SDO', 'DataSet'].includes(nodeInfo.nodeType);

    setExpandedNodesByClient((prev) => ({
      ...prev,
      [cpToUse]: {
        ...(prev[cpToUse] || {}),
        [nodeRef]: shouldToggle ? !(prev[cpToUse] || {})[nodeRef] : true,
      },
    }));

    if (nodeInfo.nodeType === 'DO' || nodeInfo.nodeType === 'SDO') {
      const nodeInTree = findNodeInTree(clientTrees[cpToUse], nodeInfo.ref);
      if (nodeInTree?.children?.length > 0) return; // already expanded once

      const def = await fetchDoDefinition(nodeInfo.ref, cpToUse);
      if (def) {
        updateTreeWithChildren(cpToUse, nodeInfo.ref, def.dataAttributes, def.subDataObjects);
      }
    } else if (nodeInfo.nodeType === 'DataSet') {
      // Fetch DataSet directory
       // Check if already loaded
      const nodeInTree = findNodeInTree(clientTrees[cpToUse], nodeInfo.ref);
      if (nodeInTree?.children?.length > 0) {
        return; // Skip re-fetching
      }

      const ldName = nodeInfo.ref.split('/')[0];
      const lnInst = nodeInfo.ref.split('/')[1].split('.')[0];
      const dsName = nodeInfo.ref.split('/')[1].split('.')[1];
      try {
        const result = await executeApiCall('dataset-directory', apiTarget, {
          ld_inst: ldName,
          ln_inst: lnInst,
          ds_inst: dsName,
          cp: cpToUse,
        });
        if (result?.ok) {
          const dataAttributes = result.payload.result.value || [];
          updateTreeWithDataSetChildren(cpToUse, nodeInfo.ref, dataAttributes);
        }
      } catch (error) {
        console.error('Failed to fetch DataSet directory:', error);
      }
    } else if (nodeInfo.nodeType === 'ReportControl') {
      // Open ReportControl modal (if implemented)
      console.log('ReportControl clicked:', nodeInfo.ref);
    }
  },
  [apiTarget, wsCp, clientTrees, fetchDoDefinition]
);
  const findNodeInTree = (tree, ref) => {
    if (!tree) return null;
    if (tree.ref === ref) return tree;
    if (tree.children) {
      for (const child of tree.children) {
        const found = findNodeInTree(child, ref);
        if (found) return found;
      }
    }
    return null;
  };
  // Helper to update tree with children for DOs/SDOs
  // Writes directly into clientTrees[cp] via functional setState, so it never
  // relies on a possibly-stale closure over the current tree.
  const updateTreeWithChildren = useCallback((cp, ref, dataAttributes, subDataObjects) => {

    const buildSdaChildren = (sdaList, parentRef, parentFc) => {
      return sdaList.map((sda) => {
        const sdaName = sda['cmpName'];
        const sdaRef = `${parentRef}.${sdaName}`;
        const sdaBType = Array.isArray(sda.cmpType) ? sda.cmpType[0] : (sda.bType || '');
        const nestedChildren =
          Array.isArray(sda.cmpType) && sda.cmpType[0] === 'structure' && Array.isArray(sda.cmpType[1])
            ? buildSdaChildren(sda.cmpType[1], sdaRef, parentFc)
            : [];
        return { name: sdaName, type: 'SDA', ref: sdaRef, fc: parentFc, bType: sdaBType, children: nestedChildren };
      });
    };

    setClientTrees((prevTrees) => {
      const tree = prevTrees[cp];
      if (!tree) return prevTrees;

      const updateNode = (nodes) => {
        let changed = false;
        const result = nodes.map((node) => {
          if (node.ref === ref) {
            const existingChildren = node.children || [];
            const existingRefs = new Set(existingChildren.map((child) => child.ref));

            const daChildren = dataAttributes
              .filter((da) => {
                const daName = da.name || da.daRef?.split('.').pop() || 'DA';
                return !existingRefs.has(`${ref}.${daName}`);
              })
              .map((da) => {
                const daName = da.name || da.daRef?.split('.').pop() || 'DA';
                const daRef = `${ref}.${daName}`;
                const fc = da.fc || '';
                const bType = Array.isArray(da.daType) ? da.daType[0] : (da.bType || '');
                const rawSubDas =
                  Array.isArray(da.daType) && da.daType[0] === 'structure' && Array.isArray(da.daType[1])
                    ? da.daType[1]
                    : (da.subDataAttributes || da.sub_attributes || da.sda || []);
                return { name: daName, type: 'DA', ref: daRef, fc, bType, children: buildSdaChildren(rawSubDas, daRef, fc) };
              });

            const sdoChildren = subDataObjects
              .filter((sdo) => !existingRefs.has(`${ref}.${sdo.name || 'SDO'}`))
              .map((sdo) => {
                const sdoName = sdo.name || 'SDO';
                const sdoRef = `${ref}.${sdoName}`;
                const sdoDas = (sdo.dataAttributes || sdo.data_attributes || []).map((sdoDa) => {
                  const sdoDaName = sdoDa.name || sdoDa.daRef?.split('.').pop() || 'SDA';
                  return { name: sdoDaName, type: 'SDA', ref: `${sdoRef}.${sdoDaName}`, fc: sdoDa.fc || '', bType: sdoDa.bType || '', children: [] };
                });
                return { name: sdoName, type: 'SDO', ref: sdoRef, cdc: sdo.cdc || '', children: sdoDas };
              });

            changed = true;
            // Return same object reference if nothing new to add
            if (daChildren.length === 0 && sdoChildren.length === 0) return node;
            return { ...node, children: [...existingChildren, ...daChildren, ...sdoChildren] };
          }

          if (node.children && node.children.length > 0) {
            const updatedChildren = updateNode(node.children);
            // Only create new object if children actually changed
            if (updatedChildren !== node.children) {
              return { ...node, children: updatedChildren };
            }
          }
          // Return same reference for unchanged nodes — React skips re-rendering these
          return node;
        });

        // Return same array reference if nothing changed
        return changed || result.some((n, i) => n !== nodes[i]) ? result : nodes;
      };

      const updatedChildren = updateNode(tree.children);
      // Only trigger re-render if something actually changed
      if (updatedChildren === tree.children) return prevTrees;
      return { ...prevTrees, [cp]: { ...tree, children: updatedChildren } };
    });
  }, []);

  // Helper to update tree with DataSet children
  const updateTreeWithDataSetChildren = useCallback((cp, ref, dataAttributes) => {
    setClientTrees((prevTrees) => {
      const tree = prevTrees[cp];
      if (!tree) return prevTrees;
      const updateNode = (nodes) => {
        return nodes.map((node) => {
          if (node.ref === ref) {
            const fcdas = dataAttributes.map((da) => ({
              name: da.ref,
              type: 'FCDA',
              ref: da.ref,
              fc: da.fc,
              children: [],
            }));
            return {
              ...node,
              children: [...(node.children || []), ...fcdas],
            };
          }
          return node.children ? { ...node, children: updateNode(node.children) } : node;
        });
      };
      return { ...prevTrees, [cp]: { ...tree, children: updateNode(tree.children) } };
    });
  }, []);

const getContextMenuItems = () => {
  if (!contextMenuTarget) return [];
  const { nodeType, ref, fc, cdc, rcbType } = contextMenuTarget;

  const items = [];

  if (nodeType === 'DO') {
    if (cdc && CONTROLLABLE_CDCS.includes(cdc.toUpperCase())) {
      if (contextMenuTarget.operPending) {
        items.push({ label: 'Checking availability...', icon: 'fa-spinner', disabled: true, action: () => {} });
      } else if (contextMenuTarget.hasOperDA) {
          items.push({
            label: 'Operate',
            icon: 'fa-play',
            action: () => {
              // Capture the target info before closing the context menu
              const {ref, name, cdc, endpoint: nodeEndpoint, cp: nodeCp} = contextMenuTarget;
              setControlModalTarget({ref, name, cdc, endpoint: nodeEndpoint, cp: nodeCp});
              setShowControlModal(true);
              closeContextMenu();
            },
          });
        }
    }
  }
  else if (nodeType === 'DA' || nodeType === 'SDA' || nodeType === 'FCDA') {
    const displayFc = fc || 'cf';
    items.push({
      label: `Read Value [${displayFc.toUpperCase()}]`,
      icon: 'fa-eye',
      action: () => {
        readDataValue(ref, displayFc, contextMenuTarget.cp || wsCp);
        closeContextMenu();
      },
    });
    if (displayFc.toLowerCase() === 'sp' || displayFc.toLowerCase() === 'cf') {
      items.push({
        label: `Write Value [${displayFc.toUpperCase()}]`,
        icon: 'fa-pen',
        action: () => {
        const { ref, fc, endpoint: nodeEndpoint, cp: nodeCp } = contextMenuTarget;  // Capture values first
        setWriteModalTarget({ ref, fc, endpoint: nodeEndpoint, cp: nodeCp });         // Store in state
        setShowWriteModal(true);
        closeContextMenu();
      },
      });
    }
  }
  else if (nodeType === 'SDO') {
    items.push({
      label: 'Expand',
      icon: 'fa-folder-open',
      action: () => {
        handleNodeClick({ ref, nodeType: 'SDO', cp: contextMenuTarget.cp || wsCp });
        closeContextMenu();
      },
    });
  }
  else if (nodeType === 'ReportControl' || nodeType === 'BRCB' || nodeType === 'URCB' || nodeType === 'ReportControlBlock' || rcbType) {
    items.push({
      label: 'Configure',
      icon: 'fa-cog',
      action: () => {
        // Capture the target info before closing the context menu
        const { ref, rcbType: nodeRcbType, endpoint: nodeEndpoint, cp: nodeCp } = contextMenuTarget;
        setBrcbConfigTarget({ ref, rcbType: nodeRcbType || nodeType, endpoint: nodeEndpoint, cp: nodeCp });
        setShowBrcbConfigModal(true);
        closeContextMenu();
      },
    });
  }

  return items;
};

  // Cleanup
  useEffect(() => {
    return () => {
      stopMonitoring();
      if (statusIntervalRef.current) {
        clearInterval(statusIntervalRef.current);
        statusIntervalRef.current = null;
      }
    };
  }, [stopMonitoring]);

   return (
    <section className="page">
      {/* Header */}
      <div className="page-header" style={{ position: 'relative' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <h1>
            <i className="fas fa-microchip" style={{ marginRight: '10px', color: 'var(--primary-light)' }}></i>
            Websocket Connection
          </h1>
        </div>
      </div>

      {/* Connection Section */}
      <div className="acsi-connection-section" style={{ display: 'flex', alignItems: 'flex-end', gap: '16px', marginBottom: '24px' }}>

        <div className="form-group">
          <label htmlFor="acsi-client-ws-host-page">WS Host</label>
          <input type="text" id="acsi-client-ws-host-page" value={wsHost} placeholder="0.0.0.0" disabled />
        </div>
        <div className="form-group">
          <label>WS Port</label>
          <input type="number" id="acsi-client-ws-port" value={wsPort} placeholder="102" disabled />
        </div>
      </div>

      {/* Security Configuration Buttons */}
      <div style={{ display: 'flex', gap: '16px', marginLeft: 'auto', marginBottom: '24px' }}>
        <button
          className="btn-secondary"
          onClick={() => setShowTLSModal(true)}
          disabled={loading}
          title="Configure TLS settings"
          id="acsi-client-tls-btn"
        >
          <i className="fas fa-shield-alt" style={{ marginRight: '8px' }}></i>TLS Config
        </button>
        <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={useOAuth}
            onChange={async (e) => {
              const newValue = e.target.checked;
              setUseOAuth(newValue);
              // Call reconfig-oauth immediately when checkbox is toggled
              if (apiTarget && endpoint?.name) {
                setLoading(true);
                try {
                  // Build OAuth config from endpoint
                  const oauthConfig = endpoint?.OAuth || {};

                  // For active mode connections, use the client's port for WebSocket connection
                  let connectionPort = endpoint?.port || wsPort;
                  if (endpoint?.ws_mode === 'active' || endpoint?.ws_mode === 'Active') {
                      // Find corresponding client connection (SO) by replacing Server with Client in endpoint name
                      const clientName = endpoint.name.replace('Server', 'Client');
                      const clientConnection = propConnections.find(c =>
                          (c.type === 'RTI-SO' || c.acsi === 'client') &&
                          c.name === clientName
                      );
                      if (clientConnection) {
                          connectionPort = clientConnection.port;
                      }
                  }

                  // Use the connection's own host/port for the target endpoint
                  const targetHost = endpoint?.host || wsHost;
                  const targetPort = endpoint?.port || wsPort;
                  const connectionTarget = buildTargetValue(targetHost, targetPort);

                  const requestBody = {
                    connection_name: endpoint?.name,
                    enable_oauth: newValue,
                    ws_mode: endpoint?.ws_mode || 'passive',
                    host: endpoint?.host || wsHost,
                    port: String(connectionPort),
                    cp: wsCp,
                    // Always send OAuth config fields (null when disabling)
                    certificate_endpoint_url: newValue ? (oauthConfig.certificate_endpoint || '') : null,
                    token_issuer_url: newValue ? (oauthConfig.token_issuer || oauthConfig.token_endpoint || '') : null,
                    ca_certificate: newValue ? (oauthConfig.auth_server_ca || '').trim() : null
                  };

                  // Save to SO server
                  const soResult = await executeApiCall('reconfig-oauth', connectionTarget, requestBody);

                  // Also save to BFF's connections.json
                  const bffOauthConfig = {
                    connection_name: endpoint?.name || wsHost,
                    enable_oauth: newValue,
                    ws_mode: endpoint?.ws_mode || 'passive',
                    // Always send OAuth config fields (null when disabling)
                    certificate_endpoint_url: newValue ? (oauthConfig.certificate_endpoint || '') : null,
                    token_issuer_url: newValue ? (oauthConfig.token_issuer || oauthConfig.token_endpoint || '') : null,
                    ca_certificate: newValue ? (oauthConfig.auth_server_ca || '').trim() : null
                  };
                  const bffResult = await fetch(`${bffBaseUrl}/api/connections/oauth-config`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(bffOauthConfig)
                  });

                  if (soResult?.ok && bffResult.ok) {
                    setMessage({ type: 'success', text: `OAuth ${newValue ? 'enabled' : 'disabled'} successfully` });
                  } else {
                    setMessage({ type: 'error', text: soResult?.payload?.error || bffResult.statusText || 'Failed to update OAuth' });
                    setUseOAuth(!newValue); // Revert on failure
                  }
                } catch (error) {
                  setMessage({ type: 'error', text: error.message });
                  setUseOAuth(!newValue); // Revert on failure
                } finally {
                  setLoading(false);
                }
              }
            }}
            disabled={loading}
            id="acsi-client-oauth-checkbox"
          />
          <span style={{ color: 'var(--text-primary)' }}>Enable OAuth</span>
        </label>
      </div>

      <div className="page-header" style={{ position: 'relative' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <h1>
            <i className="fas fa-microchip" style={{ marginRight: '10px', color: 'var(--primary-light)' }}></i>
            ACSI Client
          </h1>
          <span id="acsi-endpoint-badge" className="acsi-endpoint-badge" style={{ display: connected ? 'inline-flex' : 'none' }}>
            {connected && statusInfo && `${statusInfo.result?.host}:${statusInfo.result?.port}`}
            {statusInfo?.result?.accessPoints && <span style={{ marginLeft: '8px' }}>AP: {statusInfo.result.accessPoints}</span>}
            {endpoint && !connected && <span>{endpoint.name || `${endpoint.host}:${endpoint.port}`}</span>}
          </span>
        </div>
      </div>

      {/* ACSI Clients (from properties API's acsi_client_list) */}
      {acsiClientList.length > 0 && (
        <div className="acsi-clients-list" style={{ marginBottom: '24px' }}>
          {acsiClientList.map((cp) => {
            const isExpanded = !!expandedClients[cp];
            const isFetchingThis = !!clientLoading[cp];
            const cpTree = clientTrees[cp];
            return (
              <div
                key={cp}
                className="acsi-client-entry"
                style={{
                  border: '1px solid var(--border-color)',
                  borderRadius: '8px',
                  marginBottom: '8px',
                  overflow: 'hidden',
                }}
              >
                <div
                  onClick={() => toggleClientExpanded(cp)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '12px 16px',
                    cursor: 'pointer',
                    background: 'var(--bg-card)',
                  }}
                >
                  <span style={{ fontWeight: 500 }}>{cp}</span>
                  <i className={`fas fa-chevron-${isExpanded ? 'up' : 'down'}`}></i>
                </div>
                {isExpanded && (
                  <div
                    style={{
                      padding: '16px',
                      background: 'var(--bg-card)',
                      borderTop: '1px solid var(--border-color)',
                    }}
                  >
                    <div style={{ display: 'flex', gap: '16px', marginBottom: '16px' }}>
                      <button
                        className="btn-primary"
                        onClick={() => loadClientTree(cp)}
                        disabled={isFetchingThis || !apiTarget}
                      >
                        {isFetchingThis ? 'Fetching...' : 'Fetch Model'}
                      </button>
                    </div>
                    <div id={`acsi-client-tree-container-${cp}`} className="model-tree">
                      {cpTree ? (
                        <Tree
                          data={cpTree}
                          onNodeClick={(nodeInfo) => handleNodeClick({ ...nodeInfo, cp })}
                          onContextMenu={(e, nodeInfo) => handleContextMenu(e, { ...nodeInfo, cp })}
                          onExpandToggle={(nodeRef, isExpandedFlag) => handleExpandToggle(cp, nodeRef, isExpandedFlag)}
                          expandedNodes={expandedNodesByClient[cp] || {}}
                          endpoint={endpoint}
                          cp={cp}
                        />
                      ) : (
                        <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '12px' }}>
                          Click "Fetch Model" to load the ACSI model tree for {cp}
                        </p>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {message && (
        <div className="alert" style={{
          marginBottom: '16px',
          padding: '12px',
          background: message.type === 'success' ? 'var(--success-bg)' : 'var(--danger-bg)',
          color: message.type === 'success' ? 'var(--success-color)' : 'var(--danger-color)',
          borderRadius: '4px',
          display: 'flex',
          alignItems: 'center'
        }}>
          <i className={`fas fa-${message.type === 'success' ? 'check-circle' : 'exclamation-circle'}`} style={{ marginRight: '8px' }}></i>
          {message.text}
        </div>
      )}

      {/* Error Display */}
      {error && (
        <div className="alert alert-error" style={{ marginBottom: '16px', padding: '12px', background: 'var(--danger-bg)', color: 'var(--danger-color)', borderRadius: '4px' }}>
          <i className="fas fa-exclamation-triangle" style={{ marginRight: '8px' }}></i>
          {error}
        </div>
      )}

      {/* Status Info */}
      {/*}
      {statusInfo && (
        <div style={{ marginBottom: '24px', padding: '16px', background: 'var(--bg-card)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
          <h3 style={{ margin: 0, marginBottom: '12px', fontSize: '16px' }}>Connection Status</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            <div>
              <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>Address</span>
              <div style={{ fontWeight: '500' }}>{statusInfo.result?.host}:{statusInfo.result?.port}</div>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>Status</span>
              <div style={{ fontWeight: '500' }}>{JSON.stringify(statusInfo.result?.status)}</div>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>Model</span>
              <div style={{ fontWeight: '500' }}>{statusInfo.result?.status?.modelName || 'N/A'}</div>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>Access Points</span>
              <div style={{ fontWeight: '500' }}>{statusInfo.result?.accessPoints || 'N/A'}</div>
            </div>
          </div>
        </div>
      )}
      */}

      <div className="page-header" style={{ position: 'relative' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <h1>
            <i className="fas fa-microchip" style={{ marginRight: '10px', color: 'var(--primary-light)' }}></i>
            Monitoring
          </h1>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '16px', marginBottom: '24px' }}>
        <button id="messages-start-btn" className={isMonitoring ? 'btn-secondary' : 'btn-primary'} onClick={startMonitoring} disabled={!apiTarget || isMonitoring}>
          {isMonitoring ? 'Monitoring...' : 'Start Monitor'}
        </button>
        <button id="messages-stop-btn" className={isMonitoring ? 'btn-primary' : 'btn-secondary'} onClick={stopMonitoring} disabled={!isMonitoring}>
          Stop Monitor
        </button>
        <button id="messages-clear-btn" className="btn-secondary" onClick={clearMessages} disabled={!apiTarget}>
          Clear Logs
        </button>
      </div>

      {/* Protocol Messages */}
      {isMonitoring && (
        <div style={{ marginTop: '24px' }}>
          <h3 style={{ fontSize: '16px', marginBottom: '12px' }}>Protocol Messages</h3>
          <div style={{ background: 'var(--bg-card)', borderRadius: '8px', border: '1px solid var(--border-color)', maxHeight: '300px', overflowY: 'auto', padding: '12px' }}>
            {protocolMessages.length === 0 ? (
              <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '20px' }}>No log messages yet.</div>
            ) : (
              protocolMessages.map((msg, index) => (
                <div key={index} style={{ padding: '8px 12px', marginBottom: '8px', borderRadius: '4px', background: 'var(--bg-hover)', fontSize: '12px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                    <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>#{msg.id || index} - {msg.timestamp}</span>
                    <span style={{ fontSize: '11px', padding: '2px 6px', borderRadius: '3px', background: msg.level === 'error' ? 'var(--danger-bg)' : msg.level === 'warning' ? 'var(--warning-bg)' : 'var(--info-bg)' }}>
                      {msg.level || 'info'}
                    </span>
                  </div>
                  <div style={{ color: 'var(--text-primary)' }}>{msg.message}</div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* Context Menu */}
      <ContextMenu
        x={contextMenu.x}
        y={contextMenu.y}
        visible={contextMenu.visible}
        onClose={closeContextMenu}
        items={getContextMenuItems()}
      />

      {/* Control Modal */}
      {showControlModal && (
        <ControlModal
          objRef={controlModalTarget.ref}
          objName={controlModalTarget.name}
          cdc={controlModalTarget.cdc}
          endpoint={controlModalTarget.endpoint || endpoint}
          cp={controlModalTarget.cp || wsCp}
          onClose={() => {
            setShowControlModal(false);
            setControlModalTarget({ ref: '', name: '', cdc: '', endpoint: null, cp: null });
          }}
          onSuccess={() => {
            setShowControlModal(false);
            setControlModalTarget({ ref: '', name: '', cdc: '', endpoint: null, cp: null });
          }}
        />
      )}

      {/* Write Value Modal */}
      {showWriteModal && (
        <WriteValueModal
          objRef={writeModalTarget.ref}
          fc={writeModalTarget.fc}
          endpoint={writeModalTarget.endpoint || contextMenuTarget?.endpoint || endpoint}
          cp={writeModalTarget.cp || contextMenuTarget?.cp || wsCp}
          onClose={() => {
            setShowWriteModal(false);
            setWriteModalTarget({ ref: '', fc: '', endpoint: null, cp: null });
          }}
          onSuccess={async () => {
            setShowWriteModal(false);
            setWriteModalTarget({ ref: '', fc: '', endpoint: null, cp: null });
            // Refresh the value after write
            if (writeModalTarget.ref && writeModalTarget.fc) {
              await readDataValue(writeModalTarget.ref, writeModalTarget.fc, writeModalTarget.cp || wsCp);
            }
          }}
        />
      )}

      {/* BRCB Configuration Modal */}
      {showBrcbConfigModal && (
        <BrcbConfigModal
          objRef={brcbConfigTarget.ref}
          rcbType={brcbConfigTarget.rcbType}
          endpoint={brcbConfigTarget.endpoint || contextMenuTarget?.endpoint || endpoint}
          cp={brcbConfigTarget.cp || contextMenuTarget?.cp || wsCp}
          onClose={() => {
            setShowBrcbConfigModal(false);
            setBrcbConfigTarget({ ref: '', rcbType: '', endpoint: null, cp: null });
          }}
          onSuccess={() => {
            setShowBrcbConfigModal(false);
            setBrcbConfigTarget({ ref: '', rcbType: '', endpoint: null, cp: null });
          }}
        />
      )}

      <TLSConfigModal
        isOpen={showTLSModal}
        onClose={() => {
          setShowTLSModal(false);
          setTimeout(() => setMessage(null), 3000);
        }}
        connection={(
          () => {
            // Try to find matching connection from live connections (has updated TLS)
            const liveConn = connections.find(c =>
              (c.host === endpoint?.host && String(c.port) === String(endpoint?.port)) ||
              (c.host === wsHost && String(c.port) === String(wsPort))
            );
            if (liveConn) {
              return liveConn;
            }
            // Fallback to endpoint with TLS if available
            if (endpoint?.TLS) {
              return {
                name: endpoint.name || wsHost,
                host: endpoint.host || wsHost,
                port: endpoint.port || wsPort,
                type: 'RTI-FSP',
                ws_mode: 'passive',
                TLS: endpoint.TLS,
                properties_info: {
                  properties: {
                    ws_mode: 'passive'
                  }
                }
              };
            }
            // Final fallback
            return {
              name: endpoint?.name || wsHost,
              host: endpoint?.host || wsHost,
              port: endpoint?.port || wsPort,
              type: 'RTI-FSP',
              ws_mode: 'passive',
              TLS: {},
              properties_info: {
                properties: {
                  ws_mode: 'passive'
                }
              }
            };
          }
        )()}
        bffBaseUrl={bffBaseUrl}
        wsHost={wsHost}
        wsPort={wsPort}
        onSuccess={(msg) => {
          setMessage({ type: 'success', text: msg });
          // Refetch connections to get updated TLS config
          fetchConnections();
        }}
        onError={(msg) => setMessage({ type: 'error', text: msg })}
      />
    </section>
  );
};

export default ACSIClient;
