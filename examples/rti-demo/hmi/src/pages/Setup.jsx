import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import InstanceVisualization from '../components/InstanceVisualization';
import ConnectionModal from '../components/ConnectionModal';

function Setup({ settings, connections = [], loading = false, onReload }) {
  const navigate = useNavigate();
  const [showModal, setShowModal] = useState(false);
  const [currentConnection, setCurrentConnection] = useState(null);
  const [formData, setFormData] = useState({
    name: '',
    host: '',
    port: 5000,
    type: 'RTI-SO',
    acsi: 'server',
    ws_mode: '',
    endpoint: '',
    certificate_endpoint: '',
    auth_server_ca: '',
    token_issuer_url: '',
    realm: '',
    token_endpoint: '',
    client_id: '',
    client_secret: '',
    enable_token_refresh: false,
    idp_server: ''
  });
  const [bffError, setBffError] = useState(null);

  // Check all connections health using BFF endpoint
  const checkAllConnectionsHealth = async (connectionsList) => {
    try {
      const response = await fetch(`http://${settings.bffHost}:${settings.bffPort}/api/health`);
      const data = await response.json();
      
      await onReload?.();
    } catch (error) {
      console.error('Failed to check connections:', error);
    }
  };

  // Check all connections
  const handleCheckAllConnections = async () => {
    try {
      const connList = (await onReload?.()) || [];
      if (connList.length > 0) {
        await checkAllConnectionsHealth(connList);
      }
    } catch (error) {
      console.error('Failed to refresh connections:', error);
    }
  };

  // Add connection
  const handleAddConnection = () => {
    setCurrentConnection(null);
    setFormData({ name: '', host: '', port: 5000, type: 'RTI-SO', acsi: 'server', ws_mode: '', endpoint: '', certificate_endpoint: '', auth_server_ca: '', token_issuer_url: '', realm: '', token_endpoint: '', client_id: '', client_secret: '', enable_token_refresh: false, idp_server: '' });
    setShowModal(true);
  };

  // Edit connection
  const handleEditConnection = (conn) => {
    setCurrentConnection(conn);
    
    // Try to find OAuth config in multiple possible locations
    const oauthConfig = conn.OAuth || conn.oauth || conn.oauth_config || conn.OAuthConfig || conn.oauthConfig || {};
    
    // Also check if OAuth config is nested differently
    const propertiesOauth = (conn.properties_info || {}).properties || {};
    const oauthFromProps = propertiesOauth.OAuth || propertiesOauth.oauth || {};
    
    // Load OAuth fields from OAuth object (primary) or fallback to top-level connection
    // Check all possible field names for certificate endpoint
    let certificateEndpoint = oauthConfig.certificate_endpoint || 
                                  oauthConfig.certificate_endpoint_url || 
                                  oauthFromProps.certificate_endpoint || 
                                  oauthFromProps.certificate_endpoint_url || 
                                  oauthConfig.cert_endpoint || 
                                  oauthConfig.cert_endpoint_url || 
                                  conn.certificate_endpoint || 
                                  conn.certificate_endpoint_url || 
                                  conn.cert_endpoint || 
                                  conn.cert_endpoint_url || 
                                  '';
    
    const authServerCa = oauthConfig.auth_server_ca || 
                         oauthFromProps.auth_server_ca || 
                         oauthConfig.ca_certificate || 
                         oauthFromProps.ca_certificate || 
                         conn.auth_server_ca || '';
    
    const tokenIssuerUrl = oauthConfig.token_issuer || 
                           oauthFromProps.token_issuer || 
                           oauthConfig.token_issuer_url || 
                           oauthFromProps.token_issuer_url || 
                           conn.token_issuer_url || '';
    
    // FSP-specific OAuth fields from OAuth object (primary) or fallback to top-level
    const realm = oauthConfig.realm || oauthFromProps.realm || conn.realm || '';
    const tokenEndpoint = oauthConfig.token_endpoint || 
                          oauthFromProps.token_endpoint || 
                          oauthConfig.token_endpoint_url || 
                          oauthFromProps.token_endpoint_url || 
                          conn.token_endpoint || '';
    const clientId = oauthConfig.client_id || oauthFromProps.client_id || conn.client_id || '';
    const clientSecret = oauthConfig.client_secret || oauthFromProps.client_secret || conn.client_secret || '';
    const enableTokenRefresh = oauthConfig.enable_token_refresh || oauthFromProps.enable_token_refresh || conn.enable_token_refresh || false;
    
    // IDP Server name reference (to help with dropdown selection)
    // Try many possible locations and field names
    let idpServer = oauthConfig.idp_server || 
                   oauthFromProps.idp_server || 
                   conn.idp_server || 
                   oauthConfig.idpServer || 
                   oauthFromProps.idpServer || 
                   conn.idpServer || 
                   // Maybe it's stored as the IDP server name directly
                   (conn.OAuth || {}).idp_server_name || 
                   (conn.oauth || {}).idp_server_name || 
                   conn.idp_server_name || 
                   // Or maybe it's the endpoint URL which we can match to an IDP server
                   '';
    
    // If certificate_endpoint is empty but we have an idp_server name, try to get it from the IDP server's endpoint
    if (!certificateEndpoint && idpServer) {
      const idpServers = connections.filter(c => c.type === 'IDP-Server');
      const matchingIdp = idpServers.find(server => server.name === idpServer);
      if (matchingIdp && matchingIdp.endpoint) {
        certificateEndpoint = matchingIdp.endpoint;
        // If idp_server wasn't set, set it now
        if (!idpServer) {
          idpServer = matchingIdp.name;
        }
      }
    }
    
    setFormData({
      name: conn.name || '',
      host: conn.host || '',
      port: conn.port || 5000,
      type: conn.type || 'RTI-SO',
      acsi: conn.acsi || 'server',
      ws_mode: conn.ws_mode || '',
      endpoint: conn.endpoint || '',
      certificate_endpoint: certificateEndpoint,
      auth_server_ca: authServerCa,
      token_issuer_url: tokenIssuerUrl,
      realm: realm,
      token_endpoint: tokenEndpoint,
      client_id: clientId,
      client_secret: clientSecret,
      enable_token_refresh: enableTokenRefresh,
      idp_server: idpServer
    });
    setShowModal(true);
  };

  // Delete connection
  const handleDeleteConnection = async (connection) => {
    const confirmed = window.confirm(`Permanently delete instance "${connection.name}"? This action cannot be undone.`);
    if (!confirmed) return;

    try {
      const response = await fetch(`http://${settings.bffHost}:${settings.bffPort}/api/delete-connection/${connection.name}`, {
        method: 'DELETE'
      });
      if (response.ok) {
        onReload?.();
      }
    } catch (error) {
      console.error('Failed to delete connection:', error);
    }
  };

  // Save connection (add or update)
  const handleSaveConnection = async () => {
    try {
      // Validate required fields based on type
      if (!formData.name) {
        alert('Please fill in all required fields');
        return;
      }
      
      // For RTI-SO and RTI-FSP, host and port are required
      if ((formData.type === 'RTI-SO' || formData.type === 'RTI-FSP' || formData.type === 'Generic') && (!formData.host || !formData.port)) {
        alert('Please fill in the host and port fields');
        return;
      }
      
      // For IDP-Server, endpoint is required
      if (formData.type === 'IDP-Server' && !formData.endpoint) {
        alert('Please fill in the endpoint field');
        return;
      }

      // Add auth_server_ca to formData if it exists
      // Note: authServerCa is managed in ConnectionModal component state, not in formData
      // For now, we'll include it in the save
      const saveData = { ...formData };

      if (currentConnection) {
        // Update existing connection
        const response = await fetch(`http://${settings.bffHost}:${settings.bffPort}/api/edit-connection/${currentConnection.name}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(saveData)
        });
        if (response.ok) {
          onReload?.();
          setShowModal(false);
        } else {
          const errText = await response.text().catch(() => '');
          alert(`Failed to save connection: ${errText || response.statusText}`);
        }
      } else {
        // Add new connection
        const response = await fetch(`http://${settings.bffHost}:${settings.bffPort}/api/add-connection`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(saveData)
        });
        if (response.ok) {
          onReload?.();
          setShowModal(false);
        } else {
          const errText = await response.text().catch(() => '');
          alert(`Failed to save connection: ${errText || response.statusText}`);
        }
      }
    } catch (error) {
      console.error('Failed to save connection:', error);
      alert('Failed to save connection. Check console for details.');
    }
  };

  return (
    <section className="page">
      <div className="page-header" style={{ marginBottom: '20px' }}>
        <h2>Instances</h2>
        <p style={{ color: 'var(--text-muted)', marginTop: '4px' }}>administered manually</p>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <button className="btn-primary" id="btn-add-connection" onClick={handleAddConnection}>
          <i className="fas fa-plus"></i>
          Register Instance
        </button>
      </div>

      <React.Fragment>
        {/* SO-FSP Graphic Visualization */}
        <div style={{ marginBottom: '40px' }}>
          {loading ? (
            <div className="endpoints-loading">
              <span className="spinner"></span>
              Loading...
            </div>
          ) : bffError ? (
            <div style={{ color: 'var(--danger-color)', textAlign: 'center', padding: '20px' }}>
              <p><strong>Error:</strong> {bffError}</p>
              <p style={{ marginTop: '10px', fontSize: '12px' }}>Please check BFF settings and ensure the BFF server is running.</p>
            </div>
          ) : (
            <InstanceVisualization
              connections={connections}
              loading={loading}
              onReload={handleCheckAllConnections}
              onConnectionClick={handleEditConnection}
              showReload={true}
            />
          )}</div>

        {/* Instances Table */}
        <div style={{ paddingTop: '20px', borderTop: '1px solid var(--border-color)' }}>
          {connections && connections.length > 0 ? (
            <div style={{ border: '1px solid var(--border-color)', borderRadius: '8px', overflow: 'hidden' }}>
              {connections.map((conn, index) => (
                <div 
                  key={conn.name || index} 
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '16px 20px',
                    borderBottom: index < connections.length - 1 ? '1px solid var(--border-color)' : 'none',
                    background: index % 2 === 0 ? 'var(--bg-card)' : 'var(--bg-hover)'
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
                    <span style={{ color: 'var(--text-secondary)', fontWeight: '500', minWidth: '100px' }}>
                      {conn.type}
                    </span>
                    <span style={{ color: 'var(--text-muted)' }}>⋅</span>
                    <span style={{ color: 'var(--text-primary)', fontWeight: '500', minWidth: '150px' }}>
                      {conn.name}
                    </span>
                    <span style={{ color: 'var(--text-muted)' }}>⋅</span>
                    {conn.type === 'IDP-Server' ? (
                      <span style={{ color: 'var(--text-secondary)', minWidth: '150px' }}>
                        {conn.endpoint}
                      </span>
                    ) : (
                      <span style={{ color: 'var(--text-secondary)', minWidth: '150px' }}>
                        {conn.host}:{conn.port}
                      </span>
                    )}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                    <span 
                      className="bff-status-dot" 
                      style={{
                        background: conn.status === 'connected' ? 'var(--success-color)' : 'var(--danger-color)'
                      }}
                    ></span>
                    <button 
                      className="btn-icon" 
                      style={{ padding: '6px', fontSize: '14px' }}
                      onClick={() => handleEditConnection(conn)}
                      title="Edit"
                    >
                      <i className="fas fa-edit"></i>
                    </button>
                    <button 
                      className="btn-icon" 
                      style={{ padding: '6px', fontSize: '14px' }}
                      onClick={() => handleDeleteConnection(conn)}
                      title="Delete"
                    >
                      <i className="fas fa-trash"></i>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '20px' }}>
              No instances registered. Click "Register Instance" to get started.
            </p>
          )}
        </div>
      </React.Fragment>

      {/* Connection Modal */}
      <ConnectionModal
        settings={settings}
        showModal={showModal}
        onClose={() => setShowModal(false)}
        currentConnection={currentConnection}
        formData={formData}
        connections={connections}
        onFormChange={setFormData}
        onSave={handleSaveConnection}
      />
    </section>
  );
}

export default Setup;