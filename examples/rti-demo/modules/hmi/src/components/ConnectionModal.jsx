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

import React, { useState, useEffect } from 'react';

function ConnectionModal({
  showModal,
  onClose,
  currentConnection,
  formData,
  onFormChange,
  onSave
}) {
  const [submitting, setSubmitting] = useState(false);

  const handleInputChange = (e) => {
    const { id, value, type } = e.target;
    onFormChange(prev => ({
      ...prev,
      [id]: type === 'number' ? parseInt(value) : value
    }));
  };

  // Sync ACSI and ws_mode when type changes or modal opens
  const syncAcsiAndWsMode = (type, acsi, ws_mode) => {
    if (type === 'RTI-SO' && (acsi !== 'client' || ws_mode !== 'passive')) {
      onFormChange(prev => ({
        ...prev,
        acsi: 'client',
        ws_mode: 'passive'
      }));
    } else if (type === 'RTI-FSP' && (acsi !== 'server' || ws_mode !== 'active')) {
      onFormChange(prev => ({
        ...prev,
        acsi: 'server',
        ws_mode: 'active'
      }));
    }
  };

  useEffect(() => {
    const needsSync = (formData.type === 'RTI-SO' && (formData.acsi !== 'client' || formData.ws_mode !== 'passive')) ||
                     (formData.type === 'RTI-FSP' && (formData.acsi !== 'server' || formData.ws_mode !== 'active'));
    if (needsSync) {
      syncAcsiAndWsMode(formData.type, formData.acsi, formData.ws_mode);
    }
  }, [formData.type, formData.acsi, formData.ws_mode]);

  const handleTypeChange = (e) => {
    const { value } = e.target;
    let newAcsi = formData.acsi;
    let newWsMode = formData.ws_mode;
    
    if (value === 'RTI-SO') {
      newAcsi = 'client';
      newWsMode = 'passive';
    } else if (value === 'RTI-FSP') {
      newAcsi = 'server';
      newWsMode = 'active';
    } else if (value === 'IDP-Server') {
      newAcsi = '';
      newWsMode = '';
    }
    
    onFormChange(prev => ({
      ...prev,
      type: value,
      acsi: newAcsi,
      ws_mode: newWsMode
    }));
  };

  const handleSave = async () => {
    setSubmitting(true);
    try {
      await onSave();
    } finally {
      setSubmitting(false);
    }
  };

  const isCustom = formData.type === 'Custom';
  const isIDP = formData.type === 'IDP-Server';
  const isSO = formData.type === 'RTI-SO';
  const isFSP = formData.type === 'RTI-FSP';
  // RTI-FSP's `port` is just as much "its own BFF server's port" as
  // RTI-SO's is - only RTI-SO also has a separate ws_port to configure
  // (RTI-FSP dials out to whichever SO instance is selected on the ACSI
  // Server page at start time, rather than owning a fixed WS port of its
  // own), so the label/explanation is shared but the extra field isn't.
  const isBffPortLabeled = isSO || isFSP;

  return (
    <>
      {showModal && (
        <div className="modal active">
          <div className="modal-content">
            <div className="modal-header">
              <h2>{currentConnection ? 'Edit Instance' : 'Register Instance'}</h2>
              <button className="btn-close" onClick={onClose}>
                &times;
              </button>
            </div>
            <div className="modal-body">
              <div className="form-group">
                <label htmlFor="name">Name</label>
                <input
                  type="text"
                  id="name"
                  value={formData.name}
                  onChange={handleInputChange}
                />
                <small style={{ color: 'var(--text-muted)' }}>
                  Human-readable label for this instance, shown throughout the HMI.
                </small>
              </div>
              <div className="form-group">
                <label htmlFor="type">Type</label>
                <select
                  id="type"
                  value={formData.type}
                  onChange={handleTypeChange}
                >
                  <option value="Custom">Custom</option>
                  <option value="RTI-SO">RTI-SO (WS Passive/ACSI Client)</option>
                  <option value="RTI-FSP">RTI-FSP (WS Active/ACSI Server)</option>
                  <option value="IDP-Server">IDP-Server</option>
                </select>
                <small style={{ color: 'var(--text-muted)' }}>
                  Determines which fields below apply, and fixes ACSI role/WebSocket
                  mode for RTI-SO and RTI-FSP.
                </small>
              </div>
              {!isIDP && (
                <>
                  <div className="form-group">
                    <label htmlFor="host">Host</label>
                    <input
                      type="text"
                      id="host"
                      value={formData.host}
                      onChange={handleInputChange}
                    />
                    <small style={{ color: 'var(--text-muted)' }}>
                      Hostname or IP address of this instance's own BFF server.
                    </small>
                  </div>
                  <div className="form-group">
                    <label htmlFor="port">{isBffPortLabeled ? 'BFF Port' : 'Port'}</label>
                    <input
                      type="number"
                      id="port"
                      value={formData.port}
                      onChange={handleInputChange}
                    />
                    {isBffPortLabeled && (
                      <small style={{ color: 'var(--text-muted)' }}>
                        Port this instance's own BFF server listens on (used for all API calls to it).
                      </small>
                    )}
                  </div>
                  {isSO && (
                    <div className="form-group">
                      <label htmlFor="ws_port">WS Port</label>
                      <input
                        type="number"
                        id="ws_port"
                        value={formData.ws_port}
                        placeholder="8765"
                        onChange={handleInputChange}
                      />
                      <small style={{ color: 'var(--text-muted)' }}>
                        Port this instance's own WebSocket (Passive) endpoint
                        listens on - distinct from the BFF port above.
                      </small>
                    </div>
                  )}
                  {isFSP && (
                    <div className="form-group">
                      <label htmlFor="cp">Connection Point</label>
                      <input
                        type="text"
                        id="cp"
                        value={formData.cp || ''}
                        onChange={handleInputChange}
                        placeholder="e.g., cp1"
                      />
                      <small style={{ color: 'var(--text-muted)' }}>
                        Connection point this Customer/Flexibility Service Provider registers under.
                      </small>
                    </div>
                  )}
                </>
              )}
              {!isIDP && (
                <>
                  <div className="form-group">
                    <label htmlFor="acsi">ACSI</label>
                    {isCustom ? (
                      <select
                        id="acsi"
                        value={formData.acsi || 'server'}
                        onChange={handleInputChange}
                      >
                        <option value="server">Server</option>
                        <option value="client">Client</option>
                      </select>
                    ) : (
                      // RTI-SO/RTI-FSP: fixed by type, not a real choice -
                      // shown as a read-only field, not a dropdown that
                      // looks editable but isn't.
                      <input
                        type="text"
                        id="acsi"
                        readOnly
                        value={formData.acsi === 'client' ? 'Client' : 'Server'}
                      />
                    )}
                    <small style={{ color: 'var(--text-muted)' }}>
                      Server exposes an IEC 61850 model to be read from; Client connects
                      out to read one.
                    </small>
                  </div>
                  <div className="form-group">
                    <label htmlFor="ws_mode">WebSocket Mode</label>
                    {isCustom ? (
                      <select
                        id="ws_mode"
                        value={formData.ws_mode || ''}
                        onChange={handleInputChange}
                      >
                        <option value="">Select mode...</option>
                        <option value="active">Active</option>
                        <option value="passive">Passive</option>
                      </select>
                    ) : (
                      <input
                        type="text"
                        id="ws_mode"
                        readOnly
                        value={formData.ws_mode === 'active' ? 'Active' : formData.ws_mode === 'passive' ? 'Passive' : ''}
                      />
                    )}
                    <small style={{ color: 'var(--text-muted)' }}>
                      Active dials out to establish the WebSocket connection; Passive
                      listens for an incoming one.
                    </small>
                  </div>
                </>
              )}
              
              {(isSO || isFSP || isCustom) && (
                <p className="form-note" style={{ color: 'var(--text-muted)', fontSize: '13px' }}>
                  <i className="fas fa-info-circle" style={{ marginRight: '6px' }}></i>
                  OAuth and TLS are configured on the instance's own page, with its
                  OAuth Config and TLS Config buttons.
                </p>
              )}
              {isIDP && (
                <div className="form-group">
                  <label htmlFor="endpoint">Endpoint</label>
                  <input
                    type="text"
                    id="endpoint"
                    value={formData.endpoint || ''}
                    onChange={handleInputChange}
                    placeholder="e.g., http://keycloak:8080"
                  />
                  <small style={{ color: 'var(--text-muted)' }}>
                    Base URL of this identity provider, as reached from the BFF
                    (e.g. http://keycloak:8080) - realms live under /realms/&lt;name&gt;.
                  </small>
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button className="btn-secondary" onClick={onClose} disabled={submitting}>
                Close
              </button>
              <button className="btn-primary" onClick={handleSave} disabled={submitting}>
                <i className={`fas ${submitting ? 'fa-spinner fa-spin' : 'fa-save'}`}></i>
                {submitting ? 'Saving...' : 'Save Instance'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default ConnectionModal;