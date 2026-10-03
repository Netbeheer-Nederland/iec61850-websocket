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

// Builds Traffic's merged timeline - one row per thing that happened on an
// SO-FSP link - from the SO's and the FSPs' own logs:
//
//   call   - an ACSI service call the SO made (actions log, kind "acsi"),
//            with the SO frames it produced (its correlation's
//            messageSeqFrom..To on its cp, as MessageMonitor's linkedFrames)
//            and the FSP frames carrying the same cp + invokeId
//   report - a report an FSP sent (frame category "unconfirmed")
//   local  - an ACSI entry an FSP served on its own (a read/write aimed
//            straight at the FSP - no frames)
//   link   - an FSP's link going down or coming back up (useFspPresence's
//            events - timed by the HMI's clock, not an instance's)
//
// Rows are paired by those ids, never by clock: the SO and FSPs run on
// different machines. Only their display order uses the instance's time.

/** The list under `key` in a /api/messages or /api/actions-logs payload. */
export const unwrapList = (payload, key) => {
  if (!payload) return [];
  const list = payload[key] ?? payload.result?.[key] ?? payload.result?.payload?.[key];
  return Array.isArray(list) ? list : [];
};

const frameTime = (f) => String(f?.time || f?.timestamp || '');

const pad = (n, w = 2) => String(n).padStart(w, '0');
/** The HMI's clock as "HH:MM:SS.mmm" - the instances' frame time shape. */
export const clockTime = (ms) => {
  const d = new Date(ms);
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds(), 3)}`;
};

/** "42s", "3m 05s", "1h 02m". */
export const formatDuration = (ms) => {
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${pad(s % 60)}s`;
  return `${Math.floor(s / 3600)}h ${pad(Math.floor((s % 3600) / 60))}m`;
};

// cp + invokeId -> the FSP frames of the most recent exchange with that
// invokeId (from its last request on): invokeIds start over when an FSP
// re-associates, so older frames with the same id belong to another call.
const indexFspExchanges = (frames) => {
  const index = new Map();
  [...frames].sort((a, b) => Number(a.id) - Number(b.id)).forEach((f) => {
    if (f.invokeId == null || f.category === 'unconfirmed') return;
    const key = `${f.cp}#${f.invokeId}`;
    if (f.category === 'request' || !index.has(key)) index.set(key, [f]);
    else index.get(key).push(f);
  });
  return index;
};

const fspForCp = (so, cp, fsps) => {
  const link = (so.fspLinks || []).find((l) => l.cp === cp);
  if (link) return link.fsp;
  const match = fsps.find((f) => (f.accessPoints || []).includes(cp));
  return match ? match.name : null;
};

/**
 * @param {Object} args
 * @param {Object[]} args.sos - RTI-SO connections (with fspLinks), each with a `target` ("host:port")
 * @param {Object[]} args.fsps - RTI-FSP connections (with accessPoints), each with a `target`
 * @param {Object<string, {frames: Object[], acsi: Object[]}>} args.stores - entries per target;
 *   each entry carries `_arrival`, the order the HMI received it in
 * @param {Object[]} args.linkEvents - useFspPresence's events: { fsp, from, to, at, downMs }
 * @returns {Object[]} rows, oldest first
 */
export function buildTimeline({ sos = [], fsps = [], stores = {}, linkEvents = [] }) {
  const rows = [];
  const exchangesByFsp = {};
  fsps.forEach((f) => { exchangesByFsp[f.name] = indexFspExchanges(stores[f.target]?.frames || []); });

  sos.forEach((so) => {
    const store = stores[so.target] || { frames: [], acsi: [] };
    store.acsi.forEach((entry) => {
      const c = entry.correlation;
      const cp = c?.cp || entry.cp || '';
      const soFrames = c && c.messageSeqFrom != null && c.messageSeqTo != null
        ? store.frames.filter((m) => m.cp === c.cp
          && m.category !== 'unconfirmed'
          && Number(m.id) >= c.messageSeqFrom
          && Number(m.id) <= c.messageSeqTo)
        : [];
      const fsp = fspForCp(so, cp, fsps);
      const invokeIds = [...new Set(soFrames.map((m) => m.invokeId).filter((id) => id != null))];
      const fspFrames = fsp
        ? invokeIds.flatMap((id) => exchangesByFsp[fsp]?.get(`${cp}#${id}`) || [])
        : [];
      rows.push({
        key: `call:${so.target}:${entry.id}`,
        type: 'call',
        so: so.name,
        fsp,
        cp,
        service: entry.service || '',
        message: entry.message || '',
        level: entry.level || 'info',
        time: frameTime(soFrames[0]) || frameTime(entry),
        arrival: entry._arrival ?? 0,
        soFrames,
        fspFrames,
        hasCorrelation: Boolean(c),
      });
    });
  });

  // A report or local entry goes to the SO linked to its FSP (else the
  // first SO) - in the demo there is just the one.
  const soOf = (fspName) => (sos.find((so) => (so.fspLinks || []).some((l) => l.fsp === fspName)) || sos[0])?.name ?? null;

  fsps.forEach((fsp) => {
    const store = stores[fsp.target] || { frames: [], acsi: [] };
    store.frames
      .filter((f) => f.category === 'unconfirmed' && f.direction === 'send')
      .forEach((f) => rows.push({
        key: `report:${fsp.target}:${f.id}`,
        type: 'report',
        so: soOf(fsp.name),
        fsp: fsp.name,
        cp: f.cp || fsp.accessPoints?.[0] || '',
        service: f.service_type || f.service || 'Report',
        message: f.preview || '',
        level: f.level || 'info',
        time: frameTime(f),
        arrival: f._arrival ?? 0,
        soFrames: [],
        fspFrames: [f],
      }));
    store.acsi.forEach((entry) => rows.push({
      key: `local:${fsp.target}:${entry.id}`,
      type: 'local',
      so: null,
      fsp: fsp.name,
      cp: entry.cp || '',
      service: entry.service || '',
      message: entry.message || '',
      level: entry.level || 'info',
      time: frameTime(entry),
      arrival: entry._arrival ?? 0,
      soFrames: [],
      fspFrames: [],
    }));
  });

  linkEvents.forEach((e) => rows.push({
    key: `link:${e.fsp}:${e.at}`,
    type: 'link',
    so: soOf(e.fsp),
    fsp: e.fsp,
    cp: fsps.find((f) => f.name === e.fsp)?.accessPoints?.[0] || '',
    up: e.to === 'up',
    state: e.to,
    downMs: e.downMs,
    service: '',
    message: '',
    level: e.to === 'up' ? 'info' : 'error',
    time: clockTime(e.at),
    arrival: 0,
    soFrames: [],
    fspFrames: [],
  }));

  return rows.sort((a, b) => a.time.localeCompare(b.time) || a.arrival - b.arrival);
}
