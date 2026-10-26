/*
 * SPDX-FileCopyrightText: 2026 Netbeheer Nederland
 * SPDX-License-Identifier: Apache-2.0
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { executeApiCall } from './apiService';

// What executeApiCall posts to the BFF's /api/execute.
let sent;
beforeEach(() => {
  sent = [];
  global.fetch = vi.fn(async (url, init) => {
    sent.push(JSON.parse(init.body));
    return { ok: true, status: 200, text: async () => '{"ok": true, "result": {}}' };
  });
});

describe('executeApiCall', () => {
  it('encodes a path parameter, slashes included', async () => {
    await executeApiCall('plugin-reload', 'fsp:5001', null, { pathParams: { name: 'a/b' } });
    expect(sent[0]).toMatchObject({ method: 'POST', path: '/api/plugins/a%2Fb/reload' });
  });

  it("keeps a plugin route's slashes, encoding each segment, with the caller's method and query", async () => {
    await executeApiCall('plugin-route', 'fsp:5001', { on: true }, {
      pathParams: { name: 'dr_panel', path: 'leds/red led' }, method: 'PUT', query: '?on=1&color=dark red',
    });
    expect(sent[0]).toEqual({
      target: 'fsp:5001', method: 'PUT', path: '/api/plugins/dr_panel/leds/red%20led?on=1&color=dark+red', body: { on: true },
    });
  });

  it("uses the definition's method and no query by default", async () => {
    await executeApiCall('plugin-route', 'fsp:5001', null, { pathParams: { name: 'dr_panel', path: 'leds' } });
    expect(sent[0]).toEqual({ target: 'fsp:5001', method: 'GET', path: '/api/plugins/dr_panel/leds' });
  });
});
