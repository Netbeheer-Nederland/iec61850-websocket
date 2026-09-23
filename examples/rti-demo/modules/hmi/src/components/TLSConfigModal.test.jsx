/*
 * SPDX-FileCopyrightText: 2025 Netbeheer Nederland
 * SPDX-License-Identifier: Apache-2.0
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import TLSConfigModal from './TLSConfigModal';

const connection = { name: 'SO', host: 'rti-so', port: 5002, type: 'RTI-SO', ws_mode: 'passive' };

describe('TLSConfigModal', () => {
  beforeEach(() => {
    // /api/execute wraps the instance's own response under `result`.
    global.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({
        ok: true,
        target: 'rti-so:5002',
        result: {
          ok: true,
          enable_tls: true,
          tls_version: '1.3',
          server_key: 'KEY-PEM',
          server_cert: 'CERT-PEM',
          server_ca: null,
          ws_mode: 'passive',
        },
      }),
    }));
  });

  it('populates the form from the runtime config returned through /api/execute', async () => {
    render(
      <TLSConfigModal isOpen onClose={() => {}} connection={connection}
        bffBaseUrl="http://bff.local:5000" wsHost="rti-so" wsPort={8765} />
    );

    await waitFor(() => {
      expect(document.getElementById('tls-enable')).toBeChecked();
    });
    expect(document.getElementById('tls-version')).toHaveValue('1.3');
    expect(document.getElementById('tls-key-content')).toHaveValue('KEY-PEM');
    expect(document.getElementById('tls-server-cert-content')).toHaveValue('CERT-PEM');
    expect(global.fetch).toHaveBeenCalledWith('http://bff.local:5000/api/execute', expect.objectContaining({
      body: JSON.stringify({ target: 'rti-so:5002', method: 'GET', path: '/api/tls-config' }),
    }));
  });

  it('keeps the saved version and certificates while the runtime has TLS off', async () => {
    global.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({
        ok: true,
        result: { ok: true, enable_tls: false, tls_version: '1.2', server_key: null, server_cert: null, ws_mode: 'passive' },
      }),
    }));
    const saved = {
      ...connection,
      TLS: { enable_tls: true, tls_version: 'TLSv1_3', server_key: 'SAVED-KEY', server_cert: 'SAVED-CERT' },
    };
    render(
      <TLSConfigModal isOpen onClose={() => {}} connection={saved}
        bffBaseUrl="http://bff.local:5000" wsHost="rti-so" wsPort={8765} />
    );

    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
    await waitFor(() => expect(document.getElementById('tls-enable')).not.toBeChecked());
    expect(document.getElementById('tls-version')).toHaveValue('1.3');
    expect(document.getElementById('tls-key-content')).toHaveValue('SAVED-KEY');
    expect(document.getElementById('tls-server-cert-content')).toHaveValue('SAVED-CERT');
  });

  it('says the setting applies on next Connect when the FSP is disconnected', async () => {
    const fsp = { name: 'FSP01', host: 'rti-fsp01', port: 5001, type: 'RTI-FSP', ws_mode: 'active',
      TLS: { enable_tls: true, tls_version: 'TLSv1_3', server_ca: 'CA-PEM' } };
    global.fetch = vi.fn(async (url, init) => {
      const body = init?.body ? JSON.parse(init.body) : {};
      const reply = (payload) => ({ ok: true, status: 200, text: async () => JSON.stringify(payload) });
      if (String(url).endsWith('/api/connections/tls-config')) return reply({ ok: true });
      if (body.path === '/api/tls-config') {
        return reply({ ok: true, result: { ok: true, enable_tls: false, tls_version: '1.2', ws_mode: 'active' } });
      }
      return reply({ ok: true, result: { ok: true, status: 'saved', enable_tls: true } });
    });
    const onSuccess = vi.fn();
    render(
      <TLSConfigModal isOpen onClose={() => {}} connection={fsp} onSuccess={onSuccess}
        bffBaseUrl="http://bff.local:5000" wsHost="rti-so" wsPort={8765} />
    );
    await waitFor(() => expect(document.getElementById('tls-ca-cert-content')).toHaveValue('CA-PEM'));
    document.getElementById('tls-enable').click();
    await waitFor(() => expect(document.getElementById('tls-enable')).toBeChecked());

    screen.getByRole('button', { name: 'Save' }).click();

    await waitFor(() => expect(onSuccess).toHaveBeenCalledWith('TLS config saved for FSP01 - applies on next Connect'));
  });
});
