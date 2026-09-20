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

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import ACSIClient from './ACSIClient';

const executeApiCall = vi.fn();
vi.mock('../services/apiService', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    executeApiCall: (...args) => executeApiCall(...args),
  };
});

const endpoint = { host: '10.0.0.2', port: 5002, name: 'so1', ws_port: 8765, cp: 'cp1' };

const renderPage = (endpointOverride = endpoint) =>
  render(
    <MemoryRouter initialEntries={[{ pathname: '/acsi-client', state: { endpoint: endpointOverride } }]}>
      <ACSIClient bffBaseUrl="http://bff.local:5000" />
    </MemoryRouter>
  );

// A minimal payload shape transformTree() can turn into a real tree: one
// LDevice ("LD0") with one LogicalNode ("LLN0") and no further children.
const modelTreeResponse = () => ({
  ok: true,
  payload: {
    result: {
      model: {
        server: { logicalDevices: ['LD0'] },
        logicalDeviceMap: { LD0: ['LLN0'] },
        logicalNodeDetails: {},
      },
    },
  },
});

beforeEach(() => {
  global.fetch = vi.fn(async (url) => {
    if (String(url).endsWith('/api/connections')) {
      return { ok: true, json: async () => ({ connections: [] }) };
    }
    return { ok: false, json: async () => ({}) };
  });

  executeApiCall.mockReset();
  executeApiCall.mockImplementation(async (apiId) => {
    if (apiId === 'properties') {
      return { ok: true, payload: { result: { acsi_client_list: ['cp1', 'cp2'] } } };
    }
    // status, oauth-status, actions-logs, etc. - benign default so the
    // mount-time effects that call these don't need per-test overrides.
    return { ok: false };
  });
});

describe('ACSIClient connection fields', () => {
  it('shows the BFF and WS addresses as read-only, populated from the endpoint', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByLabelText('BFF Host')).toHaveValue('10.0.0.2');
    });
    // Port fields are type="text" (not "number") specifically so they
    // render as plain read-only text, not a native number-input control.
    expect(screen.getByLabelText('BFF Port')).toHaveValue('5002');
    // WS Host/Port reflect the SO's own WebSocket endpoint (seeded from
    // endpoint.ws_port here; kept in sync with live status once connected).
    expect(screen.getByLabelText('WS Host')).toHaveValue('10.0.0.2');
    expect(screen.getByLabelText('WS Port')).toHaveValue('8765');
    // readOnly (not disabled): these are permanently fixed by the endpoint,
    // not a control temporarily locked mid-action - see style-guide.md's
    // "Editable vs. read-only vs. disabled fields".
    expect(screen.getByLabelText('BFF Host')).toHaveAttribute('readonly');
    expect(screen.getByLabelText('BFF Host')).not.toBeDisabled();
  });
});

describe('ACSIClient ACSI Clients accordion', () => {
  it('renders one collapsed entry per name in acsi_client_list', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('cp1')).toBeInTheDocument();
    });
    expect(screen.getByText('cp2')).toBeInTheDocument();
    // Collapsed by default - neither accordion's body (Fetch Model button)
    // is rendered until its header is clicked.
    expect(screen.queryByRole('button', { name: 'Fetch Model' })).not.toBeInTheDocument();
  });

  it('expands an entry on click, showing the unfetched placeholder', async () => {
    renderPage();
    const user = userEvent.setup({ delay: null });

    await waitFor(() => {
      expect(screen.getByText('cp1')).toBeInTheDocument();
    });
    await user.click(screen.getByText('cp1'));

    expect(screen.getByRole('button', { name: 'Fetch Model' })).toBeInTheDocument();
    expect(screen.getByText('Click "Fetch Model" to load the ACSI model tree for cp1')).toBeInTheDocument();
    // cp2 stays collapsed.
    expect(screen.queryByText(/for cp2/)).not.toBeInTheDocument();
  });

  it('fetches and renders the model tree for the clicked entry\'s own cp', async () => {
    executeApiCall.mockImplementation(async (apiId, target, body) => {
      if (apiId === 'properties') {
        return { ok: true, payload: { result: { acsi_client_list: ['cp1', 'cp2'] } } };
      }
      if (apiId === 'model-tree') {
        expect(body).toEqual({ cp: 'cp1' });
        return modelTreeResponse();
      }
      return { ok: false };
    });
    renderPage();
    const user = userEvent.setup({ delay: null });

    await waitFor(() => expect(screen.getByText('cp1')).toBeInTheDocument());
    await user.click(screen.getByText('cp1'));
    await user.click(screen.getByRole('button', { name: 'Fetch Model' }));

    await waitFor(() => {
      expect(screen.getByText('LD0')).toBeInTheDocument();
    });
    expect(
      screen.queryByText('Click "Fetch Model" to load the ACSI model tree for cp1')
    ).not.toBeInTheDocument();
  });

  it('shows an error alert when the fetch fails, without touching other entries', async () => {
    executeApiCall.mockImplementation(async (apiId) => {
      if (apiId === 'properties') {
        return { ok: true, payload: { result: { acsi_client_list: ['cp1', 'cp2'] } } };
      }
      if (apiId === 'model-tree') {
        return { ok: false, payload: { error: 'instanceNotAvailable' } };
      }
      return { ok: false };
    });
    renderPage();
    const user = userEvent.setup({ delay: null });

    await waitFor(() => expect(screen.getByText('cp1')).toBeInTheDocument());
    await user.click(screen.getByText('cp1'));
    await user.click(screen.getByRole('button', { name: 'Fetch Model' }));

    await waitFor(() => {
      expect(screen.getByText('instanceNotAvailable')).toBeInTheDocument();
    });
    // The placeholder for the (untouched) fetch is still there for cp1.
    expect(
      screen.getByText('Click "Fetch Model" to load the ACSI model tree for cp1')
    ).toBeInTheDocument();
  });

  it('keeps each cp\'s fetched tree independent of the others', async () => {
    executeApiCall.mockImplementation(async (apiId, target, body) => {
      if (apiId === 'properties') {
        return { ok: true, payload: { result: { acsi_client_list: ['cp1', 'cp2'] } } };
      }
      if (apiId === 'model-tree' && body?.cp === 'cp1') {
        return modelTreeResponse();
      }
      return { ok: false };
    });
    renderPage();
    const user = userEvent.setup({ delay: null });

    await waitFor(() => expect(screen.getByText('cp1')).toBeInTheDocument());

    // Fetch cp1's model.
    await user.click(screen.getByText('cp1'));
    await user.click(screen.getByRole('button', { name: 'Fetch Model' }));
    await waitFor(() => expect(screen.getByText('LD0')).toBeInTheDocument());

    // Expand cp2 - it should still show its own unfetched placeholder,
    // not cp1's now-fetched tree.
    await user.click(screen.getByText('cp2'));
    expect(
      screen.getByText('Click "Fetch Model" to load the ACSI model tree for cp2')
    ).toBeInTheDocument();
  });
});
