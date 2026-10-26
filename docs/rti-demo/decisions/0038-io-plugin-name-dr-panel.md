<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 38. The IO plugin's code, project and image are `dr_panel` / `dr-panel`

- Status: proposed
- Date: 2026-10-25

## Context

The IO plugin's code was `rpi_io` ([0023](0023-io-server-package-rpi-io.md)), its folder too
([0032](0032-io-plugin-folder-rpi-io.md)), its distribution, script and container `rpi-io`, and its image `rti-io`.

- **`io` says what it is made of, not what it does.** The plugin drives LEDs that show switch positions, buttons that
  Operate, potentiometers as measured values and the OLED and LCD displays: a local panel for the FSP. "IO" fits any
  plugin that touches hardware.
- **`io` is also Python's standard library module.** The package was never called `io` (0018 chose `rti_io`, 0023
  `rpi_io` for that reason), but every name built on it kept the clash in sight.
- **`rpi` ties it to one board**, while its devices are configuration ([0026](0026-io-server-pins-are-configuration.md))
  and run in mock mode anywhere.
- The display plugin next to it is dr-st7789v: a `dr-` prefix and what it is.

## Decision

1. **The code, the project and the image are named after the panel:**

   | | Was | Now |
   |---|---|---|
   | Folder and package | `examples/rti-plugins/rpi_io`, `rpi_io` | `examples/rti-plugins/dr_panel`, `dr_panel` |
   | Distribution and script | `rpi-io` | `dr-panel` |
   | Image | `${RTI_IMAGE_REPO}/rti-io` | `${RTI_IMAGE_REPO}/dr-panel` |
   | Compose service, container, host name | `rpi-io` | `dr-panel` (`http://dr-panel:9000/plugin`) |

   The compose service and container follow the distribution, as they did.
2. **The role keeps its names** (0032 point 2): the plugin name `io` in the plugin configurations and its routes
   `/api/plugins/io/*`, the IO server's own routes `/api/io`, the `launch.py` service `io`, the overlay
   `docker-compose.io.yaml`, `config/plugin-configuration/io/`, the label `rti.type=RTI-IO`, port 9000, and the
   modules `server/io_config.py` and `server/io_controller.py`. They name what the plugin is in the demo, not the code.
3. `tests/unit/test_rti_demo_io_names.py` checks that `rti_io`, `rpi_io`, `rpi-io` and `rti-io` appear only in the
   decision records and in the tests that check them.

## Consequences

- Breaking for paths, the image and the host name. A checkout or script that does `cd examples/rti-plugins/rpi_io`
  needs `dr_panel`; a plugin configuration with `http://rpi-io:9000/plugin` needs `http://dr-panel:9000/plugin`;
  a Pi that pulls `rti-io` pulls `dr-panel`. Stop the old stack (`docker compose -p rpi_io down`) before starting it
  from `dr_panel`, or port 9000 is taken.
- The published `rti-io` image stays as it is; new builds publish `dr-panel` (`images.yml`).
- Superseded: 0023's package and distribution name `rpi_io` / `rpi-io`, 0032's folder `rpi_io`, and the image name
  `rti-io` of 0018 and 0032. The records 0017-0037 keep the names they were written with; this record says where
  they went.
- Renaming the role `io` itself (the plugin name and its routes) is left open: it would change every plugin
  configuration and the HMI's links to the plugin's routes.
- Superseded in [0040](0040-io-plugin-plugin-name-dr-panel.md): point 2 for the plugin name `io` and its routes
  `/api/plugins/io/*`, now `dr_panel`; the rest of point 2 stands.

## In the code

- `examples/rti-plugins/dr_panel/` (was `rpi_io/`): `pyproject.toml`, `uv.lock`, `docker/Dockerfile`, both compose
  files, `src/dr_panel/`, the tests and scripts, the README
- `examples/rti-demo/docker-compose.io.yaml`, `config/plugin-configuration/io/*.json`, `launch.py`, the READMEs,
  `TESTING.md`; `modules/plugins` (`openapi.yaml` examples, README, tests); the HMI's tests
- `.github/workflows/ci.yml`, `.github/workflows/images.yml`, `REUSE.toml`, `CONTRIBUTING.md`
- `docs/rti-demo`: README, wireframe, system architecture diagram, specs 0003 and 0005
- Tests: `tests/unit/test_rti_plugins_dr_panel_compose.py` (was `..._rpi_io_compose.py`), `test_rti_demo_io_names.py`,
  `test_rti_demo_io_image.py`, `test_rti_demo_ports.py`, `test_rti_demo_launch.py`, `test_rti_plugins_source_layout.py`
