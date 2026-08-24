import React, { useState, useEffect, useRef } from 'react';

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

  // Find matching IDP server for the certificate endpoint when modal opens
  useEffect(() => {
    if (showModal && currentConnection && formData.certificate_endpoint) {
      const certEndpoint = formData.certificate_endpoint || '';
      if (certEndpoint) {
        const matchingIdp = idpServers.find(server => 
          server.endpoint === certEndpoint || 
          server.endpoint?.includes(certEndpoint) ||
          certEndpoint?.includes(server.endpoint || '')
        );
        if (matchingIdp) {
          setSelectedIdpServer(matchingIdp.name);
        }
      }
    }
  }, [showModal, currentConnection, formData.certificate_endpoint, idpServers]);

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
              
              {/* IDP Server fields for SO and FSP types */}
              {(formData.type === 'RTI-SO' || formData.type === 'RTI-FSP') && (
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
