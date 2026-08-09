import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

function Setup({ settings }) {
  const navigate = useNavigate();
  const [connections, setConnections] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [currentConnection, setCurrentConnection] = useState(null);
  const [formData, setFormData] = useState({
    name: '',
    host: '',
    port: 5000,
    type: 'RTI-SO'
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
    setFormData({ name: '', host: '', port: 5000, type: 'RTI-SO' });
    setShowModal(true);
  };

  // Edit connection
  const handleEditConnection = (conn) => {
    setCurrentConnection(conn);
    setFormData({ ...conn });
    setShowModal(true);
  };

  // Delete connection
  const handleDeleteConnection = async (connection) => {
    try {
      const response = await fetch(`http://${settings.bffHost}:${settings.bffPort}/api/connections/${connection.name}`, {
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
      if (!formData.name || !formData.host || !formData.port) {
        alert('Please fill in all required fields');
        return;
      }

      if (currentConnection) {
        // Update existing connection
        const response = await fetch(`http://${settings.bffHost}:${settings.bffPort}/api/connections/${currentConnection.name}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(formData)
        });
        if (response.ok) {
          fetchConnections();
          setShowModal(false);
        }
      } else {
        // Add new connection
        const response = await fetch(`http://${settings.bffHost}:${settings.bffPort}/api/connections`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(formData)
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

  const handleInputChange = (e) => {
    const { id, value, type } = e.target;
    setFormData(prev => ({
      ...prev,
      [id]: type === 'number' ? parseInt(value) : value
    }));
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
        <button className="btn-icon" id="refresh-cons-btn" title="Refresh Instances" onClick={handleCheckAllConnections}>
          <i className="fas fa-sync-alt"></i>
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
            <div style={{ 
              display: 'flex', 
              justifyContent: 'center', 
              alignItems: 'flex-start',
              gap: '40px',
              minHeight: '300px'
            }}>
              {connections.filter(conn => conn.status === 'connected').length > 0 && (
                <>
                  {/* SO (Client) Side - Left */}
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', minWidth: '180px' }}>
                    <div 
                      style={{ 
                        width: '140px', 
                        height: '140px', 
                        border: '2px solid var(--border-color)',
                        borderRadius: '50%',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        marginBottom: '12px',
                        background: 'var(--bg-card)',
                        cursor: 'pointer'
                      }}
                      onClick={() => {
                        const soConnection = connections.find(conn => conn.type === 'RTI-SO' && conn.status === 'connected');
                        navigate('/acsi-client', { state: { endpoint: soConnection || { host: '127.0.0.1', port: 102, name: 'Default' } } });
                      }}
                      title="Type: RTI-SO (Client)"
                    >
                      <span style={{ color: 'var(--text-primary)', fontSize: '18px', fontWeight: '600' }}>SO</span>
                    </div>
                    <div style={{ 
                      padding: '6px 12px', 
                      background: 'var(--bg-hover)',
                      borderRadius: '16px',
                      textAlign: 'center',
                      fontSize: '11px',
                      border: '1px solid var(--border-color)'
                    }}>
                      client · passive
                    </div>
                    {connections
                      .filter(conn => conn.type === 'RTI-SO' && conn.status === 'connected')
                      .map((conn) => (
                        <div 
                          key={`so-${conn.name}`}
                          style={{
                            padding: '6px 12px',
                            background: 'var(--bg-hover)',
                            borderRadius: '16px',
                            margin: '6px 0',
                            textAlign: 'center',
                            fontSize: '10px',
                            border: '1px solid var(--border-color)',
                            minWidth: '140px',
                            cursor: 'pointer'
                          }}
                          onClick={() => handleEditConnection(conn)}
                          title={`Type: ${conn.type}`}
                        >
                          <span style={{ color: 'var(--text-primary)', fontWeight: '500' }}>{conn.name}</span>
                          {conn.properties_info?.properties && (
                            <div style={{ color: 'var(--text-muted)', marginTop: '2px' }}>
                              {conn.properties_info.properties.acsi_role} · {conn.properties_info.properties.ws_mode}
                            </div>
                          )}
                        </div>
                      ))}
                  </div>
                  
                  {/* Connection lines */}
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', marginTop: '60px' }}>
                    {connections
                      .filter(conn => conn.type === 'RTI-FSP' && conn.status === 'connected')
                      .map((_, index) => (
                        <div 
                          key={`line-${index}`}
                          style={{ 
                            height: '1px', 
                            width: '40px', 
                            background: 'var(--border-color)',
                            margin: '6px 0',
                            borderStyle: 'dashed'
                          }}
                        ></div>
                      ))}
                    {connections.filter(conn => conn.type === 'RTI-FSP' && conn.status === 'connected').length === 0 && (
                      <div style={{ 
                        height: '1px', 
                        width: '40px', 
                        background: 'var(--border-color)',
                        margin: '6px 0',
                        borderStyle: 'dashed'
                      }}></div>
                    )}
                  </div>
                  
                  {/* FSP (Server) Side - Right */}
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', minWidth: '180px' }}>
                    {connections
                      .filter(conn => conn.type === 'RTI-FSP' && conn.status === 'connected')
                      .map((conn) => (
                        <React.Fragment key={`fsp-${conn.name}`}>
                          <div 
                            style={{
                              width: '120px', 
                              height: '120px', 
                              border: '2px solid var(--border-color)',
                              borderRadius: '50%',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              margin: '6px 0',
                              background: 'var(--bg-card)',
                              cursor: 'pointer'
                            }}
                            onClick={() => navigate('/acsi-server', { state: { endpoint: conn } })}
                            title={`Type: ${conn.type}`}
                          >
                            <span style={{ color: 'var(--text-primary)', fontSize: '14px', fontWeight: '600', textAlign: 'center' }}>
                              {conn.name}
                            </span>
                          </div>
                          <div style={{ 
                            padding: '6px 12px', 
                            background: 'var(--bg-hover)',
                            borderRadius: '16px',
                            textAlign: 'center',
                            fontSize: '11px',
                            border: '1px solid var(--border-color)',
                            minWidth: '120px'
                          }}>
                            server · active
                            {conn.properties_info?.properties && (
                              <div style={{ color: 'var(--text-muted)', marginTop: '2px', fontSize: '9px' }}>
                                {conn.properties_info.properties.acsi_role} · {conn.properties_info.properties.ws_mode}
                              </div>
                            )}
                          </div>
                        </React.Fragment>
                      ))}
                  </div>
                </>
              )}
              
              {connections.filter(conn => conn.status === 'connected').length === 0 && (
                <div style={{
                  textAlign: 'center',
                  color: 'var(--text-muted)',
                  fontSize: '12px',
                  padding: '40px'
                }}>
                  No connected instances to visualize
                </div>
              )}
            </div>
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
                    <span style={{ color: 'var(--text-secondary)', minWidth: '150px' }}>
                      {conn.host}:{conn.port}
                    </span>
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
      {showModal && (
        <div className="modal active">
          <div className="modal-content">
            <div className="modal-header">
              <h2>{currentConnection ? 'Edit Instance' : 'Register Instance'}</h2>
              <button className="btn-close" onClick={() => setShowModal(false)}>
                &times;
              </button>
            </div>
            <div className="modal-body">
              <div className="form-group">
                <label htmlFor="conn-name">Name</label>
                <input 
                  type="text" 
                  id="conn-name" 
                  value={formData.name} 
                  onChange={handleInputChange}
                />
              </div>
              <div className="form-group">
                <label htmlFor="conn-host">Host</label>
                <input 
                  type="text" 
                  id="conn-host" 
                  value={formData.host} 
                  onChange={handleInputChange}
                />
              </div>
              <div className="form-group">
                <label htmlFor="conn-port">Port</label>
                <input 
                  type="number" 
                  id="conn-port" 
                  value={formData.port} 
                  onChange={handleInputChange}
                />
              </div>
              <div className="form-group">
                <label htmlFor="conn-type">Type</label>
                <select 
                  id="conn-type" 
                  value={formData.type} 
                  onChange={handleInputChange}
                >
                  <option value="RTI-SO">RTI-SO (WS Passive/ACSI Client)</option>
                  <option value="RTI-FSP">RTI-FSP (WS Active/ACSI Server)</option>
                </select>
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setShowModal(false)}>
                Close
              </button>
              <button className="btn-primary" onClick={handleSaveConnection}>
                <i className="fas fa-save"></i>
                Save Instance
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

export default Setup;

