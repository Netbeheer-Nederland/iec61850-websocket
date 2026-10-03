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

import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/apiService', () => ({ executeApiCall: vi.fn() }));

import { executeApiCall } from '../services/apiService';
import {
  controlValue, buildRequest, runAction, groupByLabel, loadActions, saveActions, STORAGE_KEY,
} from './demoActions';

const base = { id: 'a1', label: 'L', soTarget: 'so:5002', cp: 'cp1', objRef: 'LD0/DWMX1.WMaxSpt' };

describe('controlValue', () => {
  it('converts per CDC', () => {
    expect(controlValue('SPC', 'on')).toEqual({ value: true, valueType: 'boolean' });
    expect(controlValue('dpc', 'intermediate')).toEqual({ value: 'intermediateState', valueType: 'enumerated' });
    expect(controlValue('APC', ' 50.5 ')).toEqual({ value: 50.5, valueType: 'float32' });
    expect(controlValue('INC', '7')).toEqual({ value: 7, valueType: 'int32' });
    expect(controlValue('BSC', 'up')).toEqual({ value: 'stepUp', valueType: 'string' });
  });

  it('rejects what the CDC cannot take', () => {
    expect(() => controlValue('SPC', 'maybe')).toThrow('Invalid SPC value');
    expect(() => controlValue('APC', 'abc')).toThrow('Must be a number');
    expect(() => controlValue('XYZ', '1')).toThrow('Unsupported CDC type');
  });
});

describe('buildRequest', () => {
  it('reads with the fc and cp', () => {
    expect(buildRequest({ ...base, service: 'read', fc: 'mx' }))
      .toEqual({ apiId: 'read', body: { objRef: base.objRef, fc: 'mx', cp: 'cp1' } });
  });

  it('writes with the value and its data type', () => {
    expect(buildRequest({ ...base, service: 'write', fc: 'sp', value: '3', valueType: 'INT32' }))
      .toEqual({ apiId: 'write', body: { objRef: base.objRef, value: '3', fc: 'sp', cp: 'cp1', dataType: 'INT32' } });
  });

  it("operates with ControlModal's defaults", () => {
    expect(buildRequest({ ...base, service: 'operate', cdc: 'APC', value: '50' })).toEqual({
      apiId: 'operate',
      body: {
        objRef: base.objRef, value: 50, value_type: 'float32', ctlNum: 0,
        origin: { orCat: 1, orIdent: '0' }, test: false, cp: 'cp1',
      },
    });
  });
});

describe('runAction', () => {
  beforeEach(() => executeApiCall.mockReset());

  it('calls the SO and reports success', async () => {
    executeApiCall.mockResolvedValue({ ok: true, payload: { result: { value: 1 } } });

    await expect(runAction({ ...base, service: 'read', fc: 'st' })).resolves.toEqual({ ok: true, message: 'ok' });
    expect(executeApiCall).toHaveBeenCalledWith('read', 'so:5002', { objRef: base.objRef, fc: 'st', cp: 'cp1' });
  });

  it('treats an operate the SO answered with success: false as failed', async () => {
    executeApiCall.mockResolvedValue({ ok: true, payload: { result: { success: false, error: 'blocked' } } });

    await expect(runAction({ ...base, service: 'operate', cdc: 'SPC', value: 'on' }))
      .resolves.toEqual({ ok: false, message: 'blocked' });
  });

  it('fails without calling the SO when the value is invalid, and on a null result', async () => {
    await expect(runAction({ ...base, service: 'operate', cdc: 'SPC', value: 'x' }))
      .resolves.toMatchObject({ ok: false });
    expect(executeApiCall).not.toHaveBeenCalled();

    executeApiCall.mockResolvedValue(null);
    await expect(runAction({ ...base, service: 'read' })).resolves.toEqual({ ok: false, message: 'Request failed' });
  });
});

describe('groupByLabel', () => {
  it('groups in first-pinned order', () => {
    const groups = groupByLabel([{ id: '1', label: 'B' }, { id: '2', label: 'A' }, { id: '3', label: 'B' }]);
    expect(groups.map((g) => [g.label, g.actions.map((a) => a.id)])).toEqual([['B', ['1', '3']], ['A', ['2']]]);
  });
});

describe('loadActions / saveActions', () => {
  beforeEach(() => localStorage.clear());

  it('round-trips, dropping malformed entries', () => {
    saveActions([{ ...base, service: 'read' }]);
    expect(loadActions()).toEqual([{ ...base, service: 'read' }]);

    localStorage.setItem(STORAGE_KEY, JSON.stringify([{ ...base, service: 'delete' }, 'junk']));
    expect(loadActions()).toEqual([]);
    localStorage.setItem(STORAGE_KEY, '{not json');
    expect(loadActions()).toEqual([]);
  });
});
