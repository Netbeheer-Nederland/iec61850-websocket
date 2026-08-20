// src/pages/ACSIClient.jsx
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import Tree from '../components/Tree';
import ContextMenu from '../components/ContextMenu';
import ControlModal from '../components/ControlModal';
import WriteValueModal from '../components/WriteValueModal';
import BrcbConfigModal from '../components/BrcbConfigModal';
import TLSConfigModal from '../components/TLSConfigModal';
import OAuthConfigModal from '../components/OAuthConfigModal';
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
  const [treeData, setTreeData] = useState(null);
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
  const [showBrcbConfigModal, setShowBrcbConfigModal] = useState(false);
  const [showTLSModal, setShowTLSModal] = useState(false);
  const [showOAuthModal, setShowOAuthModal] = useState(false);
  const [message, setMessage] = useState(null);
  const monitorIntervalRef = useRef(null);

  useEffect(() => {
    localStorage.setItem('acsi-connected', String(connected));
  }, [connected]);

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

    const [expandedNodes, setExpandedNodes] = useState({});

    const handleExpandToggle = useCallback((nodeRef, isExpanded) => {
      setExpandedNodes((prev) => ({
        ...prev,
        [nodeRef]: isExpanded,
      }));
    }, []);


  // Connect
  const handleConnect = useCallback(async () => {
    if (!wsHost || !wsPort) {
      setError('Please enter both host and port');
      return;
    }
    if (isNaN(wsPort) || wsPort < 1 || wsPort > 65535) {
      setError('Invalid port number');
      return;
    }
    if (!apiTarget) {
      setError('No API endpoint configured');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await executeApiCall('connect', apiTarget, { host: wsHost, port: wsPort, cp: wsCp });
      if (result?.ok) {
        setConnected(true);
        await loadStatus();
      } else {
        setError(result?.payload?.error || result?.rawText || 'Connection failed');
      }
    } catch (error) {
      setError(error.message);
    } finally {
      setLoading(false);
    }
  }, [wsHost, wsPort, wsCp, apiTarget]);

  // Disconnect
  const handleDisconnect = useCallback(async () => {
    if (!connected) return;
    if (!apiTarget) return;
    setLoading(true);
    setError(null);
    try {
      const result = await executeApiCall('disconnect', apiTarget, { host: wsHost, port: wsPort, cp: wsCp });
      if (result?.ok) {
        setConnected(false);
        setTreeData(null);
      } else {
        setError(result?.payload?.error || result?.rawText || 'Disconnection failed');
      }
    } catch (error) {
      setError(error.message);
    } finally {
      setLoading(false);
    }
  }, [connected, wsHost, wsPort, wsCp, apiTarget]);

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
  const loadClientTree = useCallback(async () => {
    if (!connected) {
      setError('Please connect first');
      return;
    }
    if (!apiTarget) {
      setError('No API endpoint configured');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await executeApiCall('model-tree', apiTarget, { cp: wsCp });
      if (result?.ok) {
        const tree = transformTree(result.payload);
        setTreeData(tree.length > 0 ? { name: 'Server', type: 'server', children: tree } : null);
        if (updateModel) {
          updateModel(apiTarget, result.payload);
        }
      } else {
        setError(result?.payload?.error || result?.rawText || 'Failed to fetch model');
      }
    } catch (error) {
      setError(error.message);
    } finally {
      setLoading(false);
    }
  }, [connected, apiTarget, wsCp]);

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
      if (!connected) {
        setError('Please connect first');
        return;
      }
      if (!apiTarget) {
        setError('No endpoint configured');
        return;
      }
      try {
        const cpToUse = cpParam || wsCp;
        const result = await executeApiCall('read', apiTarget, { objRef, fc, cp: cpToUse });
        if (result?.ok) {
          const updateTreeWithValue = (nodes, targetRef, valueData, isError) => {
            const formatted = formatValueForDisplay(valueData, isError);
            return nodes.map((node) =>
              node.ref === targetRef ? { ...node, value: formatted.display, valueColor: formatted.color } : 
              node.children ? { ...node, children: updateTreeWithValue(node.children, targetRef, valueData, isError) } : node
            );
          };
          const valueData = result.payload?.result?.value;
          if (valueData && treeData) {
            setTreeData((prev) => ({ ...prev, children: updateTreeWithValue(prev.children, objRef, valueData, false) }));
          }
        } else {
          const errorValue = result?.payload?.error || 'Unknown error';
          const updateTreeWithError = (nodes, targetRef) => {
            const formatted = formatValueForDisplay(errorValue, true);
            return nodes.map((node) =>
              node.ref === targetRef ? { ...node, value: formatted.display, valueColor: formatted.color } : 
              node.children ? { ...node, children: updateTreeWithError(node.children, targetRef) } : node
            );
          };
          if (treeData) {
            setTreeData((prev) => ({ ...prev, children: updateTreeWithError(prev.children, objRef) }));
          }
        }
      } catch (error) {
        const updateTreeWithError = (nodes, targetRef) => {
          const formatted = formatValueForDisplay(error.message, true);
          return nodes.map((node) =>
            node.ref === targetRef ? { ...node, value: formatted.display, valueColor: formatted.color } : 
            node.children ? { ...node, children: updateTreeWithError(node.children, targetRef) } : node
          );
        };
        if (treeData) {
          setTreeData((prev) => ({ ...prev, children: updateTreeWithError(prev.children, objRef) }));
        }
      }
    },
    [connected, apiTarget, wsCp, treeData, formatValueForDisplay]
  );

  // Write data value
  const writeDataValue = useCallback(
    async (objRef, fc, value, value_type) => {
      if (!connected) {
        setError('Please connect first');
        throw new Error('Please connect first');
      }
      if (!apiTarget) {
        setError('No endpoint configured');
        throw new Error('No endpoint configured');
      }
      try {
        const result = await executeApiCall('write', apiTarget, { objRef, fc, value, value_type, cp: wsCp });
        if (result?.ok) {
          const updateTreeWithValue = (nodes, targetRef, valueData, isError) => {
            const formatted = formatValueForDisplay(valueData, isError);
            return nodes.map((node) =>
              node.ref === targetRef ? { ...node, value: formatted.display, valueColor: formatted.color } : 
              node.children ? { ...node, children: updateTreeWithValue(node.children, targetRef, valueData, isError) } : node
            );
          };
          const valueData = result.payload?.result?.value || value;
          if (valueData && treeData) {
            setTreeData((prev) => ({ ...prev, children: updateTreeWithValue(prev.children, objRef, valueData, false) }));
          }
          return result;
        } else {
          const errorMsg = result?.payload?.error || result?.rawText || 'Write failed';
          setError(`Write failed: ${errorMsg}`);
          throw new Error(errorMsg);
        }
      } catch (error) {
        const updateTreeWithError = (nodes, targetRef) => {
          const formatted = formatValueForDisplay(error.message, true);
          return nodes.map((node) =>
            node.ref === targetRef ? { ...node, value: formatted.display, valueColor: formatted.color } : 
            node.children ? { ...node, children: updateTreeWithError(node.children, targetRef) } : node
          );
        };
        if (treeData) {
          setTreeData((prev) => ({ ...prev, children: updateTreeWithError(prev.children, objRef) }));
        }
        setError(error.message);
        throw error;
      }
    },
    [connected, apiTarget, wsCp, treeData, formatValueForDisplay]
  );

  // Handle context menu
const handleContextMenu = useCallback((e, nodeInfo) => {
  e.preventDefault();
  e.stopPropagation();
  setContextMenuTarget(nodeInfo);
  setContextMenu({ visible: true, x: e.clientX, y: e.clientY });
}, []);

  // Close context menu
  const closeContextMenu = useCallback(() => {
    setContextMenu({ visible: false, x: 0, y: 0 });
    setContextMenuTarget(null);
  }, []);



  // Handle node click (for expanding DOs/SDOs)
  // Handle node click (for expanding DOs/SDOs)
const handleNodeClick = useCallback(
  async (nodeInfo) => {
    const nodeRef = nodeInfo.ref;

     const shouldToggle = !['DO', 'SDO', 'DataSet'].includes(nodeInfo.nodeType);

    setExpandedNodes((prev) => ({
      ...prev,
      [nodeRef]: shouldToggle ? !prev[nodeRef] : true,
    }));
    
    if (nodeInfo.nodeType === 'DO' || nodeInfo.nodeType === 'SDO') {
      // Skip fetching if children already loaded
      const nodeInTree = findNodeInTree(treeData, nodeInfo.ref);
      if (nodeInTree?.children?.length > 0) {
        return;
      }

      // Fetch DO definition and update tree
      try {
        const ldName = nodeInfo.ref.split('/')[0];
        const lnName = nodeInfo.ref.split('/')[1].split('.')[0];
        const doPath = nodeInfo.ref.split('/')[1].split('.').slice(1).join('.');
        const result = await executeApiCall('data-definition', apiTarget, {
          ld_inst: ldName,
          ln_inst: lnName,
          do_path: doPath,
          cp: wsCp,
        });
        if (result?.ok) {
          const dataAttributes = result.payload.result.value?.dataAttributeDefinition || [];
          const subDataObjects = result.payload.result.value?.subDataDefinition || [];
          const updatedTree = updateTreeWithChildren(nodeInfo.ref, dataAttributes, subDataObjects);
          setTreeData(updatedTree);
        }
      } catch (error) {
        console.error('Failed to fetch DO definition:', error);
      }
    } else if (nodeInfo.nodeType === 'DataSet') {
      // Fetch DataSet directory
       // Check if already loaded
      const nodeInTree = findNodeInTree(treeData, nodeInfo.ref);
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
        });
        if (result?.ok) {
          const dataAttributes = result.payload.result.value || [];
          const updatedTree = updateTreeWithDataSetChildren(nodeInfo.ref, dataAttributes);
          setTreeData(updatedTree);
        }
      } catch (error) {
        console.error('Failed to fetch DataSet directory:', error);
      }
    } else if (nodeInfo.nodeType === 'ReportControl') {
      // Open ReportControl modal (if implemented)
      console.log('ReportControl clicked:', nodeInfo.ref);
    }
  },
  [apiTarget, wsCp, treeData]
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
  const updateTreeWithChildren = (ref, dataAttributes, subDataObjects) => {

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

    const updatedChildren = updateNode(treeData.children);
    // Only trigger re-render if something actually changed
    if (updatedChildren === treeData.children) return treeData;
    return { ...treeData, children: updatedChildren };
  };

  // Helper to update tree with DataSet children
  const updateTreeWithDataSetChildren = (ref, dataAttributes) => {
  const updateNode = (nodes) => {
    return nodes.map((node) => {
      if (node.ref === ref) {
        const fcdas = dataAttributes.map((da) => {
          //const daName = da.name || da.daRef?.split('.').pop() || 'FCDA';
          //const daRef = `${ref}.${daName}.${da.fc}`; // Include fc in ref to ensure uniqueness
          return {
            name: da.ref,
            type: 'FCDA',
            ref: da.ref,
            fc: da.fc,
            children: [],
          };
        });
        return {
          ...node,
          children: [...(node.children || []), ...fcdas],
        };
      }
      return node.children ? { ...node, children: updateNode(node.children) } : node;
    });
  };
  return { ...treeData, children: updateNode(treeData.children) };
};

const getContextMenuItems = () => {
  if (!contextMenuTarget) return [];
  const { nodeType, ref, fc, cdc, rcbType } = contextMenuTarget;

  const items = [];

  if (nodeType === 'DO') {
    if (cdc && CONTROLLABLE_CDCS.includes(cdc.toUpperCase())) {
      items.push({
        label: 'Operate',
        icon: 'fa-play',
        action: () => {
          // Capture the target info before closing the context menu
          const { ref, name, cdc, endpoint: nodeEndpoint, cp: nodeCp } = contextMenuTarget;
          setControlModalTarget({ ref, name, cdc, endpoint: nodeEndpoint, cp: nodeCp });
          setShowControlModal(true);
          closeContextMenu();
        },
      });
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
        handleNodeClick({ ref, nodeType: 'SDO' });
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
    };
  }, [stopMonitoring]);

  return (
    <section className="page">
      {/* Header */}
      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <h1>
            <i className="fas fa-microchip" style={{ marginRight: '10px', color: 'var(--primary-light)' }}></i>
            ACSI Interface
          </h1>
          <span id="acsi-endpoint-badge" className="acsi-endpoint-badge" style={{ display: connected ? 'inline-flex' : 'none' }}>
            {connected && statusInfo && `${statusInfo.result?.host}:${statusInfo.result?.port}`}
            {statusInfo?.result?.accessPoints && <span style={{ marginLeft: '8px' }}>AP: {statusInfo.result.accessPoints}</span>}
            {endpoint && !connected && <span>{endpoint.name || `${endpoint.host}:${endpoint.port}`}</span>}
          </span>
        </div>
      </div>

      {/* Connection Section */}
      <div style={{ display: 'flex', alignItems: 'left', gap: '16px', marginBottom: '24px' }}>
        <h2>
          <i style={{ marginRight: '10px', color: 'var(--primary-light)' }}></i>ACSI Client
        </h2>
      </div>

      <div className="acsi-connection-section" style={{ display: 'flex', alignItems: 'flex-end', gap: '16px', marginBottom: '24px' }}>
        <div className="form-group">
          <label htmlFor="acsi-client-ws-host-page">WS Host</label>
          <input
            type="text"
            id="acsi-client-ws-host-page"
            value={wsHost}
            placeholder="127.0.0.1"
            onChange={(e) => setWsHost(e.target.value)}
            disabled={loading}
          />
        </div>
        <div className="form-group">
          <label>WS Port</label>
          <input
            type="number"
            id="acsi-client-ws-port"
            value={wsPort}
            placeholder="102"
            onChange={(e) => setWsPort(parseInt(e.target.value) || 102)}
            disabled={loading}
          />
        </div>
        <div className="form-group">
          <label>WS CP</label>
          <input
            type="text"
            id="acsi-client-ws-cp"
            value={wsCp}
            placeholder="cp1"
            onChange={(e) => setWsCp(e.target.value)}
            disabled={loading}
          />
        </div>
        <button id="acsi-connect-btn" className="btn-secondary" onClick={handleConnect} disabled={loading || connected}>
          {loading ? 'Starting...' : 'Start'}
        </button>
        <button id="acsi-disconnect-btn" className="btn-secondary" onClick={handleDisconnect} disabled={loading || !connected}>
          Stop
        </button>
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
        <button
          className="btn-secondary"
          onClick={() => setShowOAuthModal(true)}
          disabled={loading}
          title="Configure OAuth settings"
          id="acsi-client-oauth-btn"
        >
          <i className="fas fa-key" style={{ marginRight: '8px' }}></i>OAuth Config
        </button>
      </div>

      {/* Action Buttons */}
      <div style={{ display: 'flex', gap: '16px', marginBottom: '24px' }}>
        <button id="acsi-read-data-btn" className="btn-primary" onClick={loadClientTree} disabled={loading || !connected}>
          {loading ? 'Fetching...' : 'Fetch Model'}
        </button>
        <button className="btn-secondary" onClick={loadStatus} disabled={!apiTarget}>
          Reload Status
        </button>
        <button id="messages-start-btn" className="btn-primary" onClick={startMonitoring} disabled={!apiTarget || isMonitoring}>
          {isMonitoring ? 'Monitoring...' : 'Start Monitor'}
        </button>
        <button id="messages-stop-btn" className="btn-secondary" onClick={stopMonitoring} disabled={!isMonitoring}>
          Stop Monitor
        </button>
        <button id="messages-clear-btn" className="btn-secondary" onClick={clearMessages} disabled={!apiTarget}>
          Clear Logs
        </button>
      </div>

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

      {/* Tree Container */}
      <div id="acsi-client-tree-container" className="model-tree" style={{ marginTop: '24px' }}>
        {treeData ? (
          <Tree
            data={treeData}
            onNodeClick={handleNodeClick}
            onContextMenu={handleContextMenu}
            onExpandToggle={handleExpandToggle}
            expandedNodes={expandedNodes}
            endpoint={endpoint}
            cp={wsCp}
          />
        ) : (
          <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '20px' }}>
            {connected ? 'Click "Fetch Model" to load the ACSI model tree' : 'Start the WebSocket connection to fetch the model'}
          </p>
        )}
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
              await readDataValue(writeModalTarget.ref, writeModalTarget.fc);
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
        connection={{
          name: endpoint?.name || wsHost,
          host: endpoint?.host || wsHost,
          port: endpoint?.port || wsPort,
          properties_info: {
            properties: {
              ws_mode: 'passive'
            }
          }
        }}
        bffBaseUrl={bffBaseUrl}
        wsHost={wsHost}       // ← Add this
        wsPort={wsPort}       // ← Add this
        onSuccess={(msg) => setMessage({ type: 'success', text: msg })}
        onError={(msg) => setMessage({ type: 'error', text: msg })}
      />

      <OAuthConfigModal
        isOpen={showOAuthModal}
        onClose={() => {
          setShowOAuthModal(false);
          setTimeout(() => setMessage(null), 3000);
        }}
        connections={connections}
        connection={{
          name: endpoint?.name || wsHost,
          host: endpoint?.host || wsHost,
          port: endpoint?.port || wsPort,
          properties_info: {
            properties: {
              ws_mode: 'passive'
            }
          }
        }}
        bffBaseUrl={bffBaseUrl}
        onSuccess={(msg) => setMessage({ type: 'success', text: msg })}
        onError={(msg) => setMessage({ type: 'error', text: msg })}
      />
    </section>
  );
};

export default ACSIClient;

