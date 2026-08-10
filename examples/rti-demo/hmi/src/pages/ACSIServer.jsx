import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { executeApiCall, buildTargetValue, getApiById } from '../services/apiService';
import Tree from '../components/Tree';

function ACSIServer() {
  const location = useLocation();
  const navigate = useNavigate();
  const endpoint = location.state?.endpoint;
  
  const [host, setHost] = useState(endpoint?.host || '0.0.0.0');
  const [port, setPort] = useState(endpoint?.port || 102);
  const [cp, setCp] = useState(endpoint?.cp || 'cp1');
  const [mode, setMode] = useState(endpoint?.mode || 'server');
  const [connected, setConnected] = useState(false);
  const [treeData, setTreeData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [statusInfo, setStatusInfo] = useState(null);
  const [protocolMessages, setProtocolMessages] = useState([]);
  const [isMonitoring, setIsMonitoring] = useState(false);
  const monitorIntervalRef = useRef(null);

  // Helper to parse Python dict string to JS object
  const parsePythonDictString = useCallback((pythonStr) => {
    if (!pythonStr || typeof pythonStr !== 'string') {
      return pythonStr;
    }
    try {
      const jsonStr = pythonStr
        .replace(/'/g, '"')
        .replace(/True/g, 'true')
        .replace(/False/g, 'false')
        .replace(/None/g, 'null');
      return JSON.parse(jsonStr);
    } catch (e) {
      console.warn('Could not parse Python dict string:', e);
      return pythonStr;
    }
  }, []);

  const endpointTarget = useMemo(() =>
    buildTargetValue(endpoint?.host || host, endpoint?.port || port),
    [endpoint, host, port]
  );

  const stopMonitoring = useCallback(() => {
    if (monitorIntervalRef.current) {
      clearInterval(monitorIntervalRef.current);
      monitorIntervalRef.current = null;
    }
    setIsMonitoring(false);
  }, []);

  const loadStatus = useCallback(async () => {
    if (!endpointTarget) return;
    try {
      const result = await executeApiCall('status', endpointTarget, null);
      if (result?.ok) {
        // Parse Python dict string in status field
        const parsedPayload = result.payload;
        if (parsedPayload?.result?.status && typeof parsedPayload.result.status === 'string') {
          parsedPayload.result.status = parsePythonDictString(parsedPayload.result.status);
        }
        setStatusInfo(parsedPayload);
      }
    } catch (error) { console.error('Failed to load status:', error); }
  }, [endpointTarget, executeApiCall, parsePythonDictString]);

  const handleStartServer = useCallback(async () => {
    if (!endpointTarget) { setError('No endpoint configured'); return; }
    setLoading(true); setError(null);
    try {
      const result = await executeApiCall('start', endpointTarget, { host, port, mode, cp });
      if (result?.ok) {
        setConnected(true);
        await loadStatus();
      } else {
        setError(result?.payload?.error || result?.rawText || 'Failed to start server');
      }
    } catch (error) { setError(error.message); }
    finally { setLoading(false); }
  }, [endpointTarget, host, port, mode, cp, executeApiCall, loadStatus]);

  const handleStopServer = useCallback(async () => {
    if (!endpointTarget) { setError('No endpoint configured'); return; }
    setLoading(true); setError(null);
    try {
      const result = await executeApiCall('stop', endpointTarget, {});
      if (!result?.ok) {
        setError(result?.payload?.error || result?.rawText || 'Failed to stop server');
      }
    } catch (error) { setError(error.message); }
    finally { setLoading(false); }
  }, [endpointTarget, executeApiCall]);

  const fetchActionLogs = useCallback(async () => {
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

  const startMonitoring = useCallback(async () => {
    if (isMonitoring) return;
    if (!endpointTarget) { setError('No endpoint configured'); return; }
    
    stopMonitoring();
    setIsMonitoring(true);
    await fetchActionLogs();
    monitorIntervalRef.current = setInterval(fetchActionLogs, 5000);
  }, [endpointTarget, isMonitoring, fetchActionLogs, stopMonitoring]);

  const stopMonitoringHandler = useCallback(async () => {
    if (!isMonitoring) return;
    stopMonitoring();
  }, [isMonitoring, stopMonitoring]);

  const clearMessages = useCallback(async () => {
    if (!endpointTarget) { setError('No endpoint configured'); return; }
    const result = await executeApiCall('clear-logs', endpointTarget, {});
    if (result?.ok) setProtocolMessages([]);
    else setError(`Error clearing messages: ${result?.payload?.error || 'Unknown error'}`);
  }, [endpointTarget, executeApiCall]);

  const loadServerModel = useCallback(async () => {
    if (!endpointTarget) { setError('No endpoint configured'); return; }
    setLoading(true); setError(null);
    try {
      const result = await executeApiCall('model', endpointTarget, {});
      if (result?.ok) {
        // Debug: log the raw response
        console.log('[ACSIServer] Raw model API response:', JSON.stringify(result.payload, null, 2));
        
        // Try to extract model from various possible locations
        let modelData = result.payload;
        
        // Path 1: result.result.model (BFF wraps response in result)
        if (modelData?.result?.model) {
          modelData = modelData.result.model;
          console.log('[ACSIServer] Found model at result.result.model');
        }
        // Path 2: result.model
        else if (modelData?.result?.model) {
          modelData = modelData.result.model;
          console.log('[ACSIServer] Found model at result.model');
        }
        // Path 3: Direct model field
        else if (modelData?.model) {
          modelData = modelData.model;
          console.log('[ACSIServer] Found model at payload.model');
        }
        // Path 4: The payload itself might be the model
        
        // Check if there's a tree field
        if (modelData?.tree) {
          modelData = modelData.tree;
          console.log('[ACSIServer] Extracted tree from model');
        }
        
        // Handle case where model is a Python dict string
        if (typeof modelData === 'string') {
          console.log('[ACSIServer] Model is a string, parsing...');
          modelData = parsePythonDictString(modelData);
        }
        
        console.log('[ACSIServer] Extracted model data:', JSON.stringify(modelData, null, 2));
        
        // If we still have the full BFF response, try result field
        if (modelData === result.payload && modelData?.result) {
          modelData = modelData.result;
          console.log('[ACSIServer] Using result field as model');
        }
        
        // If modelData has accessPoints but no children structure, create a simple tree
        if (modelData?.accessPoints && !modelData.children && !modelData.ieds && !modelData.kind) {
          console.log('[ACSIServer] Creating simple tree from accessPoints');
          modelData = {
            iedName: modelData.iedName || endpoint?.name || 'Server',
            accessPoints: modelData.accessPoints.map(apName => ({
              name: apName,
              ldevices: []
            }))
          };
        }
        
        if (modelData && Object.keys(modelData).length > 0) {
          setTreeData(modelData);
        } else {
          setError('No model data found in response');
        }
      } else {
        setError(result?.payload?.error || result?.rawText || 'Failed to load model');
      }
    } catch (error) { setError(error.message); }
    finally { setLoading(false); }
  }, [endpointTarget, executeApiCall, parsePythonDictString, endpoint]);

  useEffect(() => () => { stopMonitoring(); }, [stopMonitoring]);

  return (
    <section className="page">
      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <h1><i className="fas fa-server" style={{ marginRight: '10px', color: 'var(--primary-light)' }}></i>ACSI Server</h1>
          {endpoint && (
            <span id="acsi-endpoint-badge" className="acsi-endpoint-badge" style={{ display: 'inline-flex' }}>
              {endpoint.name || `${endpoint.host}:${endpoint.port}`}
            </span>
          )}
        </div>
      </div>
      
      <div className="acsi-connection-section" style={{ display: 'flex', alignItems: 'flex-end', gap: '16px', marginBottom: '24px' }}>
        <div className="form-group">
          <label>WS Host</label>
          <input type="text" value={host} placeholder="0.0.0.0" onChange={(e) => setHost(e.target.value)} disabled={loading} />
        </div>
        <div className="form-group">
          <label>WS Port</label>
          <input type="number" value={port} placeholder="102" onChange={(e) => setPort(parseInt(e.target.value) || 102)} disabled={loading} />
        </div>
        <div className="form-group">
          <label>WS CP</label>
          <input type="text" value={cp} placeholder="cp1" onChange={(e) => setCp(e.target.value)} disabled={loading} />
        </div>
        <div className="form-group">
          <label>WS Mode</label>
          <input type="text" value={mode} placeholder="server" onChange={(e) => setMode(e.target.value)} disabled={loading} />
        </div>
        <button id="acsi-start-btn" className="btn-primary" onClick={handleStartServer} disabled={loading}>
          {loading ? 'Starting...' : 'Start Server'}
        </button>
        <button id="acsi-stop-btn" className="btn-secondary" onClick={handleStopServer} disabled={loading}>
          {loading ? 'Stopping...' : 'Stop Server'}
        </button>
      </div>
      
      <div style={{ display: 'flex', gap: '16px', marginBottom: '24px' }}>
        <button id="acsi-load-model-btn" className="btn-primary" onClick={loadServerModel} disabled={loading}>
          {loading ? 'Loading...' : 'Load Model'}
        </button>
        <button id="acsi-reload-status-btn" className="btn-secondary" onClick={loadStatus} disabled={!endpointTarget}>
          Reload Status
        </button>
        <button id="messages-start-btn" className="btn-primary" onClick={startMonitoring} disabled={!endpointTarget || isMonitoring}>
          {isMonitoring ? 'Monitoring...' : 'Start Monitor'}
        </button>
        <button id="messages-stop-btn" className="btn-secondary" onClick={stopMonitoringHandler} disabled={!isMonitoring}>
          Stop Monitor
        </button>
        <button id="messages-clear-btn" className="btn-secondary" onClick={clearMessages} disabled={!endpointTarget}>
          Clear Logs
        </button>
      </div>
      
      {error && <div className="alert alert-error" style={{ marginBottom: '16px', padding: '12px', background: 'var(--danger-bg)', color: 'var(--danger-color)', borderRadius: '4px' }}>
        <i className="fas fa-exclamation-triangle" style={{ marginRight: '8px' }}></i>{error}
      </div>}
      
      {statusInfo && (
        <div style={{ marginBottom: '24px', padding: '16px', background: 'var(--bg-card)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
          <h3 style={{ margin: 0, marginBottom: '12px', fontSize: '16px' }}>Server Status</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            <div><span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>Server Address</span><div style={{ fontWeight: '500' }}>{statusInfo.result?.status?.host}:{statusInfo.result?.status?.port}</div></div>
            <div><span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>State</span><div style={{ fontWeight: '500', color: statusInfo.result?.status?.status === 'running' ? 'var(--success-color)' : 'var(--text-secondary)' }}>{statusInfo.result?.status?.status || 'N/A'}</div></div>
            <div><span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>Model</span><div style={{ fontWeight: '500' }}>{statusInfo.result?.status?.modelName || 'N/A'}</div></div>
            <div><span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>Clients</span><div style={{ fontWeight: '500' }}>{statusInfo.result?.status?.connectedClients || 0}</div></div>
          </div>
        </div>
      )}
      
      <div id="acsi-modelPanel" className="model-tree" style={{ marginTop: '24px' }}>
        {treeData ? <Tree data={treeData} /> : 
          <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '20px' }}>
            {endpoint ? `Click "Load Model" to view the server model for ${endpoint.name || endpoint.host}:${endpoint.port}` : 'Configure and start the ACSI Server to load model'}
          </p>}
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

export default ACSIServer;
