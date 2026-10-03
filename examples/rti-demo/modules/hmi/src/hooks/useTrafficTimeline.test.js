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
import { renderHook, act, waitFor } from '@testing-library/react';

const handlers = { messages: new Set(), actions: new Set() };
let socketUp = true;
vi.mock('../services/liveSocket', () => ({
  subscribe: (type, handler) => {
    handlers[type]?.add(handler);
    return () => handlers[type]?.delete(handler);
  },
  onConnectionStateChange: (handler) => {
    handler(socketUp);
    return () => {};
  },
}));

const logs = {};
vi.mock('../services/apiService', () => ({
  buildTargetValue: (host, port) => `${host}:${port}`,
  executeApiCall: vi.fn(async (endpoint, target) => {
    const log = logs[target] || { messages: [], actions: [] };
    return endpoint === 'messages'
      ? { ok: true, payload: { messages: log.messages } }
      : { ok: true, payload: { actions: log.actions } };
  }),
}));

import { useTrafficTimeline } from './useTrafficTimeline';
import { executeApiCall } from '../services/apiService';

const push = (type, target, data) => act(() => handlers[type].forEach((h) => h({ type, target, data })));

const connections = [
  { name: 'SO', type: 'RTI-SO', status: 'connected', host: 'so', port: 5002 },
  { name: 'FSP01', type: 'RTI-FSP', status: 'connected', host: 'f1', port: 5001 },
  { name: 'FSP02', type: 'RTI-FSP', status: 'disconnected', host: 'f2', port: 5001 },
];

describe('useTrafficTimeline', () => {
  beforeEach(() => {
    handlers.messages.clear();
    handlers.actions.clear();
    Object.keys(logs).forEach((k) => delete logs[k]);
    executeApiCall.mockClear();
    socketUp = true;
    localStorage.clear();
  });

  it('runs by default and catches up on every connected instance', async () => {
    logs['so:5002'] = {
      messages: [{ id: 1, cp: 'cp1' }],
      actions: [{ id: 1, kind: 'system' }, { id: 2, kind: 'acsi' }],
    };
    const { result } = renderHook(() => useTrafficTimeline(connections));

    expect(result.current.running).toBe(true);
    await waitFor(() => expect(result.current.stores['so:5002']?.frames).toHaveLength(1));
    // Only ACSI entries are kept from the actions log.
    expect(result.current.stores['so:5002'].acsi.map((a) => a.id)).toEqual([2]);
    // The disconnected FSP isn't fetched, but keeps its lane.
    expect(executeApiCall.mock.calls.map((c) => c[1])).not.toContain('f2:5001');
    expect(result.current.fsps.map((f) => f.name)).toEqual(['FSP01', 'FSP02']);
  });

  it('follows pushes, dropping duplicates and unknown targets', async () => {
    const { result } = renderHook(() => useTrafficTimeline(connections));
    await waitFor(() => expect(executeApiCall).toHaveBeenCalled());

    push('messages', 'f1:5001', [{ id: 1 }, { id: 2 }]);
    push('messages', 'f1:5001', [{ id: 2 }, { id: 3 }]);
    push('messages', 'nowhere:1', [{ id: 1 }]);
    push('actions', 'f1:5001', [{ id: 1, kind: 'acsi' }]);

    expect(result.current.stores['f1:5001'].frames.map((f) => f.id)).toEqual([1, 2, 3]);
    expect(result.current.stores['f1:5001'].acsi).toHaveLength(1);
    expect(result.current.stores['nowhere:1']).toBeUndefined();
  });

  it('Clear hides what it held, even when a catch-up returns it again, until the instance restarts', async () => {
    const { result } = renderHook(() => useTrafficTimeline(connections));
    await waitFor(() => expect(executeApiCall).toHaveBeenCalled());

    push('messages', 'f1:5001', [{ id: 1 }, { id: 2 }]);
    act(() => result.current.clear());
    expect(result.current.stores).toEqual({});

    push('messages', 'f1:5001', [{ id: 1 }, { id: 2 }, { id: 3 }]);
    expect(result.current.stores['f1:5001'].frames.map((f) => f.id)).toEqual([3]);

    // ids went back below the clear point: a restart, so new ids count again.
    act(() => result.current.clear());
    push('messages', 'f1:5001', [{ id: 1 }]);
    expect(result.current.stores['f1:5001'].frames.map((f) => f.id)).toEqual([1]);
  });

  it('Stop unsubscribes and is remembered', async () => {
    const { result, unmount } = renderHook(() => useTrafficTimeline(connections));
    await waitFor(() => expect(executeApiCall).toHaveBeenCalled());

    act(() => result.current.stop());
    expect(result.current.running).toBe(false);
    expect(handlers.messages.size).toBe(0);
    unmount();

    const again = renderHook(() => useTrafficTimeline(connections));
    expect(again.result.current.running).toBe(false);
  });

  it('polls while the push socket is down', async () => {
    vi.useFakeTimers();
    socketUp = false;
    try {
      renderHook(() => useTrafficTimeline(connections));
      const initial = executeApiCall.mock.calls.length;
      await act(async () => { vi.advanceTimersByTime(5000); });
      expect(executeApiCall.mock.calls.length).toBeGreaterThan(initial);
    } finally {
      vi.useRealTimers();
    }
  });
});
