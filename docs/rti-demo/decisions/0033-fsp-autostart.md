<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 33. The FSP dials out to the SO when it starts

- Status: proposed
- Date: 2026-10-17

## Context

[0003](0003-so-passive-fsp-active.md) let the SO listen as soon as it starts (`SO_LISTEN_ON_START`), but kept the
FSP waiting: its ACSI server, which dials out to the SO, started only on `POST /api/iec61850server/start`, from the
HMI's Start button. A fresh stack therefore came up with every FSP idle until someone opened the HMI, and:

- a plugin that writes into the FSP's model (the IO plugin's inputs, the dr-st7789v display) got
  `server-not-running` until then;
- an FSP restarted by Docker (`restart`, a crash, a Pi reboot) stayed off the SO until started again by hand;
- an FSP without the HMI or BFF (on a Pi, beside a display plugin) needed a `curl` to join.

## Decision

1. **The FSP starts its ACSI server with the service**, after it has connected its plugins (so they see the
   association): it dials `FSP_SO_HOST:FSP_SO_PORT` on its `CP`, as `/start` with `mode: active` does.
2. **Settings**, as the SO's:

   | Variable | Default | |
   |---|---|---|
   | `FSP_AUTOSTART` | `true` | `false`, `0`, `no` or `off`: wait for `/start`, as before |
   | `FSP_SO_HOST` | `localhost` | The SO to dial |
   | `FSP_SO_PORT` | `8765` | Its WebSocket port, the SO's `SO_WS_PORT` |

3. **A failure is logged, not raised**: the REST API starts anyway. An SO that isn't there yet is not a failure;
   the dial-out tries again every few seconds, so the order in which the services start doesn't matter.
4. The Docker stack (`docker-compose.yml`) sets `FSP_SO_HOST=rti-so` for both FSPs; `launch.py` sets `localhost`,
   and `rti-so` with `--docker`.
5. The auto-start dials **without TLS or OAuth**: those settings are stored by the BFF (`connections.json`) and sent
   with the HMI's `/start`. An FSP that needs them is started with `FSP_AUTOSTART=false` and from the HMI, or
   stopped and started again there.

## Consequences

- `docker compose up` gives a running demo: both FSPs associated with the SO, the plugins' writes accepted, without
  the HMI.
- The operator no longer decides when an FSP joins (0003's last point); `FSP_AUTOSTART=false` brings that back.
- The HMI's Start answers "Server is already running" for an auto-started FSP; Stop and Start work as before, and a
  Start from the HMI is how TLS or OAuth is applied.
- An FSP started outside the stack, with nothing on `localhost:8765`, keeps trying and logs the connect error
  (throttled); set `FSP_SO_HOST` or `FSP_AUTOSTART=false`.
- The FSP's tests switch it off (`modules/fsp/tests/conftest.py`), so an app started in a test doesn't dial out.

## In the code

- `modules/fsp/src/fsp/bff_endpoint.py` (`_autostart`, `_lifespan`)
- `docker-compose.yml`, `launch.py` (`SERVICES`, `_docker_env`), `modules/fsp/README.md`
- Tests: `modules/fsp/tests/test_bff_endpoint.py` (`TestAutostart`), `modules/fsp/tests/conftest.py`,
  `tests/unit/test_rti_demo_launch.py`
