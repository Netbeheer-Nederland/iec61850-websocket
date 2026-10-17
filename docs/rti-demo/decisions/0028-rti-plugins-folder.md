<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 28. Plugins and the IO server move to `examples/rti-plugins`; the IO server is its own stack

- Status: proposed
- Date: 2026-10-17

## Context

Since [0021](0021-acsi-plugin-host.md) the FSP and SO host plugins, and since
[0027](0027-plugin-contract-as-openapi.md) the contract is published for third parties. What plugs into the FSP and SO
was spread over the demo (2026-10-17):

- **The IO server**, `modules/io` (`rpi_io`, image `rti-io`, [0023](0023-io-server-package-rpi-io.md)), is built for
  and runs on a Raspberry Pi. The FSP, SO, BFF and HMI can run on any amd64 machine. It already had its own build: its
  own uv project and lock, outside the workspace ([0011](0011-io-separate-project-runtime-plugin.md)), its own Docker
  context, and its own image filter in `images.yml`. Its release follows the Pi's, not the demo's. Yet
  `docker-compose.yml` started it with the demo, and the overlay `docker-compose.no-devices.yml`
  ([0017](0017-hardware-is-optional.md)) existed only to make that work on a machine without the Pi.
- **The IO plugin**, `modules/io-plugin` ([0022](0022-io-plugin-own-package.md)), sat in `modules/` among the
  services.
- **The sample plugin** `sim_leds` sat inside the plugin host, `modules/plugins/samples/`, and its test among the
  host's tests.

Three layouts were considered:

1. **Leave it as it is.** No churn, but nothing shows that the IO server has its own cycle, or where a new plugin goes.
2. **A `plugins/` folder inside `rti-demo`** for the plugins only, with the IO server staying in `modules/`. Groups the
   plugins, but keeps a Pi-only component in the demo's stack.
3. **A sibling example, `examples/rti-plugins`, one folder per integration**, with the IO server as its own stack
   (chosen).

## Decision

1. **`examples/rti-plugins` holds what can be attached to the FSP and SO,** one folder per integration:

   | Was | Is |
   |---|---|
   | `examples/rti-demo/modules/io` | `examples/rti-plugins/io/server` |
   | `examples/rti-demo/modules/io-plugin` | `examples/rti-plugins/io/plugin` |
   | `examples/rti-demo/modules/plugins/samples/sim_leds` | `examples/rti-plugins/sim_leds` |
   | `examples/rti-demo/scripts` (the Pi's scripts) | `examples/rti-plugins/io/server/scripts` |

   Package, distribution and image names don't change: `rpi_io`/`rpi-io` and `rti-io`, `acsi_io_plugin`/
   `acsi-io-plugin`, `sim_leds`.
2. **The plugin host stays in the demo** (`modules/plugins`, with `openapi.yaml`): it is part of the FSP and SO.
   Plugins depend on the host, never the other way round. The host's tests no longer read the sample.
   `sim_leds` has its own tests next to it (`sim_leds/tests`), as `GETTING_STARTED.md` tells a plugin author to do.
3. **The IO server is its own stack.** `rti-io` leaves `examples/rti-demo/docker-compose.yml` and gets
   `examples/rti-plugins/io/server/docker-compose.yml`, with build context `.`. The overlay
   `docker-compose.no-devices.yml` moves next to it. Both stacks join the external network `rti-network`, so on one
   Docker host the FSPs and SO still reach it as `http://rti-io:9000`, and their `IO_URL` doesn't change. Started
   without it, the IO plugin logs that it can't connect and stays loaded (it already did, 0022), and the rest of the
   demo works.
4. **The IO plugin stays in the FSP and SO images and the workspace.** Its folder groups it with its server; its
   build follows the FSP and SO: a change to it rebuilds both images, as before.
5. **`launch.py io` stays.** It runs `rpi_io` from `examples/rti-plugins/io/server/src`, in mock mode off the Pi, so
   one machine can still run the whole demo for development. Its local `io_config.json` stays in
   `examples/rti-demo/config/`.

## Consequences

- A new integration has an obvious place: a folder in `examples/rti-plugins`, with its plugin and, if it has one, its
  own service.
- The demo's compose describes what runs on any amd64 machine; the Pi starts `rti-io` from its own folder. On a laptop
  the demo needs no overlay; to try the IO server there, start its stack with the overlay.
- **Breaking for anyone running the demo on a Pi with compose**: `docker compose up` in `examples/rti-demo` no longer
  starts `rti-io`; start it in `examples/rti-plugins/io/server` as well. `COMPOSE_FILE` settings that name
  `docker-compose.no-devices.yml` in `examples/rti-demo` must be removed. Paths in local scripts and bookmarks change.
- **On two hosts** (the demo on amd64, `rti-io` on a Pi), each side reaches the other by name only on a shared Docker
  network. The FSP's and SO's `IO_URL`, and the `ACSI_BASE_URL` the IO server writes back to, must then be addresses
  each host can reach. They are fixed in `docker-compose.yml` today. Making them settable per deployment is a
  follow-up.
- Superseded in [0017](0017-hardware-is-optional.md): "`docker-compose.yml` targets the Raspberry Pi"; the overlay now
  belongs to the IO server's stack. The rest of 0017 stands.
- Superseded, in every earlier record that names them ([0011](0011-io-separate-project-runtime-plugin.md),
  [0017](0017-hardware-is-optional.md) to [0019](0019-io-server-serves-only-plugin-files.md),
  [0021](0021-acsi-plugin-host.md) to [0026](0026-io-server-pins-are-configuration.md)): the paths `modules/io`,
  `modules/io-plugin`, `modules/plugins/samples/sim_leds` and `examples/rti-demo/scripts`. Their decisions stand.
- Superseded in [0027](0027-plugin-contract-as-openapi.md): the check that the sample's manifest equals the spec's
  example. The host's test now checks that the example is a valid manifest.

## In the code

- `examples/rti-plugins/` (new): `README.md`, `io/server/`, `io/plugin/`, `sim_leds/` (with `tests/`)
- `examples/rti-plugins/io/server/docker-compose.yml` (new), `docker-compose.no-devices.yml`, `scripts/`
- `examples/rti-demo/docker-compose.yml` (no `rti-io`), `launch.py` (the IO server's path)
- `pyproject.toml` (workspace member `examples/rti-plugins/io/plugin`), `uv.lock`
- `examples/rti-demo/modules/{fsp,so}/docker/Dockerfile` (`COPY` of the IO plugin), `.dockerignore`
- `.github/workflows/ci.yml` (test paths, the `sim_leds` tests), `.github/workflows/images.yml` (filters, `rti-io`
  context), `REUSE.toml`
- Tests: `tests/unit/test_rti_demo_ports.py` (the IO server's own compose, and that the demo's has no `rti-io`),
  `test_rti_demo_compose_no_devices.py`, `test_rti_demo_launch.py`, `test_rti_demo_io_image.py`,
  `test_rti_demo_io_names.py`; `examples/rti-demo/modules/plugins/tests/test_openapi.py`
- Docs: the READMEs of `rti-demo`, `rti-plugins`, the IO server and plugin, the plugin host, the FSP and SO;
  `TESTING.md`, `CONTRIBUTING.md`, `docs/rti-demo/README.md`
