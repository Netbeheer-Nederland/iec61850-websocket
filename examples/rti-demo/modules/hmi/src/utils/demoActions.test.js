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

describe('runAction - enable-report', () => {
  const rcb = { ...base, service: 'enable-report', objRef: 'LD0/LLN0.rcbActualValues', rcbType: 'BRCB' };
  const readResult = (value) => ({ ok: true, payload: { result: { ok: true, value } } });
  const config = {
    dataSet: 'LD0/LLN0.DataSetActualValues', intgPd: 1000, rptEna: false,
    optFlds: { seqNum: true, timeStamp: true }, trgOp: { dchg: true, integrity: true },
  };

  beforeEach(() => executeApiCall.mockReset());

  it("reads the RCB and writes its own configuration back with rptEna on", async () => {
    executeApiCall
      .mockResolvedValueOnce(readResult(config))
      .mockResolvedValueOnce({ ok: true, payload: { result: { ok: true, success: true, value: true } } });

    await expect(runAction(rcb)).resolves.toEqual({ ok: true, message: 'ok' });
    expect(executeApiCall).toHaveBeenNthCalledWith(1, 'brcb-read', 'so:5002', { objRef: rcb.objRef, cp: 'cp1' });
    expect(executeApiCall).toHaveBeenNthCalledWith(2, 'brcb-write', 'so:5002', {
      objRef: rcb.objRef,
      cp: 'cp1',
      data: {
        ref: rcb.objRef,
        dataSet: 'LD0/LLN0.DataSetActualValues',
        intgPd: 1000,
        rptEna: true,
        optFlds: { seqNum: true, timeStamp: true, dataSet: false, reasonCode: false, dataRef: false, bufOvfl: false, entryID: false, configRef: false },
        trgOp: { dchg: true, qchg: false, dupd: false, integrity: true, gi: false },
      },
    });
  });

  it('uses the URCB services for an unbuffered RCB', async () => {
    executeApiCall
      .mockResolvedValueOnce(readResult(config))
      .mockResolvedValueOnce({ ok: true, payload: { result: { value: true } } });

    await runAction({ ...rcb, rcbType: 'URCB' });
    expect(executeApiCall.mock.calls.map((c) => c[0])).toEqual(['urcb-read', 'urcb-write']);
  });

  it('leaves an RCB that is already enabled alone', async () => {
    executeApiCall.mockResolvedValueOnce(readResult({ ...config, rptEna: true }));

    await expect(runAction(rcb)).resolves.toEqual({ ok: true, message: 'already enabled' });
    expect(executeApiCall).toHaveBeenCalledTimes(1);
  });

  it("reports the server's serviceError from the read or the write", async () => {
    executeApiCall.mockResolvedValueOnce(readResult('instance-not-available'));
    await expect(runAction(rcb)).resolves.toEqual({ ok: false, message: 'instance-not-available' });

    executeApiCall
      .mockResolvedValueOnce(readResult(config))
      .mockResolvedValueOnce({ ok: true, payload: { result: { value: 'parameter-value-inconsistent' } } });
    await expect(runAction(rcb)).resolves.toEqual({ ok: false, message: 'parameter-value-inconsistent' });
  });

  it('fails without writing when the read fails', async () => {
    executeApiCall.mockResolvedValueOnce({ ok: false, payload: { result: { error: 'Client is not connected' } } });

    await expect(runAction(rcb)).resolves.toEqual({ ok: false, message: 'Client is not connected' });
    expect(executeApiCall).toHaveBeenCalledTimes(1);
  });

  it('is a valid stored action', () => {
    localStorage.clear();
    saveActions([rcb]);
    expect(loadActions()).toEqual([rcb]);
  });
});

describe('runAction - disable-report', () => {
  const rcb = { ...base, service: 'disable-report', objRef: 'LD0/LLN0.rcbActualValues', rcbType: 'BRCB' };
  const readResult = (value) => ({ ok: true, payload: { result: { ok: true, value } } });
  const config = { dataSet: 'LD0/LLN0.DataSetActualValues', intgPd: 1000, rptEna: true, optFlds: {}, trgOp: { dchg: true } };

  beforeEach(() => executeApiCall.mockReset());

  it('writes the configuration back with rptEna off', async () => {
    executeApiCall
      .mockResolvedValueOnce(readResult(config))
      .mockResolvedValueOnce({ ok: true, payload: { result: { value: true } } });

    await expect(runAction(rcb)).resolves.toEqual({ ok: true, message: 'ok' });
    expect(executeApiCall.mock.calls[1][2].data).toMatchObject({
      ref: rcb.objRef, dataSet: config.dataSet, intgPd: 1000, rptEna: false, trgOp: { dchg: true },
    });
  });

  it('leaves an RCB that is already disabled alone', async () => {
    executeApiCall.mockResolvedValueOnce(readResult({ ...config, rptEna: false }));

    await expect(runAction(rcb)).resolves.toEqual({ ok: true, message: 'already disabled' });
    expect(executeApiCall).toHaveBeenCalledTimes(1);
  });

  it('reports a failed write', async () => {
    executeApiCall
      .mockResolvedValueOnce(readResult(config))
      .mockResolvedValueOnce({ ok: false, payload: {} });

    await expect(runAction(rcb)).resolves.toEqual({ ok: false, message: 'Disabling the report failed' });
  });
});
