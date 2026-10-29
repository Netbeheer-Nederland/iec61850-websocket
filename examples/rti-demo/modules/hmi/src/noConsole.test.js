// SPDX-FileCopyrightText: 2026 Netbeheer Nederland
//
// SPDX-License-Identifier: Apache-2.0

import { describe, expect, it } from 'vitest';

// Spec 0008: every console call goes through utils/log.js, so LOG_LEVEL
// decides what the browser shows.
const sources = import.meta.glob(['./**/*.{js,jsx}', '!./**/*.test.{js,jsx}', '!./utils/log.js', '!./setupTests.js'], {
  query: '?raw',
  import: 'default',
  eager: true,
});

describe('src/', () => {
  it('has sources to check', () => {
    expect(Object.keys(sources).length).toBeGreaterThan(20);
  });

  it('calls the console only in utils/log.js', () => {
    const calls = Object.entries(sources).flatMap(([path, text]) =>
      text.split('\n').flatMap((line, i) => (/\bconsole\.\w+\s*\(/.test(line) ? [`${path}:${i + 1}: ${line.trim()}`] : []))
    );
    expect(calls).toEqual([]);
  });
});
