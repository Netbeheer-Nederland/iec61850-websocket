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

import { executeApiCall } from '../services/apiService';

// Demo actions: SO service calls pinned from a Data Access Panel (an SO
// endpoint, one of its cps, a data object, a service) and replayed as
// one-click buttons on Traffic's demo bar. An action belongs to the FSP
// behind its cp; actions on different FSPs that share a label run together
// from "All FSPs" - the FSPs' models differ, so each FSP keeps its own
// objRef under the shared label.
//
// Kept in this browser's localStorage: a demo is run from one machine, and
// the pins are a convenience, not shared state.

export const STORAGE_KEY = 'traffic-demo-actions';
export const SERVICES = ['read', 'write', 'operate'];

/**
 * The ctlVal and value_type the SO's /api/operate wants for a DO of `cdc`,
 * from what the user typed. Throws with a user-facing message on a value
 * the CDC can't take. Shared with ControlModal.
 */
export function controlValue(cdc, raw) {
  const text = String(raw ?? '').trim();
  switch ((cdc || '').toUpperCase()) {
    case 'SPC':
      if (['true', '1', 'on'].includes(text.toLowerCase())) return { value: true, valueType: 'boolean' };
      if (['false', '0', 'off'].includes(text.toLowerCase())) return { value: false, valueType: 'boolean' };
      throw new Error('Invalid SPC value. Use true/false or on/off');
    case 'DPC': {
      const value = { on: 'on', off: 'off', intermediate: 'intermediateState' }[text.toLowerCase()];
      if (!value) throw new Error('Invalid DPC value. Use on, off, or intermediate-state');
      return { value, valueType: 'enumerated' };
    }
    case 'APC': {
      const value = parseFloat(text);
      if (Number.isNaN(value)) throw new Error('Invalid APC value. Must be a number');
      return { value, valueType: 'float32' };
    }
    case 'INC':
    case 'ENC': {
      const value = parseInt(text, 10);
      if (Number.isNaN(value)) throw new Error('Invalid value. Must be an integer');
      return { value, valueType: 'int32' };
    }
    case 'BSC': {
      const value = { up: 'stepUp', down: 'stepDown' }[text.toLowerCase()];
      if (!value) throw new Error('Invalid BSC value. Use step-up or step-down');
      return { value, valueType: 'string' };
    }
    case 'ING': {
      const value = parseInt(text, 10);
      if (Number.isNaN(value)) throw new Error('Invalid ING value. Must be an integer');
      return { value, valueType: 'int32' };
    }
    case 'ASG':
      // ASG typically uses enumerated values
      return { value: text, valueType: 'string' };
    case 'CTE': {
      const value = parseInt(text, 10);
      if (Number.isNaN(value)) throw new Error('Invalid CTE value. Must be an integer');
      return { value, valueType: 'int32' };
    }
    case 'ENG':
      // ENG typically uses enumerated values
      return { value: text, valueType: 'enumerated' };
    default:
      throw new Error('Unsupported CDC type for control');
  }
}

/**
 * The /api/execute call an action makes on its SO: { apiId, body }.
 * Operate uses ControlModal's defaults (ctlNum 0, orCat 1, orIdent "0",
 * not a test).
 */
export function buildRequest(action) {
  const { service, objRef, fc, cp, value, valueType, cdc } = action;
  if (service === 'read') return { apiId: 'read', body: { objRef, fc: fc || 'st', cp } };
  if (service === 'write') {
    const body = { objRef, value, fc: fc || 'sp', cp };
    if (valueType) body.dataType = valueType;
    return { apiId: 'write', body };
  }
  if (service === 'operate') {
    const ctl = controlValue(cdc, value);
    return {
      apiId: 'operate',
      body: {
        objRef,
        value: ctl.value,
        value_type: ctl.valueType,
        ctlNum: 0,
        origin: { orCat: 1, orIdent: '0' },
        test: false,
        cp,
      },
    };
  }
  throw new Error(`Unknown service ${service}`);
}

/**
 * Run an action on its SO. Resolves to { ok, message } - never throws.
 */
export async function runAction(action) {
  let request;
  try {
    request = buildRequest(action);
  } catch (error) {
    return { ok: false, message: error.message };
  }
  const result = await executeApiCall(request.apiId, action.soTarget, request.body);
  const payload = result?.payload;
  const ok = Boolean(result?.ok)
    && (payload?.result?.success ?? payload?.success ?? true) !== false;
  const message = ok
    ? 'ok'
    : payload?.result?.error || payload?.error || payload?.detail || result?.rawText || 'Request failed';
  return { ok, message: typeof message === 'string' ? message : JSON.stringify(message) };
}

/** Distinct labels in the order first pinned, each with its actions. */
export function groupByLabel(actions) {
  const groups = new Map();
  actions.forEach((a) => {
    if (!groups.has(a.label)) groups.set(a.label, []);
    groups.get(a.label).push(a);
  });
  return [...groups.entries()].map(([label, items]) => ({ label, actions: items }));
}

const isAction = (a) => a && typeof a === 'object'
  && typeof a.id === 'string' && typeof a.label === 'string'
  && SERVICES.includes(a.service) && typeof a.soTarget === 'string' && typeof a.objRef === 'string';

export function loadActions() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
    return Array.isArray(parsed) ? parsed.filter(isAction) : [];
  } catch {
    return [];
  }
}

export function saveActions(actions) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(actions));
  } catch {
    // Storage unavailable (private mode, blocked) - the pins still work
    // until the page reloads.
  }
}
