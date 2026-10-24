<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# RTI demo: specs

A spec describes a change before it is built: what it is for, what changes where, and how it is tested. When a
spec changes the plugin contract or a design choice, it gets a decision in [decisions/](../decisions/README.md) when it
is built; the spec stays as the record of what was asked for.

Status: **draft** (open for comments), **accepted** (to be built), **done** (built; the commit is named), or
**dropped** (with the reason).

## Plugins panel

The HMI's Plugins panel (PluginsPanel, on ACSI Client and ACSI Server) has Details (with a request form for the
plugin's own routes, 0001), Edit, Copy as configuration, Reload / Retry now and Remove per plugin, and Add plugin and
Retry in its header. These specs extend it.

| Spec | What | Changes | Status |
|---|---|---|---|
| [0001](0001-plugin-route-console.md) | Call a plugin's own routes from its Details | HMI | done |
| [0002](0002-add-plugin-to-another-instance.md) | Add a plugin to another SO or FSP | HMI | draft |
| [0003](0003-export-plugin-configuration.md) | Download an instance's plugin configuration | HMI | draft |
| [0004](0004-disable-plugin.md) | Disable and enable a plugin without removing it | contract, plugin host, HMI | draft |
| [0005](0005-plugin-settings-schema.md) | A plugin describes its settings as JSON Schema | contract, plugin host, HMI | draft |
| [0006](0006-check-plugin.md) | Check a plugin without restarting it | contract, plugin host, HMI | draft |
| [0007](0007-clear-plugin-error.md) | Clear a plugin's last error | contract, plugin host, HMI | draft |

0001 to 0003 need no change to the FSP, SO or plugins: they use routes that exist. 0004 to 0007 change the plugin
contract (`modules/plugins/openapi.yaml`), the plugin host (`modules/plugins/src/acsi_plugins/`) and then the HMI.

### Shared by 0004, 0006 and 0007: new routes under `/api/plugins/{name}/`

Everything under `/api/plugins/{name}/` other than `POST .../reload` is passed on to the plugin's own routes. A new
management route there (`.../disable`, `.../check`, `.../last_error`) hides a plugin route of the same name, as
`reload` does already. Before building any of them, decide once for all three:

1. **Reserve the names** (`reload`, `disable`, `enable`, `check`, `last_error`) in the contract, as `reload` is: the
   simplest; a plugin with a route of that name can't be reached there.
2. **Put management under its own prefix**, e.g. `/api/plugins/{name}/_/disable`, reserving only `_`. New actions
   then never hide plugin routes; `reload` stays where it is for compatibility.
3. **Use the plugin resource itself**: `PATCH /api/plugins/{name}` with `{enabled}` (0004), `DELETE` of a field
   (0007), `POST /api/plugins/{name}:check` style (0006). Hides nothing, but is less uniform.

Recommended: 2, since the list of actions is growing and plugins are written by third parties.

## Format

Each spec has: Status and Date; Goal; Now (how it is today); Proposal (per part that changes); Acceptance; Tests;
Docs to update; Open questions. Specs are numbered in order of writing.
