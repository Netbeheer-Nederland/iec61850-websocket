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
