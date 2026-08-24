import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import InstanceVisualization from '../components/InstanceVisualization';
import ConnectionModal from '../components/ConnectionModal';

function Setup({ settings }) {
  const navigate = useNavigate();
  const [connections, setConnections] = useState([]);
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
    enable_token_refresh: false
  });
  const [loading, setLoading] = useState(true);
  const [bffError, setBffError] = useState(null);

  // Fetch connections from BFF API
  const fetchConnections = useCallback(async () => {
    try {
      setLoading(true);
      setBffError(null);
      const response = await fetch(`http://${settings.bffHost}:${settings.bffPort}/api/connections`);
      if (response.ok) {
        const data = await response.json();
        setConnections(data.connections || []);
        return data.connections || [];
      }
      setBffError(`BFF returned error: ${response.status}`);
      return [];
    } catch (error) {
      console.error('Failed to fetch connections:', error);
      setBffError(`Cannot connect to BFF at ${settings.bffHost}:${settings.bffPort}`);
      return [];
    } finally {
      setLoading(false);
    }
  }, [settings.bffHost, settings.bffPort]);

  useEffect(() => {
    fetchConnections();
  }, [fetchConnections]);

  // Check all connections health using BFF endpoint
  const checkAllConnectionsHealth = async (connectionsList) => {
    try {
      const response = await fetch(`http://${settings.bffHost}:${settings.bffPort}/api/health`);
      const data = await response.json();
      
      // Update connections with status from BFF
      const updatedConnections = connectionsList.map(conn => {
        // IDP-Server is always connected (local server)
        if (conn.type === 'IDP-Server') {
          return { ...conn, connected: true };
        }
        const target = data.targets.find(t => t.target === `${conn.host}:${conn.port}`);
        return { ...conn, connected: target?.status === 'reachable' };
      });
      
      setConnections(updatedConnections);
    } catch (error) {
      console.error('Failed to check connections:', error);
    }
  };

  // Check all connections
  const handleCheckAllConnections = async () => {
    setLoading(true);
    try {
      const connList = await fetchConnections();
      if (connList.length > 0) {
        await checkAllConnectionsHealth(connList);
      }
    } catch (error) {
      console.error('Failed to refresh connections:', error);
    } finally {
      setLoading(false);
    }
  };

  // Add connection
  const handleAddConnection = () => {
    setCurrentConnection(null);
    setFormData({ name: '', host: '', port: 5000, type: 'RTI-SO', acsi: 'server', ws_mode: '', endpoint: '', certificate_endpoint: '', auth_server_ca: '', token_issuer_url: '', realm: '', token_endpoint: '', client_id: '', client_secret: '', enable_token_refresh: false });
    setShowModal(true);
  };

  // Edit connection
  const handleEditConnection = (conn) => {
    setCurrentConnection(conn);
    const oauthConfig = conn.OAuth || conn.oauth || {};
    
    // Load OAuth fields from OAuth object (primary) or fallback to top-level connection
    const certificateEndpoint = oauthConfig.certificate_endpoint || oauthConfig.certificate_endpoint_url || conn.certificate_endpoint || '';
    const authServerCa = oauthConfig.auth_server_ca || oauthConfig.ca_certificate || conn.auth_server_ca || '';
    const tokenIssuerUrl = oauthConfig.token_issuer || oauthConfig.token_issuer_url || conn.token_issuer_url || '';
    
    // FSP-specific OAuth fields from OAuth object (primary) or fallback to top-level
    const realm = oauthConfig.realm || conn.realm || '';
    const tokenEndpoint = oauthConfig.token_endpoint || oauthConfig.token_endpoint_url || conn.token_endpoint || '';
    const clientId = oauthConfig.client_id || conn.client_id || '';
    const clientSecret = oauthConfig.client_secret || conn.client_secret || '';
    const enableTokenRefresh = oauthConfig.enable_token_refresh || conn.enable_token_refresh || false;
    
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
      enable_token_refresh: enableTokenRefresh
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
        fetchConnections();
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
          fetchConnections();
          setShowModal(false);
        }
      } else {
        // Add new connection
        const response = await fetch(`http://${settings.bffHost}:${settings.bffPort}/api/add-connection`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(saveData)
        });
        if (response.ok) {
          fetchConnections();
          setShowModal(false);
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

