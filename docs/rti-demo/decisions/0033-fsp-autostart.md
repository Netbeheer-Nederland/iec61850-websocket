<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 33. The FSP's ACSI server starts with the service; connecting to the SO is a separate option

- Status: proposed
- Date: 2026-10-17

## Context

The FSP's ACSI server started only on `POST /api/iec61850server/start`, the HMI's Connect, and that one call did two
things: it started the server (its event loop, the model it serves, its reports) and dialed out to the SO
([0003](0003-so-passive-fsp-active.md)). Until someone pressed Connect:

- a plugin that writes into the FSP's model (the IO plugin's inputs, the dr-st7789v display) got
  `server-not-running`;
- an FSP restarted by Docker (`restart`, a crash, a Pi reboot) had no running server until started again by hand.

Running the server doesn't need the SO; joining the SO is the operator's choice (0003: "the operator decides when an
FSP joins"). Tying the two together forced a choice between a server that is down and an FSP that joins unasked.

## Decision

1. **Starting the ACSI server and connecting it to the SO are two steps.** A server started without the SO is
   `ready`: it serves its model, runs its reports and takes writes, with no connection. Connected, it is `listening`,
   as before.
2. **Settings**:

   | Variable | Default | |
   |---|---|---|
   | `FSP_AUTOSTART` | `true` | Start the ACSI server with the service, `ready`. `false`, `0`, `no` or `off`: wait for `/start` |
   | `FSP_AUTOCONNECT` | `false` | With `FSP_AUTOSTART`, also dial out to the SO: `listening` |
   | `FSP_SO_HOST` | `localhost` | The SO `FSP_AUTOCONNECT` dials |
   | `FSP_SO_PORT` | `8765` | Its WebSocket port, the SO's `SO_WS_PORT` |

3. The service starts the server **after it has connected its plugins**, so they see the association. A failure is
   logged, not raised: the REST API starts anyway. An SO that isn't there yet is not a failure: the dial-out tries
   again every few seconds.
4. **`/start` on a `ready` server only dials out**; on a stopped one it starts and dials out, as before. So the
   HMI's Connect works on an auto-started FSP, and still applies the TLS and OAuth settings the BFF stores
   (`FSP_AUTOCONNECT` dials without them).
5. **`/stop` (the HMI's Disconnect) only drops the connection**: the server goes back to `ready` and keeps serving
   its model, running its reports and taking writes. The plugins get `ServerStopped` first, as before, so they show
   the FSP as disconnected; the event keeps its name (the contract doesn't change) and now means the connection to
   the SO ends. On a `ready` server `/stop` does nothing; a server that is starting or failed is still stopped. The
   server stops only with the service.
6. A running server is `ready` or `listening`: a model loaded in either is applied at once (hot-swap) and the state
   is kept. The HMI shows `ready` as *Ready*, with Connect enabled.
7. The Docker stack sets `FSP_SO_HOST=rti-so` for both FSPs; `launch.py` sets `localhost`, and `rti-so` with
   `--docker`. Neither sets `FSP_AUTOCONNECT`.

## Consequences

- After `docker compose up` both FSPs serve their models and take the plugins' writes; the operator still connects
  them, or sets `FSP_AUTOCONNECT=true` for an FSP that joins on its own (on a Pi without the HMI).
- 0003's "the operator decides when an FSP joins" holds by default.
- Once started, the server keeps running: Disconnect and Connect only change the connection, and the plugins' writes
  are taken throughout. `server-not-running` is left for an FSP with `FSP_AUTOSTART=false` before its first Connect.
- No route stops the server; to have none running, restart the service with `FSP_AUTOSTART=false`.
- The FSP's tests switch `FSP_AUTOSTART` off (`modules/fsp/tests/conftest.py`), so an app started in a test runs no
  server.

## In the code

- `modules/fsp/src/fsp/acsi_server.py` (`RUNNING`, `start_server`, `connect`, `disconnect`),
  `modules/fsp/src/fsp/bff_endpoint.py` (`_autostart`, `_lifespan`, `/start`, `/stop`)
- `modules/plugins`: the description of `ServerStopped` (`contract.py`, `openapi.yaml`, `README.md`)
- `modules/hmi/src/pages/ACSIServer.jsx` (the label *Ready*)
- `docker-compose.yml`, `launch.py` (`SERVICES`, `_docker_env`), `modules/fsp/README.md`
- Tests: `modules/fsp/tests/test_bff_endpoint.py` (`TestAutostart`, `TestReadyServer`), `modules/fsp/tests/test_plugins.py`,
  `modules/fsp/tests/conftest.py`,
  `modules/hmi/src/pages/ACSIServer.test.jsx`, `tests/unit/test_rti_demo_launch.py`
