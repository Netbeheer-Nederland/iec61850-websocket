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

import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import {
  usePlaybookRecorder, startRecording, stopRecording, recordClick, recordedPlaybook, resetPlaybookRecorderStore,
} from './usePlaybookRecorder';

const OK = { ok: true, message: 'ok' };
const entry = (soTarget, label = 'Read', result = OK) => ({
  action: { label, service: 'read', soTarget, soName: soTarget === 'so:1' ? 'SO' : 'Other SO', objRef: 'R', fc: 'st' },
  fsp: 'F1',
  result,
});

describe('usePlaybookRecorder', () => {
  beforeEach(() => resetPlaybookRecorderStore());

  it('records only while recording', () => {
    const { result } = renderHook(() => usePlaybookRecorder());
    act(() => recordClick([entry('so:1')]));
    expect(result.current.steps).toEqual([]);

    act(() => startRecording());
    act(() => recordClick([entry('so:1')]));
    expect(result.current).toMatchObject({ recording: true, so: { name: 'SO', target: 'so:1' } });
    expect(result.current.steps).toHaveLength(1);

    act(() => stopRecording());
    expect(result.current.recording).toBe(false);
    expect(recordedPlaybook('My demo')).toEqual({
      name: 'My demo', so: 'SO', pace: '2s', steps: [{ label: 'Read', read: { fsp: 'F1', ref: 'R', fc: 'st' } }],
    });
  });

  it('keeps to the first SO and notes what it left out', () => {
    const { result } = renderHook(() => usePlaybookRecorder());
    act(() => startRecording());
    act(() => recordClick([entry('so:1')]));
    act(() => recordClick([entry('so:2', 'Elsewhere')]));
    act(() => recordClick([entry('so:1', 'Broken', { ok: false, message: 'Client is not connected' })]));
    expect(result.current.steps).toHaveLength(1);
    expect(result.current.notes).toEqual([
      'Not recorded: "Elsewhere" is on Other SO - a playbook drives one SO (SO)',
      'Not recorded: "Broken" on F1 failed (Client is not connected)',
    ]);
  });

  it('starts over on a new recording', () => {
    const { result } = renderHook(() => usePlaybookRecorder());
    act(() => startRecording());
    act(() => recordClick([entry('so:1')]));
    act(() => startRecording());
    expect(result.current).toMatchObject({ recording: true, so: null, steps: [], notes: [] });
  });
});
