<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 27. The plugin contract is published as an OpenAPI 3.1 document, kept in step by a test

- Status: proposed
- Date: 2026-10-17

## Context

Since [0021](0021-acsi-plugin-host.md) anyone can write a plugin for the FSP and SO. A third party who does needs the
contract in a form they can read without the code. How things stood (2026-10-17):

- **The contract was prose and Python.** `modules/plugins/README.md` and `GETTING_STARTED.md` describe it; the
  source of truth is `contract.py`, `loader.py` and `web.py`. Nothing machine-readable.
- **The FSP's and SO's `/openapi.json` shows only part of it.** FastAPI lists the `/api/plugins` management routes,
  but not:
  - a plugin's own routes, since they are passed on to the plugin's sub-application (`include_in_schema=False`);
  - what a **plugin source** must serve (`plugin.json`, then each file), which the third party runs, not the FSP;
  - the manifest rules, the events and `ControlResult`, which a plugin gets as Python objects.

  It also exists only while an FSP or SO runs.
- **A plugin is code inside the FSP or SO, not an HTTP service.** Its events and Operate answers are method calls
  (0021, option 3 was rejected), so no HTTP description can be the whole contract.

Three options were considered:

1. **Point to the generated `/openapi.json`.** No work, never out of date, but misses most of what a plugin author
   needs (above).
2. **Prose only**, as before. Readable, but nothing a tool can check a plugin source or a client against, and nothing
   that fails when the code changes.
3. **A hand-written OpenAPI 3.1 document, checked against the code by a test** (chosen).

## Decision

1. **One document, `modules/plugins/openapi.yaml`**, OpenAPI 3.1, next to the code it describes. It has three tags
   for the three HTTP parts:
   - **Plugin management**: the `/api/plugins` routes, served by the FSP and SO, with their errors (403, 404, 409,
     422, 500);
   - **Plugin routes**: `/api/plugins/{name}/{path}`, passed on to the plugin, for any of GET, POST, PUT, PATCH and
     DELETE. What the routes are is the plugin's own;
   - **Plugin source**: `/plugin.json` and `/{file}`, with a path-level server `{source_url}`. The third party serves
     these; any plain file server does.
2. **The Python contract as reference schemas.** `PluginManifest`, `PluginContext`, `ControlResult` and the seven
   events are JSON Schema in `components.schemas`, marked `x-python-contract: true`, with `x-roles` (`fsp`, `so`) on
   each event. They are never sent over HTTP. `Event` is a `oneOf` with a discriminator `event_type`, which only names
   the dataclass: it isn't an attribute of the Python event. The methods a plugin implements, and their timeouts, are
   a table in `info.description`.
3. **A test keeps it in step.** `tests/test_openapi.py` fails when the document and the code differ on:
   - the management routes and methods (against `create_plugins_router`);
   - the fields of a plugin's status (against `PluginHost.status`);
   - the name and file-name patterns (`loader._NAME`, `loader._FILE`) and `API_VERSION`;
   - the sample manifest (`samples/sim_leds/plugin.json`, which must also parse);
   - the fields of the events, `ControlResult` and `PluginContext` (against the dataclasses).

   It runs with the plugin tests in CI. `acsi-plugins` gets a `dev` dependency group with `pyyaml` for it.
4. **Versions.** `info.version` is the contract version, `acsi_plugins.API_VERSION`, now `1`; the manifest's `api`
   must equal it. A change a plugin written for the current version can't load or run under (a removed or renamed
   field, method or route, a stricter manifest rule) raises `API_VERSION` and `info.version` together. An addition
   it can ignore (an optional method with a default, such as 0025's `attached()`, a new event type, a new field in
   the status) keeps the version and is added to the document.

## Consequences

- A third party can read the whole contract in one place, render it with any OpenAPI viewer, generate a client for
  `/api/plugins`, and check that their plugin source answers what the FSP and SO fetch.
- The document can't drift silently from the parts the test covers. Prose in it (timeouts, what each event means,
  error texts) isn't checked; a change there is a review matter, as for the README.
- Some of it isn't something OpenAPI was built for: the Python schemas, and the source paths on another server. They
  are valid OpenAPI and pass `openapi-spec-validator`, but a generated client for the source paths, or for the event
  schemas, isn't useful.
- Every change to the contract now touches the document. For [0025](0025-plugins-show-attached-devices-in-hmi.md),
  `attached()` and the `attached` and `attached_error` fields of the status go in when they are implemented; the
  status check in the test fails until they do.
- The document isn't served by the FSP or SO; it is read from the repository. Serving it (for example at
  `GET /api/plugins/openapi.yaml`) is a possible follow-up.

## In the code

- `examples/rti-demo/modules/plugins/openapi.yaml`
- `examples/rti-demo/modules/plugins/tests/test_openapi.py`
- `examples/rti-demo/modules/plugins/pyproject.toml` (`[dependency-groups] dev`)
- Docs: `modules/plugins/README.md`, `GETTING_STARTED.md`; the *Plugins* sections of `modules/fsp/README.md` and
  `modules/so/README.md`
