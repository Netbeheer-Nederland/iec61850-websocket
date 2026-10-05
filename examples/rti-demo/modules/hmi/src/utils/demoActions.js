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
// endpoint, one of its cps, a data object, a service) - or, for
// "enable-report" / "disable-report", from the ACSI Client page's RCB
// dialog - and replayed as
// one-click buttons on Traffic's demo bar. An action belongs to the FSP
// behind its cp; actions on different FSPs that share a label run together
// from "All FSPs" - the FSPs' models differ, so each FSP keeps its own
// objRef under the shared label.
//
// Kept in this browser's localStorage: a demo is run from one machine, and
// the pins are a convenience, not shared state.

export const STORAGE_KEY = 'traffic-demo-actions';
export const SERVICES = ['read', 'write', 'operate', 'enable-report', 'disable-report'];

// The optFlds / trgOp a SetBRCBValues / SetURCBValues carries - the SO
// fills any it isn't sent with its own defaults, so all are always sent
// (missing ones false, as BrcbConfigModal does).
const OPT_FLDS_KEYS = ['seqNum', 'timeStamp', 'dataSet', 'reasonCode', 'dataRef', 'bufOvfl', 'entryID', 'configRef'];
const TRG_OP_KEYS = ['dchg', 'qchg', 'dupd', 'integrity', 'gi'];
const flags = (keys, values = {}) => Object.fromEntries(keys.map((k) => [k, Boolean(values?.[k])]));

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
    case 'DPC':
      // A DPC's Oper.ctlVal is BOOLEAN (IEC 61850-7-3): on = true, off =
      // false. intermediate-state / bad-state are states it reports, not
      // ones it can be commanded to.
      if (['true', '1', 'on'].includes(text.toLowerCase())) return { value: true, valueType: 'boolean' };
      if (['false', '0', 'off'].includes(text.toLowerCase())) return { value: false, valueType: 'boolean' };
      throw new Error('Invalid DPC value. Use on or off');
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

const errorOf = (result, fallback) => {
  const payload = result?.payload;
  const message = payload?.result?.error || payload?.error || payload?.detail || result?.rawText || fallback;
  return typeof message === 'string' ? message : JSON.stringify(message);
};

/**
 * Turn a report control block's reporting on or off: read it, then write
 * its own configuration back with rptEna set - the SO resets every field a
 * write leaves out, so a bare { rptEna } would wipe its data set. An RCB
 * already in the wanted state is left alone (a server may refuse a rewrite
 * while enabled).
 */
async function setReporting({ soTarget, objRef, cp, rcbType }, enabled) {
  const urcb = String(rcbType || '').toUpperCase() === 'URCB';
  const read = await executeApiCall(urcb ? 'urcb-read' : 'brcb-read', soTarget, { objRef, cp });
  const current = read?.payload?.result?.value;
  if (!read?.ok || !current || typeof current !== 'object') {
    // A serviceError comes back as its name in place of the values.
    const message = read?.ok && typeof current === 'string' ? current : errorOf(read, 'Could not read the report control block');
    return read?.ok && typeof current === 'string' ? { ok: false, message, refused: true } : { ok: false, message };
  }
  if (current.rptEna === enabled) return { ok: true, message: enabled ? 'already enabled' : 'already disabled' };

  const write = await executeApiCall(urcb ? 'urcb-write' : 'brcb-write', soTarget, {
    objRef,
    data: {
      ref: objRef,
      dataSet: current.dataSet || '',
      intgPd: parseInt(current.intgPd, 10) || 0,
      rptEna: enabled,
      optFlds: flags(OPT_FLDS_KEYS, current.optFlds),
      trgOp: flags(TRG_OP_KEYS, current.trgOp),
    },
    cp,
  });
  // The SO answers ok with the server's result as value (the BFF wraps that
  // answer in `result`): true, or the serviceError's name.
  const value = write?.payload?.result?.value;
  if (write?.ok && value === true) return { ok: true, message: 'ok' };
  const failed = enabled ? 'Enabling the report failed' : 'Disabling the report failed';
  if (write?.ok && typeof value === 'string') return { ok: false, message: value, refused: true };
  return { ok: false, message: errorOf(write, failed) };
}

/**
 * Run an action on its SO. Resolves to { ok, message } - never throws.
 */
export async function runAction(action) {
  if (action.service === 'enable-report') return setReporting(action, true);
  if (action.service === 'disable-report') return setReporting(action, false);
  let request;
  try {
    request = buildRequest(action);
  } catch (error) {
    return { ok: false, message: error.message };
  }
  const result = await executeApiCall(request.apiId, action.soTarget, request.body);
  return soAnswer(result, action.service);
}

/**
 * Whether the FSP did what an SO service call asked, from executeApiCall's
 * result: { ok, message }. The HTTP status (and the BFF's own `ok`) only say
 * the SO got the request. The SO's answer, which the BFF wraps in `result`,
 * says whether the FSP did it: an operate the FSP refused comes back as
 * { ok: false, error } (error empty without a serviceError), a read it
 * refused as a value that is just the serviceError's name (a real read's
 * value is a list of data). Shared with ControlModal.
 *
 * @param {Object|null} result - executeApiCall's result
 * @param {string} service - 'read' | 'write' | 'operate'
 */
export function soAnswer(result, service) {
  const answer = result?.payload?.result;
  const refusedRead = service === 'read' && typeof answer?.value === 'string';
  const ok = Boolean(result?.ok) && answer?.ok !== false && answer?.success !== false && !refusedRead;
  if (ok) return { ok, message: 'ok' };
  // refused: the SO got the request and the FSP said no - as opposed to the
  // request not getting through. A recording keeps a refusal (expect: fail).
  if (refusedRead) return { ok, message: answer.value, refused: true };
  if (result?.ok && answer?.ok === false && !answer.error) return { ok, message: 'Refused by the FSP', refused: true };
  const message = (typeof answer?.error === 'string' && answer.error) || errorOf(result, 'Request failed');
  return result?.ok && answer ? { ok, message, refused: true } : { ok, message };
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
