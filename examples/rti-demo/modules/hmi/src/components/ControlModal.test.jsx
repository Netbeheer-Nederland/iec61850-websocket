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
  executeApiCall: vi.fn(),
  getApiById: () => null,
}));

import ControlModal from './ControlModal';
import { executeApiCall } from '../services/apiService';

// What executeApiCall resolves to for the SO's /api/operate answer, as the BFF wraps it.
const viaBff = (answer) => ({ ok: true, status: 200, payload: { ok: true, result: answer } });

const renderModal = (props = {}) => render(
  <ControlModal
    objRef="GenericIO/GGIO1.SPCSO1"
    objName="SPCSO1"
    cdc="SPC"
    endpoint={{ host: 'rti-so', port: 5002 }}
    cp="cp2"
    onClose={() => {}}
    onSuccess={() => {}}
    {...props}
  />
);

const operate = (value = 'on') => {
  fireEvent.change(screen.getByPlaceholderText('true or false'), { target: { value } });
  fireEvent.click(screen.getByText('Operate'));
};

describe('ControlModal - operate result', () => {
  beforeEach(() => {
    executeApiCall.mockReset();
    // The ctlModel read on mount.
    executeApiCall.mockImplementation(async (apiId) => (apiId === 'read' ? viaBff({ ok: true, value: [{ data: ['enumerated', 1] }] }) : null));
  });

  it('reports success when the FSP carried the operate out', async () => {
    const onSuccess = vi.fn();
    renderModal({ onSuccess });
    executeApiCall.mockImplementationOnce(async () => viaBff({ ok: true, error: '' }));

    operate();
    await waitFor(() => expect(screen.getByText('Operate successful')).toBeInTheDocument());
    expect(onSuccess).toHaveBeenCalled();
    expect(executeApiCall).toHaveBeenLastCalledWith('operate', 'rti-so:5002', expect.objectContaining({ objRef: 'GenericIO/GGIO1.SPCSO1', value: true, cp: 'cp2' }));
  });

  it('reports the failure when the FSP refused (HTTP 200, ok: false)', async () => {
    const onSuccess = vi.fn();
    const onError = vi.fn();
    renderModal({ onSuccess, onError });
    executeApiCall.mockImplementationOnce(async () => viaBff({ ok: false, error: 'blocked-by-interlocking' }));

    operate();
    await waitFor(() => expect(screen.getByText('Operate failed: blocked-by-interlocking')).toBeInTheDocument());
    expect(onSuccess).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledWith('blocked-by-interlocking');
  });

  it('says the FSP refused when no reason came back', async () => {
    renderModal();
    executeApiCall.mockImplementationOnce(async () => viaBff({ ok: false, error: '' }));

    operate();
    await waitFor(() => expect(screen.getByText('Operate failed: Refused by the FSP')).toBeInTheDocument());
  });
});

describe('ControlModal - select (select-before-operate)', () => {
  const ctlModel = (value) => async (apiId) => (apiId === 'read' ? viaBff({ ok: true, value: [{ data: { enumerated: value } }] }) : null);

  beforeEach(() => executeApiCall.mockReset());

  it('offers no Select for a direct control', async () => {
    executeApiCall.mockImplementation(ctlModel('direct-with-normal-security'));
    renderModal();

    await waitFor(() => expect(screen.getByText('direct-with-normal-security')).toBeInTheDocument());
    expect(screen.queryByText('Select')).not.toBeInTheDocument();
  });

  it('selects an SBO control through the BFF and the SO', async () => {
    executeApiCall.mockImplementation(ctlModel('sbo-with-normal-security'));
    renderModal();
    await waitFor(() => expect(screen.getByText('Select')).toBeInTheDocument());
    executeApiCall.mockImplementationOnce(async () => viaBff({ ok: true, error: '' }));

    fireEvent.click(screen.getByText('Select'));
    await waitFor(() => expect(screen.getByText('Select successful - Now you can Operate')).toBeInTheDocument());
    expect(executeApiCall).toHaveBeenLastCalledWith('select', 'rti-so:5002', { objRef: 'GenericIO/GGIO1.SPCSO1', cp: 'cp2' });
  });

  it('reports a select the FSP refused', async () => {
    executeApiCall.mockImplementation(ctlModel('sbo-with-enhanced-security'));
    renderModal();
    await waitFor(() => expect(screen.getByText('Select')).toBeInTheDocument());
    executeApiCall.mockImplementationOnce(async () => viaBff({ ok: false, error: 'object-access-denied' }));

    fireEvent.click(screen.getByText('Select'));
    await waitFor(() => expect(screen.getByText('Select failed: object-access-denied')).toBeInTheDocument());
  });
});
