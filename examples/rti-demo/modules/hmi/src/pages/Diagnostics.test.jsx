import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Diagnostics, { DIAGNOSTICS_POLL_MS } from './Diagnostics';

const BODY = {
  sources: ['BFF', 'SO'],
  entries: [
    { id: 3, source: 'SO', instance: 'SO', kind: 'system', level: 'error', time: '10:00:03', message: 'Endpoint failed to start' },
    { id: 1, source: 'BFF', instance: 'FSP01', kind: 'system', level: 'warn', time: '10:00:02', message: 'FSP01 stopped responding' },
    { id: 1, source: 'SO', instance: 'SO', kind: 'system', level: 'info', time: '10:00:01', message: 'Connected to server' },
    { id: 2, source: 'SO', instance: 'SO', kind: 'system', level: 'debug', time: '10:00:00', message: 'Reconfiguring passive endpoint with TLS' },
  ],
};

const mockFetch = (body = BODY, ok = true) => {
  global.fetch = vi.fn(async () => ({ ok, status: ok ? 200 : 500, json: async () => body }));
};

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
  mockFetch();
});

afterEach(() => {
  vi.useRealTimers();
});

const messages = () => [...document.querySelectorAll('.diagnostics-entry')].map((el) => el.textContent);

describe('Diagnostics page', () => {
  it('reads GET /api/diagnostics and lists entries in the order given, hiding debug by default', async () => {
    render(<Diagnostics />);

    expect(await screen.findByText('Endpoint failed to start')).toBeInTheDocument();
    expect(String(global.fetch.mock.calls[0][0])).toMatch(/\/api\/diagnostics$/);
    expect(messages()).toHaveLength(3);
    expect(messages()[0]).toContain('Endpoint failed to start');
    expect(screen.queryByText('Reconfiguring passive endpoint with TLS')).not.toBeInTheDocument();
    expect(screen.getByText(/1 error/)).toBeInTheDocument();
    expect(screen.getByText(/1 warning/)).toBeInTheDocument();
  });

  it('names the instance a BFF event is about', async () => {
    render(<Diagnostics />);

    const bffRow = (await screen.findByText('FSP01 stopped responding')).closest('.diagnostics-entry');
    expect(bffRow.textContent).toContain('BFF · FSP01');
  });

  it('filters by source and by severity', async () => {
    const user = userEvent.setup({ delay: null });
    render(<Diagnostics />);
    await screen.findByText('Endpoint failed to start');

    await user.selectOptions(screen.getByTitle('Filter by source'), 'BFF');
    expect(messages()).toEqual([expect.stringContaining('FSP01 stopped responding')]);

    await user.selectOptions(screen.getByTitle('Filter by source'), 'all');
    await user.selectOptions(screen.getByTitle('Filter by severity'), 'all');
    expect(messages()).toHaveLength(4);

    await user.selectOptions(screen.getByTitle('Filter by severity'), 'problems');
    expect(messages()).toHaveLength(2);
  });

  it('keeps refreshing while open, and shows an error if the BFF call fails', async () => {
    render(<Diagnostics />);
    await screen.findByText('Endpoint failed to start');
    expect(global.fetch).toHaveBeenCalledTimes(1);

    mockFetch(BODY, false);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DIAGNOSTICS_POLL_MS);
    });

    expect(global.fetch).toHaveBeenCalledTimes(1); // the new mock
    expect(await screen.findByRole('alert')).toHaveTextContent(/HTTP 500/);
  });
});
