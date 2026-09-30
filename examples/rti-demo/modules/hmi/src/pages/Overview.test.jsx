import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Overview from './Overview';

const user = () => userEvent.setup({ delay: null });

const renderOverview = (connections = []) =>
  render(
    <MemoryRouter>
      <Overview
        settings={{ bffHost: 'localhost', bffPort: '5000' }}
        connections={connections}
        loading={false}
        onReload={() => {}}
      />
    </MemoryRouter>
  );

describe('Overview page - read-only (no CRUD)', () => {
  it('has no Register Instance button', () => {
    renderOverview();

    expect(screen.queryByRole('button', { name: /register instance/i })).not.toBeInTheDocument();
  });

  it('has no Actions column or Edit/Delete buttons in the status table', () => {
    renderOverview([
      { name: 'so1', host: '10.0.0.1', port: 5002, type: 'RTI-SO', status: 'connected' },
    ]);

    const headers = screen.getAllByRole('columnheader').map((h) => h.textContent);
    expect(headers).toEqual(['Status', 'Name', 'Type', 'Host', 'BFF Port']);
    expect(screen.queryByRole('button', { name: /edit/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /delete/i })).not.toBeInTheDocument();
  });

  it('points the empty state at Connections instead of offering to register here', () => {
    renderOverview([]);

    expect(screen.getByText(/Register one from the Connections page/i)).toBeInTheDocument();
  });
});

describe('Overview page - table sorting', () => {
  it('sorts by a clicked column, toggling direction on repeat clicks', async () => {
    renderOverview([
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
    renderOverview([
      { name: 'a', host: '10.0.0.1', port: 10001, type: 'RTI-SO', status: 'connected' },
      { name: 'b', host: '10.0.0.2', port: 9000, type: 'RTI-SO', status: 'connected' },
    ]);
    const u = user();

    await u.click(screen.getByRole('columnheader', { name: /^BFF Port/ }));

    const nameCells = screen.getAllByRole('row').slice(1).map((r) => r.cells[1].textContent);
    expect(nameCells).toEqual(['b', 'a']);
  });
});
