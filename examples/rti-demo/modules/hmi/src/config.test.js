// SPDX-FileCopyrightText: 2026 Netbeheer Nederland
//
// SPDX-License-Identifier: Apache-2.0

import { afterEach, describe, expect, it, vi } from 'vitest';

// config.js reads its sources when it is imported, so each case sets them up
// and then imports a fresh copy.
const loadConfig = async () => {
  vi.resetModules();
  return import('./config');
};

describe('default BFF address', () => {
  afterEach(() => {
    delete window.RTI_CONFIG;
    vi.unstubAllEnvs();
  });

  it('is localhost:5000 when nothing is configured', async () => {
    vi.stubEnv('VITE_BFF_HOST', '');
    vi.stubEnv('VITE_BFF_PORT', '');
    const { DEFAULT_BFF_HOST, DEFAULT_BFF_PORT } = await loadConfig();
    expect(DEFAULT_BFF_HOST).toBe('localhost');
    expect(DEFAULT_BFF_PORT).toBe('5000');
  });

  it('takes the build-time VITE_BFF_* values', async () => {
    vi.stubEnv('VITE_BFF_HOST', 'bff.example');
    vi.stubEnv('VITE_BFF_PORT', '5100');
    const { DEFAULT_BFF_HOST, DEFAULT_BFF_PORT } = await loadConfig();
    expect(DEFAULT_BFF_HOST).toBe('bff.example');
    expect(DEFAULT_BFF_PORT).toBe('5100');
  });

  it('prefers the runtime config over the build-time values', async () => {
    vi.stubEnv('VITE_BFF_HOST', 'bff.example');
    vi.stubEnv('VITE_BFF_PORT', '5100');
    window.RTI_CONFIG = { bffHost: '192.168.100.10', bffPort: '5200' };
    const { DEFAULT_BFF_HOST, DEFAULT_BFF_PORT } = await loadConfig();
    expect(DEFAULT_BFF_HOST).toBe('192.168.100.10');
    expect(DEFAULT_BFF_PORT).toBe('5200');
  });

  it('falls back per field when the runtime config sets only one', async () => {
    vi.stubEnv('VITE_BFF_HOST', '');
    vi.stubEnv('VITE_BFF_PORT', '5100');
    window.RTI_CONFIG = { bffHost: 'pi-bff.local' };
    const { DEFAULT_BFF_HOST, DEFAULT_BFF_PORT } = await loadConfig();
    expect(DEFAULT_BFF_HOST).toBe('pi-bff.local');
    expect(DEFAULT_BFF_PORT).toBe('5100');
  });
});
