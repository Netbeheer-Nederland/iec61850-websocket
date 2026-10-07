/*
 * SPDX-FileCopyrightText: 2026 Netbeheer Nederland
 * SPDX-License-Identifier: Apache-2.0
 */

// TLSConfigModal's "From the certificate directory" selects (GET /api/certs).

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import TLSConfigModal from './TLSConfigModal';

const so = { name: 'SO', host: 'rti-so', port: 5002, type: 'RTI-SO', ws_mode: 'passive' };
const fsp = { name: 'FSP01', host: 'rti-fsp01', port: 5001, type: 'RTI-FSP', ws_mode: 'active' };

const CERTS = {
  ok: true,
  cert_dir: '/certs',
  available: true,
  files: [
    { name: 'ca.pem', reference: 'file:ca.pem', kind: 'certificate', subject: 'RTI demo CA', is_ca: true, not_after: '2036-10-06T00:00:00+00:00', sans: [] },
    { name: 'rti-so-key.pem', reference: 'file:rti-so-key.pem', kind: 'private_key' },
    { name: 'rti-so.pem', reference: 'file:rti-so.pem', kind: 'certificate', subject: 'rti-so', is_ca: false, not_after: '2028-01-09T00:00:00+00:00', sans: ['rti-so'] },
  ],
};

// Answers per URL: /api/certs, the runtime config via /api/execute, and saves.
function mockBff({ certs = CERTS, certsStatus = 200, runtime = { ok: true, enable_tls: false, ws_mode: 'passive' } } = {}) {
  global.fetch = vi.fn(async (url) => {
    if (String(url).endsWith('/api/certs')) {
      return { ok: certsStatus === 200, status: certsStatus, json: async () => certs };
    }
    const payload = String(url).endsWith('/api/execute') ? { ok: true, result: runtime } : { ok: true };
    return { ok: true, status: 200, json: async () => payload, text: async () => JSON.stringify(payload) };
  });
}

const renderModal = (connection) =>
  render(
    <TLSConfigModal isOpen onClose={() => {}} connection={connection}
      bffBaseUrl="http://bff.local:5000" wsHost={connection.host} wsPort={8765} />
  );

const optionValues = (select) => Array.from(select.options).map((o) => o.value);

describe('TLSConfigModal certificate directory', () => {
  beforeEach(() => mockBff());

  it('offers keys for the key field and non-CA certificates for the server certificate', async () => {
    renderModal(so);
    const keySelect = await waitFor(() => {
      const el = document.getElementById('tls-key-certfile');
      expect(el).not.toBeNull();
      return el;
    });
    expect(optionValues(keySelect)).toEqual(['', 'file:rti-so-key.pem']);
    expect(optionValues(document.getElementById('tls-server-cert-certfile'))).toEqual(['', 'file:rti-so.pem']);
    expect(screen.getByText(/rti-so\.pem - rti-so, expires 2028-01-09/)).toBeInTheDocument();
  });

  it('puts the file reference in the field and says where it is read from', async () => {
    renderModal(so);
    const keySelect = await waitFor(() => {
      const el = document.getElementById('tls-key-certfile');
      expect(el).not.toBeNull();
      return el;
    });
    fireEvent.change(keySelect, { target: { value: 'file:rti-so-key.pem' } });
    expect(document.getElementById('tls-key-content')).toHaveValue('file:rti-so-key.pem');
    expect(screen.getByText(/from \/certs\/rti-so-key\.pem/)).toBeInTheDocument();
  });

  it('lists every certificate, CA marked, for a client CA field', async () => {
    mockBff({ runtime: { ok: true, enable_tls: false, ws_mode: 'active' } });
    renderModal(fsp);
    const caSelect = await waitFor(() => {
      const el = document.getElementById('tls-ca-cert-certfile');
      expect(el).not.toBeNull();
      return el;
    });
    expect(optionValues(caSelect)).toEqual(['', 'file:ca.pem', 'file:rti-so.pem']);
    expect(screen.getByText(/ca\.pem - RTI demo CA \(CA\)/)).toBeInTheDocument();
  });

  it('preselects a saved reference', async () => {
    renderModal({ ...so, TLS: { enable_tls: true, tls_version: 'TLSv1_3', server_key: 'file:rti-so-key.pem', server_cert: 'file:rti-so.pem' } });
    await waitFor(() => expect(document.getElementById('tls-key-certfile')).toHaveValue('file:rti-so-key.pem'));
    expect(document.getElementById('tls-server-cert-certfile')).toHaveValue('file:rti-so.pem');
  });

  it('shows no selects when the BFF has no certificate directory', async () => {
    mockBff({ certsStatus: 404 });
    renderModal(so);
    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith('http://bff.local:5000/api/certs'));
    expect(document.getElementById('tls-key-certfile')).toBeNull();
    expect(document.getElementById('tls-key-content')).toBeInTheDocument();
  });

  it('saves the reference, not file contents', async () => {
    renderModal(so);
    const keySelect = await waitFor(() => {
      const el = document.getElementById('tls-key-certfile');
      expect(el).not.toBeNull();
      return el;
    });
    fireEvent.change(keySelect, { target: { value: 'file:rti-so-key.pem' } });
    fireEvent.change(document.getElementById('tls-server-cert-certfile'), { target: { value: 'file:rti-so.pem' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      const save = global.fetch.mock.calls.find(([url]) => String(url).endsWith('/api/connections/tls-config'));
      expect(save).toBeDefined();
      const body = JSON.parse(save[1].body);
      expect(body.server_key).toBe('file:rti-so-key.pem');
      expect(body.server_cert).toBe('file:rti-so.pem');
    });
  });
});
