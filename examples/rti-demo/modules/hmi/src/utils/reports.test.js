/*
 * SPDX-FileCopyrightText: 2025-2026 Netbeheer Nederland
 * SPDX-License-Identifier: Apache-2.0
 *
 * Copyright 2025-2026 Netbeheer Nederland
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
import { formatValue, parseReport, buildReportValues } from './reports';

const reportText = (cp, rptID, entries) => JSON.stringify({
  unconfirmed: {
    associateId: cp,
    service: { report: { rptID, sqNum: 1, dataSet: 'LD0/LLN0.DataSetActualValues', entry: { entryID: 'x', entryData: entries } } },
  },
});
const entry = (dataRef, type, v) => ({ dataRef, value: [{ data: { [type]: v } }], reasonCode: { dataChange: true } });
const recv = (id, cp, text, time) => ({ id, cp, direction: 'recv', category: 'unconfirmed', service_type: 'report', message: text, time });

describe('formatValue', () => {
  it('unwraps ACSI data values', () => {
    expect(formatValue([{ data: { float32: 12.34567 } }])).toEqual({ text: '12.346', type: 'float32' });
    expect(formatValue([{ data: { boolean: false } }])).toEqual({ text: 'false', type: 'boolean' });
    expect(formatValue([{ data: { int32: 7 } }])).toEqual({ text: '7', type: 'int32' });
  });

  it('shows a structure as its members', () => {
    expect(formatValue([{ data: { structure: [{ data: { float32: 1.5 } }, { data: { 'bit-string': '0000' } }] } }]))
      .toEqual({ text: '{1.5, 0000}', type: 'structure' });
  });
});

describe('formatValue - shapes ws61850 reports use', () => {
  // As logged by an FSP (model_1 ActualValues).
  const quality = (q) => [{ data: { quality: { validity: 'good', source: 'process', test: false, operatorBlock: false, ...q } } }];
  const stamp = (t) => [{ data: { timeStamp: { secondSinceEpoch: 0, fractionOfSecond: 0, timeQuality: { clockFailure: false, clockNotSynchronized: false, timeAccuracy: 0 }, ...t } } }];

  it('shows a single-member structure, however deep, as its value', () => {
    expect(formatValue([{ data: { structure: { data: [{ float32: 0.0 }] } } }])).toEqual({ text: '0', type: 'float32' });
    expect(formatValue([{ data: { structure: { data: [{ structure: { data: [{ float32: 230.25 }] } }] } } }]))
      .toEqual({ text: '230.25', type: 'float32' });
    expect(formatValue([{ data: { structure: { data: [{ float32: 1.5 }, { int32: 2 }] } } }]))
      .toEqual({ text: '{1.5, 2}', type: 'structure' });
  });

  it('shows a quality as its validity and any flags set, raw in detail', () => {
    expect(formatValue(quality())).toMatchObject({ text: 'good', type: 'quality' });
    expect(formatValue(quality({ validity: 'invalid', source: 'substituted', test: true, operatorBlock: true, detailQual: { overflow: true, oscillatory: false } })).text)
      .toBe('invalid, substituted, test, blocked, overflow');
    expect(JSON.parse(formatValue(quality()).detail).validity).toBe('good');
  });

  it('shows a timestamp in UTC, "not set" for 0, with clock trouble appended', () => {
    expect(formatValue(stamp())).toMatchObject({ text: 'not set', type: 'timeStamp' });
    // ws61850's fractionOfSecond is microseconds x 10: 1234560 = 123.456 ms.
    const secs = Date.UTC(2026, 9, 4, 6, 37, 0) / 1000;
    expect(formatValue(stamp({ secondSinceEpoch: secs, fractionOfSecond: 1234560 })).text).toBe('2026-10-04 06:37:00.123 UTC');
    expect(formatValue(stamp({ secondSinceEpoch: secs, timeQuality: { clockNotSynchronized: true } })).text)
      .toBe('2026-10-04 06:37:00.000 UTC (not synchronized)');
  });
});

describe('parseReport', () => {
  it('reads rptID, data set and entries', () => {
    expect(parseReport(reportText('cp1', 'ActualValues', [entry('LD0/MMXU1.TotW.mag.f', 'float32', 42)]))).toEqual({
      rptID: 'ActualValues',
      dataSet: 'LD0/LLN0.DataSetActualValues',
      sqNum: 1,
      entries: [{ dataRef: 'LD0/MMXU1.TotW.mag.f', text: '42', type: 'float32' }],
    });
  });

  it('is null for non-reports and non-JSON (BER) frames', () => {
    expect(parseReport('{"response": {}}')).toBeNull();
    expect(parseReport('\u0001\u0002binary')).toBeNull();
  });
});

describe('buildReportValues', () => {
  const so = { name: 'SO', target: 'so:5002', fspLinks: [{ cp: 'cp1', fsp: 'FSP_North' }, { cp: 'cp2', fsp: 'FSP_South' }] };
  const fsps = [{ name: 'FSP_North' }, { name: 'FSP_South' }];

  it('keeps the latest value per data attribute, per FSP, marking what the newest report changed', () => {
    const stores = {
      'so:5002': {
        frames: [
          recv(1, 'cp1', reportText('cp1', 'ActualValues', [entry('LD0/A', 'float32', 1), entry('LD0/B', 'float32', 2)]), '12:00:01.000'),
          recv(2, 'cp2', reportText('cp2', 'Status', [entry('LD0/S', 'boolean', true)]), '12:00:02.000'),
          recv(3, 'cp1', reportText('cp1', 'ActualValues', [entry('LD0/A', 'float32', 5)]), '12:00:03.000'),
          { id: 4, cp: 'cp1', direction: 'recv', category: 'response', message: '{}' },
        ],
      },
    };

    const groups = buildReportValues({ sos: [so], fsps, stores });

    expect(groups.map((g) => [g.fsp, g.cp, g.reports, g.lastTime])).toEqual([
      ['FSP_North', 'cp1', 2, '12:00:03.000'],
      ['FSP_South', 'cp2', 1, '12:00:02.000'],
    ]);
    expect(groups[0].values).toEqual([
      { dataRef: 'LD0/A', text: '5', type: 'float32', rptID: 'ActualValues', time: '12:00:03.000', latest: true },
      { dataRef: 'LD0/B', text: '2', type: 'float32', rptID: 'ActualValues', time: '12:00:01.000', latest: false },
    ]);
  });

  it('groups reports from an SO that predates their cp as Unknown FSP, and counts undecoded ones', () => {
    const stores = { 'so:5002': { frames: [recv(1, '', 'binary', '12:00:01')] } };

    expect(buildReportValues({ sos: [so], fsps, stores })).toEqual([
      { fsp: 'Unknown FSP', cp: '', reports: 1, undecoded: 1, lastTime: '12:00:01', values: [] },
    ]);
  });
});
