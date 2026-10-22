/*
 * SPDX-FileCopyrightText: 2026 Netbeheer Nederland
 * SPDX-License-Identifier: Apache-2.0
 */

// An SO's or FSP's plugins, as its GET /api/plugins gives them (the plugin
// contract, modules/plugins/openapi.yaml): { plugins: [{ name, version, url,
// claims, routes, healthy, last_error }], failed: { name: reason } }. The BFF
// pushes it with the connections (`plugins`, null while unknown).

// One row per plugin: the connected ones, then the ones that couldn't be
// reached. state: 'healthy' | 'unhealthy' | 'unreachable'.
export function pluginRows(status) {
  if (!status) return [];
  const connected = (status.plugins || []).map((p) => ({
    name: p.name,
    version: p.version || '',
    url: p.url || '',
    claims: Array.isArray(p.claims) ? p.claims : [],
    state: p.healthy === false ? 'unhealthy' : 'healthy',
    error: p.last_error || null,
  }));
  const failed = Object.entries(status.failed || {}).map(([name, reason]) => ({
    name,
    version: '',
    url: '',
    claims: [],
    state: 'unreachable',
    error: reason || null,
  }));
  return [...connected, ...failed];
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
