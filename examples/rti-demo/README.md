<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# RTI Demo

Unified entry point for launching RTI (Real-Time Infrastructure) demo services.

How the services fit together is in the [system overview](../../docs/rti-demo/README.md); why they are built this way
is in the [decision records](../../docs/rti-demo/decisions/README.md).

## Quick Start

Install the Python services once, from the repository root, then run `launch.py` from `examples/rti-demo`:

```bash
# from the repository root: the ws61850 library plus the bff, fsp and so modules
uv sync --all-packages
```

```bash
# Launch all services (default: all services with foreground & verbose mode)
uv run python launch.py

# Launch individual services
uv run python launch.py bff
uv run python launch.py fsp
uv run python launch.py so
uv run python launch.py io
```

`launch.py` starts the Python services only. Start the HMI separately, from `modules/hmi`, with `npm install` and
`npm run dev` (see `modules/hmi/README.md`).

## Services

| Service                  | Port                                 | Description                                                           |
|--------------------------|--------------------------------------|-----------------------------------------------------------------------|
| `bff`                    | 3000                                 | Backend for Frontend - REST API gateway                               |
| `fsp`                    | 5001                                 | RTI-FSP - IEC 61850 server                                            |
| `fsp2`                   | 5005                                 | RTI-FSP, second instance (`cp2`)                                      |
| `so`                     | 5000, WebSocket 8765                 | RTI-SO - IEC 61850 client; its WebSocket server listens from the start |
| `io`                     | 9000                                 | IO device control API                                                 |
| HMI                      | 8080 (`npm run dev` and Docker)      | Web-based HMI                                                         |
| `keycloak` (Docker only) | 8081 / 8443                          | IDP-Server for OAuth - see [Keycloak](#keycloak-idp-server-for-oauth) |

## Access URLs

- BFF: http://localhost:3000/api/health
- FSP: http://localhost:5001/api/status
- SO: http://localhost:5000/api/status
- IO: http://localhost:9000/api/io/health
- HMI: http://localhost:8080

## Common Commands

```bash
# Show help
uv run python launch.py --help

# List available services
uv run python launch.py list

# Launch with custom port
uv run python launch.py bff --port 3010

# Disable foreground mode (run in background)
uv run python launch.py --background

# Disable verbose logging
uv run python launch.py --no-verbose

# Check running services
uv run python launch.py --status

# Stop all services
uv run python launch.py --stop

# Docker mode
uv run python launch.py --docker
```

## Demo playbooks

A demo can be scripted as a playbook - a YAML list of steps (link the
FSPs, read, operate, enable reports, drop an FSP, ...) that runs through
the BFF while the HMI's Traffic page shows it, checking each step:

```bash
uv run python -m playbooks.run playbooks/demo.yaml
```

The same playbook runs as an integration test. Playbooks can also be
recorded from clicks on the demo buttons, and run, from Traffic's Playbook
block in the HMI. See [playbooks/README.md](playbooks/README.md).

## Verbose Mode & Logs

By default, verbose logging is enabled and the console is kept alive (foreground mode). All service logs are prefixed
with the service name:

```
[BFF Server] INFO: Starting RTI Demo BFF Server (FastAPI)...
[BFF Server] INFO: 127.0.0.1:35682 - "GET /docs HTTP/1.1" 200 OK
[FSP ACSI-Server_WebsocketActive] Starting server on port 5001
[SO ACSI-Client_WebsocketPassive] Connected to endpoint
```

To disable verbose logging: `uv run python launch.py --no-verbose`
To run in background: `uv run python launch.py --background`

With Docker, one `LOG_LEVEL` sets the whole stack: `docker-compose.yml` passes it (default `info`) to the BFF, the
FSPs, the SO and the HMI, whose browser console and nginx error log follow it
([HMI README](modules/hmi/README.md#log-level)):

```bash
LOG_LEVEL=debug docker compose up -d
```

## Docker

After installing Docker and before starting the demo, create the following network `rti-network` to connect Keycloak for
the OAuth2 client credentials flow.

```shell
docker network create rti-network 2>/dev/null || true
```

Images are named:

```
${RTI_IMAGE_REPO}/rti-<role>:${RTI_IMAGE_TAG}     # role: bff, hmi, fsp, so; and io (the IO server, its own stack)
```

| Variable         | Default                                  | Published on GitHub                                         |
|------------------|------------------------------------------|-------------------------------------------------------------|
| `RTI_IMAGE_REPO` | `netbeheernederland/iec61850-websocket`  | `ghcr.io/netbeheernederland/iec61850-websocket`             |
| `RTI_IMAGE_TAG`  | `latest`                                 | `latest` (main), a branch name, a version or `sha-<commit>` |

`docker-compose.yml`, and `launch.py --docker` all use these names, so an image built here can be used by the demo
directly, without retagging.

### Locally built images

```shell
cd examples/rti-demo
docker compose -f docker-compose.yml -f docker-compose.leds.yaml build   # -> netbeheernederland/iec61850-websocket/{rti-<role>,dr-leds}:latest
docker compose -f docker-compose.yml -f docker-compose.leds.yaml up -d
```

`docker-compose.leds.yaml` runs the demo's default plugins: one `dr_leds` per FSP and SO (see *Plugins* below).
To save typing, put `COMPOSE_FILE=docker-compose.yml:docker-compose.leds.yaml` in `examples/rti-demo/.env`.

Every image carries the OCI labels (`org.opencontainers.image.*`: source, title, description, license; decision
[0041](../../docs/rti-demo/decisions/0041-oci-image-labels.md)). The images built by CI also have their version,
commit and build time; `docker inspect --format '{{json .Config.Labels}}' <image>` shows them.

An available `docker-compose.override.yml` is loaded automatically when no `-f` is given, and bind-mounts the module
sources over the code in the images, so a source edit only needs a container restart. With `-f`, name it too
(`-f docker-compose.yml -f docker-compose.override.yml -f docker-compose.leds.yaml`), or add it to `COMPOSE_FILE`.

### Images published on GitHub

```shell
cd examples/rti-demo
export RTI_IMAGE_REPO=ghcr.io/netbeheernederland/iec61850-websocket
export RTI_IMAGE_TAG=latest
docker compose -f docker-compose.yml -f docker-compose.leds.yaml pull
docker compose -f docker-compose.yml -f docker-compose.leds.yaml up -d --no-build
```

`-f docker-compose.yml` leaves the dev overlay out, so the containers run the code in the
published images and not your local checkout. `--no-build` stops compose from building an image
that could not be pulled. Put the two variables in `examples/rti-demo/.env` to make the setting
persistent.

### Plugins: dr_leds by default, the IO server opt-in

The FSPs and SO connect to the plugins in their plugin configuration, `config/plugin-configuration/` (decisions
[0029](../../docs/rti-demo/decisions/0029-plugins-are-http-services.md),
[0034](../../docs/rti-demo/decisions/0034-demo-stack-plugins-sim-leds-io-opt-in.md)):

| Overlay | Plugins | Needs |
|---|---|---|
| `docker-compose.leds.yaml` (default) | One [`dr_leds`](../rti-plugins/dr_leds/README.md) each (`dr-leds-fsp01`, `dr-leds-fsp02`, `dr-leds-so`): two simulated LEDs that follow the association, Operates, writes and reports | nothing |
| `docker-compose.io.yaml` | One IO server for all three, `dr-panel` (`http://dr-panel:9000/plugin`), from `config/plugin-configuration/io/` | nothing; on the Raspberry Pi also `-f ../rti-plugins/dr_panel/docker-compose.pi.yaml` for its devices (below) |

Without either overlay the FSPs and SO list `dr_leds` as failed, show a red plugin badge, and try again every 10 s;
the rest of the demo works.

A plugin's settings can be edited in the HMI's Plugins panel (✎, decision
[0036](../../docs/rti-demo/decisions/0036-plugin-definitions-editable.md)), until the FSP or SO restarts; for a lasting
change, edit its file in `config/plugin-configuration/` (the panel's Copy as configuration (⧉) gives the plugin's entry
for it). A plugin can be added, or moved to another URL, from any URL:
the instance's `PLUGIN_ALLOWED_SOURCES` is `*` by default, and compose doesn't set it. Anyone using the HMI can then
connect an instance to any server, which gets its events and can answer its Operates, so outside a closed demo narrow
it in an override of the service's `environment`: an exact URL (`PLUGIN_ALLOWED_SOURCES=http://192.168.0.226:8000`), a
whole lab network (`http://192.168.0.*:8000`, any Pi there on port 8000), or empty for none (decision
[0037](../../docs/rti-demo/decisions/0037-plugin-allowed-sources-wildcards.md)).

### The IO server (Raspberry Pi)

The IO server, `dr-panel`, isn't part of `docker-compose.yml`: it is meant for the Raspberry Pi and has its own compose file in
[`examples/rti-plugins/dr_panel`](../rti-plugins/dr_panel/README.md) (decision
[0028](../../docs/rti-demo/decisions/0028-rti-plugins-folder.md)). It joins `rti-network` too, so the FSPs and SO reach
it as `http://dr-panel:9000/plugin`. The FSPs and SO connect to it only with the overlay `docker-compose.io.yaml`;
by default they use dr_leds. That overlay also runs `dr-panel` itself, so on a Pi that runs the whole demo one command
does it (don't also start the stack below then: both are `dr-panel`):

```shell
cd examples/rti-demo
docker compose -f docker-compose.yml -f docker-compose.io.yaml -f ../rti-plugins/dr_panel/docker-compose.pi.yaml up -d
```

To run the IO server on its own instead, for example apart from the demo stack:

```shell
cd examples/rti-plugins/dr_panel
docker compose up -d                                                      # anywhere (mock mode)
docker compose -f docker-compose.yaml -f docker-compose.pi.yaml up -d     # on the Raspberry Pi
```

Like every plugin ([0030](../../docs/rti-demo/decisions/0030-plugin-project-layout.md)), `docker-compose.yaml` runs
anywhere and `docker-compose.pi.yaml` adds the Pi's devices to `dr-panel`, and the settings that only exist for them;
Docker won't start a container whose device paths are missing. Without the overlay, devices whose hardware is missing
log an error at startup and stay unavailable, except the I2C LCD, which runs in mock mode.

### Launch with Docker (all services by default)

```shell
uv run python launch.py --docker       # uses the same RTI_IMAGE_REPO / RTI_IMAGE_TAG
```

### Upgrading from the old ports

The defaults changed: HMI 3000/3001 -> 8080, BFF 5000 -> 3000, SO 5002 -> 5000, IO 8000/8080 -> 9000 (Keycloak
HTTP 8080 -> 8081).

- A browser that saved a BFF address on the HMI's Settings page keeps it - and port 5000 is now the SO. Set the BFF
  port to 3000 there, or clear the site data.
- The BFF copies its seed connections only on first start, so an existing `bff-config` volume still has the SO on
  5002. Edit the SO connection's port to 5000 on the Connections page, or reset the volume:
  `docker compose down && docker volume rm rti-demo_bff-config && docker compose up -d`.
- OAuth settings saved before the move (IDP-Server endpoint, token and certificate endpoints, token issuer) still
  name Keycloak on 8080. Change them to `http://keycloak:8081/...` and the issuer to
  `http://localhost:8081/realms/iec61850-test` (see the table below), or reset the volume as above.

### Keycloak (IDP-Server) for OAuth

From the directory scripts/keycloak `docker compose up -d` with `iec61850-test` realm (client `ws-client`) imported from
`scripts/keycloak/data`, on `rti-network`. Keycloak needs the test certificates: generate them first (see
[TLS certificates](#tls-certificates) below), or Docker creates empty directories in their place and Keycloak doesn't
start (see [scripts/keycloak/README.md](../../scripts/keycloak/README.md)).

- Admin console: http://localhost:8081 (admin / admin)
- From the other containers: `http://keycloak:8081`

Token issuer is always `http://localhost:8081/realms/iec61850-test`,
whichever address a token was requested on (`KC_HOSTNAME`), so the SO's
issuer check sees a single value. Settings to enter in the HMI (Setup):

| Where                  | Field                | Value                                                                     |
|------------------------|----------------------|---------------------------------------------------------------------------|
| IDP-Server connection  | Endpoint             | `http://keycloak:8081`                                                    |
| RTI-FSP / RTI-SO OAuth | Token endpoint       | `http://keycloak:8081/realms/iec61850-test/protocol/openid-connect/token` |
|                        | Certificate endpoint | `http://keycloak:8081/realms/iec61850-test/protocol/openid-connect/certs` |
|                        | Token issuer         | `http://localhost:8081/realms/iec61850-test`                              |
|                        | Client ID / secret   | `ws-client` / see `scripts/keycloak/README.md`                            |

HTTPS (8443) uses `testing/certs/keycloak.pem`, whose certificate only covers `keycloak`/`localhost`/`127.0.0.1`.
It is signed by the test CA: with the HTTPS endpoints, pick `ca.pem` as the *Auth Server CA* in the OAuth dialog.

### TLS certificates

The SO, the FSPs and the BFF mount `testing/certs` read-only at `/certs` (set `RTI_CERTS_DIR` to use another
directory). Generate the certificates there once, with [cfssl](https://github.com/cloudflare/cfssl) installed:

```shell
SERVER_HOSTNAMES=localhost,127.0.0.1,192.168.100.10 ../../testing/certs/generate.sh
```

`SERVER_HOSTNAMES` lists the extra names and addresses the certificates must cover - add the address the FSPs use to
reach the SO when they run on other machines. The files used here:

| File in `/certs` | Use it for |
|---|---|
| `ca.pem` | the CA certificate a WebSocket client (FSP, active) trusts; also the OAuth dialog's *Auth Server CA* for Keycloak on HTTPS |
| `server.pem`, `server-key.pem` | the SO's server certificate (`rti-so`) and key (passive) |

In the HMI's TLS dialog (and for the auth server CA, the OAuth dialog), pick these under *From the certificate directory*. The setting then holds a reference such as
`file:server-key.pem` instead of PEM text; the SO or FSP reads the file from its own `/certs` mount when it starts
TLS or applies OAuth, so keys never pass through the browser, the BFF or `connections.json`. Pasting or uploading PEM text still works.

Outside Docker (`launch.py`), the services look for referenced files in `TLS_CERT_DIR` (default `/certs`), e.g.
`TLS_CERT_DIR=$PWD/../../testing/certs uv run python launch.py`. With FSP and SO on different machines, both need
certificates from the same CA: generate them on one machine and copy the files the other one uses (`ca.pem` for an
FSP). These are test certificates - `generate.sh` makes the keys, including `ca-key.pem`, readable for everyone in
the directory.

### BFF connection persistence in Docker

The `rti-bff` container persists `connections.json` in a dedicated `/config`
directory backed by the `bff-config` named volume (not in `/app` or the module
code). On first start it is seeded from `modules/bff/src/bff/connections.json`; after that
the volume is authoritative. To reset it:

```bash
docker compose down
docker volume rm rti-demo_bff-config   # prefix matches your compose project name
docker compose up -d rti-bff
```

The `BFF_CONNECTIONS_FILE` env var overrides the path if you need a different location (e.g. a host bind mount).
A save keeps the file's mode (a new file is `0664`), so a bind-mounted file stays readable and editable by its group
on the host. The BFF runs as `app` (uid 1000): the file and its directory must be writable for it.

## Hardware demo

On Raspberry Pis, the `io` service drives LEDs, LCDs, a button and two potentiometers, so the IEC 61850 exchange between
RTI-FSP (ACSI server) and RTI-SO (ACSI client) becomes visible. It shows reporting, operate (control) and setpoints.
FSP and SO each run their own `io` service and use the same mapping, the IO server's `../rti-plugins/dr_panel/src/dr_panel/plugin/io_mapping.json`:

| Device         | Mapped to                                    | Shows / does                                                   |
|----------------|----------------------------------------------|----------------------------------------------------------------|
| `led1`         | `connected`, `stopped`                       | The WebSocket association is up (off when stopped)             |
| `led2`         | `rc_rcv`, `oper_rcv`                         | A report was received (SO) or an operate was received (FSP)    |
| `led3`         | `setpoint`, `read`, `operate`                | Setpoint, read and operate activity                            |
| `lcd1`, `lcd_i2c` | all events above, plus `oper_send`, `writeValue`             | Text log of the latest events                  |
| `button1`      | `LD0/DWMX1.DERAvail.stVal` (FC `st`)         | Toggles the status value; the change triggers a report         |
| `pot1`         | `LD0/MMXU1.TotW.mag.f` (FC `mx`)             | Sets the measured total power, which is reported               |
| `pot2`         | operate on `LD0/DWMX1.WMaxSpt` (`float32`)   | Sends an operate with the new power limit                      |

Demo flow:

1. Start FSP and SO and let them associate; `led1` lights on both sides.
2. Press `button1` on the FSP side: `DERAvail.stVal` changes, the report control block fires, and `led2` on the SO side
   shows the received report.
3. Turn `pot1` on the FSP side: the new `TotW` value reaches the SO in the next report.
4. Turn `pot2` on the SO side: the SO sends an operate on `WMaxSpt`, and `led2` on the FSP side shows that it arrived.

The IO server is a plugin of the FSP and SO: an HTTP service they connect to from their plugin configuration
(decision [0029](../../docs/rti-demo/decisions/0029-plugins-are-http-services.md)). Compose configures it in
`config/plugin-configuration/io/` as `http://dr-panel:9000/plugin`, used with the overlay `docker-compose.io.yaml`
(decision [0034](../../docs/rti-demo/decisions/0034-demo-stack-plugins-sim-leds-io-opt-in.md)), `launch.py` as
`http://localhost:9000/plugin`. Each
configuration also says where the IO server writes the button and potentiometers back to (`host_url`): the first FSP.
On two Raspberry Pis, point each side's configuration at its own `io` service (see *Plugins* in
[modules/fsp/README.md](modules/fsp/README.md)). The IO server and the other plugins are in
[examples/rti-plugins](../rti-plugins/README.md). To write a plugin of your own, start with
[modules/plugins/GETTING_STARTED.md](modules/plugins/GETTING_STARTED.md); the contract is
[modules/plugins/openapi.yaml](modules/plugins/openapi.yaml).
Wiring, pin numbers and the I2C LCD setup are in [rti-plugins/dr_panel/README.md](../rti-plugins/dr_panel/README.md).

## IO API Server

The `io` service is a REST API (under `/api/io/`) for the LEDs, buttons, potentiometers and LCDs on a Raspberry Pi; it
runs without the hardware too (see [The IO server (Raspberry Pi)](#the-io-server-raspberry-pi)). Its code is in
[`examples/rti-plugins/dr_panel`](../rti-plugins/dr_panel/README.md).

```bash
# from examples/rti-demo
uv run python launch.py io

# in Docker, its own stack (add -f docker-compose.yaml -f docker-compose.pi.yaml on the Pi)
cd ../rti-plugins/dr_panel && docker compose up dr-panel

# or directly, in the io project's own environment
cd ../rti-plugins/dr_panel && uv run dr-panel
```

`launch.py io` runs `dr_panel` from `../rti-plugins/dr_panel/src` in the repository's environment
(`uv sync --all-packages`). The direct command uses the `io` project's own environment instead: `uv run` creates
`.venv` in `rti-plugins/dr_panel` on first use and installs the Raspberry Pi packages there
(`gpiod`, `gpiozero`, ...). Use it on a Raspberry Pi; where those packages don't install, use `launch.py io`.

Devices, configuration (`io_config.json`), wiring, Raspberry Pi setup (GPIO, I2C, SPI) and troubleshooting are in
[rti-plugins/dr_panel/README.md](../rti-plugins/dr_panel/README.md); the endpoints are in its OpenAPI docs at
http://localhost:9000/docs.
It listens on 9000 however it's started (`PORT` overrides it).

## Project Structure

```
rti-demo/
├── launch.py                  # Main entry point
├── README.md                  # This file
├── docker-compose.yml         # bff, hmi, fsp01, fsp02, so (dr-panel: its own stack)
├── docker-compose.leds.yaml   # overlay: a dr_leds per FSP and SO, the default plugins
├── docker-compose.io.yaml     # overlay: the FSPs and SO connect to the IO server instead
├── config/
│   ├── launch_config.json.example
│   ├── plugin-configuration/  # the plugins each FSP and SO connects to (compose): dr_leds; io/: the IO server
│   └── models/                # IED model files (model_1.py, model_2.py)
└── modules/
    ├── bff/       { pyproject.toml, docker/Dockerfile, src/bff/, tests/ }
    ├── fsp/       { pyproject.toml, docker/Dockerfile, src/fsp/, tests/ }
    ├── so/        { pyproject.toml, docker/Dockerfile, src/so/, tests/ }
    ├── plugins/   { pyproject.toml, openapi.yaml, src/acsi_plugins/, tests/ }  # the plugin host
    └── hmi/       { package.json, docker/Dockerfile, src/ }  # Web HMI (React)

rti-plugins/                   # the plugins the FSP and SO connect to (decisions 0028-0030)
├── io/          { pyproject.toml, docker-compose.yaml, docker-compose.pi.yaml, docker/Dockerfile,
│                  scripts/, src/dr_panel/{server,plugin}/, tests/ }  # the IO plugin (Raspberry Pi)
└── dr_leds/    { pyproject.toml, docker-compose.yaml, docker/Dockerfile,
                   src/dr_leds/{server,plugin}/, tests/ }          # a sample plugin (FastAPI)
```

`bff`, `fsp`, `so` and `plugins` are members of a single uv
workspace rooted at the repository root (alongside the `ws61850` core
library at `src/`) - see `TESTING.md` for how to install/run them. The IO server and `hmi` build and
run independently (Pi hardware deps / npm toolchain respectively).

## Dependencies (uv)

The Python services share one uv workspace with the `ws61850` library, rooted at the repository root (see
`TESTING.md`). Run these from the repository root:

```bash
# install everything, including the bff, fsp and so modules
uv sync --all-packages

# add a dependency to one module, and update uv.lock
uv add --package bff <package_name>
```

After a dependency change, rebuild the images that use it (`docker compose build`). The `io` module is a separate uv
project: run `uv add` and `uv lock` in `examples/rti-plugins/dr_panel`.

## Troubleshooting

**Port already in use.** See what holds it, then stop that process or start the service on another port (`--port`):

```bash
ss -ltnp | grep ':3000'
```

The demo's own containers use the same ports as `launch.py`: stop them first with `docker compose down`.

**`ModuleNotFoundError` (`fastapi`, `bff`, `fsp`, `so`).** The workspace modules aren't installed. Run
`uv sync --all-packages` from the repository root and start the services with `uv run python launch.py`, not with
a bare `python`.

**Connections are wrong or the BFF can't read them.** Started with `launch.py`, the BFF keeps its connections in the
seed file `modules/bff/src/bff/connections.json` itself. Restore it with
`git checkout -- modules/bff/src/bff/connections.json`, or set `BFF_CONNECTIONS_FILE` to a file of your own to keep
the seed unchanged. In Docker they are on the `bff-config` volume; `docker compose down -v` resets it to the seed.
