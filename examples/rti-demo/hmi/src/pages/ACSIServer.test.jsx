import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import ACSIServer from './ACSIServer';

const executeApiCall = vi.fn();
vi.mock('../services/apiService', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    executeApiCall: (...args) => executeApiCall(...args),
  };
});

const renderPage = () =>
  render(
    <MemoryRouter>
      <ACSIServer settings={{}} updateModel={() => {}} getModel={() => {}} bffBaseUrl="http://bff.local:5000" />
    </MemoryRouter>
  );

const mockConnections = (connections) => {
  global.fetch = vi.fn(async (url) => {
    if (String(url).endsWith('/api/connections')) {
      return { ok: true, json: async () => ({ connections }) };
    }
    return { ok: false, json: async () => ({}) };
  });
};

beforeEach(() => {
  executeApiCall.mockReset();
  executeApiCall.mockResolvedValue({ ok: false });
  localStorage.clear();

  mockConnections([
    {
      name: 'so1', host: '10.0.0.1', port: 5002, ws_port: 8765,
      type: 'RTI-SO', status: 'connected',
    },
    {
      // No ws_port configured on this one.
      name: 'so2', host: '10.0.0.2', port: 5003,
      type: 'RTI-SO', status: 'connected',
    },
  ]);
});

describe('ACSIServer instance selection - ws_port vs BFF port', () => {
  it('fills WS Port from the instance\'s ws_port (not its BFF port) on auto-select', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByLabelText('Instance')).toHaveValue('so1');
    });

    expect(screen.getByLabelText('WS Host')).toHaveValue('10.0.0.1');
    expect(screen.getByLabelText('WS Port')).toHaveValue(8765);
  });

  it('leaves WS Port blank (not the BFF port) when auto-selecting an instance with no ws_port', async () => {
    // so2 (no ws_port) is the only/first instance here, so it's the one
    // auto-selected on load - exercising the "leave blank" behavior without
    // going through the now-disabled dropdown option for it.
    mockConnections([
      { name: 'so2', host: '10.0.0.2', port: 5003, type: 'RTI-SO', status: 'connected' },
    ]);
    renderPage();

    await waitFor(() => {
      expect(screen.getByLabelText('Instance')).toHaveValue('so2');
    });

    expect(screen.getByLabelText('WS Host')).toHaveValue('10.0.0.2');
    // Must NOT be 5003 (so2's BFF port) - this is the exact bug being
    // regression-tested: silently falling back to the BFF port.
    expect(screen.getByLabelText('WS Port')).toHaveValue(null);
  });

  it('clears all WS fields when switching to "custom"', async () => {
    renderPage();
    const user = userEvent.setup({ delay: null });

    await waitFor(() => {
      expect(screen.getByLabelText('Instance')).toHaveValue('so1');
    });

    await user.selectOptions(screen.getByLabelText('Instance'), 'custom');

    expect(screen.getByLabelText('WS Host')).toHaveValue('');
    expect(screen.getByLabelText('WS Port')).toHaveValue(null);
    expect(screen.getByLabelText('WS CP')).toHaveValue('');
    expect(screen.getByLabelText('WS Mode')).toHaveValue('active');
    // Custom is the only state where these fields become editable.
    expect(screen.getByLabelText('WS Host')).toBeEnabled();
  });
});

describe('ACSIServer instance dropdown - usability', () => {
  it('disables the option for an instance with no ws_port configured, and labels it', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByLabelText('Instance')).toHaveValue('so1');
    });

    const so2Option = screen.getByRole('option', { name: /so2/ });
    expect(so2Option).toBeDisabled();
    expect(so2Option.textContent).toMatch(/WS port not configured/);

    const so1Option = screen.getByRole('option', { name: /^so1/ });
    expect(so1Option).toBeEnabled();

    // A disabled option can't actually be selected via user interaction.
    const user = userEvent.setup({ delay: null });
    await user.selectOptions(screen.getByLabelText('Instance'), 'so2').catch(() => {});
    expect(screen.getByLabelText('Instance')).toHaveValue('so1');
  });

  it('disables the whole Instance dropdown while the server is connected, with an explanatory hint', async () => {
    // storageKey falls back to a constant "rti-so:8765" when there's no
    // navigation-state endpoint (see ACSIServer.jsx's instanceId).
    localStorage.setItem('acsi-server-connected-rti-so:8765', 'true');
    renderPage();

    await waitFor(() => {
      expect(screen.getByLabelText('Instance')).toBeDisabled();
    });
    expect(screen.getByText(/Stop the server to switch/i)).toBeInTheDocument();
  });

  it('re-enables the Instance dropdown once not connected', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByLabelText('Instance')).toBeEnabled();
    });
    expect(screen.queryByText(/Stop the server to switch/i)).not.toBeInTheDocument();
  });
});
