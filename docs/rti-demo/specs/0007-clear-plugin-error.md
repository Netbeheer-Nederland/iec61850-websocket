<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 0007. Clear a plugin's last error

- Status: draft
- Date: 2026-10-24
- Changes: plugin contract, plugin host, HMI

## Goal

Once a plugin's error has been looked at, take it off the panel, so a new error stands out, without restarting the
plugin.

## Now

- `last_error` is kept after the plugin is healthy again (contract: "The last error, kept after the plugin is healthy
  again"), and the panel shows it under Healthy. A blip a day ago looks the same as one a second ago.
- Reload clears it (the host makes a new entry for the plugin), but restarts the plugin.
- There is no time on the error.

## Proposal

### Plugin contract and host

1. `PluginStatus` gets **`last_error_at`**: when `last_error` was recorded (ISO 8601, UTC), `null` without one.
2. A management route **clear the error**, e.g. `DELETE /api/plugins/{name}/_/last_error` (route form per the shared
   choice in the [specs README](README.md)): sets `last_error` and `last_error_at` to `null`. `healthy` doesn't
   change: an unhealthy plugin stays unhealthy until an event or Operate succeeds, and its next failure records a new
   error. Answers the plugin's status; `404` for an unknown name.
3. A failed plugin's reason (under `failed`) is not cleared: it is the reason it isn't connected, and the next retry
   replaces it.
4. Plugin API unchanged.

### HMI

1. The error under the state shows its age: "ValueWritten timed out after 5.0s · 3 h ago" (from `last_error_at`;
   without it, as now).
2. A small **✕** next to an error of a healthy or unhealthy plugin, title "Clear the error": the `DELETE`, no
   confirm.
3. No ✕ for an unreachable plugin's reason.

## Acceptance

- Clearing removes `last_error` and `last_error_at` and leaves `healthy` as it was.
- The next failure records a new error with its time.
- The panel shows the age and hides the error after ✕, also for other viewers (it comes from the instance).

## Tests

modules/plugins: test_host.py (`last_error_at` set on failure, kept on success), test_web.py (clear, healthy kept,
404), test_openapi.py. HMI: plugins.test.js (age), PluginsPanel.test.jsx (✕ only for connected plugins, the call).

## Docs to update

`openapi.yaml` (`PluginStatus.last_error_at`, the route), plugins README, fsp/so READMEs (route tables), the decision
shared with 0004 and 0006, wireframe (age and ✕ in the State cell), HMI README.

## Alternative considered

Acknowledge in the HMI only (the cleared error kept per viewer in `localStorage`, shown again when it changes): no
contract change, but every viewer clears it again, and a repeat of the same error stays hidden. Not proposed.
