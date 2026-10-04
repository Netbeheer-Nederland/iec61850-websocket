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
import { render, screen, fireEvent } from '@testing-library/react';

const hookState = {};

import TrafficTimeline from './TrafficTimeline';

const so = { name: 'SO', target: 'so:5002', fspLinks: [{ cp: 'cp1', fsp: 'FSP01' }, { cp: 'cp2', fsp: 'FSP02' }] };
const fsp1 = { name: 'FSP01', target: 'f1:5001', accessPoints: ['cp1'] };
const fsp2 = { name: 'FSP02', target: 'f2:5001', accessPoints: ['cp2'] };

const stores = {
  'so:5002': {
    frames: [
      { id: 1, cp: 'cp1', invokeId: 4, direction: 'send', category: 'request', service_type: 'GetDataValues', time: '12:00:01.000' },
      { id: 2, cp: 'cp1', invokeId: 4, direction: 'recv', category: 'response', service_type: 'GetDataValues', time: '12:00:01.050' },
    ],
    acsi: [{ id: 1, kind: 'acsi', service: 'GetDataValues', message: 'GetDataValues LD0/LLN0.Mod.stVal - ok', level: 'info', time: '12:00:01', cp: 'cp1', correlation: { cp: 'cp1', invokeId: 4, messageSeqFrom: 1, messageSeqTo: 2 } }],
  },
  'f1:5001': {
    frames: [
      { id: 9, cp: 'cp1', invokeId: 4, direction: 'recv', category: 'request', service_type: 'GetDataValues', time: '12:00:01.010' },
      { id: 10, cp: 'cp1', invokeId: 4, direction: 'send', category: 'response', service_type: 'GetDataValues', time: '12:00:01.020' },
    ],
    acsi: [],
  },
  'f2:5001': {
    frames: [{ id: 3, cp: '', direction: 'send', category: 'unconfirmed', service_type: 'Report', time: '12:00:02.000' }],
    acsi: [{ id: 5, kind: 'acsi', service: 'SetDataValues', message: 'local write', level: 'info', time: '12:00:03' }],
  },
};

const setHook = (overrides = {}) => Object.assign(hookState, {
  sos: [so], fsps: [fsp1, fsp2], stores, running: true,
  start: vi.fn(), stop: vi.fn(), clear: vi.fn(),
}, overrides);

const rowTypes = () => screen.queryAllByTestId('timeline-row').map((r) => r.dataset.type);

describe('TrafficTimeline', () => {
  beforeEach(() => setHook());

  it('draws a lane per SO and FSP, with the FSP cps', () => {
    render(<TrafficTimeline timeline={hookState} />);

    expect(screen.getByTestId('timeline-lane-SO')).toBeInTheDocument();
    expect(screen.getByTestId('timeline-lane-FSP01').textContent).toContain('cp1');
    expect(screen.getByTestId('timeline-lane-FSP02').textContent).toContain('cp2');
  });

  it('lists calls, reports and local entries newest first, with counts', () => {
    render(<TrafficTimeline timeline={hookState} />);

    expect(rowTypes()).toEqual(['local', 'report', 'call']);
    expect(screen.getByText('Calls (1)')).toBeInTheDocument();
    expect(screen.getByText('Reports (1)')).toBeInTheDocument();
    expect(screen.getByText('SO 2 · FSP 2 frames')).toBeInTheDocument();
  });

  it('expands a call into its SO and FSP frames', () => {
    render(<TrafficTimeline timeline={hookState} />);

    fireEvent.click(screen.getByText('GetDataValues'));
    expect(screen.getByText('GetDataValues LD0/LLN0.Mod.stVal - ok')).toBeInTheDocument();
    expect(screen.getByText('SO (SO)')).toBeInTheDocument();
    expect(screen.getByText('FSP01 (FSP)')).toBeInTheDocument();
    expect(screen.getByText('#9')).toBeInTheDocument();
    expect(screen.getByText('#10')).toBeInTheDocument();
  });

  it('filters by type', () => {
    render(<TrafficTimeline timeline={hookState} />);

    fireEvent.click(screen.getByLabelText('Reports (1)'));
    fireEvent.click(screen.getByLabelText('Local (1)'));
    expect(rowTypes()).toEqual(['call']);
  });

  it("shows only the focused FSP's lane and rows, and focuses from a lane header", () => {
    const onFocusFsp = vi.fn();
    const { rerender } = render(<TrafficTimeline timeline={hookState} focusedFsp="FSP02" onFocusFsp={onFocusFsp} />);

    expect(screen.queryByTestId('timeline-lane-FSP01')).not.toBeInTheDocument();
    expect(rowTypes()).toEqual(['local', 'report']);
    fireEvent.click(screen.getByTestId('timeline-lane-FSP02'));
    expect(onFocusFsp).toHaveBeenCalledWith(null);

    rerender(<TrafficTimeline timeline={hookState} onFocusFsp={onFocusFsp} />);
    fireEvent.click(screen.getByTestId('timeline-lane-FSP01'));
    expect(onFocusFsp).toHaveBeenCalledWith('FSP01');
  });

  it('adds a No FSP lane for a call on a cp no FSP reports', () => {
    setHook({
      stores: { 'so:5002': { frames: [], acsi: [{ id: 1, kind: 'acsi', service: 'Operate', level: 'error', time: '12:00:01', cp: 'cp7' }] } },
    });
    render(<TrafficTimeline timeline={hookState} />);

    expect(screen.getByTestId('timeline-lane-?').textContent).toBe('No FSP');
    expect(screen.getByText('cp7 (no FSP)')).toBeInTheDocument();
  });

  it('wires Start / Stop / Clear', () => {
    render(<TrafficTimeline timeline={hookState} />);
    fireEvent.click(screen.getByTitle('Stop following traffic'));
    fireEvent.click(screen.getByTitle("Empty this timeline (the instances' logs are kept)"));
    expect(hookState.stop).toHaveBeenCalled();
    expect(hookState.clear).toHaveBeenCalled();

    setHook({ running: false, stores: {} });
    render(<TrafficTimeline timeline={hookState} />);
    fireEvent.click(screen.getByTitle('Follow traffic'));
    expect(hookState.start).toHaveBeenCalled();
    expect(screen.getByText(/Timeline stopped/)).toBeInTheDocument();
  });

  it("marks a dropped FSP's lane and shows its link going down and back up", () => {
    const at = new Date(2026, 9, 3, 12, 0, 5).getTime();
    render(
      <TrafficTimeline
        timeline={hookState}
        presence={{
          byName: { FSP01: { state: 'up' }, FSP02: { state: 'unreachable' } },
          events: [
            { fsp: 'FSP02', from: 'up', to: 'unreachable', at, downMs: null },
            { fsp: 'FSP01', from: 'link-down', to: 'up', at: at + 1000, downMs: 42000 },
          ],
        }}
      />
    );

    expect(screen.getByTestId('timeline-lane-FSP02').textContent).toContain('unreachable');
    expect(screen.getByTestId('timeline-lane-FSP01').textContent).not.toContain('down');
    expect(screen.getByTestId('timeline-link-FSP02').textContent).toBe('\u2717 unreachable');
    expect(screen.getByTestId('timeline-link-FSP01').textContent).toBe('\u2713 link back up after 42s');
    expect(screen.getByText('Links (2)')).toBeInTheDocument();
  });

  it('gives an FSP the BFF cannot reach a lane only while it has rows', () => {
    const fsp3 = { name: 'FSP03', target: 'f3:5001', accessPoints: ['cp3'], status: 'disconnected' };
    setHook({ fsps: [{ ...fsp1, status: 'connected' }, { ...fsp2, status: 'disconnected' }, fsp3] });
    render(<TrafficTimeline timeline={hookState} />);

    // FSP02 dropped but has rows (a report, a local entry); FSP03 never had any.
    expect(screen.getByTestId('timeline-lane-FSP01')).toBeInTheDocument();
    expect(screen.getByTestId('timeline-lane-FSP02')).toBeInTheDocument();
    expect(screen.queryByTestId('timeline-lane-FSP03')).not.toBeInTheDocument();
  });
});
