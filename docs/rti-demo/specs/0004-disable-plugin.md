<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 0004. Disable and enable a plugin without removing it

- Status: draft
- Date: 2026-10-24
- Changes: plugin contract, plugin host, HMI

## Goal

Take a plugin out of service for a while (a Pi being rewired, a historian being upgraded) and put it back, without
losing its definition and without the instance retrying it every 10 s.

## Now

- Remove (`DELETE /api/plugins/{name}`) stops the plugin and forgets its definition; a configured one is back only
  after a restart, an added one is gone.
- A plugin that can't be reached is under `failed` and retried every `PLUGIN_RETRY_SECONDS`, with an error each time.
- The Plugin API already has `POST <url>/stop` and `POST <url>/start`; the management API has no way to use them
  apart from reload, remove and edit.

## Proposal

### Plugin contract and host

1. **Disable**: the instance calls `POST <url>/stop` (an error there is logged, not answered: a plugin being disabled
   may well be down), stops sending it events, releases its claims and doesn't retry it. Its definition stays.
2. **Enable**: connected again from its definition, as reload does (`GET <url>`, `POST <url>/start`); a plugin that
   can't be reached goes to `failed` and is retried, as at startup.
3. `GET /api/plugins` lists `disabled: [name, ...]`; `definitions` keeps their entries, so they can be edited (an
   edit of a disabled plugin changes the definition without connecting).
4. The routes: per the shared choice in the [specs README](README.md), e.g. `POST /api/plugins/{name}/_/disable`
   and `.../_/enable`, or `PATCH /api/plugins/{name}` `{enabled: false}`. Both answer the plugin's status; `404` for an
   unknown name; disable of a disabled plugin and enable of an enabled one are no-ops answering `200`.
5. **The configuration**: `PluginEntry` gets `enabled` (default `true`), so a plugin can be configured disabled and the
   HMI's Copy and Export carry it. Disable at runtime lasts until the instance restarts, as edits do (decision 0036).
6. Plugin API `api` stays 2: plugins see only the `/stop` and `/start` they already implement.

### HMI

1. `pluginRows`: state `disabled` for names in `disabled`, after the unreachable ones; grey label "Disabled".
2. Per-row **Disable** / **Enable** (icon `fa-pause` / `fa-play`). Disable asks first, as Remove does: "Disable io?
   It gets no events, and its controls are answered by no plugin, until enabled."
3. A disabled row: Edit, Copy and Remove stay; Reload is hidden; it doesn't count for Retry or for the 🔌 badge's red.
4. `configEntry` writes `"enabled": false` for a disabled row.

## Acceptance

- Disabling a connected plugin calls its `/stop`, removes it from `plugins`, lists it under `disabled`, keeps its
  definition, and no retry happens.
- An Operate on an objRef the disabled plugin claimed is answered as without the plugin.
- Enabling connects it again; unreachable, it goes to `failed` and is retried.
- A configuration entry with `enabled: false` starts disabled.

## Tests

modules/plugins: test_web.py (disable/enable, no retry while disabled, edit while disabled, idempotent),
test_config.py (`enabled`), test_openapi.py (routes and `disabled` match the contract). FSP: an Operate on a released
claim. HMI: plugins.test.js (`disabled` rows, `configEntry` with `enabled`), PluginsPanel.test.jsx (confirm, calls,
row actions).

## Docs to update

`openapi.yaml` (routes, `PluginList.disabled`, `PluginEntry.enabled`), plugins README, fsp/so READMEs (route
tables), a new decision, wireframe (a Disabled row, the ⏸/▶ action, ⓘ text), HMI README.

## Open questions

- Is "as without the plugin" the right answer for a released claim, or should the FSP refuse Operates on it while
  its plugin is disabled (the objRef is still meant to be driven by hardware)?
- Should the 🔌 badge show disabled plugins (grey, "1 disabled") or count only the active ones?
