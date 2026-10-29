<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 42. A plugin's claims can be set in its settings, so the configuration and the HMI change them

- Status: proposed
- Date: 2026-10-29

## Context

A plugin owns the objRefs it lists as `claims` in `GET <url>`; an Operate on one goes to its `/control` (decision
[0021](0021-acsi-plugin-host.md)). Only the plugin decides them: dr_leds reads `DR_LEDS_CLAIMS` from its environment,
so trying an interlock in the demo meant changing compose, restarting the container and reloading the plugin.

The objRefs belong to the FSP's model, which whoever configures the plugin knows, often better than the plugin. The
plugin's settings are already in its configuration and editable in the HMI (decision
[0036](0036-plugin-definitions-editable.md)). They only reach the plugin with `POST <url>/start`, after the FSP has
checked and registered the claims from `GET <url>`; a plugin reading its claims from its settings would be too late.

## Decision

1. **`settings.claims`, a list of objRefs, is read by the FSP or SO** before it starts the plugin. The plugin owns
   those as well as the ones it describes; both are checked against the other plugins' claims, as before, and
   `GET /api/plugins` lists them together.
2. **The settings stay the plugin's**: `claims` is sent with `/start` like any other setting. A plugin needn't know
   it; one that answers `/control` per objRef sees them there.
3. An objRef is what the FSP passes to `/control`: the control's `ctlVal`, e.g.
   `GenericIO/GGIO1.SPCSO2.Oper.ctlVal`.
4. Claims that aren't a list of strings are refused: a configuration error at startup, `422` on add or edit, before
   the plugin is stopped. A claim another plugin owns is `409`, as a described one is.
5. The HMI is unchanged: Edit (settings as JSON) changes the claims, Details shows them. An edit lasts until the FSP
   or SO restarts (0036); a lasting claim goes in the plugin configuration.
6. The plugin API stays at `api` 2: no call or field changes, only what the FSP reads from the settings.

## Consequences

- An interlock can be tried from the HMI: edit dr_leds on FSP02 to `{"claims": ["GenericIO/GGIO1.SPCSO2.Oper.ctlVal"]}`
  (playbook `examples/rti-plugins/dr_leds/playbooks/05-interlock-while-red.yaml`).
- `claims` is a reserved setting name: a plugin can't use it for anything else.
- A plugin's own `GET <url>` doesn't list the claims from its settings; `GET /api/plugins` in the FSP does.
- Anyone who can edit a plugin can claim any objRef of the FSP for it, and so hand that control's Operates to the
  plugin. That is the same trust as changing its URL.

## In the code

- `examples/rti-demo/modules/plugins/src/acsi_plugins/host.py` (`setting_claims`, `PluginHost.add`), `config.py`
  (`PluginEntry` checks them), `web.py` (`422`), `openapi.yaml`, the tests
- `examples/rti-demo/modules/plugins/README.md`, `GETTING_STARTED.md`; `examples/rti-plugins/dr_leds/` (README,
  plugin docstring, playbook 05)
