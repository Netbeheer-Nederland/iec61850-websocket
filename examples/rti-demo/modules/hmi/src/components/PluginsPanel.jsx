/*
 * SPDX-FileCopyrightText: 2026 Netbeheer Nederland
 * SPDX-License-Identifier: Apache-2.0
 */

// The plugins an SO or FSP has connected to, on the ACSI Client and ACSI
// Server pages: one row per plugin (healthy / unhealthy / unreachable, with
// the reason), Details (claims, routes, what it attaches, settings, and a
// Request form for the plugin's own routes), Edit (URL and settings), Add
// to another SO or FSP, Copy as configuration, Reload (Retry for an
// unreachable one) and Remove; Add from a URL, and Retry all that have a
// problem.
// Only the plugin contract's management routes (GET/POST /api/plugins,
// PUT/DELETE .../{name}, .../{name}/reload) and its plugin routes
// (/api/plugins/{name}/{path}), through the BFF - nothing here knows any one
// plugin.
import React, { useState, useEffect, useCallback, lazy, Suspense } from 'react';
import { executeApiCall } from '../services/apiService';
import {
  pluginRows, configEntry, addTargets, ROUTE_METHODS, routeHasBody, routeRequest, routeAnswerText,
} from '../utils/plugins';

// CodeMirror is most of the HMI's size otherwise; only this form needs it.
const JsonEditor = lazy(() => import('./JsonEditor'));

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
// Decision 0042: the FSP reads settings.claims; an Operate on one goes to the plugin.
const CLAIMS_HINT = 'A "claims" setting, a list of control objRefs such as ["GenericIO/GGIO1.SPCSO2.Oper.ctlVal"], makes the plugin answer their Operates, as well as the objRefs it claims itself.';

const ATTACHED_COLORS = {
  ok: 'var(--success-color)',
  degraded: 'var(--warning-color)',
  down: 'var(--danger-color)',
  unknown: 'var(--text-muted)',
};

// Reload asks a connected plugin again what it is; for one that couldn't be
// reached, it tries now instead of after PLUGIN_RETRY_SECONDS.
const reloadLabel = (row) => (row.state === 'unreachable' ? `Retry ${row.name} now` : `Reload ${row.name}`);

const detailLabel = { color: 'var(--text-muted)', whiteSpace: 'nowrap', verticalAlign: 'top', paddingRight: '12px' };

const EMPTY_REQUEST = { method: 'GET', path: '', query: '', body: '', answer: null };

// Edit, and Add to another instance, start from the row's definition.
const formOf = (row, to = '') => {
  const settings = row.definition?.settings || {};
  return {
    name: row.name,
    url: row.definition?.url || row.url,
    settings: Object.keys(settings).length ? JSON.stringify(settings, null, 2) : '',
    to,
  };
};

// A request to the plugin's own routes (spec 0001), and what it answered.
// The BFF gives a plugin's answer only on success; a failure comes as the
// instance's error, with the plugin's status in it.
function PluginRequest({ row, request, onChange, onSend, busy }) {
  const { method, path, query, body, answer } = request;
  const set = (field) => (e) => onChange({ [field]: e.target.value });
  const setBody = (text) => onChange({ body: text });
  return (
    <div style={{ marginTop: '10px' }}>
      <form
        aria-label={`Request to ${row.name}`}
        onSubmit={(e) => { e.preventDefault(); onSend(); }}
        style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '8px' }}
      >
        <select aria-label="Method" value={method} onChange={set('method')}>
          {ROUTE_METHODS.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
        <span style={{ fontFamily: 'monospace', fontSize: '12px', color: 'var(--text-muted)' }}>/api/plugins/{row.name}/</span>
        <input aria-label="Path" placeholder="Path, e.g. leds" value={path} onChange={set('path')} style={{ flex: '1 1 140px' }} />
        <input aria-label="Query" placeholder="Query, e.g. on=1&color=red" value={query} onChange={set('query')} style={{ flex: '1 1 140px' }} />
        <button type="submit" className="btn-primary" disabled={Boolean(busy)}>Send</button>
        {routeHasBody(method) && (
          <Suspense fallback={<div style={{ flexBasis: '100%', minHeight: '48px', color: 'var(--text-muted)' }}>Loading the body editor...</div>}>
            <JsonEditor id={`plugin-request-body-${row.name}`} label="Body (JSON)" placeholder='Body (JSON object, optional), e.g. {"on": true}' value={body} onChange={setBody} style={{ flexBasis: '100%' }} />
          </Suspense>
        )}
      </form>
      {answer && (
        <div data-testid={`plugin-answer-${row.name}`} style={{ marginTop: '8px' }}>
          <div style={{ fontWeight: 600, color: answer.ok ? 'var(--success-color)' : 'var(--danger-color)' }}>
            {answer.ok ? 'OK' : 'Failed'} <span style={{ fontWeight: 400, color: 'var(--text-muted)', fontFamily: 'monospace', fontSize: '12px' }}>{answer.request}</span>
          </div>
          <pre style={{ margin: '4px 0 0', fontSize: '12px', maxHeight: '300px', overflow: 'auto', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{answer.text}</pre>
          {answer.cut && <small style={{ color: 'var(--text-muted)' }}>Cut at {answer.text.length} characters.</small>}
        </div>
      )}
    </div>
  );
}

// What a row's Details shows: everything of its status the table doesn't.
function PluginDetails({ row, showClaims }) {
  const settings = row.definition?.settings;
  return (
    <table data-testid={`plugin-details-${row.name}`} style={{ fontSize: '13px', borderCollapse: 'collapse' }}>
      <tbody>
        {showClaims && (
          <tr>
            <td style={detailLabel}>Controls</td>
            <td style={{ fontFamily: 'monospace', fontSize: '12px' }}>
              {row.claims.length ? row.claims.map((ref) => <div key={ref}>{ref}</div>) : '-'}
            </td>
          </tr>
        )}
        <tr>
          <td style={detailLabel}>Routes</td>
          <td style={{ fontFamily: 'monospace', fontSize: '12px' }}>{row.routes ? `/api/plugins/${row.name}/` : '-'}</td>
        </tr>
        <tr>
          <td style={detailLabel}>Attached</td>
          <td>
            {row.attached.length === 0 && !row.attachedError && '-'}
            {row.attached.map((item, i) => (
              <div key={i}>
                <span style={{ color: ATTACHED_COLORS[item.state] || ATTACHED_COLORS.unknown }}>&#9679;</span>{' '}
                {item.label} <span style={{ color: 'var(--text-muted)' }}>({item.kind}{item.detail ? `, ${item.detail}` : ''})</span>
                {item.address && <span style={{ fontFamily: 'monospace', fontSize: '12px', marginLeft: '6px' }}>{item.address}</span>}
              </div>
            ))}
            {row.attachedError && <div style={{ color: 'var(--warning-color)' }}>{row.attachedError}</div>}
          </td>
        </tr>
        <tr>
          <td style={detailLabel}>Settings</td>
          <td>
            {!row.definition ? "This instance doesn't list plugin definitions."
              : Object.keys(settings || {}).length
                ? <pre style={{ margin: 0, fontSize: '12px' }}>{JSON.stringify(settings, null, 2)}</pre>
                : '-'}
          </td>
        </tr>
      </tbody>
    </table>
  );
}

/**
 * @param {string|null} target - The SO/FSP's BFF target (host:port)
 * @param {'fsp'|'so'} role - FSP plugins can claim objRefs; SO plugins can't
 * @param {Object|null|undefined} pushed - The instance's `plugins` from the
 *   BFF's connections push; followed when it changes
 * @param {Array} instances - The BFF's connections, for Add to... (spec 0002)
 */
function PluginsPanel({ target, role, pushed, instances = [] }) {
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  // After Copy: { text } or, where the browser won't copy, { text, json } to copy by hand.
  const [notice, setNotice] = useState(null);
  const [expanded, setExpanded] = useState({});
  // Per plugin, its Request form and last answer, while the page is open.
  const [requests, setRequests] = useState({});
  // The form: null (closed), { mode: 'add' }, { mode: 'edit', name }, or
  // { mode: 'copy', name, targets } (Add to another instance, its `to`).
  const [formFor, setFormFor] = useState(null);
  const [form, setForm] = useState({ name: '', url: '', settings: '', to: '' });
  const editing = formFor?.mode === 'edit';
  const copying = formFor?.mode === 'copy';
  const setSettings = useCallback((settings) => setForm((f) => ({ ...f, settings })), []);

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

  const run = useCallback(async (label, apiId, body, pathParams, to = target) => {
    setBusy(label);
    setError(null);
    const result = await executeApiCall(apiId, to, body, { pathParams });
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

  // Retry every plugin with a problem, one after the other; the failures in one alert.
  const handleRetryAll = useCallback(async (names) => {
    setBusy('Retry');
    setError(null);
    const failures = [];
    for (const name of names) {
      const result = await executeApiCall('plugin-reload', target, null, { pathParams: { name } });
      if (!result?.ok) failures.push(`${name}: ${errorOf(result)}`);
    }
    setBusy(null);
    if (failures.length) setError(`Retry failed for ${failures.join('; ')}`);
    await load();
  }, [target, load]);

  // The row as an entry for the instance's plugin configuration, so an edit
  // or an added plugin lasts. The clipboard needs HTTPS or localhost;
  // otherwise the entry is shown to copy by hand.
  const handleCopy = useCallback(async (row) => {
    const json = JSON.stringify(configEntry(row), null, 2);
    const where = "the instance's plugin configuration (PLUGINS_FILE or PLUGINS), under \"plugins\"";
    try {
      await navigator.clipboard.writeText(json);
      setNotice({ text: `Copied ${row.name} as an entry for ${where}.` });
    } catch {
      setNotice({ text: `Copy ${row.name}'s entry into ${where}:`, json });
    }
  }, []);

  const changeRequest = useCallback((name, change) => {
    setRequests((r) => ({ ...r, [name]: { ...EMPTY_REQUEST, ...r[name], ...change } }));
  }, []);

  // A request to a plugin's route; anything but GET may change the plugin,
  // so it asks first.
  const handleSend = useCallback(async (name) => {
    const req = routeRequest(requests[name] || EMPTY_REQUEST);
    if (req.problem) {
      setError(`Request to ${name}: ${req.problem}`);
      return;
    }
    const shown = `${req.method} /api/plugins/${name}/${req.path}${req.query ? `?${req.query.replace(/^\?/, '')}` : ''}`;
    if (req.method !== 'GET' && !window.confirm(`${shown} may change the plugin's state. Send?`)) return;
    setBusy('Send');
    setError(null);
    const result = await executeApiCall('plugin-route', target, req.body, {
      pathParams: { name, path: req.path }, method: req.method, query: req.query,
    });
    setBusy(null);
    const answer = result?.ok
      ? { ok: true, ...routeAnswerText(result.payload?.result ?? result.rawText) }
      : { ok: false, text: errorOf(result), cut: false };
    changeRequest(name, { answer: { ...answer, request: shown } });
  }, [requests, target, changeRequest]);

  const toggleDetails = useCallback((name) => {
    setExpanded((e) => ({ ...e, [name]: !e[name] }));
  }, []);

  const openAdd = useCallback(() => {
    setFormFor((f) => (f?.mode === 'add' ? null : { mode: 'add' }));
    setForm({ name: '', url: '', settings: '', to: '' });
  }, []);

  const openEdit = useCallback((row) => {
    setFormFor({ mode: 'edit', name: row.name });
    setForm(formOf(row));
  }, []);

  const openCopy = useCallback((row) => {
    const targets = addTargets(instances, target, row);
    setFormFor({ mode: 'copy', name: row.name, targets });
    setForm(formOf(row, targets.find((t) => !t.has)?.target || ''));
  }, [instances, target]);

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
    const name = form.name.trim();
    let ok;
    if (editing) {
      ok = await run(`Edit ${formFor.name}`, 'plugin-edit', { url: form.url.trim(), settings }, { name: formFor.name });
    } else if (copying) {
      // The other instance's panel shows it through the push.
      const to = formFor.targets.find((t) => t.target === form.to);
      if (!to) {
        setError('Choose an instance to add to');
        return;
      }
      ok = await run(`Add ${name} to ${to.name}`, 'plugin-add', { name, url: form.url.trim(), settings }, undefined, to.target);
      if (ok) setNotice({ text: `Added ${name} to ${to.name}.` });
    } else {
      ok = await run(`Add ${name}`, 'plugin-add', { name, url: form.url.trim(), settings });
    }
    if (ok) {
      setFormFor(null);
      setForm({ name: '', url: '', settings: '', to: '' });
    }
  }, [form, formFor, editing, copying, run]);

  const rows = pluginRows(status);
  const showClaims = role === 'fsp';
  const columns = showClaims ? 5 : 4;
  const problems = rows.filter((r) => r.state !== 'healthy').map((r) => r.name);

  return (
    <div id="plugins-panel" style={{ marginBottom: '24px', padding: '16px', background: 'var(--bg-card)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
        <h3 style={{ margin: 0, fontSize: '16px' }}>
          <i className="fas fa-plug" style={{ marginRight: '8px' }} aria-hidden="true"></i>
          Plugins{rows.length ? ` (${rows.length})` : ''}
        </h3>
        <div style={{ display: 'flex', gap: '8px' }}>
          {problems.length > 0 && (
            <button type="button" id="plugins-retry-btn" className="btn-secondary" onClick={() => handleRetryAll(problems)} disabled={Boolean(busy)} title={`Reload ${problems.join(', ')}`}>
              Retry {problems.length === 1 ? '1 plugin' : `${problems.length} plugins`}
            </button>
          )}
          <button type="button" id="plugins-add-btn" className="btn-secondary" onClick={formFor ? () => setFormFor(null) : openAdd} disabled={!target}>
            {formFor ? 'Cancel' : 'Add plugin'}
          </button>
        </div>
      </div>

      {formFor && (
        <form onSubmit={handleSubmit} aria-label={editing ? `Edit ${formFor.name}` : copying ? `Add ${formFor.name} to another instance` : 'Add plugin'} style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '8px 12px', marginBottom: '12px' }}>
          {copying && (
            <select id="plugins-add-to" aria-label="Add to" value={form.to} onChange={(e) => setForm({ ...form, to: e.target.value })} required style={{ gridColumn: '1 / -1' }}>
              <option value="" disabled>{formFor.targets.length ? 'Choose an SO or FSP' : 'No other SO or FSP is connected'}</option>
              {formFor.targets.map((t) => (
                <option key={t.target} value={t.target} disabled={t.has}>
                  {t.name} ({t.role}, {t.target}){t.has ? ` - has ${formFor.name}` : ''}
                </option>
              ))}
            </select>
          )}
          <input id="plugins-add-name" placeholder="Name, e.g. io" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required disabled={editing} title={editing ? 'The name stays: a plugin with another name is another plugin' : undefined} />
          <input id="plugins-add-url" placeholder="URL, e.g. http://dr-panel:9000/plugin" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} required />
          <Suspense fallback={<div style={{ gridColumn: '1 / -1', minHeight: '48px', color: 'var(--text-muted)' }}>Loading the settings editor...</div>}>
            <JsonEditor id="plugins-add-settings" label="Settings (JSON)" placeholder='Settings (JSON, optional), e.g. {"write_inputs": false}' value={form.settings} onChange={setSettings} style={{ gridColumn: '1 / -1' }} />
          </Suspense>
          <small style={{ gridColumn: '1 / -1', color: 'var(--text-muted)' }}>
            {copying
              ? `The plugin's name is the one it describes itself with. ${formFor.targets.some((t) => t.role === 'SO') ? '' : 'It controls objects, so only FSPs are offered. '}The other instance's PLUGIN_ALLOWED_SOURCES applies (${SOURCES_HINT}); the plugin stays there until it restarts.`
              : editing
              ? `A new URL must be allowed by the instance's PLUGIN_ALLOWED_SOURCES (${SOURCES_HINT}); the settings replace all of them. If the plugin doesn't connect with them, it keeps its old URL and settings. The edit stays until the instance restarts; a lasting one goes in its plugin configuration.${showClaims ? ` ${CLAIMS_HINT}` : ''}`
              : `Only URLs allowed by the instance's PLUGIN_ALLOWED_SOURCES are accepted (${SOURCES_HINT}). An added plugin stays until the instance restarts; a lasting one goes in its plugin configuration.${showClaims ? ` ${CLAIMS_HINT}` : ''}`}
          </small>
          <div style={{ gridColumn: '1 / -1' }}>
            <button type="submit" id="plugins-add-submit" className="btn-primary" disabled={Boolean(busy)}>{editing ? 'Save' : copying ? 'Add to instance' : 'Add'}</button>
          </div>
        </form>
      )}

      {error && (
        <div role="alert" style={{ marginBottom: '12px', padding: '10px', borderRadius: '6px', fontSize: '13px', background: 'rgba(244, 67, 54, 0.15)', color: 'var(--danger-color)', border: '1px solid var(--danger-color)' }}>
          <i className="fas fa-exclamation-triangle" style={{ marginRight: '8px' }}></i>{error}
        </div>
      )}

      {notice && (
        <div role="status" style={{ marginBottom: '12px', padding: '10px', borderRadius: '6px', fontSize: '13px', border: '1px solid var(--border-color)', display: 'flex', gap: '8px', alignItems: 'flex-start' }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            {notice.text}
            {notice.json && <pre data-testid="plugins-config-entry" style={{ margin: '8px 0 0', fontSize: '12px', userSelect: 'all', overflowX: 'auto' }}>{notice.json}</pre>}
          </div>
          <button type="button" className="btn-icon" title="Dismiss" onClick={() => setNotice(null)}>
            <i className="fas fa-times"></i>
          </button>
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
              const open = Boolean(expanded[row.name]);
              return (
                <React.Fragment key={row.name}>
                <tr data-testid={`plugin-row-${row.name}`}>
                  <td>{row.name}{row.version && <span style={{ color: 'var(--text-muted)' }}> {row.version}</span>}</td>
                  <td>
                    <span style={{ color: st.color, fontWeight: 600 }}>{st.label}</span>
                    {row.error && <div style={{ color: 'var(--text-muted)', fontSize: '12px', maxWidth: '360px', overflowWrap: 'anywhere' }}>{row.error}</div>}
                  </td>
                  <td style={{ fontFamily: 'monospace', fontSize: '12px', overflowWrap: 'anywhere' }}>{row.url || '-'}</td>
                  {showClaims && <td title={row.claims.join('\n')}>{row.claims.length || '-'}</td>}
                  <td>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button type="button" className="btn-icon" title={`Details ${row.name}`} aria-expanded={open} onClick={() => toggleDetails(row.name)}>
                        <i className={`fas fa-chevron-${open ? 'up' : 'down'}`}></i>
                      </button>
                      <button type="button" className="btn-icon" title={row.definition ? `Edit ${row.name}` : `Edit ${row.name}: this instance doesn't list plugin definitions`} disabled={Boolean(busy) || !row.definition} onClick={() => openEdit(row)}>
                        <i className="fas fa-pen"></i>
                      </button>
                      <button type="button" className="btn-icon" title={row.definition ? `Add ${row.name} to another SO or FSP` : `Add ${row.name} to another SO or FSP: this instance doesn't list plugin definitions`} disabled={Boolean(busy) || !row.definition} onClick={() => openCopy(row)}>
                        <i className="fas fa-share-square"></i>
                      </button>
                      <button type="button" className="btn-icon" title={row.definition ? `Copy ${row.name} as configuration` : `Copy ${row.name} as configuration: this instance doesn't list plugin definitions`} disabled={!row.definition} onClick={() => handleCopy(row)}>
                        <i className="fas fa-copy"></i>
                      </button>
                      <button type="button" className="btn-icon" title={reloadLabel(row)} disabled={Boolean(busy)} onClick={() => run(reloadLabel(row), 'plugin-reload', null, { name: row.name })}>
                        <i className="fas fa-sync-alt"></i>
                      </button>
                      <button type="button" className="btn-icon" title={`Remove ${row.name}`} disabled={Boolean(busy)} onClick={() => handleRemove(row.name)}>
                        <i className="fas fa-trash"></i>
                      </button>
                    </div>
                  </td>
                </tr>
                {open && (
                  <tr>
                    <td colSpan={columns} style={{ background: 'var(--bg-hover)' }}>
                      <PluginDetails row={row} showClaims={showClaims} />
                      {row.routes && (
                        <PluginRequest
                          row={row}
                          request={requests[row.name] || EMPTY_REQUEST}
                          onChange={(change) => changeRequest(row.name, change)}
                          onSend={() => handleSend(row.name)}
                          busy={busy}
                        />
                      )}
                    </td>
                  </tr>
                )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default PluginsPanel;
