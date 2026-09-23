import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Setup from './Setup';

const user = () => userEvent.setup({ delay: null });

const renderSetup = (connections = []) =>
  render(
    <MemoryRouter>
      <Setup
        settings={{ bffHost: 'localhost', bffPort: '5000' }}
        connections={connections}
        loading={false}
        onReload={() => {}}
      />
    </MemoryRouter>
  );

beforeEach(() => {
  global.fetch = vi.fn(async () => ({ ok: true, json: async () => ({}) }));
});

describe('Setup page - Register/Edit Instance modal', () => {
  it('shows WS Port (and BFF Port) for a new RTI-SO instance', async () => {
    renderSetup();
    const u = user();

    await u.click(screen.getByRole('button', { name: /register instance/i }));

    expect(screen.getByLabelText('WS Port')).toBeInTheDocument();
    expect(screen.getByLabelText('BFF Port')).toBeInTheDocument();
  });

  it('leaves WS Port blank when editing an RTI-SO connection that has none set (not a fabricated 8765)', async () => {
    renderSetup([
      { name: 'so1', host: '10.0.0.1', port: 5002, type: 'RTI-SO', acsi: 'client', ws_mode: 'passive', status: 'connected' },
    ]);
    const u = user();

    await u.click(screen.getByRole('button', { name: 'Edit' }));

    // Must be genuinely blank, not a fake-looking pre-filled default - an
    // unconfigured instance should look unconfigured.
    expect(screen.getByLabelText('WS Port')).toHaveValue(null);
  });

  it('pre-fills WS Port with the real value when the connection has one', async () => {
    renderSetup([
      { name: 'so1', host: '10.0.0.1', port: 5002, ws_port: 9001, type: 'RTI-SO', acsi: 'client', ws_mode: 'passive', status: 'connected' },
    ]);
    const u = user();

    await u.click(screen.getByRole('button', { name: 'Edit' }));

    expect(screen.getByLabelText('WS Port')).toHaveValue(9001);
  });

  it('labels RTI-FSP\'s port "BFF Port" too, same as RTI-SO, but without a WS Port field', async () => {
    renderSetup();
    const u = user();

    await u.click(screen.getByRole('button', { name: /register instance/i }));
    await u.selectOptions(screen.getByLabelText('Type'), 'RTI-FSP');

    expect(screen.getByLabelText('BFF Port')).toBeInTheDocument();
    expect(screen.queryByLabelText('WS Port')).not.toBeInTheDocument();
  });

  it('shows ACSI/WebSocket Mode as read-only text (not a dropdown) for RTI-SO', async () => {
    renderSetup();
    const u = user();

    await u.click(screen.getByRole('button', { name: /register instance/i }));

    const acsi = screen.getByLabelText('ACSI');
    const wsMode = screen.getByLabelText('WebSocket Mode');
    expect(acsi.tagName).toBe('INPUT');
    expect(acsi).toHaveAttribute('readonly');
    expect(acsi).toHaveValue('Client');
    expect(wsMode.tagName).toBe('INPUT');
    expect(wsMode).toHaveAttribute('readonly');
    expect(wsMode).toHaveValue('Passive');
  });

  it('shows ACSI/WebSocket Mode as read-only text for RTI-FSP too', async () => {
    renderSetup();
    const u = user();

    await u.click(screen.getByRole('button', { name: /register instance/i }));
    await u.selectOptions(screen.getByLabelText('Type'), 'RTI-FSP');

    const acsi = screen.getByLabelText('ACSI');
    const wsMode = screen.getByLabelText('WebSocket Mode');
    expect(acsi.tagName).toBe('INPUT');
    expect(acsi).toHaveValue('Server');
    expect(wsMode.tagName).toBe('INPUT');
    expect(wsMode).toHaveValue('Active');
  });

  it('keeps ACSI/WebSocket Mode as real, editable dropdowns for Custom', async () => {
    renderSetup();
    const u = user();

    await u.click(screen.getByRole('button', { name: /register instance/i }));
    await u.selectOptions(screen.getByLabelText('Type'), 'Custom');

    const acsi = screen.getByLabelText('ACSI');
    const wsMode = screen.getByLabelText('WebSocket Mode');
    expect(acsi.tagName).toBe('SELECT');
    expect(acsi).toBeEnabled();
    expect(wsMode.tagName).toBe('SELECT');
    expect(wsMode).toBeEnabled();
  });
});

describe('Setup page - table sorting', () => {
  it('sorts by a clicked column, toggling direction on repeat clicks', async () => {
    renderSetup([
      { name: 'so2', host: '10.0.0.2', port: 5002, type: 'RTI-SO', status: 'connected' },
      { name: 'so1', host: '10.0.0.1', port: 5001, type: 'RTI-SO', status: 'connected' },
    ]);
    const u = user();

    const nameCells = () => screen.getAllByRole('row').slice(1).map((r) => r.cells[1].textContent);
    expect(nameCells()).toEqual(['so2', 'so1']);

    await u.click(screen.getByRole('columnheader', { name: /^Name/ }));
    expect(nameCells()).toEqual(['so1', 'so2']);

    await u.click(screen.getByRole('columnheader', { name: /^Name/ }));
    expect(nameCells()).toEqual(['so2', 'so1']);
  });

  it('sorts BFF Port numerically, not lexicographically', async () => {
    renderSetup([
      { name: 'a', host: '10.0.0.1', port: 10001, type: 'RTI-SO', status: 'connected' },
      { name: 'b', host: '10.0.0.2', port: 9000, type: 'RTI-SO', status: 'connected' },
    ]);
    const u = user();

    await u.click(screen.getByRole('columnheader', { name: /^BFF Port/ }));

    const nameCells = screen.getAllByRole('row').slice(1).map((r) => r.cells[1].textContent);
    expect(nameCells).toEqual(['b', 'a']);
  });
});

describe('Setup page - saving connections', () => {
  const lastSaveBody = () => {
    const call = global.fetch.mock.calls.find(([url]) => String(url).includes('/api/add-connection'));
    return JSON.parse(call[1].body);
  };

  it('omits ws_port entirely when saving an RTI-FSP (it has no such property)', async () => {
    renderSetup();
    const u = user();

    await u.click(screen.getByRole('button', { name: /register instance/i }));
    await u.selectOptions(screen.getByLabelText('Type'), 'RTI-FSP');
    await u.type(screen.getByLabelText('Name'), 'fsp1');
    await u.type(screen.getByLabelText('Host'), '10.0.0.2');

    await u.click(screen.getByRole('button', { name: /save instance/i }));

    // Previously sent as "" (leftover from the shared initial formData),
    // which the backend's Optional[int] field rejected outright:
    // {"detail":[{"type":"int_parsing", ..., "input":""}]}.
    expect(lastSaveBody()).not.toHaveProperty('ws_port');
  });

  it('defaults ws_port for an RTI-SO connection left blank, instead of sending ""', async () => {
    renderSetup();
    const u = user();

    await u.click(screen.getByRole('button', { name: /register instance/i }));
    await u.type(screen.getByLabelText('Name'), 'so1');
    await u.type(screen.getByLabelText('Host'), '10.0.0.1');
    // WS Port left untouched (blank).

    await u.click(screen.getByRole('button', { name: /save instance/i }));

    expect(lastSaveBody().ws_port).toBe(8765);
  });

  it('keeps a real ws_port value the user entered for RTI-SO', async () => {
    renderSetup();
    const u = user();

    await u.click(screen.getByRole('button', { name: /register instance/i }));
    await u.type(screen.getByLabelText('Name'), 'so1');
    await u.type(screen.getByLabelText('Host'), '10.0.0.1');
    const wsPortInput = screen.getByLabelText('WS Port');
    await u.clear(wsPortInput);
    await u.type(wsPortInput, '9001');

    await u.click(screen.getByRole('button', { name: /save instance/i }));

    expect(lastSaveBody().ws_port).toBe(9001);
  });
});

describe('Setup page - OAuth settings moved to the OAuth Config dialog', () => {
  const OAUTH_FIELDS = ['IDP Server', 'Realm', 'Certificate Endpoint', 'Auth Server CA', 'Token Issuer URL',
    'Token Endpoint', 'Client ID', 'Client Secret', 'Enable Token Refresh'];

  it.each(['RTI-SO', 'RTI-FSP'])('shows no OAuth fields for %s', async (type) => {
    renderSetup();
    const u = user();

    await u.click(screen.getByRole('button', { name: /register instance/i }));
    await u.selectOptions(screen.getByLabelText('Type'), type);

    for (const label of OAUTH_FIELDS) {
      expect(screen.queryByLabelText(label)).not.toBeInTheDocument();
    }
  });

  it('leaves a connection\'s saved OAuth settings alone when editing it', async () => {
    renderSetup([
      {
        name: 'so1', host: '10.0.0.1', port: 5002, ws_port: 8765, type: 'RTI-SO', acsi: 'client', ws_mode: 'passive',
        status: 'connected', OAuth: { enable_oauth: true, realm: 'iec61850-test', token_issuer: 'http://localhost:8080/realms/iec61850-test' },
      },
    ]);
    const u = user();

    await u.click(screen.getByRole('button', { name: 'Edit' }));
    await u.click(screen.getByRole('button', { name: /save instance/i }));

    const call = global.fetch.mock.calls.find(([url]) => String(url).includes('/api/edit-connection/so1'));
    const body = JSON.parse(call[1].body);
    // Omitted fields are left untouched by the BFF's edit-connection.
    for (const field of ['realm', 'certificate_endpoint', 'token_issuer_url', 'auth_server_ca', 'token_endpoint',
      'client_id', 'client_secret', 'enable_token_refresh', 'idp_server']) {
      expect(body).not.toHaveProperty(field);
    }
  });
});
