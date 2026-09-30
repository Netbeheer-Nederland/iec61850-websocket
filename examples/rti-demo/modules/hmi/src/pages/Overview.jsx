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

import React, { useMemo, useState } from 'react';
import InstanceVisualization from '../components/InstanceVisualization';

// Read-only: the graphical SO/FSP overview and a sortable status table.
// Registering, editing and deleting instances all live on the Connections
// page now - this page never mutates a connection, so it doesn't need
// ConnectionModal, useNavigate (InstanceVisualization does its own
// navigation for the FSP/SO circle clicks), or any of the add/edit/delete
// plumbing the old combined Setup page used to carry.
function Overview({ settings, connections = [], loading = false, onReload }) {
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

  return (
    <section className="page">
      <div className="page-header" style={{ marginBottom: '20px' }}>
        <h2>Overview</h2>
        <p style={{ color: 'var(--text-muted)', marginTop: '4px' }}>Live status of all registered instances and their connections</p>
      </div>

      <React.Fragment>
        {/* SO-FSP Graphic Visualization */}
        <div style={{ marginBottom: '40px' }}>
          {loading ? (
            <div className="endpoints-loading">
              <span className="spinner"></span>
              Loading...
            </div>
          ) : (
            <InstanceVisualization
              connections={connections}
              loading={loading}
              onReload={handleCheckAllConnections}
              onConnectionClick={null}
              showReload={true}
            />
          )}
        </div>

        {/* Instances Table (read-only - register/edit/delete live on Connections) */}
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
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '20px' }}>
              No instances registered. Register one from the Connections page to get started.
            </p>
          )}
        </div>
      </React.Fragment>
    </section>
  );
}

export default Overview;
