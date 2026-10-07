<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 12. Log entries carry a kind, set where they are written

- Status: accepted
- Date: 2026-10-07

## Context

The SO and FSP action log mixed lifecycle events with ACSI service calls in one free-text list, so a user couldn't
tell "what is on the wire", "what is this instance doing" and "is the system healthy" apart. Details:
[logging-kinds.md](../design/logging-kinds.md).

## Decision

- Three kinds: `system` (lifecycle, configuration), `websocket` (frames on the wire) and `acsi` (one entry per
  service call, whether it went over the wire).
- The kind is set at every call site (`_log_action(..., kind=...)`); nothing classifies by matching message text.
- Two bounded in-memory stores per instance: `messages` (WebSocket frames) and `actions` (system and acsi), so a
  burst of frames can't push the rarer entries out.
- An `acsi` entry made through the SO records the range of frame ids it produced, so the HMI can show its frames.
- Health and status polls are logged at DEBUG by uvicorn's access log (`HealthCheckAccessFilter`), so the request
  log stays readable.

## Consequences

- The HMI shows each kind in its own place (Traffic, ACSI Client/Server, Diagnostics).
- The logs are lost on a restart; retention is still open.

## In the code

- `modules/so/src/so/acsi_client.py`, `modules/fsp/src/fsp/acsi_server.py`, both `bff_endpoint.py`
- `modules/bff/src/bff/connection_manager.py` (BFF system events)
