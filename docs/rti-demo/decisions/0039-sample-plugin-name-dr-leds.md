<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 39. The sample plugin's name, code, project and image are `dr_leds` / `dr-leds`

- Status: proposed
- Date: 2026-10-26

## Context

The sample plugin is `sim_leds`: its plugin name, folder and package ([0029](0029-plugins-are-http-services.md)), its
distribution, script and image `sim-leds` ([0030](0030-plugin-project-layout.md)), and its compose services
`sim-leds-<instance>` in the demo stack ([0034](0034-demo-stack-plugins-sim-leds-io-opt-in.md)).

- The IO plugin is now `dr_panel` ([0038](0038-io-plugin-name-dr-panel.md)) and the display plugin dr-st7789v. With
  `sim_leds` the plugins in `examples/rti-plugins` had two naming schemes.
- **`sim` says how it is run, not what it is.** Its LEDs are simulated, but the plugin API, the claims and the routes
  are those of a real plugin, and the sample is what third parties copy (0030). The name it is copied from becomes
  the prefix their plugins start with.

## Decision

1. **Everything named after the sample takes the `dr-` prefix:**

   | | Was | Now |
   |---|---|---|
   | Plugin name, in the plugin configurations | `sim_leds` | `dr_leds` |
   | Its routes in the FSP and SO | `/api/plugins/sim_leds/*` | `/api/plugins/dr_leds/*` |
   | Folder and package | `examples/rti-plugins/sim_leds`, `sim_leds` | `examples/rti-plugins/dr_leds`, `dr_leds` |
   | Distribution, script and image | `sim-leds` | `dr-leds` |
   | Its own stack's service, container, host name | `sim-leds` | `dr-leds` (`http://dr-leds:8099/plugin`) |
   | The demo stack's services and containers | `sim-leds-fsp01`, `sim-leds-fsp02`, `sim-leds-so` | `dr-leds-fsp01`, `dr-leds-fsp02`, `dr-leds-so` |
   | Environment | `SIM_LEDS_CLAIMS`, `SIM_LEDS_BIND`, `SIM_LEDS_PORT` | `DR_LEDS_CLAIMS`, `DR_LEDS_BIND`, `DR_LEDS_PORT` |

   Unlike the IO plugin (0038 point 2), the plugin name changes too: `sim_leds` is the sample's own name, not a role.
2. **What stays**: port 8099, the overlay `docker-compose.leds.yaml`, the server's `/leds-api`, and the image still
   isn't published.
3. `tests/unit/test_rti_demo_io_names.py` checks that `sim_leds`, `sim-leds` and `SIM_LEDS` appear only in the
   decision records, in links to 0034, and in the tests that check them.

## Consequences

- Breaking for paths, the plugin name and its routes, the host names and the environment. A plugin configuration with
  `{"name": "sim_leds", "url": "http://sim-leds-fsp01:8099/plugin"}` needs
  `{"name": "dr_leds", "url": "http://dr-leds-fsp01:8099/plugin"}`; a link or script to `/api/plugins/sim_leds/...`
  needs `dr_leds`; `SIM_LEDS_CLAIMS` in a `.env` is no longer read. Stop the old containers
  (`docker compose -f docker-compose.yml -f docker-compose.leds.yaml down --remove-orphans`, or
  `docker compose -p sim_leds down` for its own stack) before starting them under the new names.
- `GETTING_STARTED.md` has a third party copy `dr_leds` and rename its package, project and script.
- Superseded: 0029's plugin name and folder `sim_leds`, 0030's project, script and image `sim-leds`, and 0034's
  service names `sim-leds-<instance>`. The records 0022-0037 keep the names they were written with; this record says
  where they went. 0034's file name keeps `sim-leds`, so links to it stay.

## In the code

- `examples/rti-plugins/dr_leds/` (was `sim_leds/`): `pyproject.toml`, `uv.lock`, `docker/Dockerfile`,
  `docker-compose.yaml`, `src/dr_leds/` (`NAME`, `DR_LEDS_CLAIMS`), `tests/test_dr_leds.py` (was `test_sim_leds.py`),
  `tests/test_project.py`, the README
- `examples/rti-demo/docker-compose.leds.yaml`, `docker-compose.yml`, `docker-compose.io.yaml`,
  `config/plugin-configuration/*.json`, the READMEs, `TESTING.md`; `modules/plugins` (`GETTING_STARTED.md`, README,
  tests); the HMI's tests
- `.github/workflows/ci.yml`, `REUSE.toml`
- `docs/rti-demo`: system architecture diagram, specs 0002 and 0005
- Tests: `tests/unit/test_rti_demo_io_names.py`, `test_rti_demo_ports.py`, `test_rti_plugins_source_layout.py`
