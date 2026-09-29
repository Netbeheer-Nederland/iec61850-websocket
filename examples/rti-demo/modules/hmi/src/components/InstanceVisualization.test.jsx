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
