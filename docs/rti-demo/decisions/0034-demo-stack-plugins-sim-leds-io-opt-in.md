<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 34. The demo stack connects to sim_leds by default, run by an overlay; the IO server is opt-in

- Status: proposed
- Date: 2026-10-22

## Context

Since [0029](0029-plugins-are-http-services.md) the FSPs and SO connect to their plugins from a plugin configuration,
and compose gave all three the IO server, `http://rpi-io:9000/plugin` (point 5). The IO server is its own stack and is
meant for the Raspberry Pi ([0017](0017-hardware-is-optional.md), [0028](0028-rti-plugins-folder.md)). How things stood
(2026-10-22):

- **Without a Pi there is little to see.** Off the Pi, the LEDs and buttons need GPIO and stay unavailable; the
  potentiometers report a fixed mock value and the LCDs accept text and drop it.
- **Without the IO server the demo looks broken.** Most runs of the stack have no `rpi-io`. The FSPs and SO list `io`
  under `failed`, try again every 10 s, and since the plugin badge their circles on Overview and Traffic carry a red
  badge: a fault that is only a missing Pi.
- **Plugins are now visible in the HMI**: the Plugins panel, the plugin badge and the attached boxes
  ([0025](0025-plugins-show-attached-devices-in-hmi.md)). A demo without hardware has nothing to show there.
- **`sim_leds` needs no hardware.** It is the sample plugin: two LEDs in memory that follow associations, Operates,
  writes and reports, and it reports them as attached.

Options considered:

1. **No plugins by default; the IO server and sim_leds both opt-in.** No red badges, but the plugin features of the
   HMI are empty in the usual demo.
2. **sim_leds as a service of `docker-compose.yml`.** Always works, but puts a sample plugin in the demo's own stack,
   against 0028's split of the demo and the plugins.
3. **The configuration names sim_leds; an overlay, `docker-compose.leds.yaml`, runs it** (chosen). The IO server gets
   an overlay too, `docker-compose.io.yaml`.

## Decision

1. **The default plugin configuration is sim_leds**, one per FSP and SO: `config/plugin-configuration/rti-fsp01.json`,
   `rti-fsp02.json` and `rti-so.json` name `sim_leds` at `http://sim-leds-fsp01:8099/plugin`,
   `http://sim-leds-fsp02:8099/plugin` and `http://sim-leds-so:8099/plugin`. One each, because sim_leds keeps one pair
   of LEDs per process: shared, the three instances' events would mix.
2. **`docker-compose.leds.yaml` runs them**, an overlay on `docker-compose.yml`: `sim-leds-fsp01`, `sim-leds-fsp02` and
   `sim-leds-so`, image `sim-leds`, built from `examples/rti-plugins/sim_leds`, on `rti-network`, with no published
   ports (the HMI reaches the LEDs through `/api/plugins/sim_leds/`). Without the overlay the FSPs and SO retry
   sim_leds, as they did the IO server.
3. **The IO server is opt-in, through an overlay built like the LEDs one**: `docker-compose.io.yaml` runs `rpi-io`
   (the published image, built from `examples/rti-plugins/rpi_io`, on `rti-network`, no published ports) and mounts
   its configurations, moved unchanged to `config/plugin-configuration/io/`, over the default ones. One IO server for
   all three, not one each: on the Pi it drives the pins, which one process can hold. On the Pi,
   `examples/rti-plugins/rpi_io/docker-compose.pi.yaml` is added as a third file for the devices. `rpi_io`'s own
   stack (0028) stays, for an IO server apart from the demo stack; the two aren't run together, both being `rpi-io`.
4. **The IO server's service, container and host name is `rpi-io`**, after its plugin (`rpi_io`), as sim_leds runs as
   `sim-leds`: `http://rpi-io:9000/plugin`, in `docker-compose.io.yaml`, `rpi_io`'s own stack and `launch.py --docker`.
   The image keeps its published name, `rti-io` ([0016](0016-container-build-and-image-names.md)), and the plugin its
   name, `io` (`/api/plugins/io/`).
5. **`launch.py` otherwise is unchanged.** It runs the IO server itself, in mock mode off the Pi, so its FSPs and SO
   reach their plugin.

## Consequences

- `docker compose -f docker-compose.yml -f docker-compose.leds.yaml up -d` (or `COMPOSE_FILE` in `.env`) gives a demo
  where every plugin is connected: grey plugin badges, Plugins panels with a healthy `sim_leds`, and attached boxes
  whose LEDs follow the association and the services.
- Plain `docker compose up -d` still shows red badges, now for sim_leds. The README's commands use the overlay.
- On the Pi, `-f docker-compose.io.yaml -f ../rti-plugins/rpi_io/docker-compose.pi.yaml` instead of the LEDs overlay
  gives the hardware demo in one command. Off the Pi the same overlay runs the IO server in mock mode. Both overlays
  together are allowed but pointless: the IO configuration replaces sim_leds.
- `sim-leds` isn't published as an image ([0016](0016-container-build-and-image-names.md)): with the images from
  GitHub it is still built locally, from the overlay.
- Amends 0029 point 5: compose configures sim_leds by default, and the IO server through the overlay.
- `tests/unit/test_rti_demo_ports.py` checks that each configuration names its own sim_leds service in the overlay, and
  that the IO overlay names the IO server, with the inputs to the first FSP only.

## In the code

- `examples/rti-demo/config/plugin-configuration/` (sim_leds), `config/plugin-configuration/io/` (the IO server)
- `examples/rti-demo/docker-compose.leds.yaml`, `docker-compose.io.yaml`, `docker-compose.yml` (comments)
- `examples/rti-plugins/rpi_io/docker-compose.yaml`, `docker-compose.pi.yaml` (the service `rpi-io`);
  `examples/rti-demo/launch.py` (`container_name`)
- `REUSE.toml`; `tests/unit/test_rti_demo_ports.py`, `test_rti_demo_launch.py`
