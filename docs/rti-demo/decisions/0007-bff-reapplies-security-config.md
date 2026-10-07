<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 7. The SO and FSP keep TLS and OAuth in memory; the BFF re-applies them

- Status: accepted
- Date: 2026-10-07

## Context

The SO and FSP get their TLS and OAuth settings at runtime from the HMI, through the BFF. They don't store them:
after a container restart they come back as plain, unauthenticated WebSocket, while `connections.json` still says
TLS or OAuth is on.

## Decision

Keep the SO and FSP stateless about security settings and make the BFF restore them:

- **SO**: on every status-monitor round (10 s), the BFF compares the SO's runtime TLS (`/api/tls-config`) and
  OAuth (`/api/oauth-status`) with what is stored, and re-applies the stored settings when they differ
  (`/api/reconfig-connection`, `/api/reconfig-oauth`). TLS first, then OAuth, because each restarts the listener.
  A failed re-apply is retried at most once every 60 s, so a bad certificate doesn't keep the listener restarting.
- **FSP**: its connection only starts on Connect, so the BFF adds the stored TLS and OAuth settings to the
  `/api/start` call it forwards; see [0004](0004-bff-single-gateway-execute-proxy.md).
- Each re-apply, successful or not, is a BFF system event on the Diagnostics page.

## Consequences

- The SO and FSP have no config files or volumes of their own.
- After an SO restart there is a window of up to 10 s in which it runs without its stored security settings.
- Re-applying restarts the SO's listener, which drops the FSPs connected to it.

## In the code

- `modules/bff/src/bff/connection_manager.py` (`sync_all_runtime_security`, `sync_runtime_tls`,
  `sync_runtime_oauth`)
- `modules/bff/src/bff/bff_server.py` (`/api/start` enrichment in `execute_dynamic_api`)
