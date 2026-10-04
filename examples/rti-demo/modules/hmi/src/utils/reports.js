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

// The report values the SO received, per FSP - read from the reports in the
// SO's own frame log (category "unconfirmed", received), each tagged with
// the cp it came in on (its associateId), which the SO's fspLinks name the
// FSP for.

const QUALITY_FLAGS = { test: 'test', operatorBlock: 'blocked' };

/** "good", or e.g. "invalid, substituted, test, overflow". */
function formatQuality(q) {
  if (!q || typeof q !== 'object') return String(q ?? '');
  const parts = [q.validity || 'unknown'];
  if (q.source && q.source !== 'process') parts.push(q.source);
  Object.entries(QUALITY_FLAGS).forEach(([key, label]) => { if (q[key]) parts.push(label); });
  if (q.detailQual && typeof q.detailQual === 'object') {
    Object.entries(q.detailQual).forEach(([key, on]) => { if (on) parts.push(key); });
  }
  return parts.join(', ');
}

const pad = (n, w = 2) => String(n).padStart(w, '0');

/**
 * "2026-10-04 06:37:00.123 UTC", or "not set" for 0. ws61850 writes
 * fractionOfSecond as microseconds x 10 (100 ns units - see get_now_time in
 * ws61850's data_model/helper.py), not IEC 61850's 24-bit fraction, so it is
 * read that way. A clock failure / unsynchronized clock is appended.
 */
function formatTimeStamp(t) {
  if (!t || typeof t !== 'object') return String(t ?? '');
  const seconds = Number(t.secondSinceEpoch) || 0;
  if (!seconds) return 'not set';
  const ms = Math.floor((Number(t.fractionOfSecond) || 0) / 10000);
  const d = new Date(seconds * 1000 + ms);
  let text = `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} `
    + `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}.${pad(d.getUTCMilliseconds(), 3)} UTC`;
  const tq = t.timeQuality || {};
  if (tq.clockFailure) text += ' (clock failure)';
  else if (tq.clockNotSynchronized) text += ' (not synchronized)';
  return text;
}

/**
 * A report value as text: ACSI values arrive as [{ data: { <type>: v } }],
 * a structure as { structure: { data: [...] } } of the same - one with a
 * single member shows as that member. Quality and timeStamp get a readable
 * form, with the raw value in `detail`.
 * @returns {{text: string, type: string, detail?: string}}
 */
export function formatValue(value) {
  if (Array.isArray(value)) {
    if (value.length === 1) return formatValue(value[0]);
    return { text: `[${value.map((v) => formatValue(v).text).join(', ')}]`, type: 'array' };
  }
  if (value && typeof value === 'object') {
    if ('data' in value && Object.keys(value).length === 1) return formatValue(value.data);
    const keys = Object.keys(value);
    if (keys.length === 1) {
      const [type] = keys;
      const inner = value[type];
      if (type === 'structure') {
        const members = Array.isArray(inner) ? inner : Array.isArray(inner?.data) ? inner.data : [inner];
        if (members.length === 1) return formatValue(members[0]);
        return { text: `{${members.map((m) => formatValue(m).text).join(', ')}}`, type };
      }
      if (type === 'quality') return { text: formatQuality(inner), type, detail: JSON.stringify(inner) };
      if (type === 'timeStamp') return { text: formatTimeStamp(inner), type, detail: JSON.stringify(inner) };
      return { text: formatValue(inner).text, type };
    }
    return { text: JSON.stringify(value), type: 'object' };
  }
  if (typeof value === 'number' && !Number.isInteger(value)) {
    return { text: String(Number(value.toFixed(3))), type: 'number' };
  }
  return { text: value === undefined || value === null ? '' : String(value), type: typeof value };
}

/**
 * The report in a frame's text, or null if it isn't one (or isn't JSON - a
 * BER frame is logged as undecoded bytes).
 * @returns {{rptID, dataSet, sqNum, entries: {dataRef, text, type}[]}|null}
 */
export function parseReport(text) {
  let msg;
  try {
    msg = JSON.parse(text);
  } catch {
    return null;
  }
  const report = msg?.unconfirmed?.service?.report;
  if (!report || typeof report !== 'object') return null;
  let entryData = report.entry?.entryData ?? report.entryData ?? [];
  if (!Array.isArray(entryData)) entryData = [entryData];
  return {
    rptID: report.rptID ?? '',
    dataSet: report.dataSet ?? '',
    sqNum: report.sqNum,
    entries: entryData
      .filter((e) => e && typeof e === 'object' && e.dataRef)
      .map((e) => ({ dataRef: e.dataRef, ...formatValue(e.value) })),
  };
}

/**
 * @param {Object} args - sos / fsps / stores, as for buildTimeline (utils/timeline.js)
 * @returns {Object[]} a group per FSP the SO received reports from, in FSP
 *   order: { fsp, cp, reports, undecoded, lastTime, values }, values being
 *   the latest per dataRef: { dataRef, text, type, rptID, time, latest }
 *   (latest = changed by the newest report)
 */
export function buildReportValues({ sos = [], fsps = [], stores = {} }) {
  const groups = new Map();
  const fspFor = (so, cp) => {
    if (!cp) return null;
    const link = (so.fspLinks || []).find((l) => l.cp === cp);
    if (link?.fsp) return link.fsp;
    return fsps.find((f) => (f.accessPoints || []).includes(cp))?.name ?? null;
  };

  sos.forEach((so) => {
    const frames = (stores[so.target]?.frames || [])
      .filter((f) => f.category === 'unconfirmed' && f.direction === 'recv')
      .sort((a, b) => Number(a.id) - Number(b.id));
    frames.forEach((f) => {
      const name = fspFor(so, f.cp) || (f.cp ? `cp ${f.cp}` : 'Unknown FSP');
      if (!groups.has(name)) {
        groups.set(name, { fsp: name, cp: f.cp || '', reports: 0, undecoded: 0, lastTime: '', lastKey: null, byRef: new Map() });
      }
      const group = groups.get(name);
      const time = f.time || f.timestamp || '';
      const key = `${so.target}#${f.id}`;
      group.reports += 1;
      group.lastTime = time;
      group.lastKey = key;
      const report = parseReport(f.message);
      if (!report) {
        group.undecoded += 1;
        return;
      }
      report.entries.forEach((e) => group.byRef.set(e.dataRef, { ...e, rptID: report.rptID, time, key }));
    });
  });

  const order = (name) => {
    const i = fsps.findIndex((f) => f.name === name);
    return i < 0 ? fsps.length : i;
  };
  return [...groups.values()]
    .sort((a, b) => order(a.fsp) - order(b.fsp) || a.fsp.localeCompare(b.fsp))
    .map(({ byRef, lastKey, ...group }) => ({
      ...group,
      values: [...byRef.values()]
        .sort((a, b) => a.dataRef.localeCompare(b.dataRef))
        .map(({ key, ...v }) => ({ ...v, latest: key === lastKey })),
    }));
}
