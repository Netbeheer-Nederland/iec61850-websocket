<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 0006. Check a plugin without restarting it

- Status: draft
- Date: 2026-10-24
- Changes: plugin contract, plugin host, HMI

## Goal

See whether a plugin answers, and whether it still describes itself as when it was connected, without stopping it
and without waiting for an event or Operate to fail.

## Now

- `healthy` changes only when an event or an Operate to the plugin fails or succeeds. A quiet instance (no
  association, no reports) can show a dead plugin as Healthy for a long time.
- Reload checks it, but stops and starts the plugin: its state (open hardware, a subscription) is reset.
- What the plugin attaches (`GET <url>/attached`) is asked regularly, but its failure sets `attached_error`, not
  `healthy`.

## Proposal

### Plugin contract and host

1. A management route **check**, e.g. `POST /api/plugins/{name}/_/check` (the route form per the shared choice in
   the [specs README](README.md)). It calls `GET <url>` (describe) with the event timeout, and nothing else: no
   `/stop`, no `/start`.
2. Its answer:

   ```json
   {
     "name": "dr_panel",
     "reachable": true,
     "milliseconds": 12,
     "changed": ["version", "claims"],
     "description": { "name": "dr_panel", "version": "1.1.0", "api": 2, "claims": [], "routes": "/api/io" }
   }
   ```

   `changed` lists what differs from the description the plugin was connected with (version, claims, routes, api):
   a reload takes it. Unreachable: `reachable: false` and the reason in `error`, answered `200` (the check worked).
3. A check that reaches the plugin records success, one that doesn't records failure, as an event does: `healthy` and
   `last_error` follow it.
4. For a plugin under `failed`, check is a retry now: on success it is connected (as the retry loop would).
5. Plugin API unchanged: describe is already `GET <url>`.

### HMI

1. Per-row **Check** (icon `fa-stethoscope`) for connected plugins.
2. Its answer in the row: "Answers in 12 ms" for a few seconds, or "Not reachable: <reason>"; with `changed`: "io
   describes itself differently (version, claims): Reload to take it", with a Reload button.
3. The header's **Retry** stays for failed plugins; Check doesn't replace it.

## Acceptance

- Check on a connected plugin calls only `GET <url>`; the plugin isn't stopped.
- A plugin that stopped answering turns Unhealthy after a Check, with the reason.
- A changed description is reported in `changed`, and nothing is changed until Reload.

## Tests

modules/plugins: test_web.py (only describe is called; healthy follows; changed fields; failed plugin connected on
success), test_openapi.py. HMI: PluginsPanel.test.jsx (Check call, reachable and unreachable messages, changed with
Reload).

## Docs to update

`openapi.yaml` (route and `CheckResult`), plugins README, fsp/so READMEs (route tables), a new decision (with 0004's
and 0007's route choice), wireframe, HMI README.

## Open questions

- Should the instance check every plugin itself on a timer (a heartbeat, say every 30 s), so Healthy means "answered
  recently" without anyone pressing Check? Then this route is "check now", and the timer is a setting
  (`PLUGIN_CHECK_SECONDS`).
