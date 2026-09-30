import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Overview from './Overview';

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

  it('has no instance table - that lives on the Connections page', () => {
    renderOverview([
      { name: 'so1', host: '10.0.0.1', port: 5002, type: 'RTI-SO', status: 'connected' },
    ]);

    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /edit/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /delete/i })).not.toBeInTheDocument();
  });

  it('points the empty state at Connections instead of offering to register here', () => {
    renderOverview([]);

    expect(screen.getByText(/Register one from the Connections page/i)).toBeInTheDocument();
  });
});
