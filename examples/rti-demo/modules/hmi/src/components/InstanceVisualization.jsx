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

import React from 'react';
import { useNavigate } from 'react-router-dom';

/**
 * Reusable component for visualizing SO-FSP connections
 *
 * @param {Object[]} connections - Array of connection objects
 * @param {Object|null} selectedConnection - Currently selected connection (for highlighting)
 * @param {Function|null} onConnectionClick - Click handler for connection items
 * @param {boolean} showLabels - Whether to show type labels
 * @param {boolean} loading - Whether data is currently loading
 */
function InstanceVisualization({
  connections,
  selectedConnection = null,
  onConnectionClick = null,
  showLabels = true,
  loading = false
}) {
  const navigate = useNavigate();

  // Internal click handlers for SO and FSP circles
  const handleSoClick = () => {
    const soConnection = connections.find(conn => conn.type === 'RTI-SO' && conn.status === 'connected');
    navigate('/acsi-client', { state: { endpoint: soConnection || { host: '127.0.0.1', port: 102, name: 'Default' } } });
  };

  const handleFspClick = (conn) => {
    // ?fsp=<name> lets ACSIServer.jsx recover which instance this is after
    // a page refresh, when the state below (React Router in-memory only)
    // is gone - see the paramEndpoint resolution there.
    const search = conn?.name ? `?fsp=${encodeURIComponent(conn.name)}` : '';
    navigate({ pathname: '/acsi-server', search }, { state: { endpoint: conn } });
  };

  const soConnections = connections.filter(conn => conn.type === 'RTI-SO' && conn.status === 'connected');
  const fspConnections = connections.filter(conn => conn.type === 'RTI-FSP' && conn.status === 'connected');
  const hasConnected = connections.filter(conn => conn.status === 'connected').length > 0;

  // SO side is considered "detected" if there's at least one connected SO.
  // Used to color the FSP circles (green when both sides detect a
  // connection, red if the SO side has failed). The SO circle itself uses
  // a different, per-SO signal instead (its own connectedFsps count, below).
  const soDetected = soConnections.length > 0;

  return (
    <div style={{ marginBottom: '40px', position: 'relative' }}>
      {loading ? (
        <div className="endpoints-loading">
          <span className="spinner"></span>
          Loading...
        </div>
      ) : hasConnected ? (
        <div style={{ display: 'flex', justifyContent: 'center', gap: '40px', minHeight: '300px' }}>
          {/* SO (Client) Side - Left - centers vertically against FSP column height */}
          <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', minWidth: '180px' }}>
            {soConnections.map((conn) => {
              // connectedFsps comes from the SO's own /api/properties
              // acsi_client_list (cps with an established association) -
              // see App.jsx's enrichSoClientCounts and bff_server.py's
              // _build_enriched_connections. Green as soon as one FSP is
              // connected, same threshold the FSP side already uses.
              const connectedFsps = conn.connectedFsps ?? 0;
              const fspConnected = connectedFsps > 0;
              const soCircleBg = selectedConnection?.name === conn.name
                ? 'var(--primary-light)'
                : fspConnected
                  ? 'var(--success-color)'
                  : 'var(--bg-card)';

              return (
              <React.Fragment key={`so-${conn.name}`}>
                <div style={{ position: 'relative', marginBottom: '12px' }}>
                  <div
                    style={{
                      width: '140px',
                      height: '140px',
                      border: '2px solid var(--border-color)',
                      borderRadius: '50%',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      background: soCircleBg,
                      cursor: 'pointer'
                    }}
                    onClick={handleSoClick}
                    title={`Type: RTI-SO (Client) - ${connectedFsps} FSP${connectedFsps === 1 ? '' : 's'} connected`}
                  >
                    <span style={{ color: 'var(--text-primary)', fontSize: '18px', fontWeight: '600' }}>{conn.name}</span>
                  </div>
                  {/* Counter of FSPs currently connected to this SO */}
                  <span
                    title={`${connectedFsps} connected FSP${connectedFsps === 1 ? '' : 's'}`}
                    style={{
                      position: 'absolute',
                      top: '-4px',
                      right: '-4px',
                      minWidth: '26px',
                      height: '26px',
                      padding: '0 6px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      borderRadius: '13px',
                      background: fspConnected ? 'var(--success-color)' : 'var(--text-muted)',
                      color: 'white',
                      fontSize: '12px',
                      fontWeight: 700,
                      border: '2px solid var(--bg-card)'
                    }}
                  >
                    {connectedFsps}
                  </span>
                </div>
                {showLabels && (
                  <div style={{
                      padding: '6px 12px',
                      background: selectedConnection?.name === conn.name ? 'var(--primary-light)' : 'var(--bg-hover)',
                      borderRadius: '16px',
                      textAlign: 'center',
                      fontSize: '11px',
                      border: '1px solid var(--border-color)',
                      cursor: onConnectionClick ? 'pointer' : 'default'
                    }}
                    onClick={() => onConnectionClick?.(conn)}
                    title="Edit instance"
                  >
                    RTI-SO
                  </div>
                )}
              </React.Fragment>
              );
            })}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: '24px' }}>
            {fspConnections.map((conn) => {
              const fspDetected = (conn.connectedClients ?? 0) > 0;
              const bothConnected = soDetected && fspDetected;
              const soFailed = !soDetected;

              const fspCircleBg = selectedConnection?.name === conn.name
                ? 'var(--primary-light)'
                : bothConnected
                  ? 'var(--success-color)'
                  : soFailed
                    ? 'var(--danger-color)'
                    : 'var(--bg-card)';

              return (
                <div key={`fsp-row-${conn.name}`} style={{ display: 'flex', alignItems: 'center', gap: '0' }}>
                  {/* Connection line - lives next to this specific FSP */}
                  <div
                    style={{
                      height: '4px',
                      width: '40px',
                      background: fspDetected
                        ? 'repeating-linear-gradient(to right, var(--success-color) 0, var(--success-color) 6px, transparent 6px, transparent 12px)'
                        : 'repeating-linear-gradient(to right, var(--border-color) 0, var(--border-color) 6px, transparent 6px, transparent 12px)',
                      flexShrink: 0
                    }}
                  ></div>

                  {/* FSP circle + label */}
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', minWidth: '180px', marginLeft: '16px' }}>
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
                        background: fspCircleBg,
                        cursor: 'pointer'
                      }}
                      onClick={() => handleFspClick(conn)}
                      title={`Type: ${conn.type}`}
                    >
                      <span style={{ color: 'var(--text-primary)', fontSize: '14px', fontWeight: '600', textAlign: 'center' }}>
                        {conn.name}
                      </span>
                    </div>
                    {showLabels && (
                      <div style={{
                        padding: '6px 12px',
                        background: selectedConnection?.name === conn.name ? 'var(--primary-light)' : 'var(--bg-hover)',
                        borderRadius: '16px',
                        textAlign: 'center',
                        fontSize: '11px',
                        border: '1px solid var(--border-color)',
                        cursor: onConnectionClick ? 'pointer' : 'default'
                      }}
                      onClick={() => onConnectionClick?.(conn)}
                      title="Edit instance"
                     >
                        RTI-FSP
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
            {fspConnections.length === 0 && (
              <div
                style={{
                  height: '4px',
                  width: '40px',
                  background: 'repeating-linear-gradient(to right, var(--border-color) 0, var(--border-color) 6px, transparent 6px, transparent 12px)'
                }}
              ></div>
            )}
          </div>
        </div>
      ) : (
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
  );
}

export default InstanceVisualization;