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

// OAuthConfigModal.jsx
import React, { useState, useEffect, useCallback } from 'react';
import { executeApiCall } from '../services/apiService';
import { useRuntimeFlag } from '../hooks/useRuntimeFlag';

// Whether the instance at `target` (e.g. "rti-so:5002") has OAuth turned on
// right now, per its own runtime GET /api/oauth-status.
function useRuntimeOAuthEnabled(target) {
  return useRuntimeFlag('oauth-status', 'enable_oauth', target);
}

// wsMode: the page's own role ('passive' on the SO page, 'active' on the FSP
// page) - more reliable than the connection record's ws_mode, which older or
// hand-registered records don't always carry.
const isPassiveMode = (connection, wsMode) =>
  String(wsMode || connection?.ws_mode || '').toLowerCase() === 'passive';

// The instance's /reconfig-oauth body for its saved OAuth block (the
// connection's `OAuth` in connections.json) - shared by this modal's Save
// and the FSP page's Connect, which re-applies a saved config.
function oauthRequestBody(connection, oauth, wsMode) {
  const passive = isPassiveMode(connection, wsMode);
  return {
    connection_name: connection.name,
    enable_oauth: Boolean(oauth.enable_oauth),
    ws_mode: passive ? 'passive' : 'active',
    idp_server: oauth.idp_server || null,
    realm: oauth.realm || null,
    ca_certificate: oauth.auth_server_ca || null,
    ...(passive
      ? {
          certificate_endpoint_url: oauth.certificate_endpoint || null,
          token_issuer_url: oauth.token_issuer || null,
        }
      : {
          token_endpoint_url: oauth.token_endpoint || null,
          client_id: oauth.client_id || null,
          client_secret: oauth.client_secret || null,
          enable_token_refresh: Boolean(oauth.enable_token_refresh),
        }),
  };
}

// OAuth settings for one RTI-SO (passive: validates incoming tokens) or
// RTI-FSP (active: fetches a token to present) - moved out of the Setup
// form into its own dialog, next to TLS Config. Save stores them in the
// BFF's connections.json, then always passes them to the instance: a
// disconnected FSP turns OAuth off right away but keeps "on" for its next
// Connect (it answers status "saved"), instead of the setting stopping at the
// BFF while the FSP stays on.
const OAuthConfigModal = ({
  isOpen,
  onClose,
  connection,
  wsMode,
  connections = [],
  target,
  runtimeBody = {},
  bffBaseUrl = 'http://localhost:5000',
  onSuccess = () => {},
  onError = () => {},
}) => {
  const [enableOAuth, setEnableOAuth] = useState(false);
  const [idpServer, setIdpServer] = useState('');
  const [realm, setRealm] = useState('');
  const [certificateEndpoint, setCertificateEndpoint] = useState('');
  const [tokenIssuer, setTokenIssuer] = useState('');
  const [tokenEndpoint, setTokenEndpoint] = useState('');
  const [clientId, setClientId] = useState('');
  const [clientSecret, setClientSecret] = useState('');
  const [enableTokenRefresh, setEnableTokenRefresh] = useState(false);
  const [authServerCa, setAuthServerCa] = useState('');
  const [discovering, setDiscovering] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  // Shown inline: the parent page's message banner sits behind this
  // modal's overlay (same reasoning as TLSConfigModal's localError).
  const [localError, setLocalError] = useState(null);

  const idpServers = connections.filter(c => c.type === 'IDP-Server');
  const passive = isPassiveMode(connection, wsMode);

  // Load the saved settings, then take the enable flag from the running
  // instance - the same "saved fields, live on/off" split as TLS Config.
  useEffect(() => {
    if (!isOpen || !connection) return;
    const saved = connection.OAuth || {};
    setEnableOAuth(Boolean(saved.enable_oauth));
    setIdpServer(saved.idp_server || '');
    setRealm(saved.realm || '');
    setCertificateEndpoint(saved.certificate_endpoint || '');
    setTokenIssuer(saved.token_issuer || '');
    setTokenEndpoint(saved.token_endpoint || '');
    setClientId(saved.client_id || '');
    setClientSecret(saved.client_secret || '');
    setEnableTokenRefresh(Boolean(saved.enable_token_refresh));
    setAuthServerCa(saved.auth_server_ca || '');
    setLocalError(null);

    if (!target) return;
    executeApiCall('oauth-status', target).then((result) => {
      const live = result?.ok ? (result.payload?.result?.enable_oauth ?? result.payload?.enable_oauth) : undefined;
      if (live !== undefined) setEnableOAuth(Boolean(live));
    }).catch(() => {});
  }, [isOpen, connection, target]);

  // Fill the endpoints from the realm's OIDC discovery document (read by
  // the BFF - the IDP's address is usually only reachable from there).
  const discoverEndpoints = useCallback(async () => {
    if (!idpServer || !realm) {
      setLocalError('Select an IDP server and enter a realm first');
      return;
    }
    setDiscovering(true);
    setLocalError(null);
    try {
      const params = new URLSearchParams({ idp_server: idpServer, realm });
      const response = await fetch(`${bffBaseUrl}/api/idp/discovery?${params}`);
      const data = await response.json();
      if (!data.ok) {
        setLocalError(data.error || 'Could not read the realm from the IDP server');
        return;
      }
      setCertificateEndpoint(data.certificate_endpoint || '');
      setTokenIssuer(data.issuer || '');
      setTokenEndpoint(data.token_endpoint || '');
    } catch (error) {
      setLocalError(`Could not read the realm from the IDP server: ${error.message}`);
    } finally {
      setDiscovering(false);
    }
  }, [bffBaseUrl, idpServer, realm]);

  const handleFileUpload = useCallback((e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => setAuthServerCa(ev.target.result);
    reader.readAsText(file);
  }, []);

  const fail = useCallback((msg) => {
    setLocalError(msg);
    onError?.(msg);
  }, [onError]);

  const handleSubmit = useCallback(async (e) => {
    e.preventDefault();
    setLocalError(null);

    if (enableOAuth) {
      const idp = idpServers.find(s => s.name === idpServer);
      if (idp && idp.status !== 'connected') {
        fail('IDP server unavailable');
        return;
      }
      const missing = passive
        ? !certificateEndpoint || !tokenIssuer
        : !tokenEndpoint || !clientId;
      if (missing) {
        fail(passive
          ? 'Certificate endpoint and token issuer are required - use "Discover endpoints"'
          : 'Token endpoint and client ID are required - use "Discover endpoints"');
        return;
      }
    }

    const body = oauthRequestBody(connection, {
      enable_oauth: enableOAuth,
      idp_server: idpServer,
      realm,
      auth_server_ca: authServerCa.trim(),
      certificate_endpoint: certificateEndpoint,
      token_issuer: tokenIssuer,
      token_endpoint: tokenEndpoint,
      client_id: clientId,
      client_secret: clientSecret,
      enable_token_refresh: enableTokenRefresh,
    }, wsMode);

    setSubmitting(true);
    let outcome;
    try {
      const saved = await fetch(`${bffBaseUrl}/api/connections/oauth-config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const savedPayload = await saved.json().catch(() => null);
      if (!saved.ok || savedPayload?.ok === false) {
        outcome = { ok: false, message: `Failed to save OAuth config: ${savedPayload?.message || savedPayload?.detail || saved.statusText || 'Unknown error'}` };
      } else {
        const applied = await executeApiCall('reconfig-oauth', target, { ...body, ...runtimeBody });
        const deferred = enableOAuth && applied?.payload?.result?.status === 'saved';
        outcome = !applied?.ok
          ? {
              ok: false,
              message: `OAuth config saved for ${connection.name}, but applying it failed: `
                + `${applied?.payload?.detail || applied?.payload?.error || applied?.error || 'Unknown error'}`,
            }
          : deferred
            ? { ok: true, message: `OAuth config saved for ${connection.name} - applies on next Connect` }
            : { ok: true, message: `OAuth ${enableOAuth ? 'enabled' : 'disabled'} for ${connection.name}` };
      }
    } catch (error) {
      outcome = { ok: false, message: `Failed to save OAuth config: ${error.message}` };
    } finally {
      setSubmitting(false);
    }

    // Outside the try: a bug in the parent's onSuccess mustn't be reported
    // as a failed save (same as TLSConfigModal).
    if (outcome.ok) {
      onSuccess?.(outcome.message);
      onClose();
    } else {
      fail(outcome.message);
    }
  }, [enableOAuth, idpServers, idpServer, passive, certificateEndpoint, tokenIssuer, tokenEndpoint,
      clientId, clientSecret, enableTokenRefresh, authServerCa, realm, connection, bffBaseUrl,
      target, runtimeBody, wsMode, onSuccess, onClose, fail]);

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
    row: { display: 'flex', gap: '12px', alignItems: 'flex-end' },
    checkboxLabel: {
      display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer',
      color: 'var(--text-primary)', fontSize: '14px'
    },
    checkboxInput: { width: '18px', height: '18px', accentColor: 'var(--primary-color)' },
    label: { display: 'block', marginBottom: '8px', fontWeight: '500', color: 'var(--text-primary)' },
    input: {
      width: '100%', padding: '10px 12px', borderRadius: '8px',
      border: '1px solid var(--border-color)', background: 'var(--bg-hover)',
      color: 'var(--text-primary)', fontSize: '14px'
    },
    hint: { display: 'block', marginTop: '6px', color: 'var(--text-muted)', fontSize: '12px' },
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
    // Not var(--danger-bg) - that token isn't defined in styles.css.
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
            <i className="fas fa-key" style={{ marginRight: '8px' }}></i>
            OAuth Configuration - {connection.name}
          </h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', fontSize: '24px', cursor: 'pointer', color: 'var(--text-muted)' }}>
            ×
          </button>
        </div>

        <div style={styles.modalBody}>
          <form onSubmit={handleSubmit}>
            <div style={styles.formGroup}>
              <label style={styles.checkboxLabel}>
                <input type="checkbox" id="oauth-enable" checked={enableOAuth} onChange={(e) => setEnableOAuth(e.target.checked)} style={styles.checkboxInput} />
                Enable OAuth 2.0
              </label>
            </div>

            <div style={styles.formGroup}>
              <label htmlFor="oauth-idp-server" style={styles.label}>IDP Server</label>
              <select id="oauth-idp-server" value={idpServer} onChange={(e) => setIdpServer(e.target.value)} style={styles.input}>
                <option value="">Select an IDP Server...</option>
                {idpServers.map(server => (
                  <option key={server.name} value={server.name}>{server.name}</option>
                ))}
              </select>
              <small style={styles.hint}>Identity provider registered in Setup (type IDP-Server).</small>
            </div>

            <div style={styles.formGroup}>
              <label htmlFor="oauth-realm" style={styles.label}>Realm</label>
              <div style={styles.row}>
                <input type="text" id="oauth-realm" value={realm} onChange={(e) => setRealm(e.target.value)} placeholder="e.g., iec61850-test" style={styles.input} />
                <button type="button" id="oauth-discover" className="btn-secondary" onClick={discoverEndpoints} disabled={discovering} style={{ ...styles.button, whiteSpace: 'nowrap' }}>
                  {discovering ? 'Discovering...' : 'Discover endpoints'}
                </button>
              </div>
              <small style={styles.hint}>Fills the fields below from the realm's OIDC discovery document.</small>
            </div>

            {passive ? (
              <>
                <div style={styles.formGroup}>
                  <label htmlFor="oauth-cert-url" style={styles.label}>Certificate Endpoint (JWKS)</label>
                  <input type="text" id="oauth-cert-url" value={certificateEndpoint} onChange={(e) => setCertificateEndpoint(e.target.value)} style={styles.input} />
                  <small style={styles.hint}>Signing keys incoming tokens are verified against.</small>
                </div>
                <div style={styles.formGroup}>
                  <label htmlFor="oauth-issuer-url" style={styles.label}>Token Issuer</label>
                  <input type="text" id="oauth-issuer-url" value={tokenIssuer} onChange={(e) => setTokenIssuer(e.target.value)} style={styles.input} />
                  <small style={styles.hint}>Must match the tokens' "iss" claim exactly.</small>
                </div>
              </>
            ) : (
              <>
                <div style={styles.formGroup}>
                  <label htmlFor="oauth-token-url" style={styles.label}>Token Endpoint</label>
                  <input type="text" id="oauth-token-url" value={tokenEndpoint} onChange={(e) => setTokenEndpoint(e.target.value)} style={styles.input} />
                  <small style={styles.hint}>Where this FSP requests its access token.</small>
                </div>
                <div style={styles.formGroup}>
                  <label htmlFor="oauth-client-id" style={styles.label}>Client ID</label>
                  <input type="text" id="oauth-client-id" value={clientId} onChange={(e) => setClientId(e.target.value)} placeholder="e.g., ws-client" style={styles.input} />
                </div>
                <div style={styles.formGroup}>
                  <label htmlFor="oauth-client-secret" style={styles.label}>Client Secret</label>
                  <input type="password" id="oauth-client-secret" value={clientSecret} onChange={(e) => setClientSecret(e.target.value)} style={styles.input} />
                </div>
                <div style={styles.formGroup}>
                  <label style={styles.checkboxLabel}>
                    <input type="checkbox" id="oauth-enable-refresh" checked={enableTokenRefresh} onChange={(e) => setEnableTokenRefresh(e.target.checked)} style={styles.checkboxInput} />
                    Enable Token Refresh
                  </label>
                </div>
              </>
            )}

            <div style={styles.formGroup}>
              <label htmlFor="oauth-ca-content" style={styles.label}>Auth Server CA (PEM)</label>
              <div style={styles.fileInputGroup}>
                <input type="file" id="oauth-ca-file" accept=".pem,.crt,.cer" onChange={handleFileUpload} />
              </div>
              <textarea id="oauth-ca-content" value={authServerCa} onChange={(e) => setAuthServerCa(e.target.value)} placeholder="-----BEGIN CERTIFICATE-----..." style={styles.textarea} />
              <small style={styles.hint}>Only needed when the IDP is reached over HTTPS with a private CA.</small>
            </div>

            <div style={styles.infoBox}>
              <strong>Mode:</strong> {passive ? 'Server (Passive)' : 'Client (Active)'}
              <br />
              <span style={{ color: 'var(--text-muted)' }}>
                {passive ? 'Validates the access token presented by connecting FSPs' : 'Presents an access token when connecting to the SO'}
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

export default OAuthConfigModal;
export { useRuntimeOAuthEnabled, oauthRequestBody };
