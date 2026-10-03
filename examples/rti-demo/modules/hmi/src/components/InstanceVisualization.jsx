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
import { EMPTY_LINK } from '../hooks/useLinkActivity';
import { fspStateOf, useNow } from '../hooks/useFspPresence';
import { formatDuration } from '../utils/timeline';

const DOWN_LABELS = { 'link-down': 'link down', unreachable: 'unreachable' };

const PULSE_COLORS = {
  request: 'var(--primary-color)',
  response: 'var(--success-color)',
  report: 'var(--warning-color)',
};

/**
 * The SO-FSP line with live activity (Traffic only): a dot travels along it
 * per frame batch - towards the FSP for a request, back for a response or
 * report - with the link's cp above and its counters / last service below.
 * Turns red while the last service failed. A dropped link (`down`: the
 * FSP's presence state and how long it has been so) is drawn red with an
 * X, its counters kept.
 */
function ActivityLink({ fspName, cp, link = EMPTY_LINK, detected, down = null }) {
  const failed = link.last && !link.last.ok;
  const lineColor = down || failed ? 'var(--danger-color)' : detected ? 'var(--success-color)' : 'var(--border-color)';
  const pulse = down ? null : link.pulse;
  return (
    <div style={{ width: '200px', flexShrink: 0, display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '11px' }}>
      <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontFamily: 'Consolas, "Courier New", monospace' }} title="Access point (cp) of this link">
        {cp || '\u00a0'}
      </div>
      <div className="link-line" style={{
        position: 'relative',
        height: '4px',
        background: `repeating-linear-gradient(to right, ${lineColor} 0, ${lineColor} 6px, transparent 6px, transparent 12px)`,
      }}>
        {pulse && (
          <span
            key={pulse.seq}
            data-testid={`link-pulse-${fspName}`}
            className={`link-pulse ${pulse.type === 'request' ? 'link-pulse--out' : 'link-pulse--in'}`}
            style={{ background: pulse.ok ? PULSE_COLORS[pulse.type] : 'var(--danger-color)' }}
          />
        )}
        {down && (
          <span
            data-testid={`link-down-${fspName}`}
            style={{
              position: 'absolute', left: '50%', top: '50%', transform: 'translate(-50%, -50%)',
              width: '20px', height: '20px', borderRadius: '50%', background: 'var(--danger-color)', color: 'white',
              display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '12px', fontWeight: 700,
            }}
          >
            {'\u2717'}
          </span>
        )}
      </div>
      {down && (
        <div style={{ textAlign: 'center', color: 'var(--danger-color)', fontWeight: 600 }} data-testid={`link-down-label-${fspName}`}>
          {DOWN_LABELS[down.state]}{down.forMs != null ? ` \u00b7 ${formatDuration(down.forMs)}` : ''}
        </div>
      )}
      <div style={{ display: 'flex', justifyContent: 'center', gap: '10px', color: 'var(--text-secondary)', opacity: down ? 0.5 : 1 }} data-testid={`link-counters-${fspName}`}>
        <span title="Requests (SO to FSP)" style={{ color: PULSE_COLORS.request }}>&rarr; {link.requests}</span>
        <span title="Responses (FSP to SO)" style={{ color: PULSE_COLORS.response }}>&larr; {link.responses}</span>
        <span title="Reports (FSP to SO)" style={{ color: PULSE_COLORS.report }}>&#9873; {link.reports}</span>
        {link.errors > 0 && <span title="Service errors" style={{ color: 'var(--danger-color)' }}>&#10007; {link.errors}</span>}
      </div>
      <div style={{ textAlign: 'center', color: failed ? 'var(--danger-color)' : 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} data-testid={`link-last-${fspName}`}>
        {link.last ? `${link.last.service} ${link.last.ok ? '\u2713' : '\u2717'} ${link.last.time}` : 'no traffic yet'}
      </div>
    </div>
  );
}

/**
 * Reusable component for visualizing SO-FSP connections
 *
 * @param {Object[]} connections - Array of connection objects
 * @param {Object|null} selectedConnection - Currently selected connection (for highlighting)
 * @param {Function|null} onConnectionClick - Click handler for connection items
 * @param {boolean} showLabels - Whether to show type labels
 * @param {boolean} loading - Whether data is currently loading
 * @param {Object|null} activity - Per FSP name link activity (useLinkActivity);
 *   when given, each SO-FSP line shows it live (Traffic page)
 * @param {string|null} focusedFsp - Name of the FSP whose link is focused; the others are dimmed
 * @param {Function|null} onSoSelect - Replaces the SO circle's navigation to ACSI Client
 * @param {Function|null} onFspSelect - Replaces an FSP circle's navigation to ACSI Server, called with the connection
 * @param {Object|null} presence - useFspPresence's result; when given, FSPs that
 *   dropped stay on the picture, marked down (Traffic)
 */
function InstanceVisualization({
  connections,
  selectedConnection = null,
  onConnectionClick = null,
  showLabels = true,
  loading = false,
  activity = null,
  focusedFsp = null,
  onSoSelect = null,
  onFspSelect = null,
  presence = null
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
  // With presence (Traffic) an FSP the BFF can't reach stays on the
  // picture, marked down, instead of disappearing.
  const fspConnections = connections.filter(conn => conn.type === 'RTI-FSP' && (presence || conn.status === 'connected'));
  const stateOf = (conn) => presence?.byName[conn.name]?.state ?? fspStateOf(conn);
  const now = useNow(Boolean(presence) && fspConnections.some((c) => stateOf(c) !== 'up'));
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
                    onClick={onSoSelect ? () => onSoSelect(conn) : handleSoClick}
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
              const fspState = presence ? stateOf(conn) : null;
              const since = presence?.byName[conn.name]?.since;
              const down = fspState && fspState !== 'up'
                ? { state: fspState, forMs: since != null ? now - since : null }
                : null;
              const bothConnected = soDetected && fspDetected;
              const soFailed = !soDetected;

              const fspCircleBg = selectedConnection?.name === conn.name
                ? 'var(--primary-light)'
                : bothConnected
                  ? 'var(--success-color)'
                  : soFailed
                    ? 'var(--danger-color)'
                    : 'var(--bg-card)';

              const isFocused = focusedFsp === conn.name;
              const dimmed = focusedFsp != null && !isFocused;

              return (
                <div
                  key={`fsp-row-${conn.name}`}
                  data-testid={`fsp-row-${conn.name}`}
                  style={{ display: 'flex', alignItems: 'center', gap: '0', opacity: dimmed ? 0.35 : 1, transition: 'opacity 0.2s' }}
                >
                  {/* Connection line - lives next to this specific FSP */}
                  {activity ? (
                    <ActivityLink
                      fspName={conn.name}
                      cp={conn.accessPoints?.[0]}
                      down={down}
                      link={activity[conn.name]}
                      detected={fspDetected}
                    />
                  ) : (
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
                  )}

                  {/* FSP circle + label */}
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', minWidth: '180px', marginLeft: '16px' }}>
                    <div
                      style={{
                        width: '120px',
                        height: '120px',
                        border: down ? '2px dashed var(--danger-color)' : '2px solid var(--border-color)',
                        borderRadius: '50%',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        margin: '6px 0',
                        background: down ? 'var(--bg-card)' : fspCircleBg,
                        cursor: 'pointer',
                        outline: isFocused ? '3px solid var(--primary-color)' : 'none',
                        outlineOffset: '3px'
                      }}
                      onClick={() => (onFspSelect ? onFspSelect(conn) : handleFspClick(conn))}
                      title={onFspSelect
                        ? (isFocused ? `${conn.name} - click to show all links` : `${conn.name} - click to focus this link`)
                        : `Type: ${conn.type}`}
                    >
                      <span style={{ color: down ? 'var(--text-muted)' : 'var(--text-primary)', fontSize: '14px', fontWeight: '600', textAlign: 'center' }}>
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