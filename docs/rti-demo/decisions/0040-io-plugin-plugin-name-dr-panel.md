<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 40. The IO plugin's plugin name is `dr_panel`

- Status: proposed
- Date: 2026-10-26

## Context

[0038](0038-io-plugin-name-dr-panel.md) renamed the IO plugin's code, project and image to `dr_panel` / `dr-panel`,
but kept its plugin name `io` (point 2), so a plugin configuration said `{"name": "io", "url":
"http://dr-panel:9000/plugin"}` and its routes were `/api/plugins/io/*`. It left renaming that open, as it changes every
plugin configuration and the HMI's links to the plugin's routes.

The sample plugin has since become `dr_leds` everywhere, its plugin name too ([0039](0039-sample-plugin-name-dr-leds.md)).
With `io` the IO plugin was the only one whose plugin name differs from its package, and the HMI showed `io` next to
`dr_leds`.

## Decision

1. **The IO plugin's plugin name is `dr_panel`**, after its package: `NAME` in `dr_panel/plugin/plugin.py`, the
   `name` in the plugin configurations, and its routes in the FSP and SO, `/api/plugins/dr_panel/*` (was
   `/api/plugins/io/*`).
2. **What names the role in the demo stays `io`** (0038 point 2, otherwise unchanged): the IO server's own routes
   `/api/io`, the `launch.py` service `io`, the overlay `docker-compose.io.yaml`, `config/plugin-configuration/io/`,
   the label `rti.type=RTI-IO`, port 9000, and the modules `server/io_config.py`, `server/io_controller.py`. The
   attached item's `kind` `io` is a kind of device, not the plugin, and stays too.
3. `tests/unit/test_rti_demo_io_names.py` checks that `/api/plugins/io` and a plugin named `io` appear only in the
   decision records.

## Consequences

- Breaking for plugin configurations and the plugin's routes: `{"name": "io", ...}` needs `{"name": "dr_panel", ...}`,
  and a link or script to `/api/plugins/io/...` needs `/api/plugins/dr_panel/...`. An FSP or SO with the old
  configuration doesn't connect: the plugin describes itself as `dr_panel`, and the host lists `io` as failed with
  "`<url>` is plugin 'dr_panel', not 'io'".
- The HMI has no special case for `io`; the Plugins panel, the attached boxes and the claim tags show `dr_panel`.
- Supersedes 0038 point 2 for the plugin name and its routes `/api/plugins/io/*`; the rest of that point stands.

## In the code

- `examples/rti-plugins/dr_panel/src/dr_panel/plugin/plugin.py` (`NAME`), `dr_panel/__init__.py`, the README, the tests
- `examples/rti-demo/config/plugin-configuration/io/*.json`, `launch.py`, the FSP's, SO's and plugins' READMEs
- `examples/rti-demo/modules/plugins`: `openapi.yaml` and `web.py` examples, `config.py` docstring, tests
- `examples/rti-demo/modules/hmi`: README, `apiService.js` comments, tests; `modules/bff/tests/test_push_relay.py`
- `docs/rti-demo`: wireframe, specs 0001, 0003, 0006
- `tests/unit/test_rti_demo_io_names.py`
