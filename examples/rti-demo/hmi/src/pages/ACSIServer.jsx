import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { executeApiCall, buildTargetValue, getApiById } from '../services/apiService';
import Tree from '../components/Tree';
import { transformModelToTree } from '../utils/modelUtils';

import TLSConfigModal from '../components/TLSConfigModal';

function ACSIServer({ settings, updateModel, getModel, connections: propConnections, bffBaseUrl = 'http://localhost:5000'}) {
  const location = useLocation();
  const navigate = useNavigate();
  const endpoint = location.state?.endpoint;
  
  const [host, setHost] = useState('rti-so');
  const [port, setPort] = useState(String(8765));
  const [cp, setCp] = useState(endpoint?.cp || 'cp1');
  const [mode, setMode] = useState(endpoint?.mode || 'server');
  
  // Create instance-specific storage key
  const instanceId = endpoint?.name || `${endpoint?.host || host}:${endpoint?.port || port}`;
  const storageKey = `acsi-server-connected-${instanceId}`;
  
  const [connected, setConnected] = useState(() => localStorage.getItem(storageKey) === 'true');
  const [treeData, setTreeData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [statusInfo, setStatusInfo] = useState(null);
  const [protocolMessages, setProtocolMessages] = useState([]);
  const [isMonitoring, setIsMonitoring] = useState(false);
  const [expandedNodes, setExpandedNodes] = useState({});
  const [connections, setConnections] = useState(propConnections || []);
  const monitorIntervalRef = useRef(null);

  const [showTLSModal, setShowTLSModal] = useState(false);
  const [useOAuth, setUseOAuth] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    localStorage.setItem(storageKey, String(connected));
  }, [connected, storageKey]);

  const handleExpandToggle = useCallback((ref, expanded) => {
    setExpandedNodes(prev => ({
      ...prev,
      [ref]: expanded
    }));
  }, []);

  // Fetch connections from BFF to get live TLS config
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
        .replace(/None/g, 'null')
        .replace(/""+/g, '"');
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

  // Fetch OAuth status from the FSP server on page load
  useEffect(() => {
    const fetchOAuthStatus = async () => {
      if (!endpointTarget) return;
      try {
        const result = await executeApiCall('oauth-status', endpointTarget, {});
        if (result?.ok) {
          const enableOAuth = result.payload?.result?.enable_oauth ?? result.payload?.enable_oauth ?? false;
          setUseOAuth(enableOAuth);
        }
      } catch (error) {
        console.error('Failed to fetch OAuth status:', error);
      }
    };
    fetchOAuthStatus();
  }, [endpointTarget]);

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
      if (result?.ok) {
        setConnected(false);
        await loadStatus();
      } else {
        setError(result?.payload?.error || result?.rawText || 'Failed to stop server');
      }
    } catch (error) { setError(error.message); }
    finally { setLoading(false); }
  }, [endpointTarget, executeApiCall, loadStatus]);

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
        let modelData = result.payload;
        
        // Path 1: result.result.model (BFF wraps response in result)
        if (modelData?.result?.model) {
          modelData = modelData.result.model;
        }
        // Path 2: Direct model field
        else if (modelData?.model) {
          modelData = modelData.model;
        }
        // Path 3: The payload itself might be the model
        
        // Check if there's a tree field
        if (modelData?.tree) {
          modelData = modelData.tree;
        }
        
        // Handle case where model is a Python dict string
        if (typeof modelData === 'string') {
          // Try to parse as JSON first
          try {
            modelData = JSON.parse(modelData);
          } catch (e) {
            // If not JSON, try to parse as Python dict string
            const jsonStr = modelData
              .replace(/'/g, '"')
              .replace(/True/g, 'true')
              .replace(/False/g, 'false')
              .replace(/None/g, 'null');
            try {
              modelData = JSON.parse(jsonStr);
            } catch (e2) {
              console.error('Failed to parse model data:', e2);
            }
          }
        }
        
        // If we still have the full BFF response, try result field
        if (modelData === result.payload && modelData?.result) {
          modelData = modelData.result;
        }
        
        // If modelData has accessPoints but no children structure, create a simple tree
        if (modelData?.accessPoints && !modelData.children && !modelData.ieds && !modelData.kind) {
          modelData = {
            iedName: modelData.iedName || endpoint?.name || 'Server',
            accessPoints: modelData.accessPoints.map(apName => ({
              name: apName,
              ldevices: []
            }))
          };
        }
        
        if (modelData && Object.keys(modelData).length > 0) {
          setTreeData(transformModelToTree(modelData));
          // Save the model in the global models list
          updateModel(endpointTarget, modelData);
        } else {
          setError('No model data found in response');
        }
      } else {
        setError(result?.payload?.error || result?.rawText || 'Failed to load model');
      }
    } catch (error) { setError(error.message); }
    finally { setLoading(false); }
  }, [endpointTarget, executeApiCall, endpoint]);

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
          <input type="number" value={port} placeholder="102" onChange={(e) => setPort(e.target.value)} disabled={loading} />
        </div>
        <div className="form-group">
          <label>WS CP</label>
          <input type="text" value={cp} placeholder="cp1" onChange={(e) => setCp(e.target.value)} disabled={loading} />
        </div>
        <div className="form-group">
          <label>WS Mode</label>
          <input type="text" value={mode} placeholder="server" onChange={(e) => setMode(e.target.value)} disabled={loading} />
        </div>
        <button id="acsi-start-btn" className="btn-primary" onClick={handleStartServer} disabled={loading || connected}>
          {loading ? 'Starting...' : 'Start Server'}
        </button>
        <button id="acsi-stop-btn" className="btn-secondary" onClick={handleStopServer} disabled={loading || !connected}>
          {loading ? 'Stopping...' : 'Stop Server'}
        </button>
      </div>

      {/* Security Configuration Buttons */}
      <div style={{ display: 'flex', gap: '16px', marginLeft: 'auto', marginBottom: '24px' }}>
        <button
          className="btn-secondary"
          onClick={() => setShowTLSModal(true)}
          disabled={loading}
          title="Configure TLS settings"
          id="acsi-tls-btn"
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
              if (endpointTarget && endpoint?.name) {
                setLoading(true);
                try {
                  // Build OAuth config from endpoint
                  const oauthConfig = endpoint?.OAuth || {};
                  
                  // For active mode (FSP), use the client's port for WebSocket connection
                  let connectionPort = endpoint?.port || port;
                  if (endpoint?.ws_mode === 'active' || endpoint?.ws_mode === 'Active') {
                      // Find corresponding client connection (SO) by replacing Server with Client in endpoint name
                      const clientName = endpoint.name.replace('Server', 'Client');
                      const clientConnection = connections.find(c => 
                          (c.type === 'RTI-SO' || c.acsi === 'client') && 
                          c.name === clientName
                      );
                      if (clientConnection) {
                          connectionPort = clientConnection.port;
                      }
                  }
                  
                  // Use the connection's own host/port for the target endpoint
                  const targetHost = endpoint?.host || host;
                  const targetPort = endpoint?.port || port;
                  const connectionTarget = buildTargetValue(targetHost, targetPort);
                  
                  const requestBody = {
                    connection_name: endpoint?.name,
                    enable_oauth: newValue,
                    ws_mode: endpoint?.ws_mode || 'active',
                    host: host || "127.0.0.1",
                    port: String(port) || "8675",
                    cp: cp,
                    // Always send OAuth config fields (null when disabling)
                    token_endpoint_url: newValue ? (oauthConfig.token_endpoint || '') : null,
                    client_id: newValue ? (oauthConfig.client_id || '') : null,
                    client_secret: newValue ? (oauthConfig.client_secret || '') : null,
                    ca_certificate: newValue ? (oauthConfig.auth_server_ca || '') : null,
                    enable_token_refresh: newValue ? (oauthConfig.enable_token_refresh || false) : false
                  };
                  
                  // Save to SO/FSP server
                  const soResult = await executeApiCall('reconfig-oauth', connectionTarget, requestBody);
                  
                  // Also save to BFF's connections.json
                  const bffOauthConfig = {
                    connection_name: endpoint?.name || host,
                    enable_oauth: newValue,
                    ws_mode: endpoint?.ws_mode || 'Active',
                    // Always send OAuth config fields (null when disabling)
                    token_endpoint_url: newValue ? (oauthConfig.token_endpoint || '') : null,
                    client_id: newValue ? (oauthConfig.client_id || '') : null,
                    client_secret: newValue ? (oauthConfig.client_secret || '') : null,
                    ca_certificate: newValue ? (oauthConfig.auth_server_ca || '') : null,
                    enable_token_refresh: newValue ? (oauthConfig.enable_token_refresh || false) : false
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
            id="acsi-oauth-checkbox"
          />
          <span style={{ color: 'var(--text-primary)' }}>Enable OAuth</span>
        </label>
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
        {treeData ? <Tree data={treeData} expandedNodes={expandedNodes} onExpandToggle={handleExpandToggle} /> : 
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
              (c.host === host && String(c.port) === String(port))
            );
            if (liveConn) {
              return liveConn;
            }
            // Fallback to endpoint with TLS if available
            if (endpoint?.TLS) {
              return {
                name: endpoint.name || host,
                host: endpoint.host || host,
                port: endpoint.port || port,
                type: 'RTI-SO',
                ws_mode: 'Active',
                TLS: endpoint.TLS,
                properties_info: {
                  properties: {
                    ws_mode: 'Active'
                  }
                }
              };
            }
            // Final fallback
            return {
              name: endpoint?.name || host,
              host: endpoint?.host || host,
              port: endpoint?.port || port,
              type: 'RTI-SO',
              ws_mode: 'Active',
              TLS: {},
              properties_info: {
                properties: {
                  ws_mode: 'Active'
                }
              }
            };
          }
        )()}
        bffBaseUrl={bffBaseUrl}
        wsHost={host}
        wsPort={port}
        onSuccess={(msg) => {
          setMessage({ type: 'success', text: msg });
          // Refetch connections to get updated TLS config
          const fetchConnections = async () => {
            try {
              const url = `${bffBaseUrl}/api/connections`;
              const response = await fetch(url);
              if (response.ok) {
                const data = await response.json();
                setConnections(data.connections || []);
              }
            } catch (error) {
              console.error('Failed to refetch connections:', error);
            }
          };
          fetchConnections();
        }}
        onError={(msg) => setMessage({ type: 'error', text: msg })}
      />
    </section>
  );
}

export default ACSIServer;
