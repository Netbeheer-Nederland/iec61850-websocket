import React, { useState } from 'react';

function Connections({ connections, setConnections }) {
  const [showModal, setShowModal] = useState(false);
  const [currentConnection, setCurrentConnection] = useState(null);
  const [formData, setFormData] = useState({
    name: '',
    host: '',
    port: 5000,
    type: 'RTI-SO',
    acsi: 'server',
    ws_mode: '',
    endpoint: ''
  });

  const handleAddConnection = () => {
    setCurrentConnection(null);
    setFormData({ name: '', host: '', port: 5000, type: 'RTI-SO', acsi: 'server', ws_mode: '', endpoint: '' });
    setShowModal(true);
  };

  const handleEditConnection = (conn) => {
    setCurrentConnection(conn);
    setFormData({ ...conn });
    setShowModal(true);
  };

  const handleDeleteConnection = (index) => {
    setConnections(connections.filter((_, i) => i !== index));
  };

  const handleSaveConnection = () => {
    if (currentConnection === null) {
      // Add new connection
      setConnections([...connections, formData]);
    } else {
      // Update existing connection
      setConnections(connections.map(conn => 
        conn === currentConnection ? formData : conn
      ));
    }
    setShowModal(false);
  };

  const handleInputChange = (e) => {
    const { id, value, type } = e.target;
    setFormData(prev => ({
      ...prev,
      [id]: type === 'number' ? parseInt(value) : value
    }));
  };

  const handleRefresh = () => {
    // Refresh connections - placeholder
    console.log('Refreshing connections...');
  };

  return (
    <section className="page">
      <div className="page-header">
        <h1>Connections</h1>
        <button className="btn-primary" id="btn-add-connection" onClick={handleAddConnection}>
          <i className="fas fa-plus"></i>
          Add Connection
        </button>
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '10px' }}>
        <button className="btn-icon" id="refresh-cons-btn" title="Refresh" onClick={handleRefresh}>
          <i className="fas fa-sync-alt"></i>
        </button>
      </div>
      <div className="connections-table" id="connections-container">
        {connections.length === 0 ? (
          <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '20px' }}>
            No connections configured. Click "Add Connection" to get started.
          </p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Host</th>
                <th>Port</th>
                <th>Type</th>
                <th>Endpoint</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {connections.map((conn, index) => (
                <tr key={index}>
                  <td>{conn.name}</td>
                  <td>{conn.type === 'IDP-Server' ? '-' : conn.host}</td>
                  <td>{conn.type === 'IDP-Server' ? '-' : conn.port}</td>
                  <td>{conn.type}</td>
                  <td>{conn.type === 'IDP-Server' ? conn.endpoint : '-'}</td>
                  <td>
                    <span className="endpoint-card-status">
                      {conn.connected ? 'Connected' : 'Disconnected'}
                    </span>
                  </td>
                  <td>
                    <button 
                      className="btn-icon" 
                      style={{ marginRight: '8px' }}
                      onClick={() => handleEditConnection(conn)}
                    >
                      <i className="fas fa-edit"></i>
                    </button>
                    <button 
                      className="btn-icon"
                      onClick={() => handleDeleteConnection(index)}
                    >
                      <i className="fas fa-trash"></i>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Connection Modal */}
      {showModal && (
        <div className="modal active">
          <div className="modal-content">
            <div className="modal-header">
              <h2>{currentConnection ? 'Edit Connection' : 'Add Connection'}</h2>
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
              {formData.type !== 'IDP-Server' && (
                <>
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
                </>
              )}
              <div className="form-group">
                <label htmlFor="conn-type">Type</label>
                <select 
                  id="conn-type" 
                  value={formData.type} 
                  onChange={handleInputChange}
                >
                  <option value="Generic">Generic</option>
                  <option value="RTI-SO">RTI-SO (WS Passive/ACSI Client)</option>
                  <option value="RTI-FSP">RTI-FSP (WS Active/ACSI Server)</option>
                  <option value="IDP-Server">IDP-Server</option>
                </select>
              </div>
              {formData.type === 'IDP-Server' && (
                <div className="form-group">
                  <label htmlFor="conn-endpoint">Endpoint</label>
                  <input 
                    type="text" 
                    id="conn-endpoint" 
                    value={formData.endpoint || ''} 
                    onChange={handleInputChange}
                    placeholder="e.g., /idp"
                  />
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setShowModal(false)}>
                Close
              </button>
              <button className="btn-primary" onClick={handleSaveConnection}>
                <i className="fas fa-save"></i>
                Save Connection
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

export default Connections;
