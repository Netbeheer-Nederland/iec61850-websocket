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

// TLSConfigModal.jsx
import React, { useState, useEffect, useCallback } from 'react';
import { useRuntimeFlag } from '../hooks/useRuntimeFlag';

function parsePythonDictString(pythonStr) {
  if (!pythonStr || typeof pythonStr !== 'string') return pythonStr;
  try {
    const jsonStr = pythonStr
      .replace(/'/g, '"')
      .replace(/True/g, 'true')
      .replace(/False/g, 'false')
      .replace(/None/g, 'null');
    return JSON.parse(jsonStr);
  } catch (e) {
    console.log('Warning: Could not parse Python dict string as JSON:', e);
    return pythonStr;
  }
}

const RECONFIG_CONNECTION_API = {
  id: 'reconfig-connection',
  label: 'POST /api/reconfig-connection',
  method: 'POST',
  path: '/api/reconfig-connection'
};

const TLS_CONFIG_API = {
  id: 'tls-config',
  label: 'POST /api/connections/tls-config',
  method: 'POST',
  path: '/api/connections/tls-config'
};

// The FSP/SO instance's own *runtime* TLS config (GET /api/tls-config on
// its own service, port 5001/5002) - distinct from TLS_CONFIG_API above,
// which is the BFF's own /api/connections/tls-config for persisting to
// connections.json. Both need to go through the BFF's /api/execute proxy
// (see executeApiCall below) - connection.host is a Docker-internal
// service hostname (e.g. "rti-so"), never reachable directly from the
// browser.
const RUNTIME_TLS_CONFIG_API = {
  id: 'runtime-tls-config',
  label: 'GET /api/tls-config',
  method: 'GET',
  path: '/api/tls-config'
};

// "1.2"/"1.3" (runtime) or "TLSv1_2"/"TLSv1_3" (connections.json) -> the
// select's "1.2"/"1.3"; null when there's nothing usable.
function normalizeTlsVersion(version) {
  const v = String(version ?? '');
  if (/1[._]3/.test(v)) return '1.3';
  if (/1[._]2/.test(v)) return '1.2';
  return null;
}

function getApiById(id) {
  if (id === 'reconfig-connection') return RECONFIG_CONNECTION_API;
  if (id === 'tls-config') return TLS_CONFIG_API;
  if (id === 'runtime-tls-config') return RUNTIME_TLS_CONFIG_API;
  return null;
}

// Whether the instance at `target` (e.g. "rti-so:5002") actually has TLS
// enabled right now - the same runtime source this modal's form loads from,
// not the TLS block persisted in connections.json (see useRuntimeFlag).
function useRuntimeTlsEnabled(target) {
  return useRuntimeFlag('runtime-tls-config', 'enable_tls', target);
}

const TLSConfigModal = ({
  isOpen,
  onClose,
  connection,
  bffBaseUrl = 'http://localhost:5000',
  onSuccess = () => {},
  onError = () => {}, 
  wsHost,   
  wsPort     
}) => {
  const [enableTLS, setEnableTLS] = useState(false);
  const [tlsVersion, setTlsVersion] = useState('1.2');
  const [serverKey, setServerKey] = useState('');
  const [serverCert, setServerCert] = useState('');
  const [caCert, setCaCert] = useState('');
  const [submitting, setSubmitting] = useState(false);
  // Initialize wsMode from connection if available
  const [wsMode, setWsMode] = useState(() => {
    if (connection?.ws_mode) {
      const mode = String(connection.ws_mode).toLowerCase();
      if (mode === 'passive' || mode === 'active') return mode;
    }
    // Default based on connection type
    if (connection?.type === 'RTI-SO') return 'active';
    if (connection?.properties_info?.properties?.ws_mode) {
      const mode = String(connection.properties_info.properties.ws_mode).toLowerCase();
      if (mode === 'passive' || mode === 'active') return mode;
    }
    return 'passive';
  });

  const isServerMode = wsMode === 'passive' || wsMode === 'Passive';
  const isClientMode = wsMode === 'active' || wsMode === 'Active';

  // Visible inline in the modal itself (see the render below) - not just
  // bubbled to the parent page's onError. The parent's message banner
  // renders behind this modal's own full-screen overlay (position: fixed,
  // zIndex: 1000) while the modal stays open on error, so it was
  // invisible until the user closed the modal and happened to look back -
  // matches the pattern ControlModal.jsx already uses (local result state
  // shown inline, in addition to bubbling to onError).
  const [localError, setLocalError] = useState(null);

  // Calls go through the BFF's /api/execute proxy, never a direct fetch to
  // connection.host:connection.port - that's a Docker-internal service
  // hostname (e.g. "rti-so"), resolvable from other containers but never
  // from the actual browser, so a direct fetch always fails there with a
  // generic network error.
  const executeApiCall = useCallback(async (api, targetValue, bodyOverride = null) => {
    try {
      const url = `${bffBaseUrl}/api/execute`;
      const payload = { target: targetValue, method: api.method || 'GET', path: api.path || '/' };
      if (bodyOverride && Object.keys(bodyOverride).length > 0) payload.body = bodyOverride;
      const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      const rawText = await response.text();
      let parsedPayload = null;
      try { parsedPayload = JSON.parse(rawText); } catch (error) {}
      return { ok: response.ok, status: response.status, payload: parsedPayload, rawText };
    } catch (error) {
      return { ok: false, status: 0, payload: null, error: error.message };
    }
  }, [bffBaseUrl]);

  // Load the form: the saved settings (connection.TLS, from the BFF's
  // connections.json) first, then the instance's runtime GET /api/tls-config
  // on top. The runtime decides whether TLS is actually on right now; while
  // it's off it only reports defaults (e.g. tls_version "1.2"), so the saved
  // version/certificates are kept rather than lost.
  useEffect(() => {
    const loadTlsConfig = async () => {
      if (!isOpen || !connection) return;

      const applyFields = (src) => {
        const version = normalizeTlsVersion(src.tls_version);
        if (version) setTlsVersion(version);
        if (src.server_key) setServerKey(src.server_key);
        if (src.server_cert) setServerCert(src.server_cert);
        if (src.server_ca) setCaCert(src.server_ca);
      };

      const stored = connection.TLS || {};
      setEnableTLS(Boolean(stored.enable_tls));
      applyFields(stored);

      const host = connection.host || 'localhost';
      const port = connection.port;
      if (!host || !port) {
        console.warn('Cannot fetch TLS config: missing host or port');
        return;
      }

      try {
        const result = await executeApiCall(RUNTIME_TLS_CONFIG_API, `${host}:${port}`);
        if (!result.ok) return;
        // /api/execute wraps the instance's own response under `result`.
        const data = result.payload?.result ?? result.payload ?? {};
        if (data.enable_tls !== undefined) setEnableTLS(Boolean(data.enable_tls));
        if (data.enable_tls) applyFields(data);
        if (data.ws_mode) setWsMode(data.ws_mode);
      } catch (error) {
        console.warn('Failed to fetch TLS config from server endpoint:', error);
      }
    };

    loadTlsConfig();
  }, [isOpen, connection, wsHost, executeApiCall]);

  // Clear any previous error whenever the modal is (re)opened for a
  // possibly-different connection, so a stale error from a prior attempt
  // doesn't linger.
  useEffect(() => {
    if (isOpen) setLocalError(null);
  }, [isOpen, connection]);

  const handleFileUpload = useCallback((e, fieldName) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      const content = e.target.result;
      switch (fieldName) {
        case 'serverKey': setServerKey(content); break;
        case 'serverCert': setServerCert(content); break;
        case 'caCert': setCaCert(content); break;
      }
    };
    reader.readAsText(file);
  }, []);

  const buildConfig = useCallback(() => {
    if (!connection) return null;
    return {
      host: wsHost,
      port: wsPort,
      connection_name: connection.name,
      enable_tls: enableTLS,
      tls_version: tlsVersion === '1.2' ? 'TLSv1_2' : 'TLSv1_3',
      ws_mode: wsMode,
      ...(isServerMode ? { server_key: serverKey, server_cert: serverCert, server_ca: null } : {}),
      ...(isClientMode ? { server_key: null, server_cert: null, server_ca: caCert } : {})
    };
  }, [connection, enableTLS, tlsVersion, wsMode, isServerMode, isClientMode, serverKey, serverCert, caCert]);

  const handleSubmit = useCallback(async (e) => {
    e.preventDefault();
    setLocalError(null);
    if (!connection) {
      const msg = 'Please select a connection';
      setLocalError(msg);
      onError?.(msg);
      return;
    }
    const config = buildConfig();
    if (!config) return;

    setSubmitting(true);
    // Only the actual network calls below are inside this try/catch - it
    // determines whether the save itself succeeded or failed. onSuccess/
    // onClose are called *after*, outside this boundary, so a bug in a
    // parent page's onSuccess handler (e.g. calling something out of
    // scope) can't get caught here and mislabeled as "Failed to save" when
    // the save actually went through fine - the exact kind of misleading,
    // inconsistent error this change is meant to fix, not reproduce.
    let outcome;
    try {
      // Call BFF's /api/connections/tls-config endpoint directly - this one
      // genuinely is a same-origin-reachable BFF endpoint, not a container
      // hostname, so a direct fetch is fine here.
      const bffUrl = `${bffBaseUrl}/api/connections/tls-config`;
      const bffResponse = await fetch(bffUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
      });
      const bffRawText = await bffResponse.text();
      let bffPayload = null;
      try { bffPayload = JSON.parse(bffRawText); } catch (error) {}

      if (!bffResponse.ok) {
        outcome = { ok: false, message: `Failed to save TLS config to BFF: ${bffPayload?.error || bffRawText || 'Unknown error'}` };
      } else {
        // Also reconfigure the server's runtime TLS config, through the
        // BFF's /api/execute proxy - connection.host is a Docker-internal
        // service hostname (e.g. "rti-so"), not reachable directly from the
        // browser. A raw fetch() here always failed with a generic network
        // error, regardless of whether the BFF save above succeeded.
        const host = connection.host || 'localhost';
        const port = connection.port;
        const reconfigureResult = await executeApiCall(RECONFIG_CONNECTION_API, `${host}:${port}`, config);

        // A disconnected FSP only stores the setting ("saved") - it takes
        // effect on the next Connect rather than dialing out right away.
        outcome = reconfigureResult.ok
          ? { ok: true, deferred: reconfigureResult.payload?.result?.status === 'saved' }
          : {
              ok: false,
              partial: true,
              message: `TLS config saved for ${connection.name}, but the runtime update failed: `
                + `${reconfigureResult.payload?.error || reconfigureResult.error || reconfigureResult.rawText || 'Unknown error'}`,
            };
      }
    } catch (error) {
      outcome = { ok: false, message: `Failed to save TLS config: ${error.message}` };
    } finally {
      setSubmitting(false);
    }

    if (outcome.ok) {
      onSuccess?.(outcome.deferred
        ? `TLS config saved for ${connection.name} - applies on next Connect`
        : `TLS config saved and applied for ${connection.name}`);
      onClose();
    } else {
      setLocalError(outcome.message);
      onError?.(outcome.message);
      // Partial failure (BFF save succeeded, runtime update didn't) keeps
      // the modal open too, same as a full failure - closing here would
      // hide it behind the parent page's banner again, the exact
      // visibility problem this change fixes.
    }
  }, [connection, enableTLS, buildConfig, bffBaseUrl, executeApiCall, onSuccess, onError, onClose, wsHost]);

  if (!isOpen || !connection) return null;

  const styles = {
    modal: {
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      background: 'rgba(0,0,0,0.7)', zIndex: 1000,
      display: 'flex', justifyContent: 'center', alignItems: 'center'
    },
    modalContent: {
      background: 'var(--bg-card)', borderRadius: '12px',
      width: '90%', maxWidth: '600px', maxHeight: '90vh', overflowY: 'auto',
      border: '1px solid var(--border-color)', boxShadow: '0 4px 20px rgba(0,0,0,0.2)'
    },
    modalHeader: {
      padding: '20px 24px', borderBottom: '1px solid var(--border-color)',
      display: 'flex', justifyContent: 'space-between', alignItems: 'center'
    },
    modalBody: { padding: '24px' },
    modalFooter: {
      padding: '16px 24px', borderTop: '1px solid var(--border-color)',
      display: 'flex', justifyContent: 'flex-end', gap: '12px'
    },
    formGroup: { marginBottom: '20px' },
    checkboxLabel: {
      display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer',
      color: 'var(--text-primary)', fontSize: '14px'
    },
    checkboxInput: { width: '18px', height: '18px', accentColor: 'var(--primary-color)' },
    label: { display: 'block', marginBottom: '8px', fontWeight: '500', color: 'var(--text-primary)' },
    select: {
      width: '100%', padding: '10px 12px', borderRadius: '8px',
      border: '1px solid var(--border-color)', background: 'var(--bg-hover)',
      color: 'var(--text-primary)', fontSize: '14px'
    },
    input: {
      width: '100%', padding: '10px 12px', borderRadius: '8px',
      border: '1px solid var(--border-color)', background: 'var(--bg-hover)',
      color: 'var(--text-primary)', fontSize: '14px', marginBottom: '10px'
    },
    textarea: {
      width: '100%', padding: '10px 12px', borderRadius: '8px',
      border: '1px solid var(--border-color)', background: 'var(--bg-hover)',
      color: 'var(--text-primary)', fontSize: '14px', fontFamily: 'monospace',
      minHeight: '100px', display: 'block'
    },
    button: { padding: '10px 20px', borderRadius: '8px', fontWeight: '600', cursor: 'pointer' },
    infoBox: {
      margin: '16px 0', padding: '12px', background: 'var(--bg-hover)',
      borderRadius: '6px', fontSize: '13px', border: '1px solid var(--border-light)'
    },
    fileInputGroup: { display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '10px' },
    // Not var(--danger-bg) - that token isn't actually defined anywhere in
    // styles.css (same latent issue ActionLogPanel.jsx hit) - a real color
    // via --danger-color at low opacity instead.
    errorBox: {
      margin: '16px 0', padding: '12px', borderRadius: '6px', fontSize: '13px',
      background: 'rgba(244, 67, 54, 0.15)', color: 'var(--danger-color)',
      border: '1px solid var(--danger-color)'
    }
  };

  return (
    <div style={styles.modal}>
      <div style={styles.modalContent}>
        <div style={styles.modalHeader}>
          <h2 style={{ margin: 0, color: 'var(--text-primary)' }}>
            <i className="fas fa-shield-alt" style={{ marginRight: '8px' }}></i>
            TLS Configuration - {connection.name}
          </h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', fontSize: '24px', cursor: 'pointer', color: 'var(--text-muted)' }}>
            ×
          </button>
        </div>

        <div style={styles.modalBody}>
          <form onSubmit={handleSubmit}>
            <div style={styles.formGroup}>
              <label style={styles.checkboxLabel}>
                <input type="checkbox" id="tls-enable" checked={enableTLS} onChange={(e) => setEnableTLS(e.target.checked)} style={styles.checkboxInput} />
                Enable TLS (WSS)
              </label>
            </div>

            <div style={styles.formGroup}>
              <label style={styles.label}>TLS Version:</label>
              <select id="tls-version" value={tlsVersion} onChange={(e) => setTlsVersion(e.target.value)} style={styles.select}>
                <option value="1.2">TLS 1.2</option>
                <option value="1.3">TLS 1.3</option>
              </select>
            </div>

            {isServerMode && (
              <>
                <div style={styles.formGroup}>
                  <label style={styles.label}>Server Private Key (PEM):</label>
                  <div style={styles.fileInputGroup}>
                    <input type="file" id="tls-private-key" accept=".pem,.key" onChange={(e) => handleFileUpload(e, 'serverKey')} />
                  </div>
                  <textarea id="tls-key-content" value={serverKey} onChange={(e) => setServerKey(e.target.value)} placeholder="-----BEGIN PRIVATE KEY-----..." style={styles.textarea} />
                </div>
                <div style={styles.formGroup}>
                  <label style={styles.label}>Server Certificate (PEM):</label>
                  <div style={styles.fileInputGroup}>
                    <input type="file" id="tls-server-cert" accept=".pem,.crt,.cer" onChange={(e) => handleFileUpload(e, 'serverCert')} />
                  </div>
                  <textarea id="tls-server-cert-content" value={serverCert} onChange={(e) => setServerCert(e.target.value)} placeholder="-----BEGIN CERTIFICATE-----..." style={styles.textarea} />
                </div>
              </>
            )}

            {isClientMode && (
              <div style={styles.formGroup}>
                <label style={styles.label}>Server CA Certificate (PEM):</label>
                <div style={styles.fileInputGroup}>
                  <input type="file" id="tls-ca-cert" accept=".pem,.crt,.cer" onChange={(e) => handleFileUpload(e, 'caCert')} />
                </div>
                <textarea id="tls-ca-cert-content" value={caCert} onChange={(e) => setCaCert(e.target.value)} placeholder="-----BEGIN CERTIFICATE-----..." style={styles.textarea} />
              </div>
            )}

            <div style={styles.infoBox}>
              <strong>Mode:</strong> {isServerMode ? 'Server (Passive)' : 'Client (Active)'}
              <br />
              <span style={{ color: 'var(--text-muted)' }}>
                {isServerMode ? 'Configure server certificates for incoming connections' : 'Configure CA certificate to validate server'}
              </span>
            </div>

            {localError && (
              <div style={styles.errorBox}>
                <i className="fas fa-exclamation-triangle" style={{ marginRight: '8px' }}></i>
                {localError}
              </div>
            )}

            <div style={styles.modalFooter}>
              <button type="button" className="btn-secondary" onClick={onClose} style={styles.button} disabled={submitting}>Cancel</button>
              <button type="submit" className="btn-primary" style={styles.button} disabled={submitting}>
                {submitting ? 'Saving...' : 'Save'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};

export default TLSConfigModal;
export { parsePythonDictString, getApiById, RECONFIG_CONNECTION_API, useRuntimeTlsEnabled };