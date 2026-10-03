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
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('../services/apiService', () => ({
  executeApiCall: vi.fn(async () => ({ ok: true, payload: {} })),
  buildTargetValue: (host, port) => `${host}:${port}`,
}));

import DemoActionsBar from './DemoActionsBar';
import { executeApiCall } from '../services/apiService';
import { saveActions, loadActions } from '../utils/demoActions';
import { resetDemoActionsStore } from '../hooks/useDemoActions';

const SO = {
  name: 'Demo_SO', type: 'RTI-SO', status: 'connected', host: 'so', port: 5002,
  fspLinks: [{ cp: 'cp1', fsp: 'FSP_North' }, { cp: 'cp2', fsp: 'FSP_South' }],
};
const action = (id, label, cp, fspName, extra = {}) => ({
  id, label, service: 'read', soTarget: 'so:5002', soName: 'Demo_SO', cp, fspName, objRef: `LD0/X${id}.stVal`, fc: 'st', ...extra,
});

const pin = (list) => {
  saveActions(list);
  resetDemoActionsStore();
};

describe('DemoActionsBar', () => {
  beforeEach(() => {
    localStorage.clear();
    resetDemoActionsStore();
    executeApiCall.mockClear();
  });

  it('explains how to pin when there are no actions', () => {
    render(<DemoActionsBar connections={[SO]} />);
    expect(screen.getByText(/No demo actions yet/)).toBeInTheDocument();
  });

  it('shows a row per FSP, and All FSPs only for labels on more than one FSP', () => {
    pin([action('1', 'Read status', 'cp1', 'FSP_North'), action('2', 'Read status', 'cp2', 'FSP_South'), action('3', 'Only north', 'cp1', 'FSP_North')]);
    render(<DemoActionsBar connections={[SO]} />);

    expect(screen.getByTestId('demo-row-FSP_North').textContent).toContain('Only north');
    expect(screen.getByTestId('demo-row-FSP_South').textContent).toContain('Read status');
    expect(screen.getByText('Read status (2)')).toBeInTheDocument();
    expect(screen.queryByText(/Only north \(/)).not.toBeInTheDocument();
  });

  it("All FSPs runs each FSP's own action through the SO", async () => {
    pin([action('1', 'Read status', 'cp1', 'FSP_North'), action('2', 'Read status', 'cp2', 'FSP_South')]);
    render(<DemoActionsBar connections={[SO]} />);

    fireEvent.click(screen.getByText('Read status (2)'));
    await waitFor(() => expect(executeApiCall).toHaveBeenCalledTimes(2));
    expect(executeApiCall).toHaveBeenCalledWith('read', 'so:5002', { objRef: 'LD0/X1.stVal', fc: 'st', cp: 'cp1' });
    expect(executeApiCall).toHaveBeenCalledWith('read', 'so:5002', { objRef: 'LD0/X2.stVal', fc: 'st', cp: 'cp2' });
    await waitFor(() => expect(screen.getAllByText('✓')).toHaveLength(2));
  });

  it('marks a failed run and keeps the reason in the tooltip', async () => {
    executeApiCall.mockResolvedValueOnce({ ok: false, payload: { error: 'not associated' } });
    pin([action('1', 'Read status', 'cp1', 'FSP_North')]);
    render(<DemoActionsBar connections={[SO]} />);

    fireEvent.click(screen.getByText('Read status'));
    await waitFor(() => expect(screen.getByText('✗')).toBeInTheDocument());
    expect(screen.getByText('Read status').closest('button').title).toContain('Last run failed: not associated');
  });

  it('disables actions whose SO or cp is not connected', () => {
    pin([action('1', 'Gone', 'cp9', 'FSP_Old'), action('2', 'Here', 'cp1', 'FSP_North')]);
    render(<DemoActionsBar connections={[SO]} />);

    expect(screen.getByText('Gone').closest('button')).toBeDisabled();
    expect(screen.getByText('Here').closest('button')).not.toBeDisabled();

    render(<DemoActionsBar connections={[{ ...SO, status: 'disconnected' }]} />);
    expect(screen.getAllByText('Here')[1].closest('button')).toBeDisabled();
  });

  it('removes an action in Edit mode, and narrows to the focused FSP', () => {
    pin([action('1', 'A', 'cp1', 'FSP_North'), action('2', 'B', 'cp2', 'FSP_South')]);
    const { rerender } = render(<DemoActionsBar connections={[SO]} />);

    fireEvent.click(screen.getByTitle('Remove pinned actions'));
    fireEvent.click(screen.getByTitle('Unpin "A"'));
    expect(loadActions().map((a) => a.id)).toEqual(['2']);
    expect(screen.queryByTestId('demo-row-FSP_North')).not.toBeInTheDocument();

    pin([action('1', 'A', 'cp1', 'FSP_North'), action('2', 'B', 'cp2', 'FSP_South')]);
    rerender(<DemoActionsBar connections={[SO]} focusedFsp="FSP_North" />);
    expect(screen.queryByTestId('demo-row-FSP_South')).not.toBeInTheDocument();
  });
});
