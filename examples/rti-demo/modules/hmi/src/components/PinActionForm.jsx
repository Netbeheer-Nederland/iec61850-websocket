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

import React, { useState } from 'react';
import { controlValue } from '../utils/demoActions';
import { useDemoActions } from '../hooks/useDemoActions';
import { buildTargetValue } from '../services/apiService';

const SERVICE_LABELS = { read: 'Read', write: 'Write', operate: 'Operate', 'enable-report': 'Enable report' };
const shortRef = (ref) => String(ref || '').split('/').pop();

/**
 * "Pin as demo action" for a Data Access Panel on an SO endpoint (or the
 * ACSI Client page's RCB dialog): saves the current selection as a
 * one-click button on Traffic's demo bar, under the FSP behind `cp`. See
 * utils/demoActions.js.
 *
 * @param {Object} so - the selected RTI-SO connection (with fspLinks)
 * @param {string} cp - the cp the panel is using
 * @param {Object|null} read - { objRef, fc, valueType } of a selected DA, else null
 * @param {boolean} canWrite - whether that DA's FC is writable (CF/SP)
 * @param {Object|null} operate - { objRef, cdc } of a selected controllable DO, else null
 * @param {Object|null} report - { objRef, rcbType } of a report control block, else null
 * @param {string} defaultValue - the panel's current write value
 */
function PinActionForm({ so, cp, read = null, canWrite = false, operate = null, report = null, defaultValue = '' }) {
  const { addAction } = useDemoActions();
  const services = [
    ...(read ? ['read'] : []),
    ...(read && canWrite ? ['write'] : []),
    ...(operate ? ['operate'] : []),
    ...(report ? ['enable-report'] : []),
  ];
  const [open, setOpen] = useState(false);
  const [service, setService] = useState(null);
  const [label, setLabel] = useState('');
  const [value, setValue] = useState('');
  const [error, setError] = useState(null);
  const [pinned, setPinned] = useState(null);

  if (!so || !cp || services.length === 0) return null;

  const fspName = (so.fspLinks || []).find((l) => l.cp === cp)?.fsp || null;
  const active = services.includes(service) ? service : services[0];
  const target = { operate, 'enable-report': report }[active] || read;
  const takesValue = active === 'write' || active === 'operate';

  const openForm = () => {
    setService(services[0]);
    setLabel('');
    setValue(defaultValue);
    setError(null);
    setPinned(null);
    setOpen(true);
  };

  const pin = () => {
    const name = label.trim() || `${SERVICE_LABELS[active]} ${shortRef(target.objRef)}`;
    if (active === 'write' && value === '') {
      setError('Enter the value to write');
      return;
    }
    if (active === 'operate') {
      try {
        controlValue(operate.cdc, value);
      } catch (e) {
        setError(e.message);
        return;
      }
    }
    addAction({
      label: name,
      service: active,
      soTarget: buildTargetValue(so.host, so.port),
      soName: so.name,
      cp,
      fspName,
      objRef: target.objRef,
      fc: active === 'read' || active === 'write' ? read.fc : undefined,
      valueType: active === 'write' ? read.valueType || undefined : undefined,
      cdc: active === 'operate' ? operate.cdc : undefined,
      rcbType: active === 'enable-report' ? report.rcbType : undefined,
      value: takesValue ? value : undefined,
    });
    setPinned(`Pinned "${name}" for ${fspName || cp}`);
    setOpen(false);
  };

  if (!open) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px', fontSize: '12px' }}>
        <button className="btn-secondary" style={{ padding: '4px 10px', fontSize: '12px' }} onClick={openForm} title="Add this to Traffic's demo actions">
          <i className="fas fa-thumbtack" style={{ fontSize: '11px' }}></i>Pin as demo action
        </button>
        {pinned && <span style={{ color: 'var(--success-color)' }}>{pinned}</span>}
      </div>
    );
  }

  return (
    <div className="pin-action-form" style={{ border: '1px solid var(--border-color)', borderRadius: '6px', padding: '10px', marginBottom: '16px', display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '12px' }}>
      <div style={{ color: 'var(--text-secondary)' }}>
        Demo action for <strong>{fspName || `cp ${cp}`}</strong> via {so.name}
        {!fspName && Array.isArray(so.fspLinks) && <span style={{ color: 'var(--warning-color)' }}> - no registered FSP reports {cp}</span>}
      </div>
      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          Service
          <select value={active} onChange={(e) => { setService(e.target.value); setError(null); }}>
            {services.map((s) => <option key={s} value={s}>{SERVICE_LABELS[s]}</option>)}
          </select>
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: '2px', flex: 1, minWidth: '140px' }}>
          Label
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder={`${SERVICE_LABELS[active]} ${shortRef(target.objRef)}`}
          />
        </label>
        {takesValue && (
          <label style={{ display: 'flex', flexDirection: 'column', gap: '2px', width: '120px' }}>
            Value
            <input value={value} onChange={(e) => { setValue(e.target.value); setError(null); }} />
          </label>
        )}
      </div>
      <div style={{ fontFamily: 'Consolas, "Courier New", monospace', color: 'var(--text-muted)' }}>
        {target.objRef}
        {(active === 'read' || active === 'write') && read.fc ? ` [${read.fc.toUpperCase()}]` : ''}
        {active === 'operate' ? ` (${operate.cdc})` : ''}
        {active === 'enable-report' ? ` (${report.rcbType || 'BRCB'} - its current configuration, with reporting on)` : ''}
      </div>
      <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
        Give actions on other FSPs the same label to run them together with "All FSPs".
      </div>
      {error && <div style={{ color: 'var(--danger-color)' }}>{error}</div>}
      <div style={{ display: 'flex', gap: '8px' }}>
        <button className="btn-primary" style={{ padding: '4px 12px', fontSize: '12px' }} onClick={pin}>Pin</button>
        <button className="btn-secondary" style={{ padding: '4px 12px', fontSize: '12px' }} onClick={() => setOpen(false)}>Cancel</button>
      </div>
    </div>
  );
}

export default PinActionForm;
