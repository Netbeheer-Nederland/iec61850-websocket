<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 5. One central poll in the BFF, pushed to the browsers over /ws

- Status: accepted
- Date: 2026-10-07

## Context

The HMI used to poll: connections every second, and messages and action logs every 5 to 10 s per open panel. With
several tabs or panels open, every SO and FSP was polled once per tab and panel.

## Decision

- The BFF polls once for all browsers. `push_relay_loop` runs every 2 s: it rebuilds the enriched connection
  list and fetches new messages, `acsi` actions and the SO's client list from every connected SO and FSP.
- Only changes are sent: the connection list when its snapshot differs, and messages and actions above the last id
  relayed per target.
- Browsers connect once to `GET /ws` (`liveSocket.js`) and receive typed events: `connections`, `messages`,
  `actions`, `properties` and `playbook-run`.
- A separate `status_monitor` checks every connection's health every 10 s.

## Consequences

- The load on the SO and FSPs doesn't grow with the number of open tabs.
- Live data is up to 2 s old.
- The relay state (last ids) is in BFF memory; after a BFF restart a browser gets the current list again.

## In the code

- `modules/bff/src/bff/bff_server.py` (`WSHub`, `push_relay_loop`, `websocket_endpoint`)
- `modules/bff/src/bff/connection_manager.py` (`status_monitor`)
- `modules/hmi/src/services/liveSocket.js`
