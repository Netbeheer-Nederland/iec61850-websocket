/*
 * SPDX-FileCopyrightText: 2025 Netbeheer Nederland
 * SPDX-License-Identifier: Apache-2.0
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import OAuthConfigModal from './OAuthConfigModal';

const executeApiCall = vi.fn();
vi.mock('../services/apiService', async (importOriginal) => ({
  ...(await importOriginal()),
  executeApiCall: (...args) => executeApiCall(...args),
}));

const IDP = { name: 'IDP', type: 'IDP-Server', endpoint: 'http://keycloak:8080', status: 'connected' };
const SO = { name: 'SO', host: 'rti-so', port: 5002, type: 'RTI-SO', ws_mode: 'passive', OAuth: {} };
const FSP = {
  name: 'FSP01', host: 'rti-fsp01', port: 5001, type: 'RTI-FSP', ws_mode: 'active',
  OAuth: { enable_oauth: false, idp_server: 'IDP', realm: 'iec61850-test', client_id: 'ws-client', client_secret: 's3cret' },
};
const DISCOVERY = {
  ok: true,
  issuer: 'http://localhost:8080/realms/iec61850-test',
  certificate_endpoint: 'http://keycloak:8080/realms/iec61850-test/protocol/openid-connect/certs',
  token_endpoint: 'http://keycloak:8080/realms/iec61850-test/protocol/openid-connect/token',
};

let savedBodies;
beforeEach(() => {
  savedBodies = [];
  global.fetch = vi.fn(async (url, init) => {
    if (String(url).includes('/api/idp/discovery')) return { ok: true, json: async () => DISCOVERY };
    if (String(url).endsWith('/api/connections/oauth-config')) {
      savedBodies.push(JSON.parse(init.body));
      return { ok: true, json: async () => ({ ok: true }) };
    }
    return { ok: false, json: async () => ({}) };
  });
  executeApiCall.mockReset();
  executeApiCall.mockImplementation(async (apiId) => {
    if (apiId === 'oauth-status') return { ok: true, payload: { result: { ok: true, enable_oauth: false } } };
    if (apiId === 'reconfig-oauth') return { ok: true, payload: { result: { ok: true } } };
    return { ok: false };
  });
});

const renderModal = (props) => render(
  <OAuthConfigModal isOpen onClose={() => {}} connections={[IDP]} bffBaseUrl="http://bff.local:5000" {...props} />
);

describe('OAuthConfigModal', () => {
  it('fills the SO endpoints from discovery and applies them to the SO', async () => {
    const onSuccess = vi.fn();
    const user = userEvent.setup({ delay: null });
    renderModal({ connection: SO, target: 'rti-so:5002', onSuccess });

    await user.click(document.getElementById('oauth-enable'));
    await user.selectOptions(document.getElementById('oauth-idp-server'), 'IDP');
    await user.type(document.getElementById('oauth-realm'), 'iec61850-test');
    await user.click(document.getElementById('oauth-discover'));

    // The IDP's own issuer (KC_HOSTNAME), not one built from its address.
    await waitFor(() => expect(document.getElementById('oauth-issuer-url')).toHaveValue(DISCOVERY.issuer));
    expect(document.getElementById('oauth-cert-url')).toHaveValue(DISCOVERY.certificate_endpoint);

    await user.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(onSuccess).toHaveBeenCalledWith('OAuth enabled for SO'));
    const expected = expect.objectContaining({
      connection_name: 'SO', enable_oauth: true, ws_mode: 'passive', idp_server: 'IDP', realm: 'iec61850-test',
      certificate_endpoint_url: DISCOVERY.certificate_endpoint, token_issuer_url: DISCOVERY.issuer,
    });
    expect(savedBodies).toEqual([expected]);
    expect(executeApiCall).toHaveBeenCalledWith('reconfig-oauth', 'rti-so:5002', expected);
  });

  it('tells a disconnected FSP, which keeps the setting for its next Connect', async () => {
    executeApiCall.mockImplementation(async (apiId) => {
      if (apiId === 'oauth-status') return { ok: true, payload: { result: { ok: true, enable_oauth: false } } };
      // A stopped FSP stores the setting instead of dialing out.
      if (apiId === 'reconfig-oauth') return { ok: true, payload: { result: { ok: true, status: 'saved' } } };
      return { ok: false };
    });
    const onSuccess = vi.fn();
    const user = userEvent.setup({ delay: null });
    renderModal({ connection: FSP, wsMode: 'active', target: 'rti-fsp01:5001', runtimeBody: { host: 'rti-so', port: '8765', cp: 'cp1' }, onSuccess });

    await waitFor(() => expect(document.getElementById('oauth-client-id')).toHaveValue('ws-client'));
    await user.click(document.getElementById('oauth-enable'));
    await user.click(document.getElementById('oauth-discover'));
    await waitFor(() => expect(document.getElementById('oauth-token-url')).toHaveValue(DISCOVERY.token_endpoint));
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(onSuccess).toHaveBeenCalledWith('OAuth config saved for FSP01 - applies on next Connect'));
    expect(savedBodies[0]).toEqual(expect.objectContaining({
      ws_mode: 'active', enable_oauth: true, token_endpoint_url: DISCOVERY.token_endpoint,
      client_id: 'ws-client', client_secret: 's3cret',
    }));
    expect(executeApiCall).toHaveBeenCalledWith('reconfig-oauth', 'rti-fsp01:5001', expect.objectContaining({
      enable_oauth: true, ws_mode: 'active', host: 'rti-so', port: '8765', cp: 'cp1',
    }));
  });

  it('turns OAuth off on the FSP even while it is disconnected', async () => {
    // The off switch used to stop at the BFF for a disconnected FSP, so the
    // FSP itself - and the "(On)" button - stayed on.
    let runtimeOn = true;
    executeApiCall.mockImplementation(async (apiId, target, body) => {
      if (apiId === 'oauth-status') return { ok: true, payload: { result: { ok: true, enable_oauth: runtimeOn } } };
      if (apiId === 'reconfig-oauth') {
        runtimeOn = body.enable_oauth;
        return { ok: true, payload: { result: { ok: true, status: 'saved' } } };
      }
      return { ok: false };
    });
    const onSuccess = vi.fn();
    const user = userEvent.setup({ delay: null });
    renderModal({ connection: { ...FSP, OAuth: { ...FSP.OAuth, enable_oauth: true } }, wsMode: 'active', target: 'rti-fsp01:5001', onSuccess });

    await waitFor(() => expect(document.getElementById('oauth-enable')).toBeChecked());
    await user.click(document.getElementById('oauth-enable'));
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(savedBodies[0].enable_oauth).toBe(false);
    expect(runtimeOn).toBe(false);
  });

  it('refuses to enable OAuth while the selected IDP server is unavailable', async () => {
    const onError = vi.fn();
    const user = userEvent.setup({ delay: null });
    render(
      <OAuthConfigModal isOpen onClose={() => {}} connection={SO} target="rti-so:5002" onError={onError}
        connections={[{ ...IDP, status: 'disconnected' }]} bffBaseUrl="http://bff.local:5000" />
    );

    await user.click(document.getElementById('oauth-enable'));
    await user.selectOptions(document.getElementById('oauth-idp-server'), 'IDP');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText('IDP server unavailable')).toBeInTheDocument();
    expect(onError).toHaveBeenCalledWith('IDP server unavailable');
    expect(savedBodies).toEqual([]);
  });
});
