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
import { renderHook } from '@testing-library/react';
import { fspStateOf, updatePresence, useFspPresence } from './useFspPresence';
import { formatDuration, clockTime } from '../utils/timeline';

const fsp = (name, status, connectedClients) => ({ name, type: 'RTI-FSP', status, connectedClients });
const empty = { byName: {}, events: [] };

describe('fspStateOf', () => {
  it('tells up, link down and unreachable apart', () => {
    expect(fspStateOf(fsp('A', 'connected', 1))).toBe('up');
    expect(fspStateOf(fsp('A', 'connected', 0))).toBe('link-down');
    expect(fspStateOf(fsp('A', 'disconnected', 1))).toBe('unreachable');
    expect(fspStateOf(undefined)).toBe('unreachable');
  });
});

describe('updatePresence', () => {
  it('records the first state without an event or a since', () => {
    const p = updatePresence(empty, [fsp('A', 'connected', 0)], 1000);
    expect(p).toEqual({ byName: { A: { state: 'link-down', since: null, downs: 0 } }, events: [] });
  });

  it('records going down and coming back up, with the downtime', () => {
    let p = updatePresence(empty, [fsp('A', 'connected', 1)], 1000);
    p = updatePresence(p, [fsp('A', 'disconnected', 0)], 5000);
    expect(p.byName.A).toEqual({ state: 'unreachable', since: 5000, downs: 1 });
    p = updatePresence(p, [fsp('A', 'connected', 0)], 9000);
    p = updatePresence(p, [fsp('A', 'connected', 1)], 47000);

    expect(p.byName.A).toEqual({ state: 'up', since: 47000, downs: 1 });
    expect(p.events).toEqual([
      { fsp: 'A', from: 'up', to: 'unreachable', at: 5000, downMs: null },
      { fsp: 'A', from: 'unreachable', to: 'link-down', at: 9000, downMs: null },
      { fsp: 'A', from: 'link-down', to: 'up', at: 47000, downMs: 38000 },
    ]);
  });

  it('gives back the same state when nothing changed, and forgets deleted FSPs', () => {
    const p = updatePresence(empty, [fsp('A', 'connected', 1), fsp('B', 'connected', 1)], 1000);
    expect(updatePresence(p, [fsp('A', 'connected', 1), fsp('B', 'connected', 1)], 2000)).toBe(p);
    expect(Object.keys(updatePresence(p, [fsp('A', 'connected', 1)], 3000).byName)).toEqual(['A']);
  });
});

describe('useFspPresence', () => {
  it('follows the connections it is given', () => {
    const { result, rerender } = renderHook(({ c }) => useFspPresence(c), { initialProps: { c: [fsp('A', 'connected', 1)] } });
    expect(result.current.byName.A.state).toBe('up');

    rerender({ c: [fsp('A', 'connected', 0)] });
    expect(result.current.byName.A.state).toBe('link-down');
    expect(result.current.events).toHaveLength(1);
  });
});

describe('formatDuration / clockTime', () => {
  it('formats', () => {
    expect(formatDuration(42000)).toBe('42s');
    expect(formatDuration(185000)).toBe('3m 05s');
    expect(formatDuration(3720000)).toBe('1h 02m');
    expect(clockTime(new Date(2026, 9, 3, 9, 5, 7, 42).getTime())).toBe('09:05:07.042');
  });
});
