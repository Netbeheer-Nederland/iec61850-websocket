<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 17. Raspberry Pi hardware is optional

- Status: accepted
- Date: 2026-10-07

## Context

The demo's showpiece runs on Raspberry Pis with LEDs, buttons, potentiometers and LCDs, but developers and CI run
it on machines without them. `docker-compose.yml` passes the Pi's GPIO, I2C and SPI devices into `rti-io`, and
Docker won't start a container whose device paths don't exist.

## Decision

- `docker-compose.yml` targets the Raspberry Pi.
- The overlay `docker-compose.no-devices.yml` resets everything in `rti-io` that only exists for the devices
  (`devices`, `group_add`, `user`, `ipc`, `security_opt`, `cap_add`). Use it with
  `-f docker-compose.yml -f docker-compose.no-devices.yml`, or with `COMPOSE_FILE`.
- Without hardware the IO service still starts and is healthy; devices whose hardware is missing stay
  unavailable, and the I2C LCD runs in mock mode.
- The hardware packages stay out of the root workspace; see [0011](0011-io-separate-project-runtime-plugin.md).

## Consequences

- One stack definition for the Pi and for other machines.
- `tests/unit/test_rti_demo_compose_no_devices.py` fails when a hardware setting is added to `rti-io` without a
  reset in the overlay.
- Needs Docker Compose 2.24 or later (`!reset`).

## In the code

- `examples/rti-demo/docker-compose.yml`, `examples/rti-demo/docker-compose.no-devices.yml`
- `modules/io/io_api_server/devices.py`
