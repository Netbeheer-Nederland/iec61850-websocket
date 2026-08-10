import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useLocation } from 'react-router-dom';
import { executeApiCall, buildTargetValue, getApiById } from '../services/apiService';
import Tree from '../components/Tree';

function ACSIClient() {
  const location = useLocation();
  const endpoint = location.state?.endpoint;
  const [wsHost, setWsHost] = useState(endpoint?.host || '127.0.0.1');
  const [wsPort, setWsPort] = useState(endpoint?.port || 102);
  const [wsCp, setWsCp] = useState(endpoint?.cp || 'cp1');
  const [connected, setConnected] = useState(false);
  const [treeData, setTreeData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [statusInfo, setStatusInfo] = useState(null);
  const [protocolMessages, setProtocolMessages] = useState([]);
  const [isMonitoring, setIsMonitoring] = useState(false);
  const monitorIntervalRef = useRef(null);

  // Build target from the endpoint that was clicked to open this page, or from form fields
  const endpointTarget = useMemo(() => 
    buildTargetValue(endpoint?.host || wsHost, endpoint?.port || wsPort),
    [endpoint, wsHost, wsPort]
  );

  // Stop monitoring - must be defined first as it's used by other hooks
  const stopMonitoring = useCallback(() => {
    console.log('[ACSI Client] Stop Monitor button clicked');
    if (monitorIntervalRef.current) {
      clearInterval(monitorIntervalRef.current);
      monitorIntervalRef.current = null;
    }
    setIsMonitoring(false);
  }, []);

  // Connect
  const handleConnect = useCallback(async () => {
    console.log('[ACSI Client] Start button clicked', { wsHost, wsPort, wsCp, endpointTarget });
    if (!endpointTarget) { setError('No endpoint configured'); return; }
    setLoading(true); setError(null);
    try {
      const result = await executeApiCall('connect', endpointTarget, { host: wsHost, port: wsPort, cp: wsCp });
      if (result?.ok) {
        setConnected(true);
        await loadStatus(endpointTarget);
      } else {
        setError(result?.payload?.error || result?.rawText || 'Connection failed');
      }
    } catch (error) { setError(error.message); }
    finally { setLoading(false); }
  }, [endpointTarget, wsHost, wsPort, wsCp, executeApiCall]);

  // Disconnect
  const handleDisconnect = useCallback(async () => {
    console.log('[ACSI Client] Stop button clicked', { endpointTarget });
    if (!connected) return;
    setLoading(true); setError(null);
    try {
      const result = await executeApiCall('disconnect', endpointTarget, { host: wsHost, port: wsPort, cp: wsCp });
      if (result?.ok) {
        setConnected(false);
      } else {
        setError(result?.payload?.error || result?.rawText || 'Disconnection failed');
      }
    } catch (error) { setError(error.message); }
    finally { setLoading(false); }
  }, [connected, endpointTarget, wsHost, wsPort, wsCp, executeApiCall]);

  // Load status
  const loadStatus = useCallback(async (target = null) => {
    console.log('[ACSI Client] Reload Status button clicked', { target: target || endpointTarget });
    const currentTarget = target || endpointTarget;
    if (!currentTarget) return;
    try {
      const result = await executeApiCall('status', currentTarget, null);
      if (result?.ok) setStatusInfo(result.payload);
    } catch (error) { console.error('Failed to load status:', error); }
  }, [endpointTarget, executeApiCall]);

  // Fetch action logs
  const fetchActionLogs = useCallback(async () => {
    console.log('[ACSI Client] Fetching action logs...');
    if (!endpointTarget) return;
    try {
      const result = await executeApiCall('actions-logs', endpointTarget, {});
      if (result?.ok) {
        const actions = result.payload.result?.actions || result.payload.actions || [];
        if (Array.isArray(actions) && actions.length > 0) {
          setProtocolMessages(prev => {
            const existingIds = new Set(prev.map(msg => msg.id));
            const newMessages = actions.filter(msg => msg && msg.id && !existingIds.has(msg.id))
              .map(msg => ({ ...msg, timestamp: new Date().toLocaleTimeString() }));
            return [...newMessages, ...prev].slice(0, 30);
          });
        }
      }
    } catch (error) { console.error('Failed to fetch action logs:', error); }
  }, [endpointTarget, executeApiCall]);

  // Start monitoring
  const startMonitoring = useCallback(async () => {
    console.log('[ACSI Client] Start Monitor button clicked');
    if (isMonitoring) return;
    if (!endpointTarget) { setError('No endpoint configured'); return; }
    
    stopMonitoring();
    setIsMonitoring(true);
    await fetchActionLogs();
    monitorIntervalRef.current = setInterval(fetchActionLogs, 5000);
  }, [endpointTarget, isMonitoring, fetchActionLogs, stopMonitoring]);

  // Clear messages
  const clearMessages = useCallback(async () => {
    console.log('[ACSI Client] Clear Logs button clicked');
    if (!endpointTarget) { setError('No endpoint configured'); return; }
    
    const result = await executeApiCall('clear-logs', endpointTarget, {});
    if (result?.ok) setProtocolMessages([]);
    else setError(`Error clearing messages: ${result?.payload?.error || 'Unknown error'}`);
  }, [endpointTarget, executeApiCall]);

  // Load model tree
  const loadClientTree = useCallback(async () => {
    console.log('[ACSI Client] Fetch Model button clicked', { wsCp, endpointTarget });
    if (!connected) { setError('Please connect first'); return; }
    if (!endpointTarget) { setError('No endpoint configured'); return; }
    setLoading(true); setError(null);
    try {
      const result = await executeApiCall('model-tree', endpointTarget, { cp: wsCp });
      if (result?.ok) {
        const transformTree = (data) => {
          if (!data.result?.model?.server?.logicalDevices) return [];
          const lds = data.result.model.server.logicalDevices;
          const logicalDeviceMap = data.result.model.logicalDeviceMap || {};
          const logicalNodeDetails = data.result.model.logicalNodeDetails || {};
          return lds.map(ld => {
            const ldName = typeof ld === 'object' ? ld.name : ld;
            const lns = logicalDeviceMap[ldName] || [];
            const children = lns.map(ln => {
              const lnName = typeof ln === 'object' ? (ln.name || ln.ln_class) : ln;
              const lnRef = `${ldName}/${lnName}`;
              const details = logicalNodeDetails[lnRef] || {};
              const dataSets = details.dataSets || [];
              const reportControls = details.reportControlBlocks || [];
              const dataObjects = details.dataObjects || ln.dataObjects || ln.do || [];
              const dsChildren = dataSets.map(ds => ({
                name: typeof ds === 'object' ? ds.name : ds,
                type: 'dataset',
                ref: `${lnRef}.${typeof ds === 'object' ? ds.name : ds}`,
                children: []
              }));
              const rcChildren = reportControls.map(rcb => ({
                name: typeof rcb === 'object' ? rcb.name : rcb,
                type: typeof rcb === 'object' ? rcb.type : 'ReportControl',
                ref: `${lnRef}.${typeof rcb === 'object' ? rcb.name : rcb}`,
                children: []
              }));
              const doChildren = dataObjects.map(doObj => {
                const doName = typeof doObj === 'object' ? doObj.name : doObj;
                const doRef = `${lnRef}.${doName}`;
                const das = (doObj.data_attributes || doObj.dataAttributes || doObj.da || []).map(da => ({
                  name: typeof da === 'object' ? da.name : da,
                  type: 'da',
                  ref: `${doRef}.${typeof da === 'object' ? da.name : da}`,
                  fc: (doObj.fc || da.fc || ''),
                  bType: da.bType || '',
                  children: []
                }));
                return {
                  name: doName,
                  type: 'do',
                  ref: doRef,
                  fc: doObj.fc || '',
                  cdc: doObj.cdc || '',
                  children: das
                };
              });
              return {
                name: lnName,
                type: 'ln',
                ref: lnRef,
                children: [
                  ...(dsChildren.length > 0 ? [{ name: 'DataSets', type: 'group', children: dsChildren }] : []),
                  ...(rcChildren.length > 0 ? [{ name: 'ReportControls', type: 'group', children: rcChildren }] : []),
                  ...doChildren
                ]
              };
            });
            return {
              name: ldName,
              type: 'ldevice',
              ref: ldName,
              children
            };
          });
        };
        const tree = transformTree(result.payload);
        setTreeData(tree.length > 0 ? { name: 'Server', type: 'server', children: tree } : null);
      } else {
        setError(result?.payload?.error || result?.rawText || 'Failed to fetch model');
      }
    } catch (error) { setError(error.message); }
    finally { setLoading(false); }
  }, [connected, endpointTarget, wsCp, executeApiCall]);

  // Read data value
  const readDataValue = useCallback(async (objRef, fc) => {
    if (!connected) { setError('Please connect first'); return; }
    if (!endpointTarget) { setError('No endpoint configured'); return; }
    try {
      const result = await executeApiCall('read', endpointTarget, { objRef, fc, cp: wsCp });
      if (result?.ok) {
        const updateTreeWithValue = (nodes, targetRef, value) => {
          return nodes.map(node => node.ref === targetRef ? { ...node, value } :
            node.children ? { ...node, children: updateTreeWithValue(node.children, targetRef, value) } : node);
        };
        const value = result.payload?.result?.value;
        if (value && treeData) {
          setTreeData(prev => ({ ...prev, children: updateTreeWithValue(prev.children, objRef, value) }));
        }
      } else {
        setError(`Read failed: ${result?.payload?.error || 'Unknown error'}`);
      }
    } catch (error) { setError(error.message); }
  }, [connected, endpointTarget, wsCp, executeApiCall, treeData]);

  // Cleanup
  useEffect(() => () => { stopMonitoring(); }, [stopMonitoring]);

  return (
    <section className="page">
      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <h1><i className="fas fa-microchip" style={{ marginRight: '10px', color: 'var(--primary-light)' }}></i>ACSI Interface</h1>
          <span id="acsi-endpoint-badge" className="acsi-endpoint-badge" style={{ display: connected ? 'inline-flex' : 'none' }}>
            {connected && statusInfo && `${statusInfo.result?.host}:${statusInfo.result?.port}`}
            {statusInfo?.result?.accessPoints && <span style={{ marginLeft: '8px' }}>AP: {statusInfo.result.accessPoints}</span>}
            {endpoint && !connected && <span>{endpoint.name || `${endpoint.host}:${endpoint.port}`}</span>}
          </span>
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'left', gap: '16px', marginBottom: '24px' }}>
        <h2><i style={{ marginRight: '10px', color: 'var(--primary-light)' }}></i>ACSI Client</h2>
      </div>
      <div className="acsi-connection-section" style={{ display: 'flex', alignItems: 'flex-end', gap: '16px', marginBottom: '24px' }}>
        <div className="form-group">
          <label htmlFor="acsi-client-ws-host-page">WS Host</label>
          <input type="text" id="acsi-client-ws-host-page" value={wsHost} placeholder="127.0.0.1" onChange={(e) => setWsHost(e.target.value)} disabled={loading} />
        </div>
        <div className="form-group">
          <label>WS Port</label>
          <input type="number" id="acsi-client-ws-port" value={wsPort} placeholder="102" onChange={(e) => setWsPort(parseInt(e.target.value) || 102)} disabled={loading} />
        </div>
        <div className="form-group">
          <label>WS CP</label>
          <input type="text" id="acsi-client-ws-cp" value={wsCp} placeholder="cp1" onChange={(e) => setWsCp(e.target.value)} disabled={loading} />
        </div>
        <button id="acsi-connect-btn" className="btn-secondary" onClick={handleConnect} disabled={loading || connected}>
          {loading ? 'Starting...' : 'Start'}
        </button>
        <button id="acsi-disconnect-btn" className="btn-secondary" onClick={handleDisconnect} disabled={loading || !connected}>Stop</button>
      </div>
      <div style={{ display: 'flex', gap: '16px', marginBottom: '24px' }}>
        <button id="acsi-read-data-btn" className="btn-primary" onClick={loadClientTree} disabled={loading || !connected}>{loading ? 'Fetching...' : 'Fetch Model'}</button>
        <button className="btn-secondary" onClick={() => loadStatus(endpointTarget)} disabled={!endpointTarget}>Reload Status</button>
        <button id="messages-start-btn" className="btn-primary" onClick={startMonitoring} disabled={!endpointTarget || isMonitoring}>{isMonitoring ? 'Monitoring...' : 'Start Monitor'}</button>
        <button id="messages-stop-btn" className="btn-secondary" onClick={stopMonitoring} disabled={!isMonitoring}>Stop Monitor</button>
        <button id="messages-clear-btn" className="btn-secondary" onClick={clearMessages} disabled={!endpointTarget}>Clear Logs</button>
      </div>
      {error && <div className="alert alert-error" style={{ marginBottom: '16px', padding: '12px', background: 'var(--danger-bg)', color: 'var(--danger-color)', borderRadius: '4px' }}><i className="fas fa-exclamation-triangle" style={{ marginRight: '8px' }}></i>{error}</div>}
      {statusInfo && (
        <div style={{ marginBottom: '24px', padding: '16px', background: 'var(--bg-card)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
          <h3 style={{ margin: 0, marginBottom: '12px', fontSize: '16px' }}>Connection Status</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            <div><span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>Address</span><div style={{ fontWeight: '500' }}>{statusInfo.result?.host}:{statusInfo.result?.port}</div></div>
            <div><span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>Status</span><div style={{ fontWeight: '500' }}>{JSON.stringify(statusInfo.result?.status)}</div></div>
            <div><span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>Model</span><div style={{ fontWeight: '500' }}>{statusInfo.result?.status?.modelName || 'N/A'}</div></div>
            <div><span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>Access Points</span><div style={{ fontWeight: '500' }}>{statusInfo.result?.accessPoints || 'N/A'}</div></div>
          </div>
        </div>
      )}
      <div id="acsi-client-tree-container" className="model-tree" style={{ marginTop: '24px' }}>
        {treeData ? <Tree data={treeData} /> : <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '20px' }}>{connected ? 'Click "Fetch Model" to load the ACSI model tree' : endpoint ? `Start the WebSocket connection to ${endpoint.name || endpoint.host}:${endpoint.port}` : 'Start the WebSocket connection to fetch the model'}</p>}
      </div>
      {isMonitoring && (
        <div style={{ marginTop: '24px' }}>
          <h3 style={{ fontSize: '16px', marginBottom: '12px' }}>Protocol Messages</h3>
          <div style={{ background: 'var(--bg-card)', borderRadius: '8px', border: '1px solid var(--border-color)', maxHeight: '300px', overflowY: 'auto', padding: '12px' }}>
            {protocolMessages.length === 0 ? <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '20px' }}>No log messages yet. Messages will appear here when monitoring.</div> :
              protocolMessages.map((msg, index) => (
                <div key={index} style={{ padding: '8px 12px', marginBottom: '8px', borderRadius: '4px', background: 'var(--bg-hover)', fontSize: '12px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                    <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>#{msg.id || index} - {msg.timestamp}</span>
                    <span style={{ fontSize: '11px', padding: '2px 6px', borderRadius: '3px', background: msg.level === 'error' ? 'var(--danger-bg)' : msg.level === 'warning' ? 'var(--warning-bg)' : 'var(--info-bg)' }}>{msg.level || 'info'}</span>
                  </div>
                  <div style={{ color: 'var(--text-primary)' }}>{msg.message}</div>
                </div>
              ))}
          </div>
        </div>
      )}
    </section>
  );
}

export default ACSIClient;
