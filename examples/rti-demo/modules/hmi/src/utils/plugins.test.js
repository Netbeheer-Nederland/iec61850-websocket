/*
 * SPDX-FileCopyrightText: 2026 Netbeheer Nederland
 * SPDX-License-Identifier: Apache-2.0
 */

import { describe, it, expect } from 'vitest';
import { pluginRows, configEntry, addTargets, routeRequest, routeAnswerText, pluginSummary, claimOwners, claimOwnerOf, attachedItems } from './plugins';

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

  it('lists the other connected SOs and FSPs to add a plugin to; only FSPs for one with claims', () => {
    const connections = [
      { name: 'so', type: 'RTI-SO', host: 'rti-so', port: 5000, status: 'connected', plugins: { plugins: [{ name: 'leds' }], failed: {} } },
      { name: 'fsp01', type: 'RTI-FSP', host: 'rti-fsp01', port: 5001, status: 'connected' },
      { name: 'fsp02', type: 'RTI-FSP', host: 'rti-fsp02', port: 5005, status: 'disconnected' },
      { name: 'idp', type: 'IDP-Server', host: 'keycloak', port: 8081, status: 'connected' },
    ];
    const [io, leds] = pluginRows(STATUS);
    expect(addTargets(connections, 'rti-fsp01:5001', leds)).toEqual([{ name: 'so', role: 'SO', target: 'rti-so:5000', has: true }]);
    expect(addTargets(connections, 'rti-so:5000', io)).toEqual([{ name: 'fsp01', role: 'FSP', target: 'rti-fsp01:5001', has: false }]);
    expect(addTargets(undefined, 'rti-so:5000', io)).toEqual([]);
  });

  it('summarises for a badge, null without plugins or status', () => {
    const summary = pluginSummary(STATUS);
    expect(summary.count).toBe(3);
    expect(summary.problems.map((p) => p.name)).toEqual(['leds', 'display']);
    expect(summary.worst).toBe('unreachable');
    expect(pluginSummary({ plugins: STATUS.plugins, failed: {} }).worst).toBe('unhealthy');
    expect(pluginSummary({ plugins: [STATUS.plugins[0]], failed: {} }).worst).toBe('healthy');
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
    expect(items.map((i) => i.key)).toEqual(['io:0', 'io:1', 'sim_leds:0', 'display:disconnected']);
    expect(items[2].plugin).toEqual({ name: 'sim_leds', version: '', healthy: false, state: 'unhealthy', lastError: 'boom', attachedError: 'attached timed out after 1.0s' });
    expect(items[0].plugin.state).toBe('healthy');
    expect(items[3]).toMatchObject({ label: 'display', disconnected: true, plugin: { state: 'unreachable', lastError: 'down' } });
  });

  it("marks a running plugin whose /attached failed as stale", () => {
    const [item] = attachedItems({ plugins: [{ name: 'io', healthy: true, attached_error: 'timed out', attached: [{ kind: 'io', label: 'IO server' }] }], failed: {} });
    expect(item.plugin.state).toBe('stale');
  });

  it('is empty while the status is unknown', () => {
    expect(attachedItems(null)).toEqual([]);
    expect(attachedItems(undefined)).toEqual([]);
  });
});

describe('plugin route requests', () => {
  it('takes the path without leading slashes, and the query as given', () => {
    expect(routeRequest({ method: 'GET', path: ' /leds/1', query: ' on=1 ', body: '{"x": 1}' }))
      .toEqual({ method: 'GET', path: 'leds/1', query: 'on=1', body: null });
  });

  it('parses the body of POST, PUT and PATCH, which must be a JSON object', () => {
    expect(routeRequest({ method: 'PUT', path: 'leds', body: '{"on": true}' }).body).toEqual({ on: true });
    expect(routeRequest({ method: 'POST', path: 'leds', body: '' }).body).toBeNull();
    expect(routeRequest({ method: 'POST', path: 'leds', body: 'nope' }).problem).toMatch(/^Body must be JSON/);
    expect(routeRequest({ method: 'PATCH', path: 'leds', body: '[1]' }).problem).toBe('Body must be a JSON object');
  });

  it("refuses no path, and POST reload, the instance's own route", () => {
    expect(routeRequest({ method: 'GET', path: ' / ' }).problem).toMatch(/path is needed/);
    expect(routeRequest({ method: 'POST', path: '/reload/' }).problem).toMatch(/own Reload/);
    expect(routeRequest({ method: 'GET', path: 'reload' }).problem).toBeUndefined();
  });

  it('shows JSON pretty-printed and text as it is, cut at the limit', () => {
    expect(routeAnswerText({ a: 1 })).toEqual({ text: '{\n  "a": 1\n}', cut: false });
    expect(routeAnswerText('plain')).toEqual({ text: 'plain', cut: false });
    expect(routeAnswerText('abcdef', 4)).toEqual({ text: 'abcd', cut: true });
  });
});
