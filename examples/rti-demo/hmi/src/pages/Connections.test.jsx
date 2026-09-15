import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Connections from './Connections';

const setup = (connections = []) => {
  const setConnections = vi.fn();
  const utils = render(
    <Connections connections={connections} setConnections={setConnections} />
  );
  return { ...utils, setConnections };
};

const user = () => userEvent.setup({ delay: null });

describe('Connections page - Add/Edit modal', () => {
  it('typing in a field actually updates its value (regression: DOM id vs formData key mismatch)', async () => {
    const { setConnections } = setup();
    const u = user();

    await u.click(screen.getByRole('button', { name: /add connection/i }));
    const hostInput = screen.getByLabelText('Host');

    await u.clear(hostInput);
    await u.type(hostInput, '10.0.0.5');

    expect(hostInput).toHaveValue('10.0.0.5');

    await u.click(screen.getByRole('button', { name: /save connection/i }));
    expect(setConnections).toHaveBeenCalledWith([
      expect.objectContaining({ host: '10.0.0.5' }),
    ]);
  });

  it('shows BFF Port and WS Port as two distinct fields for RTI-SO (the default type)', async () => {
    setup();
    const u = user();

    await u.click(screen.getByRole('button', { name: /add connection/i }));

    expect(screen.getByLabelText('BFF Port')).toBeInTheDocument();
    expect(screen.getByLabelText('WS Port')).toBeInTheDocument();
  });

  it('shows BFF Port and WS Port for a Generic ("custom") connection too', async () => {
    setup();
    const u = user();

    await u.click(screen.getByRole('button', { name: /add connection/i }));
    await u.selectOptions(screen.getByLabelText('Type'), 'Generic');

    expect(screen.getByLabelText('BFF Port')).toBeInTheDocument();
    expect(screen.getByLabelText('WS Port')).toBeInTheDocument();
  });

  it('does not show a WS Port field for RTI-FSP - only a plain Port', async () => {
    setup();
    const u = user();

    await u.click(screen.getByRole('button', { name: /add connection/i }));
    await u.selectOptions(screen.getByLabelText('Type'), 'RTI-FSP');

    expect(screen.getByLabelText('Port')).toBeInTheDocument();
    expect(screen.queryByLabelText('BFF Port')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('WS Port')).not.toBeInTheDocument();
  });

  it('saves the BFF port and WS port as two independent values', async () => {
    const { setConnections } = setup();
    const u = user();

    await u.click(screen.getByRole('button', { name: /add connection/i }));
    await u.type(screen.getByLabelText('Name'), 'so1');
    await u.type(screen.getByLabelText('Host'), '10.0.0.1');

    const bffPortInput = screen.getByLabelText('BFF Port');
    await u.clear(bffPortInput);
    await u.type(bffPortInput, '5002');

    const wsPortInput = screen.getByLabelText('WS Port');
    await u.clear(wsPortInput);
    await u.type(wsPortInput, '8765');

    await u.click(screen.getByRole('button', { name: /save connection/i }));

    expect(setConnections).toHaveBeenCalledWith([
      expect.objectContaining({ name: 'so1', host: '10.0.0.1', port: 5002, ws_port: 8765 }),
    ]);
  });

  it('pre-fills the WS Port field when editing an existing RTI-SO connection', async () => {
    setup([
      { name: 'so1', host: '10.0.0.1', port: 5002, ws_port: 8765, type: 'RTI-SO', status: 'connected' },
    ]);
    const u = user();

    // The edit button is icon-only (no accessible name) - grab it by
    // position: the first .btn-icon in the connections table row.
    const editButton = document.querySelector('#connections-container .btn-icon');
    await u.click(editButton);

    expect(screen.getByLabelText('WS Port')).toHaveValue(8765);
  });
});

describe('Connections page - table', () => {
  it('shows the WS Port column value for RTI-SO rows and "-" for other types', () => {
    setup([
      { name: 'so1', host: '10.0.0.1', port: 5002, ws_port: 8765, type: 'RTI-SO', status: 'connected' },
      { name: 'fsp1', host: '10.0.0.2', port: 5001, type: 'RTI-FSP', status: 'connected' },
    ]);

    const rows = screen.getAllByRole('row');
    // rows[0] is the header row.
    expect(rows[1]).toHaveTextContent('8765');
    expect(rows[2]).not.toHaveTextContent('8765');
  });

  it('shows an em dash when an RTI-SO connection has no ws_port set yet', () => {
    setup([
      { name: 'so1', host: '10.0.0.1', port: 5002, type: 'RTI-SO', status: 'connected' },
    ]);

    expect(screen.getAllByRole('row')[1]).toHaveTextContent('—');
  });
});
