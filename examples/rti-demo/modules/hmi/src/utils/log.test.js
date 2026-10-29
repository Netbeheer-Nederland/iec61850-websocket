// SPDX-FileCopyrightText: 2026 Netbeheer Nederland
//
// SPDX-License-Identifier: Apache-2.0

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { parseLogLevel, resolveLogLevel } from './log';

// log.js reads ?log= when it is imported, so each case sets up its sources
// and then imports a fresh copy.
const loadLog = async () => {
  vi.resetModules();
  return import('./log');
};

const cleanUp = () => {
  delete window.RTI_CONFIG;
  localStorage.clear();
  window.history.replaceState(null, '', '/');
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
};

// LOG_LEVEL in the environment of the test run reaches VITE_LOG_LEVEL
// (vite.config.js); the cases set their own.
const setUp = () => {
  cleanUp();
  vi.stubEnv('VITE_LOG_LEVEL', '');
};

describe('parseLogLevel', () => {
  it('takes the names in any case, as resolve_log_level does', () => {
    expect(parseLogLevel('DEBUG')).toBe(10);
    expect(parseLogLevel(' Warning ')).toBe(30);
    expect(parseLogLevel('warn')).toBe(30);
    expect(parseLogLevel('critical')).toBe(50);
    expect(parseLogLevel('error')).toBe(40);
    expect(parseLogLevel('info')).toBe(20);
  });

  it('takes trace as debug, and a number as it is', () => {
    expect(parseLogLevel('trace')).toBe(10);
    expect(parseLogLevel('15')).toBe(15);
  });

  it('is null for an unknown name', () => {
    expect(parseLogLevel('loud')).toBeNull();
    expect(parseLogLevel('-5')).toBeNull();
  });
});

describe('resolveLogLevel', () => {
  it('is info by default, when every source is empty', () => {
    expect(resolveLogLevel([{ value: '', from: 'LOG_LEVEL' }, { value: undefined, from: 'the build' }]))
      .toMatchObject({ level: 20, name: 'info', from: 'default', unknown: false });
  });

  it('takes the first source with a value, even an unknown one, which is info', () => {
    expect(resolveLogLevel([{ value: 'loud', from: 'LOG_LEVEL' }, { value: 'debug', from: 'the build' }]))
      .toMatchObject({ level: 20, name: 'info', from: 'LOG_LEVEL', value: 'loud', unknown: true });
  });
});

describe('the HMI log level', () => {
  beforeEach(setUp);
  afterEach(cleanUp);

  it('is info with no source, and says so', async () => {
    const { getLogLevel, describeLogLevel } = await loadLog();
    expect(getLogLevel()).toMatchObject({ name: 'info', from: 'default' });
    expect(describeLogLevel()).toBe('info (default)');
  });

  it('takes the build-time VITE_LOG_LEVEL', async () => {
    vi.stubEnv('VITE_LOG_LEVEL', 'warning');
    const { describeLogLevel } = await loadLog();
    expect(describeLogLevel()).toBe('warning (from the build)');
  });

  it("prefers the container's LOG_LEVEL over the build", async () => {
    vi.stubEnv('VITE_LOG_LEVEL', 'warning');
    window.RTI_CONFIG = { logLevel: 'DEBUG' };
    const { describeLogLevel } = await loadLog();
    expect(describeLogLevel()).toBe('debug (from LOG_LEVEL)');
  });

  it('prefers the Settings page over LOG_LEVEL', async () => {
    window.RTI_CONFIG = { logLevel: 'debug' };
    localStorage.setItem('rti-hmi-log-level', 'error');
    const { describeLogLevel, resolveServerLogLevel } = await loadLog();
    expect(describeLogLevel()).toBe('error (from the Settings page)');
    expect(resolveServerLogLevel()).toMatchObject({ name: 'debug', from: 'LOG_LEVEL' });
  });

  it('prefers ?log= over both, and keeps it after the URL changes', async () => {
    window.RTI_CONFIG = { logLevel: 'error' };
    localStorage.setItem('rti-hmi-log-level', 'warning');
    window.history.replaceState(null, '', '/traffic?log=debug');
    const { describeLogLevel, getUrlLogLevel } = await loadLog();
    window.history.replaceState(null, '', '/settings');
    expect(describeLogLevel()).toBe('debug (from ?log=)');
    expect(getUrlLogLevel()).toBe('debug');
  });

  it('says an unknown value is info', async () => {
    window.RTI_CONFIG = { logLevel: 'loud' };
    const { describeLogLevel } = await loadLog();
    expect(describeLogLevel()).toBe('info ("loud" from LOG_LEVEL is unknown)');
  });

  it('applies a Settings page choice straight away, and its clearing', async () => {
    window.RTI_CONFIG = { logLevel: 'debug' };
    const { setStoredLogLevel, getLogLevel } = await loadLog();
    setStoredLogLevel('error');
    expect(localStorage.getItem('rti-hmi-log-level')).toBe('error');
    expect(getLogLevel()).toMatchObject({ name: 'error', from: 'the Settings page' });
    setStoredLogLevel(null);
    expect(localStorage.getItem('rti-hmi-log-level')).toBeNull();
    expect(getLogLevel()).toMatchObject({ name: 'debug', from: 'LOG_LEVEL' });
  });

  it('logs the level once at start, at info', async () => {
    window.RTI_CONFIG = { logLevel: 'debug' };
    const info = vi.spyOn(console, 'info').mockImplementation(() => {});
    const { logStartLevel } = await loadLog();
    logStartLevel();
    expect(info).toHaveBeenCalledWith('HMI log level: debug (from LOG_LEVEL)');
  });
});

describe('log', () => {
  beforeEach(setUp);
  afterEach(cleanUp);

  const shown = async (level) => {
    window.RTI_CONFIG = { logLevel: level };
    const spies = Object.fromEntries(
      ['error', 'warn', 'info', 'debug'].map((m) => [m, vi.spyOn(console, m).mockImplementation(() => {})])
    );
    const { log } = await loadLog();
    for (const m of Object.keys(spies)) log[m]('x');
    return Object.keys(spies).filter((m) => spies[m].mock.calls.length > 0);
  };

  it.each([
    ['debug', ['error', 'warn', 'info', 'debug']],
    ['trace', ['error', 'warn', 'info', 'debug']],
    ['info', ['error', 'warn', 'info']],
    ['warning', ['error', 'warn']],
    ['error', ['error']],
    ['critical', ['error']],
    ['5', ['error', 'warn', 'info', 'debug']],
    ['', ['error', 'warn', 'info']],
  ])('at %s calls %j', async (level, methods) => {
    expect(await shown(level)).toEqual(methods);
  });

  it('passes the arguments on', async () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    const { log } = await loadLog();
    const e = new Error('boom');
    log.error('Failed to fetch:', e);
    expect(error).toHaveBeenCalledWith('Failed to fetch:', e);
  });
});
