<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 4. The BFF is the HMI's only backend, with a generic execute proxy

- Status: accepted
- Date: 2026-10-07

## Context

The HMI has to reach the SO, every FSP and the IO service. Letting the browser call each one directly means CORS,
addresses that differ per network and secrets (OAuth client secrets, TLS settings) in the browser.

## Decision

- The HMI talks only to the BFF (default port 3000; in Docker, nginx proxies `/api/` to `rti-bff:3000`).
- The BFF keeps a registry of targets, each a `BffClient` keyed by `host:port`.
- `POST /api/execute` with `{target, method, path, body}` forwards a call to a registered target. The HMI's
  `apiService.js` lists the calls it makes this way. The BFF doesn't need an endpoint per SO/FSP operation.
- Where a call needs data the HMI doesn't hold, the BFF adds it from `connections.json` on the way through:
  `/api/start` on an FSP gets its stored TLS and OAuth settings, `/reconfig-oauth` gets the stored OAuth fields.

## Consequences

- New SO/FSP endpoints can be used from the HMI without a BFF change.
- The BFF is a thin, generic proxy: it doesn't validate what it forwards.
- Targets are keyed by address. Two connection entries with the same `host:port` share one client, and deleting
  one of them removes the shared client (a known weakness).
- The forwarded call uses blocking `requests` inside an async handler, so a slow target holds up the BFF's event
  loop for up to the 15 s timeout.

## In the code

- `modules/bff/src/bff/bff_server.py` (`execute_dynamic_api`), `modules/bff/src/bff/bff_client.py`
- `modules/hmi/src/services/apiService.js`, `modules/hmi/nginx.conf`
