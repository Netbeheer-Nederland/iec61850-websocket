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
import { renderHook, act } from '@testing-library/react';

const handlers = new Set();
vi.mock('../services/liveSocket', () => ({
  subscribe: (type, handler) => {
    if (type !== 'messages') return () => {};
    handlers.add(handler);
    return () => handlers.delete(handler);
  },
}));

import { classifyFspFrame, applyFspFrames, useLinkActivity, EMPTY_LINK } from './useLinkActivity';

const push = (msg) => act(() => handlers.forEach((h) => h(msg)));

const request = { direction: 'recv', category: 'request', service_type: 'GetDataValues', time: '12:00:00.001' };
const response = { direction: 'send', category: 'response', service_type: 'GetDataValues', time: '12:00:00.010' };
const report = { direction: 'send', category: 'unconfirmed', service_type: 'Report', time: '12:00:01.000' };
const serviceError = { direction: 'send', category: 'response', service_type: 'serviceError', level: 'error', time: '12:00:02.000' };

describe('classifyFspFrame', () => {
  it('reads an FSP frame as request, response or report', () => {
    expect(classifyFspFrame(request)).toBe('request');
    expect(classifyFspFrame(response)).toBe('response');
    expect(classifyFspFrame(report)).toBe('report');
  });

  it('ignores associate traffic and unknown frames', () => {
    expect(classifyFspFrame({ direction: 'recv', category: 'associate' })).toBeNull();
    expect(classifyFspFrame({ direction: 'send', category: 'request' })).toBeNull();
    expect(classifyFspFrame(undefined)).toBeNull();
  });
});

describe('applyFspFrames', () => {
  it('counts every frame but pulses once, with the last one', () => {
    const link = applyFspFrames(EMPTY_LINK, [request, response, report], 7);

    expect(link).toMatchObject({ requests: 1, responses: 1, reports: 1, errors: 0 });
    expect(link.last).toEqual({ type: 'report', ok: true, service: 'Report', time: '12:00:01.000' });
    expect(link.pulse).toEqual({ type: 'report', ok: true, seq: 7 });
  });

  it('counts a serviceError and marks the last service failed', () => {
    const link = applyFspFrames(EMPTY_LINK, [request, serviceError], 1);

    expect(link.errors).toBe(1);
    expect(link.last.ok).toBe(false);
    expect(link.pulse).toEqual({ type: 'response', ok: false, seq: 1 });
  });

  it('returns the same link when a batch has nothing to count', () => {
    expect(applyFspFrames(EMPTY_LINK, [{ category: 'associate' }], 1)).toBe(EMPTY_LINK);
  });
});

describe('useLinkActivity', () => {
  beforeEach(() => handlers.clear());

  const connections = [
    { name: 'SO', type: 'RTI-SO', host: 'so', port: 5002 },
    { name: 'FSP01', type: 'RTI-FSP', host: 'fsp1', port: 5001 },
    { name: 'FSP02', type: 'RTI-FSP', host: 'fsp2', port: 5001 },
  ];

  it("attributes each FSP's pushed frames to its own link", () => {
    const { result } = renderHook(() => useLinkActivity(connections));

    push({ type: 'messages', target: 'fsp1:5001', data: [request, response] });
    push({ type: 'messages', target: 'fsp2:5001', data: [report] });

    expect(result.current.activity.FSP01).toMatchObject({ requests: 1, responses: 1 });
    expect(result.current.activity.FSP02).toMatchObject({ reports: 1 });
  });

  it("ignores the SO's own frames and unknown targets", () => {
    const { result } = renderHook(() => useLinkActivity(connections));

    push({ type: 'messages', target: 'so:5002', data: [request] });
    push({ type: 'messages', target: 'elsewhere:1', data: [request] });

    expect(result.current.activity).toEqual({});
  });

  it('gives every batch a new pulse seq, and reset() clears the counters', () => {
    const { result } = renderHook(() => useLinkActivity(connections));

    push({ type: 'messages', target: 'fsp1:5001', data: [request] });
    const first = result.current.activity.FSP01.pulse.seq;
    push({ type: 'messages', target: 'fsp1:5001', data: [response] });
    expect(result.current.activity.FSP01.pulse.seq).toBeGreaterThan(first);

    act(() => result.current.reset());
    expect(result.current.activity).toEqual({});
  });
});
