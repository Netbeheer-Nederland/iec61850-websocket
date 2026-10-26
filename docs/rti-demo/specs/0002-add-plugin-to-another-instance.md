<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 0002. Add a plugin to another SO or FSP

- Status: done
- Date: 2026-10-24
- Changes: HMI

## Goal

Give a second FSP (or the SO) the same plugin as the first, from the HMI, without typing its URL and settings again.

## Now

- Each Plugins panel shows one instance; Add plugin takes a name, URL and settings by hand.
- A plugin describes itself with a fixed name, and that name must be the name it is added under (contract,
  *Describe the plugin*). So a copy of a plugin **within one instance**, under another name, is always refused; this
  is why the earlier idea "Duplicate" became this spec.
- One plugin service can serve several instances: each `POST <url>/start` carries the instance's `Host` (name, role,
  `host_url`), as dr_leds does for every FSP.
- The BFF's connections list every SO and FSP the HMI can reach (the targets), with their roles.

## Proposal

### HMI

1. A per-row action **Add to another SO or FSP** (icon `fa-share-square`), enabled when the row has a definition.
2. It opens a small form: a select of the other instances the BFF knows (name and role; the current one left out;
   FSPs only for a plugin with claims, as SO plugins answer no Operate), and the plugin's name, URL and settings,
   filled in and editable.
3. **Add** calls `POST /api/plugins` on the chosen instance (`plugin-add`, with that instance's target), and shows the
   result in the panel: "Added io to rti-fsp02", or the instance's reason in the alert.
4. The other instance's panel shows the plugin through the BFF's push, as for any add.

### FSP, SO, BFF

No change. The other instance's `PLUGIN_ALLOWED_SOURCES` applies, and its reason is shown when it refuses.

## Acceptance

- Add to... lists the other reachable instances, not the current one; a plugin with claims lists only FSPs.
- Adding sends `POST /api/plugins` with the definition to the chosen instance's target.
- A refusal (409: already has a plugin with that name, or a claim taken; 403: source not allowed; 422: unreachable)
  shows the instance's reason, and the form stays open.

## Tests

PluginsPanel.test.jsx: target list without the current instance; FSP-only for claims; the call goes to the chosen
target with the definition; refusal keeps the form open with the reason.

## Docs to update

Wireframe (an "Add to..." icon in the rows, the form in the ⓘ text), HMI README (Plugins panel).

## Answered

- The list of instances is a prop from the page: ACSIServer and ACSIClient pass App.jsx's live connections
  (`instances`), which also carry each instance's plugins, so an instance that has the plugin already is greyed.
- **Add to all FSPs** is left out for now: one Add per FSP does the same, and each refusal stays clear.
