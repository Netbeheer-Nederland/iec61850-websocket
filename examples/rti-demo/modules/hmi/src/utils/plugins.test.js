/*
 * SPDX-FileCopyrightText: 2026 Netbeheer Nederland
 * SPDX-License-Identifier: Apache-2.0
 */

import { describe, it, expect } from 'vitest';
import { pluginRows, configEntry, pluginSummary, claimOwners, claimOwnerOf, attachedItems } from './plugins';

const STATUS = {
  plugins: [
    { name: 'io', version: '1.2', url: 'http://rpi-io:9000/plugin', claims: ['LD0/CSWI1.Pos.Oper.ctlVal'], healthy: true, last_error: null },
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

  it("gives each row its definition, and an unreachable one its URL from it", () => {
    const rows = pluginRows({
      ...STATUS,
      definitions: { io: { url: 'http://rpi-io:9000/plugin', settings: {} }, display: { url: 'http://pi:8000/plugin', settings: { rotate: 90 } } },
    });
    expect(rows.map((r) => [r.name, r.url, r.definition])).toEqual([
      ['io', 'http://rpi-io:9000/plugin', { url: 'http://rpi-io:9000/plugin', settings: {} }],
      ['leds', 'http://sim-leds:8099/plugin', null],
      ['display', 'http://pi:8000/plugin', { url: 'http://pi:8000/plugin', settings: { rotate: 90 } }],
    ]);
    // From an instance without definitions: nothing to edit.
    expect(pluginRows(STATUS).every((r) => r.definition === null)).toBe(true);
  });

  it("gives each connected row its routes and what it attaches", () => {
    const rows = pluginRows({
      plugins: [{ name: 'io', routes: true, attached: [{ kind: 'io', label: 'IO server' }], attached_error: 'attached timed out after 1.0s' }],
      failed: { display: 'down' },
    });
    expect(rows.map((r) => [r.name, r.routes, r.attached.length, r.attachedError])).toEqual([
      ['io', true, 1, 'attached timed out after 1.0s'],
      ['display', false, 0, null],
    ]);
  });

  it('gives a row as a plugin configuration entry, settings only when there are some', () => {
    const rows = pluginRows({
      ...STATUS,
      definitions: { io: { url: 'http://rpi-io:9000/plugin', settings: {} }, display: { url: 'http://pi:8000/plugin', settings: { rotate: 90 } } },
    });
    expect(rows.map(configEntry)).toEqual([
      { name: 'io', url: 'http://rpi-io:9000/plugin' },
      null,
      { name: 'display', url: 'http://pi:8000/plugin', settings: { rotate: 90 } },
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

describe('attachedItems', () => {
  it('lists every plugin\'s items with the plugin they come from', () => {
    const items = attachedItems({
      plugins: [
        { name: 'io', version: '1.0', healthy: true, last_error: null, attached_error: null, attached: [{ kind: 'io', label: 'IO server', state: 'ok' }, { kind: 'display', label: 'lcd1', state: 'ok' }] },
        { name: 'sim_leds', healthy: false, last_error: 'boom', attached_error: 'attached timed out after 1.0s', attached: [{ kind: 'other', label: 'Simulated LEDs', state: 'ok' }] },
        { name: 'old' },
      ],
      failed: { display: 'down' },
    });
    expect(items.map((i) => i.key)).toEqual(['io:0', 'io:1', 'sim_leds:0']);
    expect(items[2].plugin).toEqual({ name: 'sim_leds', version: '', healthy: false, lastError: 'boom', attachedError: 'attached timed out after 1.0s' });
  });

  it('is empty while the status is unknown', () => {
    expect(attachedItems(null)).toEqual([]);
    expect(attachedItems(undefined)).toEqual([]);
  });
});
