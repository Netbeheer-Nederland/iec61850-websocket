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

/**
 * Shared "Monitoring" block for ACSIServer.jsx / ACSIClient.jsx: Start/Stop/
 * Clear controls plus the action-log list fetched from GET /api/actions-logs
 * (fsp/acsi_server.py's / so/acsi_client.py's `_log_action`, entries shaped
 * { id, time, level, message, detail }). Not the same thing as
 * MessageMonitor.jsx, which shows raw protocol traffic from GET
 * /api/messages (direction/category, no severity level) - these are two
 * genuinely different logs, not a case of picking one over the other.
 *
 * Presentation only - fetching/interval management (and whether monitoring
 * survives navigating away) stays owned by the page, same as before.
 */

// Real values _log_action ever sends (fsp/acsi_server.py, so/acsi_client.py):
// "info" (default), "warn", "error" - NOT "warning". The inline
// implementations this replaces checked for "warning", which never matched
// a real "warn" entry - those silently fell through to the default/info
// styling. Order here also defines severity rank, high to low, for sorting.
const SEVERITY_LEVELS = ['error', 'warn', 'info'];

// --danger-bg/--warning-bg/--info-bg (used by the inline implementations
// this replaces) aren't actually defined anywhere in styles.css - badges
// rendered with no background at all. Using the real --danger-color/
// --warning-color/--info-color tokens directly, at low opacity, instead.
const SEVERITY_STYLE = {
  error: { label: 'error', bg: 'rgba(244, 67, 54, 0.15)', color: 'var(--danger-color)' },
  warn: { label: 'warn', bg: 'rgba(255, 152, 0, 0.15)', color: 'var(--warning-color)' },
  info: { label: 'info', bg: 'rgba(3, 169, 244, 0.15)', color: 'var(--info-color)' },
};

const styleFor = (level) => SEVERITY_STYLE[level] || SEVERITY_STYLE.info;

function ActionLogPanel({ messages, isMonitoring, disabled, onStart, onStop, onClear }) {
  const [severityFilter, setSeverityFilter] = useState('all');
  // Messages already arrive newest-first (each page prepends new entries) -
  // "newest" here is a no-op pass-through, "oldest" reverses for display
  // only, without touching the underlying array/ordering used elsewhere.
  const [sortOrder, setSortOrder] = useState('newest');

  const counts = useMemo(() => {
    const c = { error: 0, warn: 0, info: 0 };
    for (const msg of messages) {
      const level = SEVERITY_LEVELS.includes(msg.level) ? msg.level : 'info';
      c[level] += 1;
    }
    return c;
  }, [messages]);

  const visibleMessages = useMemo(() => {
    let list = messages;
    if (severityFilter !== 'all') {
      list = list.filter((msg) => (SEVERITY_LEVELS.includes(msg.level) ? msg.level : 'info') === severityFilter);
    }
    if (sortOrder === 'oldest') {
      list = [...list].reverse();
    }
    return list;
  }, [messages, severityFilter, sortOrder]);

  return (
    <>
      <div style={{ display: 'flex', gap: '16px', marginBottom: '24px', flexWrap: 'wrap', alignItems: 'center' }}>
        <button id="messages-start-btn" className={isMonitoring ? 'btn-secondary' : 'btn-primary'} onClick={onStart} disabled={disabled || isMonitoring}>
          {isMonitoring ? 'Monitoring...' : 'Start Monitor'}
        </button>
        <button id="messages-stop-btn" className={isMonitoring ? 'btn-primary' : 'btn-secondary'} onClick={onStop} disabled={!isMonitoring}>
          Stop Monitor
        </button>
        <button id="messages-clear-btn" className="btn-secondary" onClick={onClear} disabled={disabled}>
          Clear Logs
        </button>
      </div>

      {isMonitoring && (
        <div style={{ marginTop: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px', flexWrap: 'wrap', gap: '8px' }}>
            <h3 style={{ fontSize: '16px', margin: 0 }}>
              Protocol Messages
              {messages.length > 0 && (
                <span style={{ marginLeft: '8px', fontSize: '12px', fontWeight: 'normal', color: 'var(--text-muted)' }}>
                  {messages.length} total
                  {counts.error > 0 && <span style={{ color: 'var(--danger-color)' }}> · {counts.error} error{counts.error !== 1 ? 's' : ''}</span>}
                  {counts.warn > 0 && <span style={{ color: 'var(--warning-color)' }}> · {counts.warn} warning{counts.warn !== 1 ? 's' : ''}</span>}
                </span>
              )}
            </h3>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <select
                id="messages-severity-filter"
                value={severityFilter}
                onChange={(e) => setSeverityFilter(e.target.value)}
                disabled={messages.length === 0}
                style={{ fontSize: '12px' }}
                title="Filter by severity"
              >
                <option value="all">All levels</option>
                <option value="error">Error only</option>
                <option value="warn">Warning only</option>
                <option value="info">Info only</option>
              </select>
              <button
                id="messages-sort-toggle"
                className="btn-icon"
                onClick={() => setSortOrder((prev) => (prev === 'newest' ? 'oldest' : 'newest'))}
                disabled={messages.length === 0}
                title={sortOrder === 'newest' ? 'Showing newest first - click for oldest first' : 'Showing oldest first - click for newest first'}
              >
                <i className={`fas fa-sort-${sortOrder === 'newest' ? 'amount-down' : 'amount-up'}`}></i>
              </button>
            </div>
          </div>
          <div style={{ background: 'var(--bg-card)', borderRadius: '8px', border: '1px solid var(--border-color)', maxHeight: '300px', overflowY: 'auto', padding: '12px' }}>
            {visibleMessages.length === 0 ? (
              <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '20px' }}>
                {messages.length === 0
                  ? 'No log messages yet. Messages will appear here when monitoring.'
                  : 'No messages match the selected severity filter.'}
              </div>
            ) : (
              visibleMessages.map((msg, index) => {
                const level = SEVERITY_LEVELS.includes(msg.level) ? msg.level : 'info';
                const style = styleFor(level);
                return (
                  <div key={msg.id ?? index} style={{ padding: '8px 12px', marginBottom: '8px', borderRadius: '4px', background: 'var(--bg-hover)', fontSize: '12px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                      <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>#{msg.id ?? index} - {msg.timestamp}</span>
                      <span style={{ fontSize: '11px', padding: '2px 6px', borderRadius: '3px', background: style.bg, color: style.color }}>
                        {style.label}
                      </span>
                    </div>
                    <div style={{ color: 'var(--text-primary)' }}>{msg.message}</div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </>
  );
}

export default ActionLogPanel;
