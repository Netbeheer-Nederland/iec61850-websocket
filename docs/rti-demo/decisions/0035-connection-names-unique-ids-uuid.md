<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 35. A connection's name is unique; its id is a UUID

- Status: proposed
- Date: 2026-10-22

## Context

Every entry in `connections.json` ([0006](0006-connections-json-source-of-truth.md)) has a `name` and an `id`. The
`name` is how a connection is found: `/api/edit-connection/{name}`, `/api/delete-connection/{name}`, the TLS and OAuth
settings, the plugin status in the `connections` push, and the HMI's pages. The `id` was an integer, the highest one
in use plus 1, and read only to pick the newest IDP-Server at startup. How things stood (2026-10-22):

- **Renaming could duplicate a name.** `PUT /api/edit-connection/C` with `{"name": "B"}` succeeded while a `B`
  existed. Edits then reached only the first `B`, and deleting `B` removed both.
- **Adding with a taken name overwrote that connection.** `POST /api/add-connection` updated the existing entry's
  host, port and type in place and answered 201; discovery did the same for a name it found elsewhere.
- **One shared client could be dropped from under another connection.** Two names may point at one instance; deleting
  or moving one removed the client both used.
- **Ids came back.** Deleting the highest ones made the next adds reuse them.
- **The file wasn't checked**, and the HMI put the raw name into the URL path, so `/`, `?` or `#` broke editing.

## Decision

1. **Names are unique**, compared without case and surrounding spaces, and stored without the spaces.
   `POST /api/add-connection` and a rename through `PUT /api/edit-connection/{name}` refuse a name another connection
   has with `409` and the reason; an empty name is `400`. Nothing of a refused edit is applied. Registering the same
   name, type and address again changes nothing and answers `200`. Discovery doesn't register a service whose name
   is taken. `ConnectionManager.add_connection` itself still updates by name, for callers inside the BFF.
2. **A delete removes exactly one connection.**
3. **A client is dropped only when no connection uses its host:port any more.**
4. **The id is an opaque UUID** (version 4, as a string): never reused, unique across BFFs, with no order or meaning,
   so other references (a playbook, another store, a future API keyed by id) can rely on it. The newest IDP-Server is
   now the one with the latest `created_at`.
5. **The file is checked on load.** A connection without a name, or with the name of one before it, is dropped and
   logged. An id that isn't a UUID (the old integers) or that repeats gets a new UUID. When anything changed, the file
   is saved, so ids stay the same across restarts. The seed `connections.json` ships with UUIDs.
6. **The HMI URL-encodes the name** in the edit and delete calls, and the routes take a name with `/`
   (`{conn_name:path}`). A refused save or delete shows the BFF's reason.

## Consequences

- A name can't be lost or doubled through the API, and an existing `connections.json` with integer ids is upgraded
  once, on the first start of this BFF.
- A file with duplicate names loses the later ones on load; the log says which. Fix the file by hand to keep them,
  under other names.
- Connections are still addressed by name in the API. The UUID makes addressing by id possible later without another
  change to the file.
- A client relying on add-as-update (posting a known name to change its address) now gets `409`; it uses
  `PUT /api/edit-connection/{name}` instead.

## In the code

- `examples/rti-demo/modules/bff/src/bff/connection_manager.py` (`new_connection_id`, `name_key`, `claim_name`,
  `create_connection`, `rebind_client`, `release_client`, `_checked`), `bff_server.py` (the add, edit and delete
  routes), `connections.json` (the seed's ids)
- `examples/rti-demo/modules/hmi/src/pages/Connections.jsx` (`namePath`, `failureReason`)
- Tests: `modules/bff/tests/test_connection_names.py`, `test_connection_manager_ids.py`;
  `modules/hmi/src/pages/Connections.test.jsx`
