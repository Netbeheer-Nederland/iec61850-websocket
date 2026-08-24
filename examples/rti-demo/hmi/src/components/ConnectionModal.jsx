import React, { useState, useEffect, useRef, useCallback } from 'react';

function ConnectionModal({ 
  settings, 
  showModal, 
  onClose, 
  currentConnection, 
  formData, 
  connections = [],
  onFormChange,
  onSave 
}) {
  const [selectedIdpServer, setSelectedIdpServer] = useState('');

  // Get IDP-Server connections
  const idpServers = connections.filter(conn => conn.type === 'IDP-Server');

  const handleInputChange = (e) => {
    const { id, value, type } = e.target;
    onFormChange(prev => ({
      ...prev,
      [id]: type === 'number' ? parseInt(value) : value
    }));
  };

  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      const content = e.target.result;
      onFormChange(prev => ({
        ...prev,
        auth_server_ca: content
      }));
    };
    reader.readAsText(file);
  };

  // Sync ACSI and ws_mode when type changes or modal opens
  const syncAcsiAndWsMode = (type, acsi, ws_mode) => {
    if (type === 'RTI-SO' && (acsi !== 'client' || ws_mode !== 'passive')) {
      onFormChange(prev => ({
        ...prev,
        acsi: 'client',
        ws_mode: 'passive'
      }));
    } else if (type === 'RTI-FSP' && (acsi !== 'server' || ws_mode !== 'active')) {
      onFormChange(prev => ({
        ...prev,
        acsi: 'server',
        ws_mode: 'active'
      }));
    }
  };

  useEffect(() => {
    syncAcsiAndWsMode(formData.type, formData.acsi, formData.ws_mode);
  }, [formData.type, formData.acsi, formData.ws_mode]);

  // Fetch OAuth config from BFF for the connection being edited
  useEffect(() => {
    const fetchBffOAuthConfig = async () => {
      if (!showModal || !currentConnection) return;
      
      // Only for connections that might have OAuth config
      const connType = currentConnection.type || formData.type || '';
      if (connType !== 'RTI-SO' && connType !== 'RTI-FSP' && connType !== 'Generic') return;
      
      const connName = currentConnection.name || formData.name;
      if (!connName) return;
      
      try {
        // Try to get OAuth config from BFF - use the same endpoint used for saving
        const bffHost = localStorage.getItem('bffHost') || settings?.bffHost || 'localhost';
        const bffPort = localStorage.getItem('bffPort') || settings?.bffPort || '5000';
        const url = `http://${bffHost}:${bffPort}/api/connections/oauth-config?connection_name=${encodeURIComponent(connName)}`;
        
        const response = await fetch(url, {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' }
        });
        
        if (response.ok) {
          const data = await response.json();
          const updates = {};
          
          // Extract OAuth fields from response - try both snake_case and camelCase variants
          const extractFields = (obj) => {
            const getField = (snake, camel, formField) => {
              const value = obj[snake] || obj[camel];
              if (value !== undefined && value !== null && value !== '') {
                updates[formField] = value;
              }
            };
            
            getField('certificate_endpoint', 'certificateEndpoint', 'certificate_endpoint');
            getField('certificate_endpoint_url', 'certificateEndpointUrl', 'certificate_endpoint');
            getField('token_issuer', 'tokenIssuer', 'token_issuer_url');
            getField('token_issuer_url', 'tokenIssuerUrl', 'token_issuer_url');
            getField('auth_server_ca', 'authServerCa', 'auth_server_ca');
            getField('ca_certificate', 'caCertificate', 'auth_server_ca');
            getField('realm', 'realm', 'realm');
            getField('token_endpoint', 'tokenEndpoint', 'token_endpoint');
            getField('token_endpoint_url', 'tokenEndpointUrl', 'token_endpoint');
            getField('client_id', 'clientId', 'client_id');
            getField('client_secret', 'clientSecret', 'client_secret');
            
            if (obj.enable_token_refresh !== undefined) {
              updates.enable_token_refresh = obj.enable_token_refresh;
            }
          };
          
          // Try to extract from root level
          extractFields(data);
          
          // Also check nested config
          if (data.config) {
            extractFields(data.config);
          }
          
          // Also check if wrapped in a connection object
          if (data.connection) {
            extractFields(data.connection);
          }
          
          // Only update if we have values
          if (Object.keys(updates).length > 0) {
            onFormChange(prev => ({ ...prev, ...updates }));
          }
        }
      } catch (error) {
        console.warn('Failed to fetch OAuth config from BFF:', error);
      }
    };
    
    fetchBffOAuthConfig();
  }, [showModal, currentConnection, formData.name, formData.type, onFormChange, settings]);


  // Find matching IDP server for the certificate endpoint when modal opens
  useEffect(() => {
    if (showModal && currentConnection) {
      // Try to find IDP server by name from formData (set by Setup.jsx or fetched from backend)
      const idpServerName = formData.idp_server || 
                           currentConnection.idp_server || 
                           (currentConnection.OAuth || {}).idp_server ||
                           (currentConnection.oauth || {}).idp_server ||
                           '';
      
      if (idpServerName) {
        const matchingByName = idpServers.find(server => server.name === idpServerName);
        if (matchingByName) {
          setSelectedIdpServer(matchingByName.name);
          // Also ensure certificate_endpoint is populated from IDP server
          if (matchingByName.endpoint && !formData.certificate_endpoint) {
            onFormChange(prev => ({
              ...prev,
              certificate_endpoint: matchingByName.endpoint
            }));
          }
          return;
        }
      }
      
      // Fall back to matching by certificate endpoint
      const certEndpoint = formData.certificate_endpoint || '';
      if (certEndpoint) {
        const matchingIdp = idpServers.find(server => {
          const serverEndpoint = server.endpoint || '';
          return serverEndpoint === certEndpoint ||
                 (serverEndpoint.includes(certEndpoint) && certEndpoint.length > 0) ||
                 (certEndpoint.includes(serverEndpoint) && serverEndpoint.length > 0);
        });
        if (matchingIdp) {
          setSelectedIdpServer(matchingIdp.name);
        }
      }
    }
  }, [showModal, currentConnection, formData.certificate_endpoint, formData.idp_server, idpServers, onFormChange]);

  // Auto-populate certificate endpoint when IDP server is selected
  // Update both state and formData in the onChange handler to avoid timing issues
  const handleIdpServerChange = (e) => {
    const serverName = e.target.value;
    setSelectedIdpServer(serverName);
    if (serverName) {
      const selected = idpServers.find(server => server.name === serverName);
      if (selected && selected.endpoint) {
        onFormChange(prev => ({
          ...prev,
          certificate_endpoint: selected.endpoint
        }));
      }
    }
  };

  const handleTypeChange = (e) => {
    const { value } = e.target;
    let newAcsi = formData.acsi;
    let newWsMode = formData.ws_mode;
    
    if (value === 'RTI-SO') {
      newAcsi = 'client';
      newWsMode = 'passive';
    } else if (value === 'RTI-FSP') {
      newAcsi = 'server';
      newWsMode = 'active';
    } else if (value === 'IDP-Server') {
      newAcsi = '';
      newWsMode = '';
    }
    
    onFormChange(prev => ({
      ...prev,
      type: value,
      acsi: newAcsi,
      ws_mode: newWsMode
    }));
  };

  const isGeneric = formData.type === 'Generic';
  const isIDP = formData.type === 'IDP-Server';

  return (
    <>
      {showModal && (
        <div className="modal active">
          <div className="modal-content">
            <div className="modal-header">
              <h2>{currentConnection ? 'Edit Instance' : 'Register Instance'}</h2>
              <button className="btn-close" onClick={onClose}>
                &times;
              </button>
            </div>
            <div className="modal-body">
              <div className="form-group">
                <label htmlFor="name">Name</label>
                <input 
                  type="text" 
                  id="name" 
                  value={formData.name} 
                  onChange={handleInputChange}
                />
              </div>
              {!isIDP && (
                <>
                  <div className="form-group">
                    <label htmlFor="host">Host</label>
                    <input 
                      type="text" 
                      id="host" 
                      value={formData.host} 
                      onChange={handleInputChange}
                    />
                  </div>
                  <div className="form-group">
                    <label htmlFor="port">Port</label>
                    <input 
                      type="number" 
                      id="port" 
                      value={formData.port} 
                      onChange={handleInputChange}
                    />
                  </div>
                </>
              )}
              <div className="form-group">
                <label htmlFor="type">Type</label>
                <select 
                  id="type" 
                  value={formData.type} 
                  onChange={handleTypeChange}
                >
                  <option value="Generic">Generic</option>
                  <option value="RTI-SO">RTI-SO (WS Passive/ACSI Client)</option>
                  <option value="RTI-FSP">RTI-FSP (WS Active/ACSI Server)</option>
                  <option value="IDP-Server">IDP-Server</option>
                </select>
              </div>
              {!isIDP && (
                <>
                  <div className="form-group">
                    <label htmlFor="acsi">ACSI</label>
                    <select 
                      id="acsi" 
                      value={formData.acsi || 'server'}
                      onChange={handleInputChange}
                      disabled={!isGeneric}
                    >
                      <option value="server">Server</option>
                      <option value="client">Client</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label htmlFor="ws_mode">WebSocket Mode</label>
                    <select 
                      id="ws_mode" 
                      value={formData.ws_mode || ''}
                      onChange={handleInputChange}
                      disabled={!isGeneric}
                    >
                      <option value="">Select mode...</option>
                      <option value="active">Active</option>
                      <option value="passive">Passive</option>
                    </select>
                  </div>
                </>
              )}
              
              {/* IDP Server fields for SO and FSP types (and Generic) */}
              {(formData.type === 'RTI-SO' || formData.type === 'RTI-FSP' || formData.type === 'Generic') && (
                <>
                  <div className="form-group">
                    <label htmlFor="idp_server">IDP Server</label>
                    <select 
                      id="idp_server"
                      value={selectedIdpServer} 
                      onChange={handleIdpServerChange}
                    >
                      <option value="">Select an IDP Server...</option>
                      {idpServers.map(server => (
                        <option key={server.name} value={server.name}>{server.name}</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label htmlFor="certificate_endpoint">Certificate Endpoint</label>
                    <input 
                      type="text" 
                      id="certificate_endpoint" 
                      value={formData.certificate_endpoint || ''} 
                      onChange={handleInputChange}
                      placeholder="e.g., https://localhost:8443/certs"
                    />
                  </div>
                  <div className="form-group">
                    <label htmlFor="auth_server_ca">Auth Server CA</label>
                    <div style={{ display: 'flex', gap: '10px', alignItems: 'center', marginBottom: '10px' }}>
                      <input 
                        type="file" 
                        id="auth_server_ca_file" 
                        accept=".pem,.crt,.cer" 
                        onChange={handleFileUpload}
                      />
                    </div>
                    <textarea 
                      id="auth_server_ca"
                      value={formData.auth_server_ca || ''}
                      onChange={handleInputChange}
                      placeholder="-----BEGIN CERTIFICATE-----..."
                      style={{ minHeight: '80px', fontFamily: 'monospace' }}
                    />
                  </div>
                </>
              )}
              
              {/* FSP-specific OAuth fields when IDP server exists */}
              {formData.type === 'RTI-FSP' && (
                <>
                  <div className="form-group">
                    <label htmlFor="realm">Realm</label>
                    <input 
                      type="text" 
                      id="realm" 
                      value={formData.realm || ''} 
                      onChange={handleInputChange}
                      placeholder="e.g., master"
                    />
                  </div>
                  <div className="form-group">
                    <label htmlFor="token_endpoint">Token Endpoint</label>
                    <input 
                      type="text" 
                      id="token_endpoint" 
                      value={formData.token_endpoint || ''} 
                      onChange={handleInputChange}
                      placeholder="e.g., https://localhost:8443/auth/realms/master/protocol/openid-connect/token"
                    />
                  </div>
                  <div className="form-group">
                    <label htmlFor="client_id">Client ID</label>
                    <input 
                      type="text" 
                      id="client_id" 
                      value={formData.client_id || ''} 
                      onChange={handleInputChange}
                      placeholder="e.g., rti-fsp-client"
                    />
                  </div>
                  <div className="form-group">
                    <label htmlFor="client_secret">Client Secret</label>
                    <input 
                      type="password" 
                      id="client_secret" 
                      value={formData.client_secret || ''} 
                      onChange={handleInputChange}
                      placeholder="Client secret"
                    />
                  </div>
                  <div className="form-group">
                    <label htmlFor="enable_token_refresh">Enable Token Refresh</label>
                    <input 
                      type="checkbox" 
                      id="enable_token_refresh" 
                      checked={formData.enable_token_refresh || false}
                      onChange={(e) => onFormChange(prev => ({
                        ...prev,
                        enable_token_refresh: e.target.checked
                      }))}
                    />
                  </div>
                </>
              )}
              {isIDP && (
                <div className="form-group">
                  <label htmlFor="endpoint">Endpoint</label>
                  <input 
                    type="text" 
                    id="endpoint" 
                    value={formData.endpoint || ''} 
                    onChange={handleInputChange}
                    placeholder="e.g., /idp"
                  />
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button className="btn-secondary" onClick={onClose}>
                Close
              </button>
              <button className="btn-primary" onClick={onSave}>
                <i className="fas fa-save"></i>
                Save Instance
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default ConnectionModal;
