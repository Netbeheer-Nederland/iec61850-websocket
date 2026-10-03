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

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Traffic from './Traffic';

// Isolate Traffic.jsx's own endpoint-filtering logic from what these
// components actually do (network polling, navigation, model fetches) -
// each stub just renders its `title`/a marker so the assertions below can
// tell which endpoints Traffic decided to render a monitor for.
vi.mock('../components/MessageMonitor', () => ({
  default: ({ title }) => <div data-testid="message-monitor">{title}</div>,
}));
// Exposes its select callbacks as buttons, so focusing can be driven here.
vi.mock('../components/InstanceVisualization', () => ({
  default: ({ connections = [], onFspSelect, onSoSelect }) => (
    <div data-testid="instance-visualization">
      {connections.filter((c) => c.type === 'RTI-FSP').map((c) => (
        <button key={c.name} onClick={() => onFspSelect?.(c)}>{`focus ${c.name}`}</button>
      ))}
      <button onClick={() => onSoSelect?.()}>focus SO</button>
    </div>
  ),
}));
vi.mock('../components/DataAccessPanel', () => ({
  default: () => <div data-testid="data-access-panel" />,
}));

const renderTraffic = (connections) =>
  render(
    <MemoryRouter>
      <Traffic settings={{}} getModel={() => {}} updateModel={() => {}} connections={connections} />
    </MemoryRouter>
  );

const SO = { name: 'SO', type: 'RTI-SO', status: 'connected', host: 'rti-so', port: 5002 };
const fsp = (name, connectedClients) => ({
  name,
  type: 'RTI-FSP',
  status: 'connected',
  host: `${name}-host`,
  port: 5001,
  connectedClients,
});

describe('Traffic - Message Monitors only lists FSPs with an active connection', () => {
  it('lists an FSP with at least one connected client', () => {
    renderTraffic([SO, fsp('FSP01', 1)]);

    expect(screen.getByText('FSP01')).toBeInTheDocument();
  });

  it('omits an FSP with zero connected clients', () => {
    renderTraffic([SO, fsp('FSP01', 0)]);

    expect(screen.queryByText('FSP01')).not.toBeInTheDocument();
  });

  it('omits an FSP whose connectedClients is missing entirely', () => {
    const { connectedClients, ...fspWithoutCount } = fsp('FSP01', 0);
    renderTraffic([SO, fspWithoutCount]);

    expect(screen.queryByText('FSP01')).not.toBeInTheDocument();
  });

  it('omits a disconnected FSP even with a stale positive connectedClients', () => {
    renderTraffic([SO, { ...fsp('FSP01', 3), status: 'disconnected' }]);

    expect(screen.queryByText('FSP01')).not.toBeInTheDocument();
  });

  it('only lists the FSPs that qualify, alongside connected SOs (unaffected by this filter)', () => {
    renderTraffic([SO, fsp('FSP01', 2), fsp('FSP02', 0), fsp('FSP03', 1)]);

    expect(screen.getByText('SO')).toBeInTheDocument();
    expect(screen.getByText('FSP01')).toBeInTheDocument();
    expect(screen.queryByText('FSP02')).not.toBeInTheDocument();
    expect(screen.getByText('FSP03')).toBeInTheDocument();
  });
});

describe('Traffic - focusing an FSP link', () => {
  const all = () => [SO, fsp('FSP01', 1), fsp('FSP02', 1)];
  const monitors = () => screen.getAllByTestId('message-monitor').map((m) => m.textContent);

  it('lists only the focused FSP monitor, and shows all again on a second click', () => {
    renderTraffic(all());

    fireEvent.click(screen.getByText('focus FSP02'));
    expect(monitors()).toEqual(['SO', 'FSP02']);
    expect(screen.getByText(/Focused on/)).toBeInTheDocument();

    fireEvent.click(screen.getByText('focus FSP02'));
    expect(monitors()).toEqual(['SO', 'FSP01', 'FSP02']);
    expect(screen.queryByText(/Focused on/)).not.toBeInTheDocument();
  });

  it('clears the focus from the SO or the Show all button', () => {
    renderTraffic(all());

    fireEvent.click(screen.getByText('focus FSP01'));
    fireEvent.click(screen.getByText('focus SO'));
    expect(monitors()).toEqual(['SO', 'FSP01', 'FSP02']);

    fireEvent.click(screen.getByText('focus FSP01'));
    fireEvent.click(screen.getByTitle('Show all links'));
    expect(monitors()).toEqual(['SO', 'FSP01', 'FSP02']);
  });

  it('keeps the SO monitor listed while an FSP is focused', () => {
    renderTraffic(all());

    fireEvent.click(screen.getByText('focus FSP01'));
    expect(monitors()).toEqual(['SO', 'FSP01']);
  });
});
