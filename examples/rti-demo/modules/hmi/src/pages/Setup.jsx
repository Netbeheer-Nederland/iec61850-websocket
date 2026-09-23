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

import React, { useState, useEffect, useCallback, useMemo } from 'react';
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
    // Only meaningful for RTI-SO: the port its own WebSocket (Passive)
    // endpoint listens on, distinct from `port` above (that instance's
    // BFF server port, used for every /api/execute call to it). A real
    // default value, same as `port`'s 5000 - not just a placeholder hint -
    // so a freshly opened "Register Instance" form shows it the same way
    // BFF Port is shown, rather than looking prefilled while actually
    // being empty.
    ws_port: 8765,
    type: 'RTI-SO',
    // Matches type: 'RTI-SO' (client/passive) - ConnectionModal has a
    // self-correcting effect for when these get out of sync with type, but
    // starting them already-correct avoids a visible flip on first render.
    acsi: 'client',
    ws_mode: 'passive',
    endpoint: '',
    cp: ''
  });
  const [bffError, setBffError] = useState(null);

  // Sortable columns: Name, Type, Host, BFF Port ('name' | 'type' | 'host'
  // | 'port', or null for unsorted).
  const [sortConfig, setSortConfig] = useState({ key: null, direction: 'asc' });

  const handleSort = (key) => {
    setSortConfig((prev) => ({
      key,
      direction: prev.key === key && prev.direction === 'asc' ? 'desc' : 'asc',
    }));
  };

  const sortedConnections = useMemo(() => {
    if (!sortConfig.key) return connections;
    const { key, direction } = sortConfig;
    const sign = direction === 'asc' ? 1 : -1;
    return [...connections].sort((a, b) => {
      if (key === 'port') {
        return sign * ((Number(a.port) || 0) - (Number(b.port) || 0));
      }
      const aVal = String(a[key] ?? '').toLowerCase();
      const bVal = String(b[key] ?? '').toLowerCase();
      if (aVal < bVal) return -1 * sign;
      if (aVal > bVal) return 1 * sign;
      return 0;
    });
  }, [connections, sortConfig]);

  const sortIcon = (key) => {
    if (sortConfig.key !== key) {
      return <i className="fas fa-sort" style={{ marginLeft: '6px', fontSize: '11px', opacity: 0.4 }}></i>;
    }
    return (
      <i
        className={`fas fa-sort-${sortConfig.direction === 'asc' ? 'up' : 'down'}`}
        style={{ marginLeft: '6px', fontSize: '11px' }}
      ></i>
    );
  };

  const sortableTh = (key, label) => (
    <th onClick={() => handleSort(key)} style={{ cursor: 'pointer', userSelect: 'none' }}>
      {label}{sortIcon(key)}
    </th>
  );

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
    setFormData({ name: '', host: '', port: 5000, ws_port: 8765, type: 'RTI-SO', acsi: 'client', ws_mode: 'passive', endpoint: '', cp: '' });
    setShowModal(true);
  };

  // Edit connection
  const handleEditConnection = (conn) => {
    setCurrentConnection(conn);
    // OAuth settings aren't edited here any more (see OAuthConfigModal on
    // the instance's own page) - and since edit-connection leaves omitted
    // fields untouched, saving this form keeps them as they are.
    setFormData({
      name: conn.name || '',
      host: conn.host || '',
      port: conn.port || 5000,
      // Leave blank (not a fabricated 8765) when the connection genuinely
      // has no ws_port set - defaulting to a fake-looking real port would
      // make an unconfigured instance look configured, exactly what the WS
      // port split was meant to stop happening.
      ws_port: conn.ws_port || '',
      cp: conn.cp || '',
      type: conn.type || 'RTI-SO',
      acsi: conn.acsi || 'server',
      ws_mode: conn.ws_mode || '',
      endpoint: conn.endpoint || ''
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
      if ((formData.type === 'RTI-SO' || formData.type === 'RTI-FSP' || formData.type === 'Custom') && (!formData.host || !formData.port)) {
        alert('Please fill in the host and port fields');
        return;
      }
      
      // For IDP-Server, endpoint is required
      if (formData.type === 'IDP-Server' && !formData.endpoint) {
        alert('Please fill in the endpoint field');
        return;
      }

      const saveData = { ...formData };

      // ws_port only applies to RTI-SO (see ConnectionModal.jsx) - for every
      // other type formData.ws_port is just leftover '' from the shared
      // initial state, and the backend's ws_port field is a plain
      // Optional[int]: sending "" for it 400s ("unable to parse string as
      // an integer"). For RTI-SO itself, blank still shouldn't be sent as
      // "" either - default it instead, so a freshly registered instance
      // always has a usable ws_port rather than needing a second edit.
      if (saveData.type === 'RTI-SO') {
        const parsedWsPort = Number(saveData.ws_port);
        saveData.ws_port = Number.isFinite(parsedWsPort) && parsedWsPort > 0 ? parsedWsPort : 8765;
      } else {
        delete saveData.ws_port;
      }

      // cp only applies to RTI-FSP (see ConnectionModal.jsx).
      if (saveData.type !== 'RTI-FSP') {
        delete saveData.cp;
      }

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
            <table className="table">
              <thead>
                <tr>
                  <th>Status</th>
                  {sortableTh('name', 'Name')}
                  {sortableTh('type', 'Type')}
                  {sortableTh('host', 'Host')}
                  {sortableTh('port', 'BFF Port')}
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {sortedConnections.map((conn, index) => (
                  <tr key={conn.name || index}>
                    <td>
                      <span
                        className="bff-status-dot"
                        style={{
                          background: conn.status === 'connected' ? 'var(--success-color)' : 'var(--danger-color)'
                        }}
                      ></span>
                    </td>
                    <td>{conn.name}</td>
                    <td>{conn.type}</td>
                    <td>{conn.type === 'IDP-Server' ? '-' : conn.host}</td>
                    <td>{conn.type === 'IDP-Server' ? '-' : conn.port}</td>
                    <td>
                      {/* .btn-icon is display:flex (block-outer), so as
                          direct <td> children these would stack on
                          separate lines instead of sitting side by side -
                          a flex wrapper restores the row layout, the same
                          way their old flex-row parent used to. */}
                      <div style={{ display: 'flex', gap: '8px' }}>
                        <button
                          className="btn-icon"
                          onClick={() => handleEditConnection(conn)}
                          title="Edit"
                        >
                          <i className="fas fa-edit"></i>
                        </button>
                        <button
                          className="btn-icon"
                          onClick={() => handleDeleteConnection(conn)}
                          title="Delete"
                        >
                          <i className="fas fa-trash"></i>
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '20px' }}>
              No instances registered. Click "Register Instance" to get started.
            </p>
          )}
        </div>
      </React.Fragment>

      {/* Connection Modal */}
      <ConnectionModal
        showModal={showModal}
        onClose={() => setShowModal(false)}
        currentConnection={currentConnection}
        formData={formData}
        onFormChange={setFormData}
        onSave={handleSaveConnection}
      />
    </section>
  );
}

export default Setup;