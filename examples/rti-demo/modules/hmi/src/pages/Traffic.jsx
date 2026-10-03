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

import React, { useState, useEffect, useCallback } from 'react';
import InstanceVisualization from '../components/InstanceVisualization';
import MessageMonitor from '../components/MessageMonitor';
import DataAccessPanel from '../components/DataAccessPanel';
import TrafficTimeline from '../components/TrafficTimeline';
import { useLinkActivity } from '../hooks/useLinkActivity';

function Traffic({ settings, getModel, updateModel, connections = [], loading = false }) {

  // The per-instance monitors start collapsed - the timeline above them
  // shows the same traffic merged; they stay for the raw per-instance view.
  const [monitorsExpanded, setMonitorsExpanded] = useState(false);
  const [timelineExpanded, setTimelineExpanded] = useState(true);
  const [panelsExpanded, setPanelsExpanded] = useState(true);
  const [dataAccessPanels, setDataAccessPanels] = useState([1]);
  const { activity, reset: resetActivity } = useLinkActivity(connections);
  // Clicking an FSP focuses its link: the others dim and only its monitor
  // is listed below. Clicking it again, or the SO, shows all links again.
  const [focusedFspName, setFocusedFspName] = useState(null);
  const focusedFsp = connections.some((c) => c.type === 'RTI-FSP' && c.name === focusedFspName)
    ? focusedFspName
    : null;

  return (
    <section className="page">
      <div className="page-header" style={{ marginBottom: '20px' }}>
        <h2>Traffic</h2>
        <p style={{ color: 'var(--text-muted)', marginTop: '4px' }}>SOs, FSP and Instances</p>
      </div>

      <div style={{ marginBottom: '40px' }}>
        <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: '8px', marginBottom: '8px', fontSize: '12px' }}>
          {focusedFsp && (
            <span className="link-focus-chip" style={{ color: 'var(--text-secondary)' }}>
              Focused on <strong>{focusedFsp}</strong>
              <button className="btn-secondary" style={{ marginLeft: '6px', padding: '3px 10px', fontSize: '12px' }} onClick={() => setFocusedFspName(null)} title="Show all links">
                Show all
              </button>
            </span>
          )}
          <button className="btn-secondary" style={{ padding: '3px 10px', fontSize: '12px' }} onClick={resetActivity} title="Reset the link counters">
            <i className="fas fa-undo" style={{ fontSize: '11px', marginRight: '4px' }}></i>Reset counters
          </button>
        </div>
        <InstanceVisualization
          connections={connections}
          selectedConnection={null}
          loading={loading}
          onConnectionClick={null}
          showLabels={true}
          activity={activity}
          focusedFsp={focusedFsp}
          onSoSelect={() => setFocusedFspName(null)}
          onFspSelect={(conn) => setFocusedFspName((prev) => (prev === conn.name ? null : conn.name))}
        />
      </div>
      
      {/* Collapsible merged timeline block */}
      <div style={{
        marginBottom: '20px',
        border: '1px solid var(--border-color)',
        borderRadius: '8px',
        padding: '12px',
        background: 'var(--bg-card)'
      }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            cursor: 'pointer',
            marginBottom: '12px',
            padding: '4px 0'
          }}
          onClick={() => setTimelineExpanded(!timelineExpanded)}
        >
          <h3 style={{ margin: 0, color: 'var(--text-secondary)', flex: 1 }}>
            Timeline
          </h3>
          <i
            className={`fas ${timelineExpanded ? 'fa-chevron-up' : 'fa-chevron-down'}`}
            style={{ color: 'var(--text-muted)', fontSize: '14px' }}
          ></i>
        </div>
        <div style={{ display: timelineExpanded ? 'block' : 'none' }}>
          <TrafficTimeline
            connections={connections}
            focusedFsp={focusedFsp}
            onFocusFsp={setFocusedFspName}
          />
        </div>
      </div>

      {/* Collapsible Data Access Panels block */}
      <div style={{ 
        marginBottom: '20px',
        border: '1px solid var(--border-color)',
        borderRadius: '8px',
        padding: '12px',
        background: 'var(--bg-card)'
      }}>
        <div 
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            cursor: 'pointer',
            marginBottom: '12px',
            padding: '4px 0'
          }}
          onClick={() => setPanelsExpanded(!panelsExpanded)}
        >
          <h3 style={{ margin: 0, color: 'var(--text-secondary)', flex: 1 }}>
            Data Access Panels
          </h3>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <button
              className="btn-icon"
              onClick={(e) => {
                e.stopPropagation();
                setDataAccessPanels(prev => [...prev, prev.length + 1]);
              }}
              title="Add panel"
              style={{ padding: '4px 8px' }}
            >
              <i className="fas fa-plus" style={{ fontSize: '12px' }}></i>
            </button>
            <button
              className="btn-icon"
              onClick={(e) => {
                e.stopPropagation();
                if (dataAccessPanels.length > 1) {
                  setDataAccessPanels(prev => prev.slice(0, -1));
                }
              }}
              title="Remove panel"
              disabled={dataAccessPanels.length <= 1}
              style={{ padding: '4px 8px' }}
            >
              <i className="fas fa-minus" style={{ fontSize: '12px' }}></i>
            </button>
            <i 
              className={`fas ${panelsExpanded ? 'fa-chevron-up' : 'fa-chevron-down'}`}
              style={{ color: 'var(--text-muted)', fontSize: '14px' }}
            ></i>
          </div>
        </div>
        
        <div style={{ display: panelsExpanded ? 'block' : 'none' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '16px' }}>
            {dataAccessPanels.map((id) => (
              <DataAccessPanel
                key={`data-access-panel-${id}`}
                connections={connections}
                getModel={getModel}
                updateModel={updateModel}
                settings={settings}
                cp={settings?.cp || 'cp1'}
              />
            ))}
          </div>
        </div>
      </div>
      
      {/* Collapsible monitors block */}
      <div style={{ 
        marginBottom: '20px',
        border: '1px solid var(--border-color)',
        borderRadius: '8px',
        padding: '12px',
        background: 'var(--bg-card)'
      }}>
        <div 
          style={{
            display: 'flex',
            alignItems: 'center',
            cursor: 'pointer',
            marginBottom: '12px',
            padding: '4px 0'
          }}
          onClick={() => setMonitorsExpanded(!monitorsExpanded)}
        >
          <h3 style={{ margin: 0, color: 'var(--text-secondary)', flex: 1 }}>
            Message Monitors (per instance)
          </h3>
          <i 
            className={`fas ${monitorsExpanded ? 'fa-chevron-up' : 'fa-chevron-down'}`}
            style={{ color: 'var(--text-muted)', fontSize: '14px' }}
          ></i>
        </div>
        
        <div style={{ display: monitorsExpanded ? 'block' : 'none' }}>
          {/* ACSI Client endpoints (RTI-SO) - First row */}
          <div style={{ marginBottom: '30px' }}>
            <h4 style={{ marginBottom: '12px', color: 'var(--text-muted)' }}>
              ACSI Client Endpoints (RTI-SO)
            </h4>
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
              gap: '16px',
              width: '100%'
            }}>
              {connections
                .filter(conn => conn.status === 'connected' && conn.type === 'RTI-SO')
                .map((endpoint) => (
                  <MessageMonitor
                    key={`client-monitor-${endpoint.host}-${endpoint.port}`}
                    endpoints={[endpoint]}
                    title={endpoint.name || endpoint.host}
                    defaultInterval={10000}
                    showEndpointSelect={false}
                  />
                ))}
            </div>
          </div>

          {/* ACSI Server endpoints (RTI-FSP) - Second row */}
          <div style={{ marginBottom: '0' }}>
            <h4 style={{ marginBottom: '12px', color: 'var(--text-muted)' }}>
              ACSI Server Endpoints (RTI-FSP)
            </h4>
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
              gap: '16px',
              width: '100%'
            }}>
              {connections
                // connectedClients (fsp/acsi_server.py's get_status -
                // len(endpoint.websocket_info_list)) is this FSP's own live
                // WebSocket connection count - only list FSPs that actually
                // have one open, same threshold InstanceVisualization
                // already uses to light up its FSP circle/connection line.
                .filter(conn => conn.status === 'connected' && conn.type === 'RTI-FSP' && (conn.connectedClients ?? 0) > 0)
                .filter(conn => !focusedFsp || conn.name === focusedFsp)
                .map((endpoint) => (
                  <MessageMonitor
                    key={`server-monitor-${endpoint.host}-${endpoint.port}`}
                    endpoints={[endpoint]}
                    title={endpoint.name || endpoint.host}
                    defaultInterval={10000}
                    showEndpointSelect={false}
                  />
                ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export default Traffic;
