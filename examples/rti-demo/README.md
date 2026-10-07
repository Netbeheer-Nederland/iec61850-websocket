<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# RTI Demo

Unified entry point for launching RTI (Real-Time Infrastructure) demo services.

## Quick Start

```bash
# Launch all services (default: all services with foreground & verbose mode)
python launch.py

# Launch individual services
python launch.py bff
python launch.py fsp
python launch.py so
python launch.py io
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
python launch.py --help

# List available services
python launch.py list

# Launch with custom port
python launch.py bff --port 5005

# Disable foreground mode (run in background)
python launch.py --background

# Disable verbose logging
python launch.py --no-verbose

# Check running services
python launch.py --status

# Stop all services
python launch.py --stop

# Docker mode
python launch.py --docker
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
[Frontend] Serving HTTP on 0.0.0.0 port 8080
```

To disable verbose logging: `python launch.py --no-verbose`
To run in background: `python launch.py --background`

## Docker

After installing Docker and before starting the demo, create the following network `rti-network` to connect Keycloak for
the OAuth2 client credentials flow.

```shell
docker network create rti-network 2>/dev/null || true
```

Images are named:

```
${RTI_IMAGE_REPO}/rti-<role>:${RTI_IMAGE_TAG}     # role: bff, hmi, fsp, so, io
```

| Variable         | Default                                  | Published on GitHub                                         |
|------------------|------------------------------------------|-------------------------------------------------------------|
| `RTI_IMAGE_REPO` | `netbeheer-nederland/iec61850-websocket` | `ghcr.io/netbeheer-nederland/iec61850-websocket`            |
| `RTI_IMAGE_TAG`  | `latest`                                 | `latest` (main), a branch name, a version or `sha-<commit>` |

`docker-compose.yml`, and `launch.py --docker` all use these names, so an image built here can be used by the demo
directly, without retagging.

### Locally built images

```shell
cd examples/rti-demo
docker compose build            # -> netbeheer-nederland/iec61850-websocket/rti-<role>:latest
docker compose up -d
```

An available `docker-compose.override.yml` is loaded automatically and bind-mounts the module sources over
the code in the images, so a source edit only needs a container restart.

### Images published on GitHub

```shell
cd examples/rti-demo
export RTI_IMAGE_REPO=ghcr.io/netbeheer-nederland/iec61850-websocket
export RTI_IMAGE_TAG=latest
docker compose -f docker-compose.yml pull
docker compose -f docker-compose.yml up -d --no-build
```

`-f docker-compose.yml` leaves the dev overlay out, so the containers run the code in the
published images and not your local checkout. `--no-build` stops compose from building an image
that could not be pulled. Put the two variables in `examples/rti-demo/.env` to make the setting
persistent.

### Without Raspberry Pi hardware

`docker-compose.yml` passes the Raspberry Pi's GPIO, I2C and SPI devices into `rti-io`. Docker won't start a container
whose device paths are missing on the host. On any other machine, add `docker-compose.no-devices.yml`. It removes the
devices from `rti-io`, along with the settings that only exist for them: `group_add`, `user`, `ipc`, `security_opt`
and `cap_add`.

```shell
cd examples/rti-demo
docker compose -f docker-compose.yml -f docker-compose.no-devices.yml up -d
```

Set `COMPOSE_FILE=docker-compose.yml:docker-compose.no-devices.yml` in `examples/rti-demo/.env` to make it persistent.
This needs Docker Compose 2.24 or later. `rti-io` then starts and is healthy. Devices whose hardware is missing log an
error at startup and stay unavailable, except the I2C LCD, which runs in mock mode. The other services don't change.

### Launch with Docker (all services by default)

```shell
python launch.py --docker       # uses the same RTI_IMAGE_REPO / RTI_IMAGE_TAG
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
`scripts/keycloak/data`, on `rti-network`.

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
| `ca.pem` | the CA certificate a WebSocket client (FSP, active) trusts |
| `server.pem`, `server-key.pem` | the SO's server certificate (`rti-so`) and key (passive) |

In the HMI's TLS dialog, pick these under *From the certificate directory*. The setting then holds a reference such as
`file:server-key.pem` instead of PEM text; the SO or FSP reads the file from its own `/certs` mount when it starts
TLS, so keys never pass through the browser, the BFF or `connections.json`. Pasting or uploading PEM text still works.

Outside Docker (`launch.py`), the services look for referenced files in `TLS_CERT_DIR` (default `/certs`), e.g.
`TLS_CERT_DIR=$PWD/../../testing/certs python launch.py`. With FSP and SO on different machines, both need
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

## Hardware demo

On Raspberry Pis, the `io` service drives LEDs, LCDs, a button and two potentiometers, so the IEC 61850 exchange between
RTI-FSP (ACSI server) and RTI-SO (ACSI client) becomes visible. It shows reporting, operate (control) and setpoints.
FSP and SO each run their own `io` service and use the same mapping, `modules/io/io_client/io_mapping.json`:

| Device         | Mapped to                                    | Shows / does                                                   |
|----------------|----------------------------------------------|----------------------------------------------------------------|
| `led1`         | `connected`, `stopped`                       | The WebSocket association is up (off when stopped)             |
| `led2`         | `rc_rcv`, `oper_rcv`                         | A report was received (SO) or an operate was received (FSP)    |
| `led3`         | `setpoints`, `read`, `operate`               | Setpoint, read and operate activity                            |
| `lcd1`, `lcd_i2c` | all events above, plus `oper_send`, `setpoint`, `writeValue` | Text log of the latest events                  |
| `button1`      | `LD0/DWMX1.DERAvail.stVal` (FC `st`)         | Toggles the status value; the change triggers a report         |
| `pot1`         | `LD0/MMXU1.TotW.mag.f` (FC `mx`)             | Sets the measured total power, which is reported               |
| `pot2`         | operate on `LD0/DWMX1.WMaxSpt` (`float32`)   | Sends an operate with the new power limit                      |

Demo flow:

1. Start FSP and SO and let them associate; `led1` lights on both sides.
2. Press `button1` on the FSP side: `DERAvail.stVal` changes, the report control block fires, and `led2` on the SO side
   shows the received report.
3. Turn `pot1` on the FSP side: the new `TotW` value reaches the SO in the next report.
4. Turn `pot2` on the SO side: the SO sends an operate on `WMaxSpt`, and `led2` on the FSP side shows that it arrived.

FSP and SO load the IO client on request, not at startup: connect each one to its IO server with
`POST /api/io-plugin/connect` (see *IO Client Integration* in [modules/fsp/README.md](modules/fsp/README.md)).
Wiring, pin numbers and the I2C LCD setup are in [modules/io/README.md](modules/io/README.md).

## IO API Server

The `io` service is a REST API (under `/api/io/`) for the LEDs, buttons, potentiometers and LCDs on a Raspberry Pi; it
runs without the hardware too (see [Without Raspberry Pi hardware](#without-raspberry-pi-hardware)).

```bash
# from examples/rti-demo
python launch.py io
docker compose up rti-io

# or directly
cd modules/io/io_api_server && python main.py
```

Devices, configuration (`io_config.json`), wiring, Raspberry Pi setup (GPIO, I2C, SPI) and troubleshooting are in
[modules/io/README.md](modules/io/README.md); the endpoints are in its OpenAPI docs at http://localhost:9000/docs.
It listens on 9000 however it's started (`PORT` overrides it).

## Project Structure

```
rti-demo/
├── launch.py                  # Main entry point
├── README.md                  # This file
├── docker-compose.yml
├── docker-compose.no-devices.yml  # Overlay: rti-io without Raspberry Pi devices
├── config/
│   ├── launch_config.json.example
│   └── models/                # IED model files (model_1.py, model_2.py)
├── scripts/
│   ├── set_docker_user.sh     # Detect/export host UID+GID for the demo_io build
│   └── setup_raspberry_docker.sh  # Install Docker on a fresh Raspberry Pi
└── modules/
    ├── bff/       { pyproject.toml, docker/Dockerfile, src/bff/, tests/ }
    ├── fsp/       { pyproject.toml, docker/Dockerfile, src/fsp/, tests/ }
    ├── so/        { pyproject.toml, docker/Dockerfile, src/so/, tests/ }
    ├── io/        { pyproject.toml, docker/Dockerfile, io_api_server/, io_client/ }
    └── hmi/       { package.json, docker/Dockerfile, src/ }  # Web HMI (React)
```

`bff`, `fsp` and `so` are members of a single uv workspace rooted at the
repository root (alongside the `ws61850` core library at `src/`) - see
`TESTING.md` for how to install/run them. `demo_io` and `hmi` build and
run independently (Pi hardware deps / npm toolchain respectively).

## UV

UV is already implemented to manage the dependencies inside the dockers. To add a dependency to the project, you can use
the following command:

```bash
uv add <package_name>
```

This should be followed by rebuilding the dockers to make sure the new dependency is included in the images.

```bash

After adding the dependency, you can run the following command to make sure the lock file is updated with the new dependency:

```bash
uv lock
```

To run the python codes without the dockers, you can use the following command to install the dependencies in your local
environment:

```bash
uv sync
```

and the python codes can be run using the following command:

```bash
uv run python <script_name.py>
```

## Troubleshooting

* Port already in use
```bash
# Find and kill process on port 8080
sudo kill -9 $(sudo lsof -t -i :8080) 2>/dev/null
```

* Module not found

```bash
# Install dependencies
uv add <packages>
uv add uvicorn fastapi requests
```

* connections.json error when running locally
```bash
# Remove file and create a new one
rmdir /S /Q connections.json 2>/dev/null
echo [] > connections.json
```
