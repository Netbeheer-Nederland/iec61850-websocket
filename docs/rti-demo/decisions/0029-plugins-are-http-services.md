<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 29. Plugins are HTTP services the FSP and SO connect to, from a plugin configuration

- Status: proposed
- Date: 2026-10-17

## Context

Since [0021](0021-acsi-plugin-host.md) a plugin is Python code inside the FSP or SO: a subclass of `AcsiPlugin`,
either installed with the image (the IO plugin, [0022](0022-io-plugin-own-package.md)) or downloaded from a plugin
source and imported. [0027](0027-plugin-contract-as-openapi.md) published that contract for third parties, and
[0028](0028-rti-plugins-folder.md) moved the plugins and the IO server out of the demo. The FSP and SO were still tied
to the IO plugin (2026-10-17):

- **The IO plugin was part of them.** `acsi-io-plugin` was a dependency of the `fsp` and `so` packages and built into
  their images; a change to it rebuilt both.
- **Its wiring was theirs.** Compose and `launch.py` gave every FSP and SO `IO_URL`, `ACSI_BASE_URL` and
  `IO_MAPPING_FILE`, which only the IO plugin reads.
- **Two hops for one integration.** The IO plugin was an HTTP client of the IO server: about 3 500 lines (client,
  router, mapping, utilities) that turned events into calls to the server, with its own copy of the server's API.
- **A plugin could only be Python**, and ran with the FSP's or SO's rights, in its process, with its dependencies.
- **Misconfiguration was hard to see.** A wrong `IO_URL` showed up as a 404 in the log of an FSP whose image held a
  plugin from another layout.

0021 had rejected option 3, *plugins as separate services*, as too heavy for the demo. With the IO server already a
separate service, on another machine and cycle (0028), most of that weight is already there.

Three ways were considered:

1. **Keep in-process plugins, but install none.** The IO plugin is downloaded like any other, from a plugin
   configuration. Small change, but plugins stay Python-only and inside the FSP or SO.
2. **Remote plugins: a plugin is an HTTP service implementing the plugin API** (chosen).
3. **Both**, chosen per plugin. Most flexible, but two contracts to keep, test and document.

## Decision

1. **A plugin is an HTTP service** that implements the plugin API, contract version **2**, in `openapi.yaml` (tag
   *Plugin API*), under a base URL:

   | Call | What for |
   |---|---|
   | `GET <url>` | The plugin describes itself: `name`, `version`, `api: 2`, `claims`, `routes` |
   | `POST <url>/start` | Start serving one FSP or SO: `name`, `role`, `host_url`, `settings` |
   | `POST <url>/events` | Every event, as JSON `{"type": <class name>, <fields>}`, with the `host` it comes from |
   | `POST <url>/control` | An Operate on a claimed objRef (FSP): a `ControlResult`, or `204` to leave it to the FSP |
   | `POST <url>/stop` | Stop serving that FSP or SO |

   The dispatch rules of 0021 stay: events to every plugin with a 5 s timeout, unhealthy on failure; one owner per
   objRef, refused at connect; `/control` within 2 s or the Operate fails. A plugin ignores event types it doesn't
   know, so adding one doesn't need a new version. `host_url` tells the plugin where to write back.
2. **A plugin configuration per FSP or SO** says which plugins to connect to: a JSON file (`PLUGINS_FILE`) or the same
   JSON inline (`PLUGINS`), `{"host_url": ..., "plugins": [{"name", "url", "settings"}]}`; `PLUGIN_HOST_URL` wins over
   `host_url`. At startup the FSP or SO describes and starts each one. One that can't be reached is listed under
   `failed` and tried again every `PLUGIN_RETRY_SECONDS` (10 s), so plugins and the FSP or SO start in any order. The
   configuration is trusted; `POST /api/plugins` adds a plugin at runtime only from a URL in `PLUGIN_ALLOWED_SOURCES`,
   until the next start.
3. **A plugin's routes** are where its description says (`routes`, a URL or a path on its server); the FSP or SO passes
   `/api/plugins/<name>/*` on to them (`502` when unreachable).
4. **The IO server implements the plugin API itself**, under `/plugin`, with `routes` `/api/io`. The event handling of
   the IO plugin and its `io_mapping.json` move into the IO server (`rpi_io/plugin.py`, `rpi_io/mapping.py`,
   `IO_MAPPING_FILE`), acting on its devices directly. On `/start` it sends its input changes to that host's
   `host_url`, unless the settings say `"write_inputs": false`; the demo's configurations give the inputs to the first
   FSP only. The package `acsi_io_plugin` (`examples/rti-plugins/io/plugin`) is removed.
5. **The FSP and SO know no plugin.** `fsp` and `so` depend on `acsi_plugins` only; no plugin is in their images, and
   compose and `launch.py` configure the IO plugin like any other: `config/plugin-configuration/<service>.json` and
   `PLUGINS` with `http://<io>:9000/plugin`.
6. **`acsi_plugins` becomes the client side**: `remote.py` (`RemotePlugin`, the allowed-sources check), `config.py`
   (the plugin configuration), and `host.py` and `web.py` as before, without downloading or importing. `AcsiPlugin`
   stays as the host's view of a plugin, with `RemotePlugin` as its implementation. `loader.py`, the manifest
   (`plugin.json`), `PLUGIN_STORAGE`, the entry point group `acsi.plugins` and `install.json` go.
7. **`sim_leds` is a standalone FastAPI service** (`examples/rti-plugins/sim_leds/sim_leds.py`) that imports nothing of
   the FSP or SO, as the example for third parties.

## Consequences

- An integration can be written in any language, run anywhere the FSP or SO can reach, crash or be updated on its own
  cycle, and be added by configuration alone. A third party needs `openapi.yaml`, not this repository.
- The IO integration is one service instead of a plugin plus a server, and the FSP and SO images don't change when IO
  does.
- **Every event and Operate is a network call.** Events are sent one by one, without waiting in the ACSI path; an
  Operate on a claimed objRef waits for `/control` (2 s at most). On one Docker host or LAN that is a few ms; a plugin
  that needs more must answer first and work afterwards.
- **A plugin that is down is visible.** `GET /api/plugins` lists it under `failed` with the reason (connection refused,
  wrong name, wrong `api`), and the FSP or SO keeps trying; the 404 of the log in the context would now read
  `GET http://192.168.0.226:8000/plugin: HTTP 404`.
- **One IO server, several hosts.** The IO server remembers each host that started it, and sends input changes to one:
  the most recent that wants them. Two hosts both wanting the inputs of one IO server is not supported; give each FSP
  its own IO server, as on two Raspberry Pis.
- **Trust moves, it doesn't go away.** A plugin no longer runs in the FSP's or SO's process, but it sees every event
  and decides Operates on its objRefs. The configuration is trusted; runtime additions need the allow-list. The plugin
  API has no authentication yet: serve plugins on a network you trust. Authentication (for example the OAuth of
  [0020](0020-so-authorizes-tokens.md)) is a follow-up.
- **Breaking, without a transition.** Contract version 1 plugins (Python classes, `plugin.json`) don't load; the old
  `POST /api/plugins` body (`source_url`) is refused (422); `IO_URL`, `ACSI_BASE_URL`, `IO_MAPPING_FILE` in the FSP and
  SO, and `PLUGIN_STORAGE`, aren't read. Images built before this still contain the IO plugin; rebuild them.
- 0025's `attached()` isn't implemented yet; in this model it becomes an optional `GET <url>/attached`, a follow-up
  decided with 0025.
- Supersedes [0021](0021-acsi-plugin-host.md) in the in-process model: points 1 (`AcsiPlugin` as the plugin contract,
  the manifest), 3 (downloads, `PLUGIN_STORAGE`, entry points), 4 (sub-applications for routes; the management routes
  stand), 5 (now the plugin configuration), 6 (the allow-list now covers runtime additions only) and 7 (the IO plugin
  package). Point 2, the dispatch rules, stands. Supersedes [0022](0022-io-plugin-own-package.md) (the IO plugin package, installed in the
  images), [0027](0027-plugin-contract-as-openapi.md) point 2 (the Python contract as reference schemas: the events are
  now the wire format) and its version 1, and the `io/plugin` folder of [0028](0028-rti-plugins-folder.md). The
  approach of 0027 (a hand-written spec kept in step by a test) and the rest of 0028 stand.
- Review once a second plugin, written outside this repository, runs against version 2.
- Superseded in [0039](0039-sample-plugin-name-dr-leds.md): the plugin name and folder `sim_leds` are now `dr_leds`.

## In the code

- `examples/rti-demo/modules/plugins/`: `src/acsi_plugins/` (`contract.py`, `remote.py` new, `config.py` new,
  `host.py`, `web.py`; `loader.py` removed), `openapi.yaml` (version 2), `README.md`, `GETTING_STARTED.md`, `tests/`
  (`fake_plugin.py`, `test_remote.py`, `test_config.py`, `test_web.py`, `test_openapi.py`)
- `examples/rti-plugins/io/server/src/rpi_io/plugin.py` (new), `mapping.py` and `io_mapping.json` (from the IO plugin),
  `api_endpoint.py` (mounts `/plugin`); `tests/test_plugin.py`
- `examples/rti-plugins/io/plugin/` removed; `examples/rti-plugins/sim_leds/sim_leds.py`
- `examples/rti-demo/modules/{fsp,so}/pyproject.toml`, `docker/Dockerfile`, `src/*/bff_endpoint.py`,
  `tests/test_plugins.py`
- `examples/rti-demo/docker-compose.yml`, `config/plugin-configuration/`, `launch.py`; `pyproject.toml` (workspace),
  `uv.lock`, `.dockerignore`, `.github/workflows/{ci,images}.yml`, `REUSE.toml`, `.gitignore`
- Tests: `tests/unit/test_rti_demo_ports.py`, `test_rti_demo_launch.py`
