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

import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/apiService', () => ({
  buildBffApiUrl: (path) => `http://bff${path}`,
}));

import {
  clicksToSteps, listPlaybooks, savePlaybook, uploadPlaybook, runPlaybook, getPlaybookRun,
  playbookFileUrl, uploadName, uploadFormat, recordingName,
} from './playbooks';

const OK = { ok: true, message: 'ok' };
const REFUSED = { ok: false, message: 'blocked', refused: true };
const action = (extra) => ({ id: 'x', label: 'Act', soTarget: 'so:1', soName: 'SO', cp: 'cp1', service: 'read', objRef: 'LD0/A.st', fc: 'st', ...extra });
const entry = (fsp, extra, result = OK) => ({ action: action(extra), fsp, result });

describe('clicksToSteps', () => {
  it('makes a step per service', () => {
    const steps = (extra) => clicksToSteps([entry('F1', extra)]).steps;
    expect(steps({})).toEqual([{ label: 'Act', read: { fsp: 'F1', ref: 'LD0/A.st', fc: 'st' } }]);
    expect(steps({ service: 'write', fc: 'sp', value: '5', valueType: 'int32' }))
      .toEqual([{ label: 'Act', write: { fsp: 'F1', ref: 'LD0/A.st', value: '5', fc: 'sp', type: 'int32' } }]);
    expect(steps({ service: 'operate', fc: undefined, cdc: 'SPC', value: 'on' }))
      .toEqual([{ label: 'Act', operate: { fsp: 'F1', ref: 'LD0/A.st', cdc: 'SPC', value: 'on', origin: { orCat: 1, orIdent: '0' } } }]);
    expect(steps({ service: 'enable-report', fc: undefined, objRef: 'LD0/LLN0.rcb', rcbType: 'urcb' }))
      .toEqual([{ label: 'Act', 'enable-report': { fsp: 'F1', rcb: 'LD0/LLN0.rcb', type: 'URCB' } }]);
    expect(steps({ service: 'disable-report', fc: undefined, objRef: 'R' }))
      .toEqual([{ label: 'Act', 'disable-report': { fsp: 'F1', rcb: 'R', type: 'BRCB' } }]);
  });

  it('turns an All FSPs click into one step with per-FSP values where they differ', () => {
    const { steps } = clicksToSteps([entry('F1', { objRef: 'A' }), entry('F2', { objRef: 'B' })]);
    expect(steps).toEqual([{ label: 'Act', read: { fsp: ['F1', 'F2'], ref: { F1: 'A', F2: 'B' }, fc: 'st' } }]);
  });

  it('records a refusal as expect: fail', () => {
    expect(clicksToSteps([entry('F1', {}, REFUSED)]).steps)
      .toEqual([{ label: 'Act', read: { fsp: 'F1', ref: 'LD0/A.st', fc: 'st' }, expect: 'fail' }]);
  });

  it('splits a mixed outcome into an ok and a refused step', () => {
    const { steps } = clicksToSteps([entry('F1', {}), entry('F2', {}, REFUSED)]);
    expect(steps).toEqual([
      { label: 'Act', read: { fsp: 'F1', ref: 'LD0/A.st', fc: 'st' } },
      { label: 'Act', read: { fsp: 'F2', ref: 'LD0/A.st', fc: 'st' }, expect: 'fail' },
    ]);
  });

  it('splits FSPs whose fc differs, since only ref / rcb / value can be per FSP', () => {
    const { steps } = clicksToSteps([entry('F1', { fc: 'st' }), entry('F2', { fc: 'mx' })]);
    expect(steps.map((s) => s.read.fsp)).toEqual(['F1', 'F2']);
  });

  it('splits two actions on the same FSP within one All-FSPs group into separate steps', () => {
    const { steps } = clicksToSteps([
      entry('F1', { objRef: 'A' }), entry('F2', { objRef: 'B' }), entry('F1', { objRef: 'C' }), entry('F2', { objRef: 'D' }),
    ]);
    expect(steps).toEqual([
      { label: 'Act', read: { fsp: ['F1', 'F2'], ref: { F1: 'A', F2: 'B' }, fc: 'st' } },
      { label: 'Act', read: { fsp: ['F1', 'F2'], ref: { F1: 'C', F2: 'D' }, fc: 'st' } },
    ]);
  });

  it('skips clicks that failed for another reason', () => {
    const failed = entry('F1', {}, { ok: false, message: 'Client is not connected' });
    expect(clicksToSteps([failed])).toEqual({ steps: [], skipped: [failed] });
  });
});

describe('file names', () => {
  it('derives a valid playbook name from an uploaded file', () => {
    expect(uploadName('demo.yaml')).toBe('demo');
    expect(uploadName('My demo (2).yml')).toBe('My-demo-2');
    expect(uploadName('..json')).toBe('upload');
    expect(uploadName('run.yaml')).toBe('run-upload');
    expect(uploadFormat('x.JSON')).toBe('json');
    expect(uploadFormat('x.yml')).toBe('yaml');
  });

  it('names a recording after the time', () => {
    expect(recordingName(new Date(2026, 9, 5, 9, 7))).toBe('recording-20261005-0907');
  });
});

describe('BFF calls', () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });
  const answer = (status, body) => fetch.mockResolvedValueOnce({ ok: status < 400, status, json: async () => body });

  it('lists, saves, uploads and runs', async () => {
    answer(200, { ok: true, playbooks: [{ name: 'demo' }] });
    await expect(listPlaybooks()).resolves.toEqual([{ name: 'demo' }]);
    expect(fetch).toHaveBeenLastCalledWith('http://bff/api/playbooks', expect.anything());

    answer(200, { ok: true, name: 'r' });
    await savePlaybook('r', { steps: [] });
    expect(fetch.mock.lastCall[1]).toMatchObject({ method: 'PUT', body: JSON.stringify({ playbook: { steps: [] } }) });

    answer(200, { ok: true, name: 'u' });
    await uploadPlaybook('u', 'steps: []', 'yaml');
    expect(fetch.mock.lastCall[1].body).toBe(JSON.stringify({ text: 'steps: []', format: 'yaml' }));

    answer(200, { ok: true, run: { state: 'running' } });
    await expect(runPlaybook('demo')).resolves.toEqual({ state: 'running' });
    expect(fetch.mock.lastCall[0]).toBe('http://bff/api/playbooks/demo/run');

    answer(200, { ok: true, run: null });
    await expect(getPlaybookRun()).resolves.toBeNull();
  });

  it("throws the BFF's error", async () => {
    answer(409, { ok: false, error: "'demo' is a built-in playbook" });
    await expect(savePlaybook('demo', {})).rejects.toThrow("'demo' is a built-in playbook");
  });

  it('builds the download URL', () => {
    expect(playbookFileUrl('my rec')).toBe('http://bff/api/playbooks/my%20rec/file');
  });
});
