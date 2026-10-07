<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 9. The ACSI runtime runs on its own event loop thread

- Status: accepted
- Date: 2026-10-07

## Context

The SO and FSP serve a FastAPI REST API (run by uvicorn) and also run a long-lived ws61850 endpoint with its own
tasks (association, reports, keep-alive). The endpoint must be started, stopped and reconfigured (TLS, OAuth) on
request without restarting the process.

## Decision

- The ws61850 endpoint runs on a dedicated asyncio event loop in a daemon thread (`_event_loop_thread`), started
  by `start_server` / `connect` and stopped by stopping that loop.
- REST handlers hand work to it with `asyncio.run_coroutine_threadsafe` and wait on the result with a timeout.
- Shared runtime state (status, host, port, error) is behind a lock.

## Consequences

- A stop or reconfigure only restarts the endpoint, not the service.
- A slow ACSI call doesn't block uvicorn's event loop.
- Two event loops in one process: code must not share asyncio objects between them.

## In the code

- `modules/fsp/src/fsp/acsi_server.py`, `modules/so/src/so/acsi_client.py`
