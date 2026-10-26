<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 30. Every plugin is a project with one layout: `server` and `plugin` subpackages, `docker/`, a compose pair

- Status: proposed
- Date: 2026-10-17

## Context

Since [0029](0029-plugins-are-http-services.md) a plugin is an HTTP service the FSP and SO connect to, built and run on
its own. The two plugins in this repository were laid out differently, and neither like the plugin of the dr-st7789v
display, which is developed outside it (2026-10-17):

| | dr-st7789v | `io` | `sim_leds` |
|---|---|---|---|
| Project root | the repository | `io/server/`, under a folder with nothing else in it since the IO plugin package went (0029) | the folder, with no `pyproject.toml` |
| Code | `src/dr_st7789v/server/` and `src/dr_st7789v/plugin/` | `src/rpi_io/`, flat (0023); the plugin API in `plugin.py` next to the server's modules | `sim_leds.py` and `leds.py`, run with `uvicorn --app-dir` |
| Started with | a script, `dr-st7789v` | `python -m rpi_io.main` | `uv run --no-project --with fastapi --with uvicorn uvicorn sim_leds:app ...` |
| Image | `docker/Dockerfile`, `docker/Dockerfile.dockerignore` | `docker/Dockerfile`, no ignore file | none |
| Compose | `docker-compose.yaml` runs anywhere; `docker-compose.pi.yaml` adds the Pi's devices | `docker-compose.yml` needs the Pi; `docker-compose.no-devices.yml` takes the devices out again with `!reset` (Compose 2.24+) | none |

With plugins written by third parties, the layout is what they copy. 0023 kept `rpi_io` flat because a `server` level
"separates nothing"; with the plugin API in the same package, it now does.

## Decision

1. **Every plugin is its own project with this layout**, the one dr-st7789v has:

   ```text
   <plugin>/
   ├── pyproject.toml, uv.lock   # its own uv project, not a workspace member; [project.scripts] starts it
   ├── README.md
   ├── docker-compose.yaml       # its own stack, on the external network rti-network; runs anywhere
   ├── docker-compose.pi.yaml    # only with hardware: passes the Raspberry Pi's devices in
   ├── docker/Dockerfile, docker/Dockerfile.dockerignore   # context: the project folder
   ├── src/<package>/server/     # the service, with its own routes
   ├── src/<package>/plugin/     # the plugin API under /plugin (0029)
   └── tests/
   ```

   The server's app mounts the plugin's router; the plugin uses the server's objects. Nothing else is at the top of
   the package.
2. **`io`**: `io/server/` moves up to `io/`. `rpi_io` gets `server/` (`main`, `api_endpoint`, `io_controller`,
   `devices`, `pins`, `io_config` with `io_config.json`, `lcd_i2c_check`) and `plugin/` (`plugin`, `mapping`,
   `io_mapping.json`). It starts with the script `rpi-io` (`rpi_io.server.main:main`), in the image too, or
   `python -m rpi_io.server.main`. `docker-compose.yml` becomes `docker-compose.yaml` without the devices, and
   `docker-compose.no-devices.yml` becomes `docker-compose.pi.yaml`, which adds them (`user`, `group_add`, `devices`,
   `ipc`, `security_opt`, `cap_add`). This supersedes 0023 point 2 (flat, `python -m rpi_io.main`) and point 6's
   start command; the name `rpi_io`, its own uv project and its dependencies stand.
3. **`sim_leds`** becomes the project `sim-leds`: `src/sim_leds/server/` (`leds`, `app` with `/leds-api`, `main`)
   and `src/sim_leds/plugin/` (`plugin`), the script `sim-leds`, its own `uv.lock`, an image and a
   `docker-compose.yaml` (`http://sim-leds:8099/plugin` on `rti-network`). It has no hardware, so no Pi overlay. The
   app is built by `create_app()`, so each test has its own LEDs.
4. **Tests stay where 0029 ran them**: the IO plugin's in the `fsp` environment, `sim_leds`'s in `acsi-plugins`'s,
   both with `pythonpath = ["src"]`. CI checks every compose file with `docker compose config`, the IO plugin's with
   and without the Pi overlay.

## Consequences

- A plugin from this repository and one from outside it look the same; `GETTING_STARTED.md` tells a third party to
  copy `sim_leds` and keep the layout.
- **On the Pi, compose needs the overlay.** `docker compose up` in `io/` now starts `rti-io` without devices, in mock
  mode. Use `docker compose -f docker-compose.yaml -f docker-compose.pi.yaml up -d`, or set
  `COMPOSE_FILE=docker-compose.yaml:docker-compose.pi.yaml` in `.env`. The `!reset` overlay, and its need for Compose
  2.24, are gone. `rti-io` now restarts with the Docker daemon (`restart: unless-stopped`), like dr-st7789v.
- **Breaking, without a transition**: `python -m rpi_io.main`, the path `io/server`, `docker-compose.yml` and
  `docker-compose.no-devices.yml` in `io/`, and `sim_leds.py` as an `--app-dir` module are gone. A `.env` or script
  on the Pi that names them needs the new names. The image `rti-io` is built from `examples/rti-plugins/io`.
- `sim_leds` has an image to build but none is published; `images.yml` publishes `rti-io` only.
- dr-st7789v's plugin still has contract version 1 (`plugin.json`, downloaded into the FSP); in this layout its
  `plugin/` becomes the plugin API of 0029, as here.
- Superseded in [0039](0039-sample-plugin-name-dr-leds.md): the project, script and image `sim-leds` and the
  package `sim_leds` are now `dr-leds` / `dr_leds`.

## In the code

- `examples/rti-plugins/io/`: `pyproject.toml` (script, package data per subpackage), `docker/Dockerfile`,
  `docker/Dockerfile.dockerignore` (new), `docker-compose.yaml`, `docker-compose.pi.yaml`, `scripts/`,
  `src/rpi_io/{server,plugin}/`, `tests/test_project.py`, `README.md`
- `examples/rti-plugins/sim_leds/`: `pyproject.toml`, `uv.lock`, `README.md`, `docker/`, `docker-compose.yaml` (new),
  `src/sim_leds/{server,plugin}/`, `tests/test_project.py` (new)
- `examples/rti-demo/launch.py` (`rpi_io.server.main` from `io/src`); `.github/workflows/{ci,images}.yml`,
  `REUSE.toml`, `.dockerignore`, `pyproject.toml` (workspace comment)
- Tests: `tests/unit/test_rti_plugins_io_compose.py` (was `test_rti_demo_compose_no_devices.py`),
  `test_rti_demo_launch.py`, `test_rti_demo_ports.py`, `test_rti_demo_io_image.py`
