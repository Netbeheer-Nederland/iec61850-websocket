<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 2. Five separate services: HMI, BFF, SO, FSP and IO

- Status: accepted
- Date: 2026-10-07

## Context

The demo has to show the two RTI roles as separate parties that talk over the RTI WebSocket protocol, with more than one
FSP, and with physical IO on a Raspberry Pi.

## Decision

The demo is five independently started services, each with its own REST API, its own Docker image and its own module
under `examples/rti-demo/modules/`:

| Service | Role                                                                                                  |
|---------|-------------------------------------------------------------------------------------------------------|
| HMI     | React single-page app, served by nginx                                                                |
| BFF     | Backend for frontend: the HMI's only backend, connection registry, playbooks                          |
| RTI-SO  | System operator: ACSI client                                                                          |
| RTI-FSP | Flexibility service provider: ACSI server; one image, started once per FSP (`rti-fsp01`, `rti-fsp02`) |
| IO      | Raspberry Pi devices (LEDs, buttons, potentiometers, LCDs) behind a REST API                          |

The SO and the FSP each expose a REST API (FastAPI) next to their RTI WebSocket endpoint. That REST API is how the
BFF drives them; it's not part of the RTI protocol.

## Consequences

- Each service can be restarted, scaled (more FSPs) or run on another machine on its own.
- The BFF has to keep track of the others, see [0004](0004-bff-single-gateway-execute-proxy.md) and
  [0006](0006-connections-json-source-of-truth.md).
- State that lives in one service's memory is lost when that service restarts; see
  [0007](0007-bff-reapplies-security-config.md).

## In the code

- `examples/rti-demo/modules/{hmi,bff,so,fsp,io}`
- `examples/rti-demo/docker-compose.yml`, `examples/rti-demo/launch.py`
