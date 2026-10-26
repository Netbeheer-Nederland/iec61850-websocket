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

describe('InstanceVisualization - TLS badge', () => {
  const FSP = { name: 'FSP01', type: 'RTI-FSP', status: 'connected', host: 'h', port: 1, connectedClients: 1 };

  it('badges the SO and an FSP whose stored TLS is on, with the version', () => {
    renderViz([
      { ...SO, TLS: { enable_tls: true, tls_version: 'TLSv1_3' } },
      { ...FSP, TLS: { enable_tls: true, tls_version: 'TLSv1_2' } },
    ]);

    expect(screen.getByTestId('tls-badge-SO').title).toBe('Secure transport: WebSocket over TLS 1.3 (wss)');
    expect(screen.getByTestId('tls-badge-FSP01').title).toBe('Secure transport: WebSocket over TLS 1.2 (wss)');
    expect(screen.getByTestId('tls-badge-FSP01').textContent).toBe('TLS');
  });

  it('draws no badge for plain WS or a connection without TLS config', () => {
    renderViz([
      { ...SO, TLS: { enable_tls: false, tls_version: 'TLSv1_2' } },
      { ...FSP },
    ]);

    expect(screen.queryByTestId('tls-badge-SO')).not.toBeInTheDocument();
    expect(screen.queryByTestId('tls-badge-FSP01')).not.toBeInTheDocument();
  });
});

describe('InstanceVisualization - OAuth badge', () => {
  const FSP = { name: 'FSP01', type: 'RTI-FSP', status: 'connected', host: 'h', port: 1, connectedClients: 1 };

  it('badges the SO and an FSP whose stored OAuth is on, by role', () => {
    renderViz([
      { ...SO, OAuth: { enable_oauth: true, idp_server: 'keycloak' } },
      { ...FSP, OAuth: { enable_oauth: true, client_id: 'rti-fsp', client_secret: 'x' } },
    ]);

    expect(screen.getByTestId('oauth-badge-SO').title)
      .toBe("Authenticated: validates the FSPs' OAuth 2.0 access tokens (keycloak)");
    expect(screen.getByTestId('oauth-badge-FSP01').title)
      .toBe('Authenticated: presents an OAuth 2.0 access token to the SO');
    expect(screen.getByTestId('oauth-badge-FSP01').textContent).toBe('OAuth');
  });

  it('draws no badge when OAuth is off or not configured', () => {
    renderViz([
      { ...SO, OAuth: { enable_oauth: false, idp_server: 'keycloak' } },
      { ...FSP },
    ]);

    expect(screen.queryByTestId('oauth-badge-SO')).not.toBeInTheDocument();
    expect(screen.queryByTestId('oauth-badge-FSP01')).not.toBeInTheDocument();
  });

  it('sits alongside the TLS badge when both are on', () => {
    renderViz([{ ...SO, TLS: { enable_tls: true, tls_version: '1.3' }, OAuth: { enable_oauth: true } }]);

    expect(screen.getByTestId('tls-badge-SO').style.top).toBe('-4px');
    expect(screen.getByTestId('oauth-badge-SO').style.bottom).toBe('-4px');
  });
});

describe('InstanceVisualization - plugin badge', () => {
  const FSP = { name: 'FSP01', type: 'RTI-FSP', status: 'connected', host: 'h', port: 1, connectedClients: 1 };
  const io = { name: 'dr_panel', claims: [], healthy: true, last_error: null };

  it('counts the plugins, green while all are connected and running', () => {
    renderViz([{ ...SO, plugins: { plugins: [io], failed: {} } }]);

    const badge = screen.getByTestId('plugin-badge-SO');
    expect(badge.textContent).toBe('1');
    expect(badge.title).toBe('1 plugin, all connected and running');
    expect(badge.style.background).toBe('var(--success-color)');
    expect(badge.style.right).toBe('-4px');
  });

  it('turns red and names the problem when a plugin is disconnected', () => {
    renderViz([{ ...FSP, plugins: { plugins: [{ ...io, healthy: false, last_error: 'timed out' }], failed: { display: "Can't reach http://pi:8000/plugin" } } }]);

    const badge = screen.getByTestId('plugin-badge-FSP01');
    expect(badge.textContent).toBe('2');
    expect(badge.style.background).toBe('var(--danger-color)');
    expect(badge.title).toBe("Plugins: dr_panel connected, its last event or Operate failed - timed out; display disconnected - Can't reach http://pi:8000/plugin");
  });

  it('turns orange while a connected plugin is unhealthy', () => {
    renderViz([{ ...FSP, plugins: { plugins: [{ ...io, healthy: false, last_error: 'timed out' }], failed: {} } }]);
    expect(screen.getByTestId('plugin-badge-FSP01').style.background).toBe('var(--warning-color)');
  });

  it('draws nothing without plugins, or while their status is unknown', () => {
    renderViz([{ ...SO, plugins: { plugins: [], failed: {} } }, { ...FSP, plugins: null }]);

    expect(screen.queryByTestId('plugin-badge-SO')).not.toBeInTheDocument();
    expect(screen.queryByTestId('plugin-badge-FSP01')).not.toBeInTheDocument();
  });
});

describe('InstanceVisualization - attached boxes (decision 0025)', () => {
  const attached = { plugins: [{ name: 'dr_panel', healthy: true, attached: [{ kind: 'io', label: 'IO server', state: 'ok', live: [] }] }], failed: {} };
  const FSP = { name: 'FSP01', type: 'RTI-FSP', status: 'connected', host: 'rti-fsp01', port: 5001, plugins: attached };

  it('draws them next to the SO and FSP when asked to', () => {
    render(
      <MemoryRouter>
        <InstanceVisualization connections={[{ ...SO, plugins: attached }, FSP]} showAttached />
      </MemoryRouter>
    );
    expect(screen.getByTestId('attached-SO')).toHaveTextContent('IO server');
    expect(screen.getByTestId('attached-FSP01')).toHaveTextContent('IO server');
  });

  it('leaves them out by default (Model, Traffic)', () => {
    renderViz([{ ...SO, plugins: attached }, FSP]);
    expect(screen.queryByTestId('attached-SO')).not.toBeInTheDocument();
    expect(screen.queryByTestId('attached-FSP01')).not.toBeInTheDocument();
  });
});
