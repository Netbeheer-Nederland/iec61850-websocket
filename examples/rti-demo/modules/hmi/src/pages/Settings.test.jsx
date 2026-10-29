// SPDX-FileCopyrightText: 2026 Netbeheer Nederland
//
// SPDX-License-Identifier: Apache-2.0

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const SETTINGS = { bffHost: 'localhost', bffPort: 3000 };

// log.js reads ?log= when it is imported, so each case imports fresh copies.
const renderSettings = async () => {
  vi.resetModules();
  const { default: Settings } = await import('./Settings');
  const logModule = await import('../utils/log');
  render(<Settings settings={SETTINGS} setSettings={() => {}} />);
  return logModule;
};

const inUse = () => document.getElementById('log-level-in-use').textContent;

beforeEach(() => {
  global.fetch = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({}) }));
  vi.stubEnv('VITE_LOG_LEVEL', '');
  window.RTI_CONFIG = { logLevel: 'debug' };
});

afterEach(() => {
  delete window.RTI_CONFIG;
  localStorage.clear();
  window.history.replaceState(null, '', '/');
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe('Settings page: log level (spec 0008)', () => {
  it("offers the server's level and the six names", async () => {
    await renderSettings();
    const select = screen.getByLabelText('Log level');
    expect([...select.options].map(o => o.textContent)).toEqual([
      'From the server (debug)', 'critical', 'error', 'warning', 'info', 'debug', 'trace',
    ]);
    expect(select).toHaveValue('');
    expect(inUse()).toBe('debug (from LOG_LEVEL)');
  });

  it('stores a choice and applies it without a reload', async () => {
    const user = userEvent.setup({ delay: null });
    const { log } = await renderSettings();
    const debug = vi.spyOn(console, 'debug').mockImplementation(() => {});

    await user.selectOptions(screen.getByLabelText('Log level'), 'error');

    expect(localStorage.getItem('rti-hmi-log-level')).toBe('error');
    expect(inUse()).toBe('error (from the Settings page)');
    log.debug('hidden');
    expect(debug).not.toHaveBeenCalled();
  });

  it('clears the choice with "From the server"', async () => {
    localStorage.setItem('rti-hmi-log-level', 'error');
    const user = userEvent.setup({ delay: null });
    await renderSettings();
    expect(screen.getByLabelText('Log level')).toHaveValue('error');

    await user.selectOptions(screen.getByLabelText('Log level'), '');

    expect(localStorage.getItem('rti-hmi-log-level')).toBeNull();
    expect(inUse()).toBe('debug (from LOG_LEVEL)');
  });

  it('says when ?log= in the URL is in use', async () => {
    window.history.replaceState(null, '', '/settings?log=warning');
    await renderSettings();
    expect(inUse()).toBe('warning (from ?log=)');
    expect(screen.getByText(/\?log=warning in the URL wins over this choice/)).toBeInTheDocument();
  });
});
