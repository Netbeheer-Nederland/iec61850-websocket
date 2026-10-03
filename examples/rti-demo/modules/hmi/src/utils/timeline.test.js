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

import { describe, it, expect } from 'vitest';
import { buildTimeline, unwrapList } from './timeline';

const so = { name: 'SO', target: 'so:5002', fspLinks: [{ cp: 'cp1', fsp: 'FSP01' }, { cp: 'cp2', fsp: 'FSP02' }, { cp: 'cp9', fsp: null }] };
const fsp1 = { name: 'FSP01', target: 'f1:5001', accessPoints: ['cp1'] };
const fsp2 = { name: 'FSP02', target: 'f2:5001', accessPoints: ['cp2'] };

const frame = (id, cp, invokeId, direction, category, extra = {}) => ({
  id, cp, invokeId, direction, category, service_type: 'GetDataValues', time: `12:00:0${id}.000`, ...extra,
});
const call = (id, cp, from, to, extra = {}) => ({
  id, kind: 'acsi', service: 'GetDataValues', message: `GetDataValues ${cp} - ok`, level: 'info', time: '12:00:09',
  cp, correlation: { cp, invokeId: 1, messageSeqFrom: from, messageSeqTo: to }, ...extra,
});

describe('buildTimeline - calls', () => {
  it("joins an SO call to its SO frames by seq range and to its FSP's frames by cp + invokeId", () => {
    const stores = {
      'so:5002': {
        frames: [frame(1, 'cp1', 5, 'send', 'request'), frame(2, 'cp1', 5, 'recv', 'response'), frame(3, 'cp2', 8, 'send', 'request')],
        acsi: [call(1, 'cp1', 1, 2)],
      },
      'f1:5001': { frames: [frame(1, 'cp1', 5, 'recv', 'request'), frame(2, 'cp1', 5, 'send', 'response')], acsi: [] },
      'f2:5001': { frames: [frame(1, 'cp2', 5, 'recv', 'request')], acsi: [] },
    };

    const [row] = buildTimeline({ sos: [so], fsps: [fsp1, fsp2], stores });

    expect(row).toMatchObject({ type: 'call', so: 'SO', fsp: 'FSP01', cp: 'cp1', service: 'GetDataValues' });
    expect(row.soFrames.map((f) => f.id)).toEqual([1, 2]);
    // FSP02 also has an invokeId 5, but on another cp - not this call's.
    expect(row.fspFrames.map((f) => f.id)).toEqual([1, 2]);
    // Ordered by the SO's first frame, which carries milliseconds.
    expect(row.time).toBe('12:00:01.000');
  });

  it('takes only the latest exchange when an FSP reused the invokeId (re-association)', () => {
    const stores = {
      'so:5002': { frames: [frame(7, 'cp1', 1, 'send', 'request')], acsi: [call(1, 'cp1', 7, 7)] },
      'f1:5001': {
        frames: [
          frame(1, 'cp1', 1, 'recv', 'request'), frame(2, 'cp1', 1, 'send', 'response'),
          frame(3, 'cp1', 1, 'recv', 'request'), frame(4, 'cp1', 1, 'send', 'response'),
        ],
        acsi: [],
      },
    };

    const [row] = buildTimeline({ sos: [so], fsps: [fsp1], stores });
    expect(row.fspFrames.map((f) => f.id)).toEqual([3, 4]);
  });

  it('leaves fsp null for a cp no registered FSP reports, and falls back to accessPoints without fspLinks', () => {
    const stores = { 'so:5002': { frames: [], acsi: [call(1, 'cp9', 1, 1), call(2, 'cp2', 2, 2)] } };

    const rows = buildTimeline({ sos: [{ ...so, fspLinks: [] }], fsps: [fsp1, fsp2], stores });
    expect(rows.map((r) => r.fsp)).toEqual([null, 'FSP02']);
  });

  it('keeps a call whose frames are no longer held, with empty frame lists', () => {
    const stores = { 'so:5002': { frames: [], acsi: [call(1, 'cp1', 40, 41)] } };

    const [row] = buildTimeline({ sos: [so], fsps: [fsp1], stores });
    expect(row).toMatchObject({ soFrames: [], fspFrames: [], hasCorrelation: true, time: '12:00:09' });
  });
});

describe('buildTimeline - reports and local entries', () => {
  it("adds a row per report an FSP sent, on that FSP's SO", () => {
    const stores = {
      'f2:5001': {
        frames: [frame(1, '', null, 'send', 'unconfirmed', { service_type: 'Report' }), frame(2, 'cp2', 3, 'recv', 'request')],
        acsi: [],
      },
    };

    const rows = buildTimeline({ sos: [so], fsps: [fsp2], stores });
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ type: 'report', so: 'SO', fsp: 'FSP02', cp: 'cp2', service: 'Report' });
  });

  it("adds an FSP's own ACSI entries as local rows", () => {
    const stores = { 'f1:5001': { frames: [], acsi: [{ id: 1, kind: 'acsi', service: 'SetDataValues', message: 'local write', level: 'info', time: '12:00:05' }] } };

    const [row] = buildTimeline({ sos: [so], fsps: [fsp1], stores });
    expect(row).toMatchObject({ type: 'local', so: null, fsp: 'FSP01', service: 'SetDataValues' });
  });

  it('orders rows by time, then by arrival', () => {
    const stores = {
      'so:5002': { frames: [], acsi: [call(1, 'cp1', 1, 1, { time: '12:00:05', _arrival: 2 })] },
      'f1:5001': {
        frames: [frame(1, '', null, 'send', 'unconfirmed', { time: '12:00:05', _arrival: 1 }), frame(2, '', null, 'send', 'unconfirmed', { time: '12:00:01', _arrival: 3 })],
        acsi: [],
      },
    };

    const rows = buildTimeline({ sos: [so], fsps: [fsp1], stores });
    expect(rows.map((r) => r.key)).toEqual(['report:f1:5001:2', 'report:f1:5001:1', 'call:so:5002:1']);
  });
});

describe('unwrapList', () => {
  it('finds the list at any of the payload shapes the BFF returns', () => {
    expect(unwrapList({ messages: [1] }, 'messages')).toEqual([1]);
    expect(unwrapList({ result: { messages: [2] } }, 'messages')).toEqual([2]);
    expect(unwrapList({ result: { payload: { messages: [3] } } }, 'messages')).toEqual([3]);
    expect(unwrapList(null, 'messages')).toEqual([]);
  });
});

describe('buildTimeline - link events', () => {
  it("adds a row per FSP link change, on the FSP's SO, by the HMI's clock", () => {
    const at = new Date(2026, 9, 3, 12, 0, 4, 500).getTime();
    const rows = buildTimeline({
      sos: [so],
      fsps: [fsp1],
      stores: {},
      linkEvents: [
        { fsp: 'FSP01', from: 'up', to: 'link-down', at, downMs: null },
        { fsp: 'FSP01', from: 'link-down', to: 'up', at: at + 42000, downMs: 42000 },
      ],
    });

    expect(rows.map((r) => [r.type, r.so, r.fsp, r.cp, r.up, r.state, r.time, r.downMs])).toEqual([
      ['link', 'SO', 'FSP01', 'cp1', false, 'link-down', '12:00:04.500', null],
      ['link', 'SO', 'FSP01', 'cp1', true, 'up', '12:00:46.500', 42000],
    ]);
  });
});
