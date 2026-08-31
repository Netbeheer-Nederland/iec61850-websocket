// TLSConfigModal.jsx
import React, { useState, useEffect, useCallback } from 'react';

function parsePythonDictString(pythonStr) {
  if (!pythonStr || typeof pythonStr !== 'string') return pythonStr;
  try {
    const jsonStr = pythonStr
      .replace(/'/g, '"')
      .replace(/True/g, 'true')
      .replace(/False/g, 'false')
      .replace(/None/g, 'null');
    return JSON.parse(jsonStr);
  } catch (e) {
    console.log('Warning: Could not parse Python dict string as JSON:', e);
    return pythonStr;
  }
}

const RECONFIG_CONNECTION_API = {
  id: 'reconfig-connection',
  label: 'POST /api/reconfig-connection',
  method: 'POST',
  path: '/api/reconfig-connection'
};

const TLS_CONFIG_API = {
  id: 'tls-config',
  label: 'POST /api/connections/tls-config',
  method: 'POST',
  path: '/api/connections/tls-config'
};

function getApiById(id) {
  if (id === 'reconfig-connection') return RECONFIG_CONNECTION_API;
  if (id === 'tls-config') return TLS_CONFIG_API;
  return null;
}

const TLSConfigModal = ({
  isOpen,
  onClose,
  connection,
  bffBaseUrl = 'http://localhost:5000',
  onSuccess = () => {},
  onError = () => {}, 
  wsHost,   
  wsPort     
}) => {
  const [enableTLS, setEnableTLS] = useState(false);
  const [tlsVersion, setTlsVersion] = useState('1.2');
  const [serverKey, setServerKey] = useState('');
  const [serverCert, setServerCert] = useState('');
  const [caCert, setCaCert] = useState('');
  // Initialize wsMode from connection if available
  const [wsMode, setWsMode] = useState(() => {
    if (connection?.ws_mode) {
      const mode = String(connection.ws_mode).toLowerCase();
      if (mode === 'passive' || mode === 'active') return mode;
    }
    // Default based on connection type
    if (connection?.type === 'RTI-SO') return 'active';
    if (connection?.properties_info?.properties?.ws_mode) {
      const mode = String(connection.properties_info.properties.ws_mode).toLowerCase();
      if (mode === 'passive' || mode === 'active') return mode;
    }
    return 'passive';
  });

  const isServerMode = wsMode === 'passive' || wsMode === 'Passive';
  const isClientMode = wsMode === 'active' || wsMode === 'Active';

  // Fetch TLS config ONLY from the server's runtime endpoint
  // If it fails, fields remain empty (no fallbacks)
  useEffect(() => {
    const fetchRuntimeTlsConfig = async () => {
      if (!isOpen || !connection) return;
      
      // Determine the runtime server port based on connection type
      // RTI-SO uses port 5002, RTI-FSP uses port 5001
      const host = connection.host || 'localhost';
      const port = connection.port;
      
      if (!host || !port) {
        console.warn('Cannot fetch TLS config: missing host or port');
        return;
      }
      
      const url = `http://${host}:${port}/api/tls-config`;
      
      try {
        
        const response = await fetch(url, {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' }
        });
        
        if (response.ok) {
          const data = await response.json();
          const updates = {};
          
          // Extract TLS fields from response - try both snake_case and camelCase variants
          const extractFields = (obj) => {
            const getField = (snake, camel, formField) => {
              const value = obj[snake] || obj[camel];
              if (value !== undefined && value !== null && value !== '') {
                updates[formField] = value;
              }
            };
            
            getField('enable_tls', 'enableTLS', 'enableTLS');
            getField('tls_version', 'tlsVersion', 'tlsVersion');
            getField('server_key', 'serverKey', 'serverKey');
            getField('server_cert', 'serverCert', 'serverCert');
            getField('server_ca', 'serverCa', 'caCert');
            getField('ws_mode', 'wsMode', 'wsMode');
          };
          
          // Try to extract from root level
          extractFields(data);
          
          // Also check nested config
          if (data.config) {
            extractFields(data.config);
          }
          
          // Only update if we have values
          if (Object.keys(updates).length > 0) {
            if (updates.enableTLS !== undefined) setEnableTLS(updates.enableTLS);
            if (updates.tlsVersion !== undefined) {
              // Parse tls_version - handle both '1.2'/'1.3' and 'TLSv1_2'/'TLSv1_3' formats
              let version = '1.2';
              if (updates.tlsVersion) {
                const versionStr = String(updates.tlsVersion).toLowerCase();
                if (versionStr.includes('1.3') || versionStr.includes('tls1_3')) {
                  version = '1.3';
                } else if (versionStr.includes('1.2') || versionStr.includes('tls1_2')) {
                  version = '1.2';
                } else {
                  version = versionStr;
                }
              }
              setTlsVersion(version);
            }
            if (updates.serverKey !== undefined) setServerKey(updates.serverKey);
            if (updates.serverCert !== undefined) setServerCert(updates.serverCert);
            if (updates.caCert !== undefined) setCaCert(updates.caCert);
            if (updates.wsMode !== undefined) setWsMode(updates.wsMode);
          }
        }
        // If response is not ok or any error occurs, fields remain empty - no fallback
      } catch (error) {
        console.warn('Failed to fetch TLS config from server endpoint:', error);
        // Fields remain empty - user can configure from scratch
      }
    };
    
    fetchRuntimeTlsConfig();
  }, [isOpen, connection, wsHost]);

  const handleFileUpload = useCallback((e, fieldName) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      const content = e.target.result;
      switch (fieldName) {
        case 'serverKey': setServerKey(content); break;
        case 'serverCert': setServerCert(content); break;
        case 'caCert': setCaCert(content); break;
      }
    };
    reader.readAsText(file);
  }, []);

  const buildConfig = useCallback(() => {
    if (!connection) return null;
    return {
      host: wsHost,
      port: wsPort,
      connection_name: connection.name,
      enable_tls: enableTLS,
      tls_version: tlsVersion === '1.2' ? 'TLSv1_2' : 'TLSv1_3',
      ws_mode: wsMode,
      ...(isServerMode ? { server_key: serverKey, server_cert: serverCert, server_ca: null } : {}),
      ...(isClientMode ? { server_key: null, server_cert: null, server_ca: caCert } : {})
    };
  }, [connection, enableTLS, tlsVersion, wsMode, isServerMode, isClientMode, serverKey, serverCert, caCert]);

  const executeApiCall = useCallback(async (api, targetValue, bodyOverride = {}) => {
    try {
      const url = `${bffBaseUrl}/api/execute`;
      const payload = { target: targetValue, method: api.method || 'GET', path: api.path || '/' };
      if (bodyOverride && Object.keys(bodyOverride).length > 0) payload.body = bodyOverride;
      const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      const rawText = await response.text();
      let parsedPayload = null;
      try { parsedPayload = JSON.parse(rawText); } catch (error) {}
      return { ok: response.ok, status: response.status, payload: parsedPayload, rawText };
    } catch (error) {
      return { ok: false, status: 0, payload: null, error: error.message };
    }
  }, [bffBaseUrl]);

  const handleSubmit = useCallback(async (e) => {
    e.preventDefault();
    if (!connection) { onError?.('Please select a connection'); return; }
    const config = buildConfig();
    if (!config) return;
    try {
      // Call BFF's /api/connections/tls-config endpoint directly
      // This saves TLS config to BFF's connections.json
      const bffUrl = `${bffBaseUrl}/api/connections/tls-config`;
      const bffResponse = await fetch(bffUrl, { 
        method: 'POST', 
        headers: { 'Content-Type': 'application/json' }, 
        body: JSON.stringify(config) 
      });
      const bffRawText = await bffResponse.text();
      let bffPayload = null;
      try { bffPayload = JSON.parse(bffRawText); } catch (error) {}
      
      if (!bffResponse.ok) { 
        onError?.(`Failed to save TLS config to BFF: ${bffPayload?.error || bffRawText || 'Unknown error'}`); 
        return;
      }
      
      // Also reconfigure the server's runtime TLS config
      // This ensures the /api/tls-config GET endpoint returns the updated values
      const host = connection.host || 'localhost';
      const port = connection.port;
      const reconfigureUrl = `http://${host}:${port}/api/reconfig-connection`;
      
      const reconfigureResponse = await fetch(reconfigureUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
      });
      
      const reconfigureRawText = await reconfigureResponse.text();
      let reconfigurePayload = null;
      try { reconfigurePayload = JSON.parse(reconfigureRawText); } catch (error) {}
      
      if (reconfigureResponse.ok) {
        onSuccess?.(`TLS config saved and applied for ${connection.name}`);
        onClose();
      } else {
        // Even if reconfigure fails, the BFF save succeeded
        onSuccess?.(`TLS config saved for ${connection.name} (runtime update may have failed)`);
        onClose();
      }
    } catch (error) { 
      onError?.(`Failed to save TLS config: ${error.message}`); 
    }
  }, [connection, enableTLS, buildConfig, bffBaseUrl, onSuccess, onError, onClose, wsHost]);

  if (!isOpen || !connection) return null;
  
  // If wsMode is still 'N/A', we still want to show the modal with empty fields
  // The user can configure TLS even if there's no existing config

  // All styles use CSS variables from your theme
  const styles = {
    modal: {
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      background: 'rgba(0,0,0,0.7)', zIndex: 1000,
      display: 'flex', justifyContent: 'center', alignItems: 'center'
    },
    modalContent: {
      background: 'var(--bg-card)', borderRadius: '12px',
      width: '90%', maxWidth: '600px', maxHeight: '90vh', overflowY: 'auto',
      border: '1px solid var(--border-color)', boxShadow: '0 4px 20px rgba(0,0,0,0.2)'
    },
    modalHeader: {
      padding: '20px 24px', borderBottom: '1px solid var(--border-color)',
      display: 'flex', justifyContent: 'space-between', alignItems: 'center'
    },
    modalBody: { padding: '24px' },
    modalFooter: {
      padding: '16px 24px', borderTop: '1px solid var(--border-color)',
      display: 'flex', justifyContent: 'flex-end', gap: '12px'
    },
    formGroup: { marginBottom: '20px' },
    checkboxLabel: {
      display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer',
      color: 'var(--text-primary)', fontSize: '14px'
    },
    checkboxInput: { width: '18px', height: '18px', accentColor: 'var(--primary-color)' },
    label: { display: 'block', marginBottom: '8px', fontWeight: '500', color: 'var(--text-primary)' },
    select: {
      width: '100%', padding: '10px 12px', borderRadius: '8px',
      border: '1px solid var(--border-color)', background: 'var(--bg-hover)',
      color: 'var(--text-primary)', fontSize: '14px'
    },
    input: {
      width: '100%', padding: '10px 12px', borderRadius: '8px',
      border: '1px solid var(--border-color)', background: 'var(--bg-hover)',
      color: 'var(--text-primary)', fontSize: '14px', marginBottom: '10px'
    },
    textarea: {
      width: '100%', padding: '10px 12px', borderRadius: '8px',
      border: '1px solid var(--border-color)', background: 'var(--bg-hover)',
      color: 'var(--text-primary)', fontSize: '14px', fontFamily: 'monospace',
      minHeight: '100px', display: 'block'
    },
    button: { padding: '10px 20px', borderRadius: '8px', fontWeight: '600', cursor: 'pointer' },
    infoBox: {
      margin: '16px 0', padding: '12px', background: 'var(--bg-hover)',
      borderRadius: '6px', fontSize: '13px', border: '1px solid var(--border-light)'
    },
    fileInputGroup: { display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '10px' }
  };

  return (
    <div style={styles.modal}>
      <div style={styles.modalContent}>
        <div style={styles.modalHeader}>
          <h2 style={{ margin: 0, color: 'var(--text-primary)' }}>
            <i className="fas fa-shield-alt" style={{ marginRight: '8px' }}></i>
            TLS Configuration - {connection.name}
          </h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', fontSize: '24px', cursor: 'pointer', color: 'var(--text-muted)' }}>
            ×
          </button>
        </div>

        <div style={styles.modalBody}>
          <form onSubmit={handleSubmit}>
            <div style={styles.formGroup}>
              <label style={styles.checkboxLabel}>
                <input type="checkbox" id="tls-enable" checked={enableTLS} onChange={(e) => setEnableTLS(e.target.checked)} style={styles.checkboxInput} />
                Enable TLS (WSS)
              </label>
            </div>

            <div style={styles.formGroup}>
              <label style={styles.label}>TLS Version:</label>
              <select id="tls-version" value={tlsVersion} onChange={(e) => setTlsVersion(e.target.value)} style={styles.select}>
                <option value="1.2">TLS 1.2</option>
                <option value="1.3">TLS 1.3</option>
              </select>
            </div>

            {isServerMode && (
              <>
                <div style={styles.formGroup}>
                  <label style={styles.label}>Server Private Key (PEM):</label>
                  <div style={styles.fileInputGroup}>
                    <input type="file" id="tls-private-key" accept=".pem,.key" onChange={(e) => handleFileUpload(e, 'serverKey')} />
                  </div>
                  <textarea id="tls-key-content" value={serverKey} onChange={(e) => setServerKey(e.target.value)} placeholder="-----BEGIN PRIVATE KEY-----..." style={styles.textarea} />
                </div>
                <div style={styles.formGroup}>
                  <label style={styles.label}>Server Certificate (PEM):</label>
                  <div style={styles.fileInputGroup}>
                    <input type="file" id="tls-server-cert" accept=".pem,.crt,.cer" onChange={(e) => handleFileUpload(e, 'serverCert')} />
                  </div>
                  <textarea id="tls-server-cert-content" value={serverCert} onChange={(e) => setServerCert(e.target.value)} placeholder="-----BEGIN CERTIFICATE-----..." style={styles.textarea} />
                </div>
              </>
            )}

            {isClientMode && (
              <div style={styles.formGroup}>
                <label style={styles.label}>Server CA Certificate (PEM):</label>
                <div style={styles.fileInputGroup}>
                  <input type="file" id="tls-ca-cert" accept=".pem,.crt,.cer" onChange={(e) => handleFileUpload(e, 'caCert')} />
                </div>
                <textarea id="tls-ca-cert-content" value={caCert} onChange={(e) => setCaCert(e.target.value)} placeholder="-----BEGIN CERTIFICATE-----..." style={styles.textarea} />
              </div>
            )}

            <div style={styles.infoBox}>
              <strong>Mode:</strong> {isServerMode ? 'Server (Passive)' : 'Client (Active)'}
              <br />
              <span style={{ color: 'var(--text-muted)' }}>
                {isServerMode ? 'Configure server certificates for incoming connections' : 'Configure CA certificate to validate server'}
              </span>
            </div>

            <div style={styles.modalFooter}>
              <button type="button" className="btn-secondary" onClick={onClose} style={styles.button}>Cancel</button>
              <button type="submit" className="btn-primary" style={styles.button}>Save</button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};

export default TLSConfigModal;
export { parsePythonDictString, getApiById, RECONFIG_CONNECTION_API };