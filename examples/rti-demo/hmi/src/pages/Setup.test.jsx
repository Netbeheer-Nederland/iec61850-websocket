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
});
