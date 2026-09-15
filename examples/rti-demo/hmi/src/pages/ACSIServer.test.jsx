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

beforeEach(() => {
  executeApiCall.mockReset();
  executeApiCall.mockResolvedValue({ ok: false });

  global.fetch = vi.fn(async (url) => {
    if (String(url).endsWith('/api/connections')) {
      return {
        ok: true,
        json: async () => ({
          connections: [
            {
              name: 'so1', host: '10.0.0.1', port: 5002, ws_port: 8765,
              type: 'RTI-SO', status: 'connected',
            },
            {
              // No ws_port configured on this one - the WS Port field must
              // NOT fall back to its BFF port (5003).
              name: 'so2', host: '10.0.0.2', port: 5003,
              type: 'RTI-SO', status: 'connected',
            },
          ],
        }),
      };
    }
    return { ok: false, json: async () => ({}) };
  });
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

  it('leaves WS Port blank (not the BFF port) when the selected instance has no ws_port', async () => {
    renderPage();
    const user = userEvent.setup({ delay: null });

    await waitFor(() => {
      expect(screen.getByLabelText('Instance')).toHaveValue('so1');
    });

    await user.selectOptions(screen.getByLabelText('Instance'), 'so2');

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
