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

import { buildBffApiUrl } from '../services/apiService';

// Demo playbooks (examples/rti-demo/playbooks/README.md): turning pinned-
// button clicks into playbook steps for a recording, and the BFF's
// /api/playbooks calls. The BFF keeps and runs playbooks; the HMI never
// reads or writes YAML itself.

// The origin a pinned operate sends (buildRequest), so a replay sends the same.
const OPERATE_ORIGIN = { orCat: 1, orIdent: '0' };
// The fields run.py takes per FSP (a map from FSP name to value).
const PER_FSP = ['ref', 'rcb', 'value'];

/** A pinned action's step fields, without `fsp`. */
function specOf(action) {
  const { service } = action;
  if (service === 'read') return { ref: action.objRef, fc: action.fc || 'st' };
  if (service === 'write') {
    return { ref: action.objRef, value: action.value, fc: action.fc || 'sp', ...(action.valueType ? { type: action.valueType } : {}) };
  }
  if (service === 'operate') return { ref: action.objRef, cdc: action.cdc, value: action.value, origin: OPERATE_ORIGIN };
  return { rcb: action.objRef, type: String(action.rcbType || 'BRCB').toUpperCase() };
}

/** One step from clicks that share a label, service, outcome and fixed fields. */
function stepOf(entries, refused) {
  const { service, label } = entries[0].action;
  const specs = entries.map((e) => specOf(e.action));
  const fsps = entries.map((e) => e.fsp);
  const spec = { fsp: fsps.length === 1 ? fsps[0] : fsps };
  Object.keys(specs[0]).forEach((key) => {
    const values = specs.map((s) => s[key]);
    const same = values.every((v) => JSON.stringify(v) === JSON.stringify(values[0]));
    spec[key] = same ? values[0] : Object.fromEntries(fsps.map((f, i) => [f, values[i]]));
  });
  return { label, [service]: spec, ...(refused ? { expect: 'fail' } : {}) };
}

/**
 * Playbook steps for one click on a pinned button (one entry) or on an All
 * FSPs button (an entry per FSP): { steps, skipped }. A refusal is kept, as
 * a step expecting one; a click that didn't get through is skipped. Clicks
 * end up in one step unless their outcome, service or a field run.py can't
 * take per FSP (fc, cdc, type) differs - or they'd put the same FSP twice in
 * one step, which splits into separate steps instead (in click order).
 *
 * @param {{action: Object, fsp: string, result: {ok: boolean, message: string, refused?: boolean}}[]} entries
 */
export function clicksToSteps(entries) {
  const skipped = entries.filter((e) => !e.result?.ok && !e.result?.refused);
  const groups = new Map();
  entries.filter((e) => !skipped.includes(e)).forEach((e) => {
    const refused = !e.result.ok;
    const fixed = Object.fromEntries(Object.entries(specOf(e.action)).filter(([k]) => !PER_FSP.includes(k)));
    const key = JSON.stringify([refused, e.action.service, fixed]);
    if (!groups.has(key)) groups.set(key, { refused, slots: [] });
    const group = groups.get(key);
    let slot = group.slots.find((entries) => !entries.some((se) => se.fsp === e.fsp));
    if (!slot) {
      slot = [];
      group.slots.push(slot);
    }
    slot.push(e);
  });
  const steps = [...groups.values()].flatMap((g) => g.slots.map((slot) => stepOf(slot, g.refused)));
  return { steps, skipped };
}

/** A playbook name for an uploaded file: its base name, made valid. */
export function uploadName(fileName) {
  const name = String(fileName).replace(/\.(ya?ml|json)$/i, '')
    .replace(/[^A-Za-z0-9_.-]+/g, '-').replace(/^[^A-Za-z0-9]+/, '').replace(/-+$/, '').slice(0, 64);
  if (!name) return 'upload';
  return name === 'run' ? 'run-upload' : name;
}

export const uploadFormat = (fileName) => (/\.json$/i.test(fileName) ? 'json' : 'yaml');

const pad = (n) => String(n).padStart(2, '0');
export const recordingName = (date = new Date()) =>
  `recording-${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}-${pad(date.getHours())}${pad(date.getMinutes())}`;

const path = (name, rest = '') => `/api/playbooks/${encodeURIComponent(name)}${rest}`;

async function bff(apiPath, options = {}) {
  const response = await fetch(buildBffApiUrl(apiPath), { headers: { 'Content-Type': 'application/json' }, ...options });
  let body = null;
  try {
    body = await response.json();
  } catch {
    // no JSON body
  }
  if (!response.ok) throw new Error(body?.error || `HTTP ${response.status}`);
  return body;
}

export const listPlaybooks = async () => (await bff('/api/playbooks')).playbooks;
export const getPlaybook = (name) => bff(path(name));
export const savePlaybook = (name, playbook) => bff(path(name), { method: 'PUT', body: JSON.stringify({ playbook }) });
export const uploadPlaybook = (name, text, format) => bff(path(name), { method: 'PUT', body: JSON.stringify({ text, format }) });
export const deletePlaybook = (name) => bff(path(name), { method: 'DELETE' });
export const runPlaybook = async (name, options = {}) =>
  (await bff(path(name, '/run'), { method: 'POST', body: JSON.stringify(options) })).run;
export const stopPlaybook = () => bff('/api/playbooks/run/stop', { method: 'POST' });
export const getPlaybookRun = async () => (await bff('/api/playbooks/run')).run;
export const playbookFileUrl = (name) => buildBffApiUrl(path(name, '/file'));
