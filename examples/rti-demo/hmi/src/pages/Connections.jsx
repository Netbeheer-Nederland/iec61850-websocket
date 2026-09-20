/*
 * SPDX-FileCopyrightText: 2025 Netbeheer Nederland
 * SPDX-License-Identifier: Apache-2.0
 *
 * Copyright 2025 Netbeheer Nederland
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import React, { useState } from 'react';

function Connections({ connections, setConnections, loading = false, onReload }) {
  const [showModal, setShowModal] = useState(false);
  const [currentConnection, setCurrentConnection] = useState(null);
  const [formData, setFormData] = useState({
    name: '',
    host: '',
    port: 5000,
    // Only meaningful for RTI-SO/Custom: the port its own WebSocket
    // (Passive) endpoint listens on - distinct from `port` above (that
    // instance's BFF server port, used for every API call to it). A real
    // default value, same as `port`'s 5000 - not just a placeholder hint -
    // so it's shown the same way BFF Port is on a freshly opened form.
    ws_port: 8765,
    type: 'RTI-SO',
    acsi: 'server',
    ws_mode: '',
    endpoint: ''
  });

  const handleAddConnection = () => {
    setCurrentConnection(null);
    setFormData({ name: '', host: '', port: 5000, ws_port: 8765, type: 'RTI-SO', acsi: 'server', ws_mode: '', endpoint: '' });
    setShowModal(true);
  };

  const handleEditConnection = (conn) => {
    setCurrentConnection(conn);
    // ws_port defaults to '' (not undefined) for connections that predate
    // it, so the input stays a controlled component.
    setFormData({ ws_port: '', ...conn });
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

  // Maps each field's DOM id to its formData key. Without this, every field
  // below silently never updated state at all: e.target.id (e.g.
  // "conn-host") was used directly as the formData key, which never matched
  // the actual field name ("host") the inputs read their value from - so
  // typing in any of them had no visible effect.
  const CONN_FIELD_ID_MAP = {
    'conn-name': 'name',
    'conn-host': 'host',
    'conn-port': 'port',
    'conn-ws-port': 'ws_port',
    'conn-type': 'type',
    'conn-endpoint': 'endpoint',
  };

  const handleInputChange = (e) => {
    const { id, value, type } = e.target;
    const key = CONN_FIELD_ID_MAP[id] || id;
    setFormData(prev => ({
      ...prev,
      [key]: type === 'number' ? parseInt(value) : value
    }));
  };

  const handleRefresh = () => {
    onReload?.();
  };

  // RTI-SO (and a "Custom" connection standing in for one) is the only
  // type with a WebSocket endpoint of its own to configure a port for,
  // distinct from its BFF server port.
  const needsWsPort = formData.type === 'RTI-SO' || formData.type === 'Custom';
  // RTI-FSP's `port` is just as much "its own BFF server's port" as
  // RTI-SO's is - it just doesn't have a separate ws_port to configure
  // (it dials out to whichever SO instance is selected on the ACSI Server
  // page, rather than owning a fixed WS port itself) - so the label/
  // explanation is shared with RTI-SO/Custom, same as ConnectionModal.jsx.
  const isBffPortLabeled = needsWsPort || formData.type === 'RTI-FSP';

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
        <button className="btn-icon" id="refresh-cons-btn" title="Refresh" onClick={handleRefresh} disabled={loading}>
          <i className={`fas fa-sync-alt${loading ? ' fa-spin' : ''}`}></i>
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
                <th>BFF Port</th>
                <th>WS Port</th>
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
                  <td>{conn.type === 'RTI-SO' ? (conn.ws_port || '—') : '-'}</td>
                  <td>{conn.type}</td>
                  <td>{conn.type === 'IDP-Server' ? conn.endpoint : '-'}</td>
                  <td>
                    <span className="endpoint-card-status">
                      {conn.status === 'connected' ? 'Connected' : 'Disconnected'}
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
                    <label htmlFor="conn-port">{isBffPortLabeled ? 'BFF Port' : 'Port'}</label>
                    <input
                      type="number"
                      id="conn-port"
                      value={formData.port}
                      onChange={handleInputChange}
                    />
                    {isBffPortLabeled && (
                      <small style={{ color: 'var(--text-muted)' }}>
                        Port this instance's own BFF server listens on (used for all API calls to it).
                      </small>
                    )}
                  </div>
                  {needsWsPort && (
                    <div className="form-group">
                      <label htmlFor="conn-ws-port">WS Port</label>
                      <input
                        type="number"
                        id="conn-ws-port"
                        value={formData.ws_port}
                        placeholder="8765"
                        onChange={handleInputChange}
                      />
                      <small style={{ color: 'var(--text-muted)' }}>
                        Port this instance's own WebSocket (Passive) endpoint
                        listens on - distinct from the BFF port above.
                      </small>
                    </div>
                  )}
                </>
              )}
              <div className="form-group">
                <label htmlFor="conn-type">Type</label>
                <select 
                  id="conn-type" 
                  value={formData.type} 
                  onChange={handleInputChange}
                >
                  <option value="Custom">Custom</option>
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
