<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 31. A plugin's source: `server/` is the service, `plugin/` the plugin API, and the plugin depends on the server

- Status: proposed
- Date: 2026-10-17

## Context

[0030](0030-plugin-project-layout.md) gave every plugin the project layout of the dr-st7789v display: `pyproject.toml`,
`docker/`, a compose pair, and `src/<package>/` with the subpackages `server/` and `plugin/`. It didn't say what goes
in each, or how they may use each other. Without that, the next plugin decides again; the two in this repository
already differed in small ways (2026-10-17):

| | `io` (`rpi_io`) | `sim_leds` |
|---|---|---|
| The service's state | `IOController`, `server/io_controller.py` | `SimulatedLeds`, `server/leds.py` |
| Its own routes | `/api/io`, `server/api_endpoint.py` | `/leds-api`, `server/app.py` |
| App factory | `create_fastapi_app(io_controller)`, which mounts the plugin router | `create_app(leds)`, which mounts it |
| Plugin router | `create_plugin_router(io_controller, mapping)`, tag `ACSI plugin (decision 0029)` | `create_plugin_router(leds)`, tag `Plugin API (decision 0029)` |
| `version` in the description | from the package metadata | written in the code, `2.0.0` |
| Plugin data | `plugin/io_mapping.json` | none |

The plugin of dr-st7789v, still contract version 1, will be the third. It is ported to this source layout, and so is
any plugin a third party starts from `sim_leds`.

## Decision

1. **`server/` is the service, as if no FSP or SO existed.** It holds:
   - the service's state and logic, in modules that don't import `plugin/`;
   - its own routes, under a prefix of its own (`/api/io`, `/leds-api`), which the FSP or SO passes on as
     `/api/plugins/<name>/*` (0029, point 3);
   - the **app factory**, which takes the state (or makes it) and mounts the plugin router. It is the only module of
     `server/` that imports `plugin/`;
   - `main.py` with `main()`, the project's script (`[project.scripts]`, 0030), which reads `HOST` and `PORT` and runs
     the app with uvicorn.
2. **`plugin/` is the plugin API (0029) and nothing else.** `plugin/plugin.py` holds:
   - `NAME`, the plugin's name, and `API_VERSION = 2`;
   - the request bodies of `openapi.yaml` as pydantic models (`Host`, `StartRequest`, `EventRequest`, and
     `ControlRequest` when it reads one);
   - `create_plugin_router(<the server's state>) -> APIRouter`, with prefix `/plugin` and tag
     `Plugin API (decision 0029)`: `GET ""`, `POST /start`, `/stop`, `/events`, `/control`. A plugin may add routes of
     its own under `/plugin` (the IO plugin's `/plugin/mappings`); the FSP and SO don't call them.

   `plugin/__init__.py` exports `create_plugin_router`. Data only the plugin uses is next to it (`io_mapping.json`),
   as package data of `<package>.plugin`.
3. **The plugin depends on the server, not the other way round.** `plugin/` imports the server's state and logic and
   translates events into calls on them; the server's modules don't know about events, hosts or claims. The app
   factory is where the two meet.
4. **The description says what the project says.** `name` is `NAME`, `version` comes from the package metadata
   (`importlib.metadata.version("<distribution>")`), and `routes` is the server's prefix, a path on the same server.
5. **No code of the FSP or SO.** `src/` imports FastAPI, pydantic, uvicorn and the service's own dependencies; the
   contract is `openapi.yaml`, not `acsi_plugins`. The tests may use `acsi_plugins`, to connect the FSP's plugin
   service to the app, as `sim_leds`'s do.
6. **A unit test holds every plugin in `examples/rti-plugins` to this**, reading the source without importing it.

## Consequences

- A plugin is read the same way every time: start at `plugin/plugin.py` for what the FSP or SO sees, at `server/`
  for what the service does. A service that already exists becomes a plugin by adding `plugin/` and one line in its
  app factory.
- The server can be run, tested and reused without the plugin API; the plugin's tests need the server's state but no
  hardware (the IO plugin's use a fake controller).
- The models of `openapi.yaml` are written again in each plugin. That is the price of rule 5; they are small, and
  `openapi.yaml`'s version and the test of 0029 keep the host side stable.
- In this change: the IO plugin's router tag becomes `Plugin API (decision 0029)`, and `sim_leds` reads its version
  from its metadata (`sim-leds`, `2.0.0`).
- dr-st7789v's plugin, ported to version 2, has the layout already (its decision 0007); its `plugin/` becomes
  `create_plugin_router(<the display's state>)` as here.

## In the code

- `examples/rti-plugins/io/src/rpi_io/plugin/plugin.py` (tag), `examples/rti-plugins/sim_leds/src/sim_leds/plugin/plugin.py`
  (version from metadata)
- `tests/unit/test_rti_plugins_source_layout.py` (new)
- `examples/rti-plugins/README.md`, `examples/rti-demo/modules/plugins/GETTING_STARTED.md`
