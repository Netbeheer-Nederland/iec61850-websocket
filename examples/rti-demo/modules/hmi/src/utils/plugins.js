/*
 * SPDX-FileCopyrightText: 2026 Netbeheer Nederland
 * SPDX-License-Identifier: Apache-2.0
 */

// An SO's or FSP's plugins, as its GET /api/plugins gives them (the plugin
// contract, modules/plugins/openapi.yaml): { plugins: [{ name, version, url,
// claims, routes, healthy, last_error }], failed: { name: reason },
// definitions: { name: { url, settings } } }. The BFF pushes it with the
// connections (`plugins`, null while unknown).

// One row per plugin: the connected ones, then the ones that couldn't be
// reached. state: 'healthy' | 'unhealthy' | 'unreachable'. definition: its
// { url, settings }, what an edit changes; null from an instance that
// doesn't list definitions. routes: whether it has routes under
// /api/plugins/{name}/; attached and attachedError: what it attaches.
export function pluginRows(status) {
  if (!status) return [];
  const definitionOf = (name) => status.definitions?.[name] ?? null;
  const connected = (status.plugins || []).map((p) => ({
    name: p.name,
    version: p.version || '',
    url: p.url || '',
    claims: Array.isArray(p.claims) ? p.claims : [],
    state: p.healthy === false ? 'unhealthy' : 'healthy',
    error: p.last_error || null,
    routes: Boolean(p.routes),
    attached: Array.isArray(p.attached) ? p.attached : [],
    attachedError: p.attached_error || null,
    definition: definitionOf(p.name),
  }));
  const failed = Object.entries(status.failed || {}).map(([name, reason]) => ({
    name,
    version: '',
    url: definitionOf(name)?.url || '',
    claims: [],
    state: 'unreachable',
    error: reason || null,
    routes: false,
    attached: [],
    attachedError: null,
    definition: definitionOf(name),
  }));
  return [...connected, ...failed];
}

// A row as an entry of the instance's plugin configuration (PluginsConfig's
// `plugins`), to make an edit or an added plugin last; null without its
// definition.
export function configEntry(row) {
  if (!row.definition) return null;
  const entry = { name: row.name, url: row.definition.url };
  const settings = row.definition.settings || {};
  if (Object.keys(settings).length) entry.settings = settings;
  return entry;
}

// For a badge: how many plugins, and which have a problem. null while the
// status is unknown or there are no plugins at all.
export function pluginSummary(status) {
  const rows = pluginRows(status);
  if (!rows.length) return null;
  const problems = rows.filter((r) => r.state !== 'healthy');
  return { count: rows.length, problems };
}

// objRef -> name of the plugin that answers an Operate on it.
export function claimOwners(status) {
  const owners = {};
  for (const p of status?.plugins || []) {
    for (const ref of p.claims || []) owners[ref] = p.name;
  }
  return owners;
}

// The plugin that answers an Operate on a model tree node: a claim is the
// control attribute the Operate writes (LD0/CSWI1.Pos.Oper.ctlVal), shown on
// its data object (LD0/CSWI1.Pos); a claim naming the node itself counts too.
export function claimOwnerOf(owners, ref) {
  if (!ref) return null;
  return owners[ref] || owners[`${ref}.Oper.ctlVal`] || null;
}

// What an SO's or FSP's plugins attach (decision 0025): every plugin's
// `attached` items, as the instance checked them, each with the plugin it
// comes from. Only connected plugins have items; [] while unknown.
export function attachedItems(status) {
  const items = [];
  for (const p of status?.plugins || []) {
    (Array.isArray(p.attached) ? p.attached : []).forEach((item, index) => {
      items.push({
        ...item,
        key: `${p.name}:${index}`,
        plugin: {
          name: p.name,
          version: p.version || '',
          healthy: p.healthy !== false,
          lastError: p.last_error || null,
          attachedError: p.attached_error || null,
        },
      });
    });
  }
  return items;
}

// A request to a plugin's own routes (spec 0001), as the Details' Request
// form has it: { method, path, query, body } with the body as JSON text.
export const ROUTE_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'];
export const routeHasBody = (method) => ['POST', 'PUT', 'PATCH'].includes(method);

// The request ready to send - { method, path, query, body } with the path
// without leading slashes and the body parsed (null without one) - or
// { problem } when it can't be sent. The BFF passes a body only as a JSON
// object, and POST .../reload is the instance's own Reload.
export function routeRequest({ method, path, query, body }) {
  const cleanPath = String(path || '').trim().replace(/^\/+/, '');
  if (!cleanPath) return { problem: 'A path is needed, e.g. leds' };
  if (method === 'POST' && cleanPath.replace(/\/+$/, '') === 'reload') {
    return { problem: "POST reload is the instance's own Reload, not the plugin's route" };
  }
  let parsed = null;
  if (routeHasBody(method) && String(body || '').trim()) {
    try {
      parsed = JSON.parse(body);
    } catch (err) {
      return { problem: `Body must be JSON: ${err.message}` };
    }
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return { problem: 'Body must be a JSON object' };
    }
  }
  return { method, path: cleanPath, query: String(query || '').trim(), body: parsed };
}

// What the plugin answered, as text to show: JSON pretty-printed, text as it
// is, cut at `limit` characters.
export const ROUTE_ANSWER_LIMIT = 20000;
export function routeAnswerText(result, limit = ROUTE_ANSWER_LIMIT) {
  const text = typeof result === 'string' ? result : JSON.stringify(result, null, 2) ?? '';
  return text.length > limit ? { text: text.slice(0, limit), cut: true } : { text, cut: false };
}
