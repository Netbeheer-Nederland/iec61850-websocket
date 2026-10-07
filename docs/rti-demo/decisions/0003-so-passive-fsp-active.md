<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 3. The SO listens, the FSPs dial out

- Status: accepted
- Date: 2026-10-07

## Context

RTI separates the WebSocket role (who opens the connection) from the ACSI role (who serves the data model). An FSP
sits behind the customer's network edge and may have no reachable address; the SO is a fixed, known endpoint that
many FSPs connect to.

## Decision

| Service | WebSocket role | ACSI role | ws61850 classes |
|---|---|---|---|
| RTI-SO | passive: WebSocket server on 8765 | ACSI client | `PassiveEndpoint` + `IEC61850Client` |
| RTI-FSP | active: WebSocket client | ACSI server | `ActiveEndpoint` + `IEC61850Server` |

- One SO serves several FSPs, each on its own communication point (`CP`: `cp1`, `cp2`, ...).
- The SO's WebSocket server starts when the SO starts (`SO_LISTEN_ON_START`, `SO_WS_HOST`, `SO_WS_PORT`;
  default on, `0.0.0.0`, 8765). `POST /api/connect` restarts it after a `POST /api/disconnect`.
- An FSP dials out only when told to (`/api/start`, the HMI's Connect), so the operator decides when an FSP joins.

## Consequences

- A fresh stack is ready for the FSPs without a manual step on the SO.
- The SO's Connect button reports "already connected" while the server runs.
- Reports travel FSP to SO on the connection the FSP opened.

## In the code

- `modules/so/src/so/bff_endpoint.py` (`_listen_on_start`), `modules/so/src/so/acsi_client.py`
- `modules/fsp/src/fsp/acsi_server.py`
- [docs/architecture/endpoint-architecture.md](../../architecture/endpoint-architecture.md)
