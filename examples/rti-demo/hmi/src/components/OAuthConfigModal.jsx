// OAuthConfigModal.jsx
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

const RECONFIG_OAUTH_API = {
  id: 'reconfig-oauth',
  label: 'POST /api/reconfig-oauth',
  method: 'POST',
  path: '/api/reconfig-oauth'
};

const OAUTH_CONFIG_API = {
  id: 'oauth-config',
  label: 'POST /api/connections/oauth-config',
  method: 'POST',
  path: '/api/connections/oauth-config'
};

function getApiById(id) {
  if (id === 'reconfig-oauth') return RECONFIG_OAUTH_API;
  if (id === 'oauth-config') return OAUTH_CONFIG_API;
  return null;
}

const OAuthConfigModal = ({
  isOpen,
  onClose,
  connection,
  connections = [],
  bffBaseUrl = 'http://localhost:5000',
  onSuccess,
  onError,
  wsHost,
  wsPort
}) => {
  const [enableOAuth, setEnableOAuth] = useState(false);
  const [enableTokenRefresh, setEnableTokenRefresh] = useState(false);
  const [certificateEndpointUrl, setCertificateEndpointUrl] = useState('');
  const [tokenIssuerUrl, setTokenIssuerUrl] = useState('');
  const [serverCaCert, setServerCaCert] = useState('');
  const [tokenEndpointUrl, setTokenEndpointUrl] = useState('');
  const [clientId, setClientId] = useState('');
  const [clientSecret, setClientSecret] = useState('');
  const [clientCaCert, setClientCaCert] = useState('');
  const [selectedIdpServer, setSelectedIdpServer] = useState('');

  // Get IDP-Server connections
  const idpServers = connections.filter(conn => conn.type === 'IDP-Server');

  const wsMode = connection?.properties_info?.properties?.ws_mode || 'N/A';
  const isClientMode = wsMode === 'active' || wsMode === 'Active';
  const isServerMode = wsMode === 'passive' || wsMode === 'Passive';

  // Helper to get OAuth config from connection
  const getOAuthConfigFromConnection = useCallback(() => {
    if (!connection) return {};
    
    // Try to get OAuth config from different possible locations
    const oauthConfig = connection.OAuth || connection.oauth || {};
    
    return {
      enableOAuth: oauthConfig.enable_oauth || oauthConfig.enabled || false,
      enableTokenRefresh: oauthConfig.enable_token_refresh || false,
      certificateEndpointUrl: oauthConfig.certificate_endpoint || oauthConfig.certificate_endpoint_url || '',
      tokenIssuerUrl: oauthConfig.token_issuer || oauthConfig.token_issuer_url || '',
      serverCaCert: oauthConfig.auth_server_ca || oauthConfig.ca_certificate || oauthConfig.server_ca || '',
      tokenEndpointUrl: oauthConfig.token_endpoint || oauthConfig.token_endpoint_url || '',
      clientId: oauthConfig.client_id || '',
      clientSecret: oauthConfig.client_secret || '',
      clientCaCert: oauthConfig.client_ca_cert || oauthConfig.ca_cert || oauthConfig.ca_certificate || ''
    };
  }, [connection]);

  const handleFileUpload = useCallback((e, fieldType) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      const content = e.target.result;
      if (fieldType === 'server') setServerCaCert(content);
      else setClientCaCert(content);
    };
    reader.readAsText(file);
  }, []);

  useEffect(() => {
    if (isOpen && connection) {
      const oauthConfig = getOAuthConfigFromConnection();
      setEnableOAuth(oauthConfig.enableOAuth || false);
      setEnableTokenRefresh(oauthConfig.enableTokenRefresh || false);
      setCertificateEndpointUrl(oauthConfig.certificateEndpointUrl || '');
      setTokenIssuerUrl(oauthConfig.tokenIssuerUrl || '');
      setServerCaCert(oauthConfig.serverCaCert || '');
      setTokenEndpointUrl(oauthConfig.tokenEndpointUrl || '');
      setClientId(oauthConfig.clientId || '');
      setClientSecret(oauthConfig.clientSecret || '');
      setClientCaCert(oauthConfig.clientCaCert || '');
      
      // Try to find matching IDP server for the certificate endpoint
      if (oauthConfig.certificateEndpointUrl) {
        const matchingIdp = idpServers.find(server => 
          server.endpoint === oauthConfig.certificateEndpointUrl ||
          server.endpoint?.includes(oauthConfig.certificateEndpointUrl) ||
          oauthConfig.certificateEndpointUrl?.includes(server.endpoint || '')
        );
        if (matchingIdp) {
          setSelectedIdpServer(matchingIdp.name);
        }
      }
    }
  }, [isOpen, connection, getOAuthConfigFromConnection, idpServers]);

  // When an IDP-Server is selected, populate the certificate endpoint
  useEffect(() => {
    if (selectedIdpServer) {
      const selected = idpServers.find(server => server.name === selectedIdpServer);
      if (selected && selected.endpoint) {
        setCertificateEndpointUrl(selected.endpoint);
      }
    }
  }, [selectedIdpServer, idpServers]);

  const buildConfig = useCallback(() => {
    if (!connection) return null;
    const config = {host: connection.host || wsHost, port: connection.port || wsPort, connection_name: connection.name, enable_oauth: enableOAuth, ws_mode: wsMode };
    if (isServerMode) {
      return { ...config, certificate_endpoint_url: certificateEndpointUrl, token_issuer_url: tokenIssuerUrl, ca_certificate: serverCaCert };
    } else {
      return { 
        ...config, 
        token_endpoint_url: tokenEndpointUrl, 
        client_id: clientId, 
        client_secret: clientSecret, 
        ca_certificate: clientCaCert,
        client_ca_cert: clientCaCert,
        enable_token_refresh: enableTokenRefresh 
      };
    }
  }, [connection, enableOAuth, wsMode, isServerMode, certificateEndpointUrl, tokenIssuerUrl, serverCaCert, tokenEndpointUrl, clientId, clientSecret, clientCaCert, enableTokenRefresh, wsHost, wsPort]);

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
    if (!connection) { onError?.('No connection selected'); return; }
    const config = buildConfig();
    if (!config) return;
    try {
      // Save to BFF's connections.json
      const bffUrl = `${bffBaseUrl}/api/connections/oauth-config`;
      const bffResponse = await fetch(bffUrl, { 
        method: 'POST', 
        headers: { 'Content-Type': 'application/json' }, 
        body: JSON.stringify(config) 
      });
      const bffRawText = await bffResponse.text();
      let bffPayload = null;
      try { bffPayload = JSON.parse(bffRawText); } catch (error) {}
      
      if (!bffResponse.ok) { 
        onError?.(`Failed to save OAuth config to BFF: ${bffPayload?.error || bffPayload?.message || bffRawText || 'Unknown error'}`); 
        return;
      }
      
      // Also call reconfig-oauth on the actual endpoint (if enabled)
      if (enableOAuth) {
        const targetValue = `${connection.host}:${connection.port}`;
        const endpointConfig = { ...config };
        // Add cp if available in connection
        if (connection.cp) {
          endpointConfig.cp = connection.cp;
        }
        const api = getApiById('reconfig-oauth');
        const endpointResult = await executeApiCall(api.id, targetValue, endpointConfig);
        
        if (!endpointResult?.ok) {
          onError?.(`Failed to reconfigure OAuth on endpoint: ${endpointResult?.payload?.error || endpointResult?.rawText || 'Unknown error'}`);
          return;
        }
      }
      
      onSuccess?.(`OAuth config saved for ${connection.name}`); 
      onClose(); 
    } catch (error) { 
      onError?.(`Failed to save OAuth config: ${error.message}`); 
    }
  }, [connection, enableOAuth, buildConfig, bffBaseUrl, onSuccess, onError, onClose, executeApiCall]);

  if (!isOpen || !connection || wsMode === 'N/A') return null;

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
    input: {
      width: '100%', padding: '10px 12px', borderRadius: '8px',
      border: '1px solid var(--border-color)', background: 'var(--bg-hover)',
      color: 'var(--text-primary)', fontSize: '14px'
    },
    textarea: {
      width: '100%', padding: '10px 12px', borderRadius: '8px',
      border: '1px solid var(--border-color)', background: 'var(--bg-hover)',
      color: 'var(--text-primary)', fontSize: '14px', fontFamily: 'monospace',
      minHeight: '100px', display: 'block', marginTop: '10px'
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
            <i className="fas fa-key" style={{ marginRight: '8px' }}></i>
            OAuth Configuration - {connection.name}
          </h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', fontSize: '24px', cursor: 'pointer', color: 'var(--text-muted)' }}>
            ×
          </button>
        </div>

        <div style={styles.modalBody}>
          <form onSubmit={handleSubmit}>
            <div style={styles.formGroup}>
              <label style={styles.checkboxLabel}>
                <input type="checkbox" id="oauth-enable" checked={enableOAuth} onChange={(e) => setEnableOAuth(e.target.checked)} style={styles.checkboxInput} />
                Enable OAuth 2.0
              </label>
            </div>

            {idpServers.length > 0 && (
              <div style={styles.formGroup}>
                <label style={styles.label}>IDP Server:</label>
                <select 
                  id="oauth-idp-server" 
                  value={selectedIdpServer} 
                  onChange={(e) => setSelectedIdpServer(e.target.value)} 
                  disabled={!enableOAuth}
                  style={styles.input}
                >
                  <option value="">Select an IDP Server...</option>
                  {idpServers.map(server => (
                    <option key={server.name} value={server.name}>{server.name}</option>
                  ))}
                </select>
              </div>
            )}

            {isServerMode && (
              <>
                <div style={styles.formGroup}>
                  <label style={styles.label}>Certificate Endpoint URL:</label>
                  <input type="text" id="oauth-cert-url" value={certificateEndpointUrl} onChange={(e) => setCertificateEndpointUrl(e.target.value)} placeholder="https://auth.example.com/certs" disabled={!enableOAuth} style={styles.input} />
                </div>
                <div style={styles.formGroup}>
                  <label style={styles.label}>Token Issuer URL:</label>
                  <input type="text" id="oauth-issuer-url" value={tokenIssuerUrl} onChange={(e) => setTokenIssuerUrl(e.target.value)} placeholder="https://auth.example.com" disabled={!enableOAuth} style={styles.input} />
                </div>
                <div style={styles.formGroup}>
                  <label style={styles.label}>Auth Server CA Certificate (PEM):</label>
                  <div style={styles.fileInputGroup}>
                    <input type="file" id="oauth-ca-cert" accept=".pem,.crt,.cer" onChange={(e) => handleFileUpload(e, 'server')} disabled={!enableOAuth} />
                  </div>
                  <textarea id="oauth-cert-content" value={serverCaCert} onChange={(e) => setServerCaCert(e.target.value)} placeholder="-----BEGIN CERTIFICATE-----..." disabled={!enableOAuth} style={styles.textarea} />
                </div>
              </>
            )}

            {isClientMode && (
              <>
                <div style={styles.formGroup}>
                  <label style={styles.label}>Token Endpoint URL:</label>
                  <input type="text" id="oauth-token-url" value={tokenEndpointUrl} onChange={(e) => setTokenEndpointUrl(e.target.value)} placeholder="https://auth.example.com/token" disabled={!enableOAuth} style={styles.input} />
                </div>
                <div style={styles.formGroup}>
                  <label style={styles.label}>Client ID:</label>
                  <input type="text" id="oauth-client-id" value={clientId} onChange={(e) => setClientId(e.target.value)} placeholder="Your client ID" disabled={!enableOAuth} style={styles.input} />
                </div>
                <div style={styles.formGroup}>
                  <label style={styles.label}>Client Secret:</label>
                  <input type="password" id="oauth-client-secret" value={clientSecret} onChange={(e) => setClientSecret(e.target.value)} placeholder="Your client secret" disabled={!enableOAuth} style={styles.input} />
                </div>
                <div style={styles.formGroup}>
                  <label style={styles.label}>Auth Server CA Certificate (PEM):</label>
                  <div style={styles.fileInputGroup}>
                    <input type="file" id="oauth-ca-cert-client" accept=".pem,.crt,.cer" onChange={(e) => handleFileUpload(e, 'client')} disabled={!enableOAuth} />
                  </div>
                  <textarea id="oauth-cert-content-client" value={clientCaCert} onChange={(e) => setClientCaCert(e.target.value)} placeholder="-----BEGIN CERTIFICATE-----..." disabled={!enableOAuth} style={styles.textarea} />
                </div>
                <div style={styles.formGroup}>
                  <label style={styles.checkboxLabel}>
                    <input type="checkbox" id="oauth-enable-refresh" checked={enableTokenRefresh} onChange={(e) => setEnableTokenRefresh(e.target.checked)} disabled={!enableOAuth} style={styles.checkboxInput} />
                    Enable Token Refresh
                  </label>
                </div>
              </>
            )}

            <div style={styles.infoBox}>
              <strong>Mode:</strong> {isServerMode ? 'Server (Active)' : 'Client (Passive)'}
              <br />
              <span style={{ color: 'var(--text-muted)' }}>
                {isServerMode ? 'Configure as OAuth provider' : 'Configure as OAuth client'}
              </span>
            </div>

            <div style={styles.modalFooter}>
              <button type="button" className="btn-secondary" onClick={onClose} style={styles.button}>Cancel</button>
              <button type="submit" className="btn-primary" disabled={!enableOAuth} style={styles.button}>Save</button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};

OAuthConfigModal.defaultProps = {
  onSuccess: () => {},
  onError: () => {}
};

export default OAuthConfigModal;
export { parsePythonDictString, getApiById, RECONFIG_OAUTH_API };