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

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import InstanceVisualization from './InstanceVisualization';

const renderViz = (connections) =>
  render(
    <MemoryRouter>
      <InstanceVisualization connections={connections} />
    </MemoryRouter>
  );

const SO = { name: 'SO', type: 'RTI-SO', status: 'connected', host: 'rti-so', port: 5002 };

describe('InstanceVisualization - SO circle reflects connected FSP count', () => {
  it('is plain (not green) and badged 0 when no FSP is connected', () => {
    renderViz([{ ...SO, connectedFsps: 0 }]);

    const circle = screen.getByTitle('Type: RTI-SO (Client) - 0 FSPs connected');
    expect(circle.style.background).toBe('var(--bg-card)');

    const badge = screen.getByTitle('0 connected FSPs');
    expect(badge.textContent).toBe('0');
    expect(badge.style.background).toBe('var(--text-muted)');
  });

  it('also defaults to 0/plain when connectedFsps is missing entirely', () => {
    renderViz([{ ...SO }]);

    expect(screen.getByTitle('Type: RTI-SO (Client) - 0 FSPs connected')).toBeInTheDocument();
    expect(screen.getByTitle('0 connected FSPs').textContent).toBe('0');
  });

  it('turns green and shows the count as soon as one FSP is connected', () => {
    renderViz([{ ...SO, connectedFsps: 1 }]);

    const circle = screen.getByTitle('Type: RTI-SO (Client) - 1 FSP connected');
    expect(circle.style.background).toBe('var(--success-color)');

    const badge = screen.getByTitle('1 connected FSP');
    expect(badge.textContent).toBe('1');
    expect(badge.style.background).toBe('var(--success-color)');
  });

  it('shows the exact count for multiple connected FSPs', () => {
    renderViz([{ ...SO, connectedFsps: 3 }]);

    const circle = screen.getByTitle('Type: RTI-SO (Client) - 3 FSPs connected');
    expect(circle.style.background).toBe('var(--success-color)');
    expect(screen.getByTitle('3 connected FSPs').textContent).toBe('3');
  });

  it('does not render an SO circle at all when no SO is connected', () => {
    renderViz([{ name: 'FSP01', type: 'RTI-FSP', status: 'connected', host: 'h', port: 1, connectedClients: 0 }]);

    expect(screen.queryByTitle(/Type: RTI-SO/)).not.toBeInTheDocument();
  });
});

describe('InstanceVisualization - no manual refresh', () => {
  it('has no Refresh Instances button (connections arrive via the live push)', () => {
    renderViz([SO]);

    expect(screen.queryByTitle('Refresh Instances')).not.toBeInTheDocument();
  });
});

describe('InstanceVisualization - live link activity (Traffic)', () => {
  const FSP = (name, extra = {}) => ({
    name, type: 'RTI-FSP', status: 'connected', host: `${name}-host`, port: 5001, connectedClients: 1, ...extra,
  });
  const link = {
    requests: 4, responses: 3, reports: 2, errors: 1,
    last: { type: 'response', ok: false, service: 'serviceError', time: '12:00:02.000' },
    pulse: { type: 'response', ok: false, seq: 3 },
  };

  it('shows nothing extra without an activity prop', () => {
    renderViz([SO, FSP('FSP01')]);

    expect(screen.queryByTestId('link-counters-FSP01')).not.toBeInTheDocument();
  });

  it("shows each link's cp, counters, last service and pulse", () => {
    render(
      <MemoryRouter>
        <InstanceVisualization
          connections={[SO, FSP('FSP01', { accessPoints: ['cp2'] }), FSP('FSP02')]}
          activity={{ FSP01: link }}
        />
      </MemoryRouter>
    );

    expect(screen.getByText('cp2')).toBeInTheDocument();
    expect(screen.getByTestId('link-counters-FSP01').textContent).toContain('4');
    expect(screen.getByTestId('link-counters-FSP01').textContent).toContain('2');
    expect(screen.getByTestId('link-last-FSP01').textContent).toContain('serviceError');
    expect(screen.getByTestId('link-pulse-FSP01')).toHaveClass('link-pulse--in');
    // An FSP without activity yet still gets an (empty) link.
    expect(screen.getByTestId('link-last-FSP02').textContent).toBe('no traffic yet');
  });

  it('calls onFspSelect / onSoSelect instead of navigating, and dims unfocused links', () => {
    const onFspSelect = vi.fn();
    const onSoSelect = vi.fn();
    render(
      <MemoryRouter>
        <InstanceVisualization
          connections={[SO, FSP('FSP01'), FSP('FSP02')]}
          activity={{}}
          focusedFsp="FSP01"
          onFspSelect={onFspSelect}
          onSoSelect={onSoSelect}
        />
      </MemoryRouter>
    );

    fireEvent.click(screen.getByTitle('FSP02 - click to focus this link'));
    expect(onFspSelect).toHaveBeenCalledWith(expect.objectContaining({ name: 'FSP02' }));
    fireEvent.click(screen.getByTitle(/Type: RTI-SO/));
    expect(onSoSelect).toHaveBeenCalled();

    expect(screen.getByTestId('fsp-row-FSP01').style.opacity).toBe('1');
    expect(screen.getByTestId('fsp-row-FSP02').style.opacity).toBe('0.35');
  });
});

describe('InstanceVisualization - dropped FSPs (Traffic)', () => {
  const FSP = (name, extra = {}) => ({
    name, type: 'RTI-FSP', status: 'connected', host: `${name}-host`, port: 5001, connectedClients: 1, ...extra,
  });
  const presence = (byName) => ({ byName, events: [] });

  it('leaves an unreachable FSP out without presence, as on Overview', () => {
    renderViz([SO, FSP('FSP01', { status: 'disconnected' })]);
    expect(screen.queryByText('FSP01')).not.toBeInTheDocument();
  });

  it('leaves out an FSP the BFF cannot reach, and marks one whose link to the SO dropped', () => {
    render(
      <MemoryRouter>
        <InstanceVisualization
          connections={[SO, FSP('FSP01', { status: 'disconnected' }), FSP('FSP02', { connectedClients: 0 }), FSP('FSP03')]}
          activity={{}}
          presence={presence({
            FSP01: { state: 'unreachable', since: Date.now() - 42000, downs: 1 },
            FSP02: { state: 'link-down', since: Date.now() - 42000, downs: 1 },
            FSP03: { state: 'up', since: null, downs: 0 },
          })}
        />
      </MemoryRouter>
    );

    expect(screen.queryByText('FSP01')).not.toBeInTheDocument();
    expect(screen.getByTestId('link-down-label-FSP02').textContent).toMatch(/^link down \u00b7 4[2-3]s$/);
    expect(screen.getByTestId('link-down-FSP02')).toBeInTheDocument();
    expect(screen.queryByTestId('link-down-FSP03')).not.toBeInTheDocument();
  });
});
