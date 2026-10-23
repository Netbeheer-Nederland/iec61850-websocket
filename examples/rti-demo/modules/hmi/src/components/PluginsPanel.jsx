/*
 * SPDX-FileCopyrightText: 2026 Netbeheer Nederland
 * SPDX-License-Identifier: Apache-2.0
 */

// The plugins an SO or FSP has connected to, on the ACSI Client and ACSI
// Server pages: one row per plugin (healthy / unhealthy / unreachable, with
// the reason), Edit (URL and settings), Reload and Remove, and Add from a URL.
// Only the plugin contract's management routes (GET/POST /api/plugins,
// PUT/DELETE .../{name}, .../{name}/reload), through the BFF - nothing here
// knows any one plugin.
import React, { useState, useEffect, useCallback } from 'react';
import { executeApiCall } from '../services/apiService';
import { pluginRows } from '../utils/plugins';

const STATE_STYLES = {
  healthy: { label: 'Healthy', color: 'var(--success-color)' },
  unhealthy: { label: 'Unhealthy', color: 'var(--warning-color)' },
  unreachable: { label: 'Unreachable', color: 'var(--danger-color)' },
};

// The error of a failed call: the BFF's "error", which carries the
// instance's own reason (e.g. a URL outside PLUGIN_ALLOWED_SOURCES).
const errorOf = (result) =>
  result?.payload?.error || result?.payload?.detail || result?.rawText || 'Unknown error';

// What PLUGIN_ALLOWED_SOURCES can hold (decision 0037), for the form's hint.
const SOURCES_HINT = 'exact URLs, wildcards such as http://192.168.0.*:8000 or http://*:9000, or * for any URL';

/**
 * @param {string|null} target - The SO/FSP's BFF target (host:port)
 * @param {'fsp'|'so'} role - FSP plugins can claim objRefs; SO plugins can't
 * @param {Object|null|undefined} pushed - The instance's `plugins` from the
 *   BFF's connections push; followed when it changes
 */
function PluginsPanel({ target, role, pushed }) {
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  // The form: null (closed), { mode: 'add' }, or { mode: 'edit', name }.
  const [formFor, setFormFor] = useState(null);
  const [form, setForm] = useState({ name: '', url: '', settings: '' });
  const editing = formFor?.mode === 'edit';

  const load = useCallback(async () => {
    if (!target) return;
    const result = await executeApiCall('plugins', target);
    if (result?.ok) setStatus(result.payload?.result ?? null);
  }, [target]);

  useEffect(() => { load(); }, [load]);

  // The push carries the same GET /api/plugins every 2s, so a plugin that
  // drops or comes back shows without this panel polling.
  const pushedKey = pushed ? JSON.stringify(pushed) : null;
  useEffect(() => {
    if (pushedKey) setStatus(JSON.parse(pushedKey));
  }, [pushedKey]);

  const run = useCallback(async (label, apiId, body, pathParams) => {
    setBusy(label);
    setError(null);
    const result = await executeApiCall(apiId, target, body, { pathParams });
    setBusy(null);
    if (!result?.ok) {
      setError(`${label} failed: ${errorOf(result)}`);
      await load();
      return false;
    }
    await load();
    return true;
  }, [target, load]);

  const handleRemove = useCallback((name) => {
    if (!window.confirm(`Remove plugin '${name}'? A configured plugin comes back on the next restart.`)) return;
    run(`Remove ${name}`, 'plugin-remove', null, { name });
  }, [run]);

  const openAdd = useCallback(() => {
    setFormFor((f) => (f?.mode === 'add' ? null : { mode: 'add' }));
    setForm({ name: '', url: '', settings: '' });
  }, []);

  const openEdit = useCallback((row) => {
    const settings = row.definition?.settings || {};
    setFormFor({ mode: 'edit', name: row.name });
    setForm({
      name: row.name,
      url: row.definition?.url || row.url,
      settings: Object.keys(settings).length ? JSON.stringify(settings, null, 2) : '',
    });
  }, []);

  const handleSubmit = useCallback(async (e) => {
    e.preventDefault();
    let settings = {};
    if (form.settings.trim()) {
      try {
        settings = JSON.parse(form.settings);
      } catch (err) {
        setError(`Settings must be JSON: ${err.message}`);
        return;
      }
    }
    const ok = editing
      ? await run(`Edit ${formFor.name}`, 'plugin-edit', { url: form.url.trim(), settings }, { name: formFor.name })
      : await run(`Add ${form.name}`, 'plugin-add', { name: form.name.trim(), url: form.url.trim(), settings });
    if (ok) {
      setFormFor(null);
      setForm({ name: '', url: '', settings: '' });
    }
  }, [form, formFor, editing, run]);

  const rows = pluginRows(status);
  const showClaims = role === 'fsp';

  return (
    <div id="plugins-panel" style={{ marginBottom: '24px', padding: '16px', background: 'var(--bg-card)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
        <h3 style={{ margin: 0, fontSize: '16px' }}>
          <i className="fas fa-plug" style={{ marginRight: '8px' }} aria-hidden="true"></i>
          Plugins{rows.length ? ` (${rows.length})` : ''}
        </h3>
        <button type="button" id="plugins-add-btn" className="btn-secondary" onClick={formFor ? () => setFormFor(null) : openAdd} disabled={!target}>
          {formFor ? 'Cancel' : 'Add plugin'}
        </button>
      </div>

      {formFor && (
        <form onSubmit={handleSubmit} aria-label={editing ? `Edit ${formFor.name}` : 'Add plugin'} style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '8px 12px', marginBottom: '12px' }}>
          <input id="plugins-add-name" placeholder="Name, e.g. io" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required disabled={editing} title={editing ? 'The name stays: a plugin with another name is another plugin' : undefined} />
          <input id="plugins-add-url" placeholder="URL, e.g. http://rpi-io:9000/plugin" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} required />
          <textarea id="plugins-add-settings" placeholder='Settings (JSON, optional), e.g. {"write_inputs": false}' value={form.settings} onChange={(e) => setForm({ ...form, settings: e.target.value })} style={{ gridColumn: '1 / -1', fontFamily: 'monospace', minHeight: '48px' }} />
          <small style={{ gridColumn: '1 / -1', color: 'var(--text-muted)' }}>
            {editing
              ? `A new URL must be allowed by the instance's PLUGIN_ALLOWED_SOURCES (${SOURCES_HINT}); the settings replace all of them. If the plugin doesn't connect with them, it keeps its old URL and settings. The edit stays until the instance restarts; a lasting one goes in its plugin configuration.`
              : `Only URLs allowed by the instance's PLUGIN_ALLOWED_SOURCES are accepted (${SOURCES_HINT}). An added plugin stays until the instance restarts; a lasting one goes in its plugin configuration.`}
          </small>
          <div style={{ gridColumn: '1 / -1' }}>
            <button type="submit" id="plugins-add-submit" className="btn-primary" disabled={Boolean(busy)}>{editing ? 'Save' : 'Add'}</button>
          </div>
        </form>
      )}

      {error && (
        <div role="alert" style={{ marginBottom: '12px', padding: '10px', borderRadius: '6px', fontSize: '13px', background: 'rgba(244, 67, 54, 0.15)', color: 'var(--danger-color)', border: '1px solid var(--danger-color)' }}>
          <i className="fas fa-exclamation-triangle" style={{ marginRight: '8px' }}></i>{error}
        </div>
      )}

      {rows.length === 0 ? (
        <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '13px' }}>
          {status ? 'No plugins connected.' : 'Plugin status not available.'}
        </p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Plugin</th>
              <th>State</th>
              <th>URL</th>
              {showClaims && <th title="objRefs whose Operate this plugin answers">Controls</th>}
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const st = STATE_STYLES[row.state];
              return (
                <tr key={row.name} data-testid={`plugin-row-${row.name}`}>
                  <td>{row.name}{row.version && <span style={{ color: 'var(--text-muted)' }}> {row.version}</span>}</td>
                  <td>
                    <span style={{ color: st.color, fontWeight: 600 }}>{st.label}</span>
                    {row.error && <div style={{ color: 'var(--text-muted)', fontSize: '12px', maxWidth: '360px', overflowWrap: 'anywhere' }}>{row.error}</div>}
                  </td>
                  <td style={{ fontFamily: 'monospace', fontSize: '12px', overflowWrap: 'anywhere' }}>{row.url || '-'}</td>
                  {showClaims && <td title={row.claims.join('\n')}>{row.claims.length || '-'}</td>}
                  <td>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button type="button" className="btn-icon" title={row.definition ? `Edit ${row.name}` : `Edit ${row.name}: this instance doesn't list plugin definitions`} disabled={Boolean(busy) || !row.definition} onClick={() => openEdit(row)}>
                        <i className="fas fa-pen"></i>
                      </button>
                      <button type="button" className="btn-icon" title={`Reload ${row.name}`} disabled={Boolean(busy)} onClick={() => run(`Reload ${row.name}`, 'plugin-reload', null, { name: row.name })}>
                        <i className="fas fa-sync-alt"></i>
                      </button>
                      <button type="button" className="btn-icon" title={`Remove ${row.name}`} disabled={Boolean(busy)} onClick={() => handleRemove(row.name)}>
                        <i className="fas fa-trash"></i>
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default PluginsPanel;
