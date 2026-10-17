<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 32. The IO plugin's folder is `rpi_io`, after its package

- Status: proposed
- Date: 2026-10-17

## Context

Since [0030](0030-plugin-project-layout.md) every plugin is a project in its own folder of `examples/rti-plugins`, and
[0031](0031-plugin-source-layout.md) gave them one source layout. The IO plugin's folder still had the name of its
role, `io` ([0018](0018-io-module-names.md)), while everything else of the project had the name 0023 chose for the
code (2026-10-17):

| | `io` | `sim_leds` | dr-st7789v |
|---|---|---|---|
| Folder | `io` | `sim_leds` | `dr-st7789v` |
| Package | `rpi_io` | `sim_leds` | `dr_st7789v` |
| Distribution and script | `rpi-io` | `sim-leds` | `dr-st7789v` |

- **The folder was the only name that differed.** In the other plugins the folder, package and project share one
  name; a reader who knows one finds the others.
- **`io` is a role, not a plugin.** In a folder of plugins it says nothing about what this one drives, and leaves no
  obvious name for a second IO plugin, for another board or for the SSD1306 OLED of [0024](0024-ssd1306-oled-display-device.md)
  as a plugin of its own.
- 0023 already explained the name `rpi_io`: what runs (IO) and what it runs on (the Raspberry Pi).

Names for the hardware, as dr-st7789v has, were not considered: the IO plugin's devices are configuration
([0026](0026-io-server-pins-are-configuration.md)), not one panel.

## Decision

1. **The folder `examples/rti-plugins/io` becomes `examples/rti-plugins/rpi_io`**, the package's name, as `sim_leds`
   is. Nothing inside it changes: the package `rpi_io`, the distribution and script `rpi-io`, the subpackages
   `server` and `plugin`, the compose files and the image's build context relative to the folder.
2. **The role keeps its names** (0018, 0023 point 1): the image and container `rti-io`, the compose service `rti-io`,
   port 9000, the `launch.py` service `io`, and the plugin name `io` in the plugin configurations
   (`config/plugin-configuration/`, `PLUGINS`), with its routes `/api/plugins/io/*`. They name what the IO plugin
   is in the demo; the folder names the code that fills that role.
3. Every path follows: CI (`ci.yml`, `images.yml`), `launch.py`, `REUSE.toml`, the READMEs, `TESTING.md`,
   `CONTRIBUTING.md` and the unit tests. `tests/unit/test_rti_plugins_io_compose.py` becomes
   `test_rti_plugins_rpi_io_compose.py`.

## Consequences

- In `examples/rti-plugins` the folder is the package: `rpi_io`, `sim_leds`, and the next plugin's.
- Breaking for paths only: a checkout, script or `.env` that does `cd examples/rti-plugins/io` needs `rpi_io`. On the
  Raspberry Pi, a running `rti-io` keeps running. Compose names the project after the folder, so the stack started
  from `io` is the project `io`: stop it with `docker compose -p io down` before starting it from `rpi_io`, or the
  container name `rti-io` is taken.
- The records 0028-0031 keep the path `io` they were written with; this record says where it is now.

## In the code

- `examples/rti-plugins/rpi_io/` (was `io/`); `examples/rti-plugins/README.md`
- `.github/workflows/ci.yml`, `.github/workflows/images.yml`, `examples/rti-demo/launch.py`, `REUSE.toml`
- `examples/rti-demo/README.md`, `TESTING.md`, `docker-compose.yml` (comment), `modules/fsp/README.md`,
  `modules/so/README.md`, `docs/rti-demo/README.md`, `CONTRIBUTING.md`
- Tests: `tests/unit/test_rti_plugins_rpi_io_compose.py`, `test_rti_plugins_source_layout.py`,
  `test_rti_demo_launch.py`, `test_rti_demo_ports.py`, `test_rti_demo_io_image.py`, `test_rti_demo_io_names.py`
