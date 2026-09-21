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

  it('shows BFF Port and WS Port for a Custom connection too', async () => {
    setup();
    const u = user();

    await u.click(screen.getByRole('button', { name: /add connection/i }));
    await u.selectOptions(screen.getByLabelText('Type'), 'Custom');

    expect(screen.getByLabelText('BFF Port')).toBeInTheDocument();
    expect(screen.getByLabelText('WS Port')).toBeInTheDocument();
  });

  it('labels RTI-FSP\'s port "BFF Port" too, same as RTI-SO, but without a WS Port field', async () => {
    setup();
    const u = user();

    await u.click(screen.getByRole('button', { name: /add connection/i }));
    await u.selectOptions(screen.getByLabelText('Type'), 'RTI-FSP');

    expect(screen.getByLabelText('BFF Port')).toBeInTheDocument();
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
  it('shows Status, Name, Type, Host, BFF Port and Actions columns, in that order', () => {
    setup([
      { name: 'so1', host: '10.0.0.1', port: 5002, ws_port: 8765, type: 'RTI-SO', status: 'connected' },
    ]);

    const headers = screen.getAllByRole('columnheader').map((h) => h.textContent);
    expect(headers).toEqual(['Status', 'Name', 'Type', 'Host', 'BFF Port', 'Actions']);
  });

  it('shows each row\'s status, name, type, host and BFF port', () => {
    setup([
      { name: 'so1', host: '10.0.0.1', port: 5002, ws_port: 8765, type: 'RTI-SO', status: 'connected' },
      { name: 'fsp1', host: '10.0.0.2', port: 5001, type: 'RTI-FSP', status: 'disconnected' },
    ]);

    const rows = screen.getAllByRole('row');
    // rows[0] is the header row.
    expect(rows[1]).toHaveTextContent('Connected');
    expect(rows[1]).toHaveTextContent('so1');
    expect(rows[1]).toHaveTextContent('RTI-SO');
    expect(rows[1]).toHaveTextContent('10.0.0.1');
    expect(rows[1]).toHaveTextContent('5002');

    expect(rows[2]).toHaveTextContent('Disconnected');
    expect(rows[2]).toHaveTextContent('fsp1');
  });

  it('sorts by a clicked column, toggling direction on repeat clicks', async () => {
    setup([
      { name: 'so2', host: '10.0.0.2', port: 5002, type: 'RTI-SO', status: 'connected' },
      { name: 'so1', host: '10.0.0.1', port: 5001, type: 'RTI-SO', status: 'connected' },
    ]);
    const u = user();

    const nameCells = () => screen.getAllByRole('row').slice(1).map((r) => r.cells[1].textContent);
    // Unsorted: original order.
    expect(nameCells()).toEqual(['so2', 'so1']);

    await u.click(screen.getByRole('columnheader', { name: /^Name/ }));
    expect(nameCells()).toEqual(['so1', 'so2']);

    await u.click(screen.getByRole('columnheader', { name: /^Name/ }));
    expect(nameCells()).toEqual(['so2', 'so1']);
  });

  it('sorts BFF Port numerically, not lexicographically', async () => {
    setup([
      { name: 'a', host: '10.0.0.1', port: 10001, type: 'RTI-SO', status: 'connected' },
      { name: 'b', host: '10.0.0.2', port: 9000, type: 'RTI-SO', status: 'connected' },
    ]);
    const u = user();

    await u.click(screen.getByRole('columnheader', { name: /^BFF Port/ }));

    const nameCells = screen.getAllByRole('row').slice(1).map((r) => r.cells[1].textContent);
    // Numeric: 9000 < 10001. A lexicographic sort would put "10001" first.
    expect(nameCells).toEqual(['b', 'a']);
  });
});
