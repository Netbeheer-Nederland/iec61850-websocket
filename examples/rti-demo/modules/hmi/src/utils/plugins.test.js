/*
 * SPDX-FileCopyrightText: 2026 Netbeheer Nederland
 * SPDX-License-Identifier: Apache-2.0
 */

import { describe, it, expect } from 'vitest';
import { pluginRows, pluginSummary, claimOwners, claimOwnerOf } from './plugins';

const STATUS = {
  plugins: [
    { name: 'io', version: '1.2', url: 'http://rti-io:9000/plugin', claims: ['LD0/CSWI1.Pos.Oper.ctlVal'], healthy: true, last_error: null },
    { name: 'leds', version: '0.1', url: 'http://sim-leds:8099/plugin', claims: [], healthy: false, last_error: 'on_event timed out' },
  ],
  failed: { display: "Can't reach http://pi:8000/plugin" },
};

describe('plugins', () => {
  it('lists connected plugins, then the unreachable ones', () => {
    expect(pluginRows(STATUS).map((r) => [r.name, r.state, r.error])).toEqual([
      ['io', 'healthy', null],
      ['leds', 'unhealthy', 'on_event timed out'],
      ['display', 'unreachable', "Can't reach http://pi:8000/plugin"],
    ]);
  });

  it('summarises for a badge, null without plugins or status', () => {
    const summary = pluginSummary(STATUS);
    expect(summary.count).toBe(3);
    expect(summary.problems.map((p) => p.name)).toEqual(['leds', 'display']);
    expect(pluginSummary({ plugins: [], failed: {} })).toBeNull();
    expect(pluginSummary(null)).toBeNull();
  });

  it("shows a control attribute's claim on its data object", () => {
    const owners = claimOwners(STATUS);
    expect(claimOwnerOf(owners, 'LD0/CSWI1.Pos')).toBe('io');
    expect(claimOwnerOf(owners, 'LD0/CSWI1.Pos.Oper.ctlVal')).toBe('io');
    expect(claimOwnerOf(owners, 'LD0/CSWI1')).toBeNull();
    expect(claimOwnerOf(owners, undefined)).toBeNull();
  });
});
