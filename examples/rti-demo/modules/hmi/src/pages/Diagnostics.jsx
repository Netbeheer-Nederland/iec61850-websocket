/*
 * SPDX-FileCopyrightText: 2025-2026 Netbeheer Nederland
 * SPDX-License-Identifier: Apache-2.0
 *
 * Copyright 2025-2026 Netbeheer Nederland
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

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { buildBffApiUrl } from '../services/apiService';
import LogKindBadge from '../components/LogKindBadge';
import { SEVERITY_LEVELS, styleFor } from '../components/ActionLogPanel';

// How often the page re-reads GET /api/diagnostics while it's open.
export const DIAGNOSTICS_POLL_MS = 5000;

// 'nodebug' (default) hides debug - the SO logs a burst of debug system
// entries on every TLS/OAuth reconfiguration, which would otherwise bury
// the warnings this page is for.
const LEVEL_FILTERS = {
  nodebug: { label: 'All but debug', match: (level) => level !== 'debug' },
  problems: { label: 'Errors & warnings', match: (level) => level === 'error' || level === 'warn' },
  all: { label: 'All levels', match: () => true },
};

const levelOf = (entry) => (SEVERITY_LEVELS.includes(entry.level) ? entry.level : 'info');

/**
 * Diagnostics: "is the system healthy?" - the system log across the whole
 * demo. GET /api/diagnostics merges the BFF's own events (an instance
 * coming up or dropping, TLS/OAuth re-apply results, the startup IDP check)
 * with every reachable RTI-SO/RTI-FSP's kind "system" actions-log entries,
 * errors and warnings first. ACSI service and WebSocket entries are on
 * Traffic instead. See docs/rti-demo/design/logging-kinds.md.
 */
function Diagnostics() {
  const [entries, setEntries] = useState([]);
  const [sources, setSources] = useState([]);
  const [error, setError] = useState(null);
  const [loaded, setLoaded] = useState(false);
  const [sourceFilter, setSourceFilter] = useState('all');
  const [levelFilter, setLevelFilter] = useState('nodebug');

  const load = useCallback(async () => {
    try {
      const response = await fetch(buildBffApiUrl('/api/diagnostics'));
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const body = await response.json();
      setEntries(Array.isArray(body.entries) ? body.entries : []);
      setSources(Array.isArray(body.sources) ? body.sources : []);
      setError(null);
    } catch (e) {
      setError(e.message || 'Failed to load diagnostics');
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, DIAGNOSTICS_POLL_MS);
    return () => clearInterval(interval);
  }, [load]);

  const visible = useMemo(() => entries.filter((e) => (
    (sourceFilter === 'all' || e.source === sourceFilter)
    && LEVEL_FILTERS[levelFilter].match(levelOf(e))
  )), [entries, sourceFilter, levelFilter]);

  const counts = useMemo(() => ({
    error: entries.filter((e) => levelOf(e) === 'error').length,
    warn: entries.filter((e) => levelOf(e) === 'warn').length,
  }), [entries]);

  return (
    <section className="page">
      <div className="page-header" style={{ marginBottom: '20px' }}>
        <h2>Diagnostics</h2>
        <p style={{ color: 'var(--text-muted)', marginTop: '4px' }}>
          System events from the BFF and every reachable instance - errors and warnings first
        </p>
      </div>

      <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap', marginBottom: '12px' }}>
        <span style={{ fontSize: '13px', color: 'var(--text-muted)', flex: 1 }}>
          {entries.length} entries
          {counts.error > 0 && <span style={{ color: 'var(--danger-color)' }}> · {counts.error} error{counts.error !== 1 ? 's' : ''}</span>}
          {counts.warn > 0 && <span style={{ color: 'var(--warning-color)' }}> · {counts.warn} warning{counts.warn !== 1 ? 's' : ''}</span>}
        </span>
        <select
          className="action-log-select"
          value={sourceFilter}
          onChange={(e) => setSourceFilter(e.target.value)}
          title="Filter by source"
        >
          <option value="all">All sources</option>
          {sources.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select
          className="action-log-select"
          value={levelFilter}
          onChange={(e) => setLevelFilter(e.target.value)}
          title="Filter by severity"
        >
          {Object.entries(LEVEL_FILTERS).map(([key, def]) => <option key={key} value={key}>{def.label}</option>)}
        </select>
      </div>

      {error && (
        <div className="alert alert-error" role="alert" style={{ marginBottom: '12px', padding: '12px', border: '1px solid var(--danger-color)', color: 'var(--danger-color)', borderRadius: '4px' }}>
          Couldn't load diagnostics from the BFF: {error}
        </div>
      )}

      <div className="diagnostics-section" id="diagnostics-container" style={{ background: 'var(--bg-card)', borderRadius: '8px', border: '1px solid var(--border-color)', padding: '12px' }}>
        {visible.length === 0 ? (
          <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '20px', margin: 0 }}>
            {!loaded ? 'Loading...' : entries.length === 0 ? 'No system events yet.' : 'No entries match the selected filters.'}
          </p>
        ) : (
          visible.map((entry) => {
            const style = styleFor(levelOf(entry));
            return (
              <div
                key={`${entry.source}:${entry.id}`}
                className="diagnostics-entry"
                style={{ padding: '8px 12px', marginBottom: '8px', borderRadius: '4px', background: 'var(--bg-hover)', fontSize: '12px' }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', marginBottom: '4px' }}>
                  <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>
                    <strong className="diagnostics-source" style={{ color: 'var(--text-secondary)' }}>{entry.source}</strong>
                    {entry.source === 'BFF' && entry.instance ? ` · ${entry.instance}` : ''} - {entry.time}
                  </span>
                  <span style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                    <LogKindBadge kind={entry.kind} />
                    <span style={{ fontSize: '11px', padding: '2px 6px', borderRadius: '3px', background: style.bg, color: style.color }}>
                      {style.label}
                    </span>
                  </span>
                </div>
                <div style={{ color: 'var(--text-primary)' }}>{entry.message}</div>
              </div>
            );
          })
        )}
      </div>
    </section>
  );
}

export default Diagnostics;
