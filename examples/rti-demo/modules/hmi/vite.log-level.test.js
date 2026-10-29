// SPDX-FileCopyrightText: 2026 Netbeheer Nederland
//
// SPDX-License-Identifier: Apache-2.0

import { describe, expect, it } from 'vitest';
import { buildLogLevel, cliLogLevel, viteLogLevel } from './vite.log-level.js';

const argv = (...args) => ['node', 'vite', ...args];

describe('the build-time log level', () => {
  it('takes --log-level, in either form', () => {
    expect(cliLogLevel(argv('--log-level', 'debug'))).toBe('debug');
    expect(cliLogLevel(argv('build', '--log-level=warning'))).toBe('warning');
    expect(cliLogLevel(argv('build'))).toBeUndefined();
  });

  it('prefers --log-level over LOG_LEVEL', () => {
    expect(buildLogLevel(argv('--log-level', 'warning'), { LOG_LEVEL: 'debug' })).toBe('warning');
  });

  it('takes LOG_LEVEL without --log-level, and nothing without either', () => {
    expect(buildLogLevel(argv(), { LOG_LEVEL: 'debug' })).toBe('debug');
    expect(buildLogLevel(argv(), { LOG_LEVEL: '' })).toBeUndefined();
    expect(buildLogLevel(argv(), {})).toBeUndefined();
  });

  it("keeps Vite's own --logLevel for Vite's output", () => {
    expect(viteLogLevel(argv('--log-level', 'debug'))).toBe('info');
    expect(viteLogLevel(argv('--log-level', 'debug', '--logLevel', 'warn'))).toBe('warn');
    expect(viteLogLevel(argv('-l', 'silent'))).toBe('silent');
  });
});
