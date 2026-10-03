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
import { render, screen } from '@testing-library/react';
import ReportValues from './ReportValues';

const so = { name: 'SO', target: 'so:5002', fspLinks: [{ cp: 'cp1', fsp: 'FSP_North' }, { cp: 'cp2', fsp: 'FSP_South' }] };
const fsps = [{ name: 'FSP_North' }, { name: 'FSP_South' }];
const report = (cp, dataRef, v) => JSON.stringify({
  unconfirmed: { associateId: cp, service: { report: { rptID: 'ActualValues', entry: { entryData: [{ dataRef, value: [{ data: { float32: v } }] }] } } } },
});
const frames = [
  { id: 1, cp: 'cp1', direction: 'recv', category: 'unconfirmed', message: report('cp1', 'LD0/MMXU1.TotW.mag.f', 42.5), time: '12:00:01.000' },
  { id: 2, cp: 'cp2', direction: 'recv', category: 'unconfirmed', message: report('cp2', 'LD0/MHAI1.Hz.mag.f', 50), time: '12:00:02.000' },
];
const timeline = (overrides = {}) => ({ sos: [so], fsps, stores: { 'so:5002': { frames, acsi: [] } }, running: true, ...overrides });

describe('ReportValues', () => {
  it("shows each FSP's latest report values", () => {
    render(<ReportValues timeline={timeline()} />);

    const north = screen.getByTestId('report-values-FSP_North');
    expect(north.textContent).toContain('cp1');
    expect(north.textContent).toContain('1 report');
    expect(north.textContent).toContain('LD0/MMXU1.TotW.mag.f');
    expect(north.textContent).toContain('42.5');
    expect(screen.getByTestId('report-values-FSP_South').textContent).toContain('50');
  });

  it('narrows to the focused FSP', () => {
    render(<ReportValues timeline={timeline()} focusedFsp="FSP_South" />);

    expect(screen.queryByTestId('report-values-FSP_North')).not.toBeInTheDocument();
    expect(screen.getByTestId('report-values-FSP_South')).toBeInTheDocument();
  });

  it('explains what to do when nothing has been received, or the timeline is stopped', () => {
    const { rerender } = render(<ReportValues timeline={timeline({ stores: {} })} />);
    expect(screen.getByText(/No reports received by the SO yet/)).toBeInTheDocument();

    rerender(<ReportValues timeline={timeline({ stores: {}, running: false })} />);
    expect(screen.getByText(/The timeline is stopped/)).toBeInTheDocument();
  });

  it("keeps a dropped FSP's last values, marked", () => {
    render(<ReportValues timeline={timeline()} presence={{ byName: { FSP_North: { state: 'unreachable' }, FSP_South: { state: 'up' } }, events: [] }} />);

    const north = screen.getByTestId('report-values-FSP_North');
    expect(north.textContent).toContain('unreachable');
    expect(north.textContent).toContain('last known values');
    expect(north.textContent).toContain('42.5');
    expect(screen.getByTestId('report-values-FSP_South').textContent).not.toContain('last known values');
  });
});
