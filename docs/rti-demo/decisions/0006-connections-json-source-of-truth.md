<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 6. connections.json is the source of truth, on a volume, seeded once

- Status: accepted
- Date: 2026-10-07

## Context

The BFF needs to remember which SO, FSP, IO and IDP instances exist and how each is configured (TLS, OAuth), across
restarts and image upgrades. In the image, `/app` is owned by root while the BFF runs as an unprivileged user.

## Decision

- All connection state is in one JSON file, `connections.json`. `BFF_CONNECTIONS_FILE` sets its location; Docker
  Compose puts it on the named volume `bff-config` at `/config`.
- Saves are atomic: a temporary file in the same directory, then `os.replace`. A directory volume is used, not a
  single-file bind mount, which would make `os.replace` fail with `EBUSY`.
- On first start, when the configured file doesn't exist, the BFF copies the seed `connections.json` shipped next to
  its code. After that the file on the volume wins; the seed is never read again.
- The seed holds no private keys or certificates; see [0008](0008-certificates-as-file-references.md).

## Consequences

- Connections survive container restarts and image upgrades.
- A change to the seed file doesn't reach an existing installation; reset the volume
  (`docker compose down -v`) or edit the connection in the HMI.
- The HMI keeps a copy of the list in `localStorage` for its first paint; the BFF's list replaces it as soon as it
  arrives.

## In the code

- `modules/bff/src/bff/bff_server.py` (seed copy), `modules/bff/src/bff/connection_manager.py` (`save_connections`)
- `modules/bff/src/bff/connections.json` (seed)
