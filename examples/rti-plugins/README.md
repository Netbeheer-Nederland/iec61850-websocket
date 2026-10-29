<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# RTI plugins

The plugins the FSP and SO of the [rti-demo](../rti-demo/README.md) can connect to. **A plugin is an HTTP service**
that implements the plugin API in [`openapi.yaml`](../rti-demo/modules/plugins/openapi.yaml) (tag *Plugin API*); an
FSP or SO connects to it from its plugin configuration. Nothing here is installed in the FSP or SO, and nothing here
imports them: each plugin runs, is built and is released on its own. The decisions behind this are
[0028](../../docs/rti-demo/decisions/0028-rti-plugins-folder.md) (this folder),
[0029](../../docs/rti-demo/decisions/0029-plugins-are-http-services.md) (plugins are HTTP services),
[0030](../../docs/rti-demo/decisions/0030-plugin-project-layout.md) (the layout of a plugin) and
[0031](../../docs/rti-demo/decisions/0031-plugin-source-layout.md) (its source).

| Folder | What it is | Its plugin URL | Runs on |
|---|---|---|---|
| [`dr_panel`](dr_panel/README.md) | The IO plugin, `dr_panel` (image `dr-panel`, plugin name `dr_panel`): the IO server with the LEDs, buttons, potentiometers and displays, and the plugin API | `http://dr-panel:9000/plugin` | the Raspberry Pi; mock mode elsewhere |
| [`dr_leds`](dr_leds/README.md) | A sample plugin: two simulated LEDs, FastAPI only | `http://localhost:8099/plugin` | anywhere |

## The layout of a plugin

Every plugin is its own project, with the same layout (decision 0030; the same as the dr-st7789v display's):

```text
<plugin>/
├── pyproject.toml, uv.lock   # its own uv project (not in the repository's workspace), with a script that starts it
├── README.md
├── docker-compose.yaml       # its own stack, on the external network rti-network; runs anywhere
├── docker-compose.pi.yaml    # only with hardware: the overlay that passes the Raspberry Pi's devices in
├── docker/
│   ├── Dockerfile            # built from the project folder: docker build -f docker/Dockerfile .; OCI labels (0041)
│   └── Dockerfile.dockerignore
├── src/<package>/
│   ├── server/               # the service: what the plugin is about, with its own routes
│   └── plugin/               # the plugin API (decision 0029) under /plugin, which the FSP and SO connect to
└── tests/
```

In the source (decision 0031):

| Where | What |
|---|---|
| `server/` | The service's state and logic, which don't import `plugin/`; its own routes under a prefix of its own; the app factory, the one module that mounts the plugin router; `main.py` with `main()`, the script, reading `HOST` and `PORT` |
| `plugin/plugin.py` | `NAME`, `API_VERSION = 2`, the request models of `openapi.yaml`, and `create_plugin_router(<the server's state>)`: prefix `/plugin`, tag `Plugin API (decision 0029)`. The description's `version` is the package's, `routes` the server's prefix |
| `plugin/__init__.py` | Exports `create_plugin_router`; data only the plugin uses sits next to it (`io_mapping.json`) |

The plugin depends on the server, not the other way round, and nothing in `src/` imports the FSP's or SO's code.
`tests/unit/test_rti_plugins_source_layout.py` checks every plugin here.

To write your own plugin, start with [`GETTING_STARTED.md`](../rti-demo/modules/plugins/GETTING_STARTED.md), which walks
through `dr_leds`. A new integration is a new folder here (or anywhere else) and an entry in the FSP's or SO's plugin
configuration:

```json
{"host_url": "http://rti-fsp01:5001", "plugins": [{"name": "dr_panel", "url": "http://dr-panel:9000/plugin"}]}
```

## Their own stacks

Each plugin has its own compose file, apart from the demo stack; the IO plugin is built for and runs on the Raspberry
Pi. All stacks join the external network `rti-network`, where the FSPs and SO reach the plugins' APIs as
`http://dr-panel:9000/plugin` and `http://dr-leds:8099/plugin`. The demo stack runs its own dr_leds, one per FSP and SO,
with its overlay `docker-compose.leds.yaml`, and connects to the IO server only with `docker-compose.io.yaml`
(decision [0034](../../docs/rti-demo/decisions/0034-demo-stack-plugins-sim-leds-io-opt-in.md)).

```bash
docker network create rti-network 2>/dev/null || true

cd examples/rti-plugins/dr_panel
docker compose up -d                                                      # anywhere (mock mode)
docker compose -f docker-compose.yaml -f docker-compose.pi.yaml up -d     # on the Raspberry Pi

cd ../dr_leds
docker compose up -d
```

While a plugin isn't reachable, the FSPs and SO list it as failed and try again every 10 s; the rest of the demo
works. `launch.py io` in the demo starts the IO plugin as a local process, so one machine can run everything. The Pi's scripts
(Docker setup, the build user and groups, GPIO simulation) are in [`dr_panel/scripts`](dr_panel/scripts).

## Design decisions

The decisions behind plugins are kept with the demo's, in [`docs/rti-demo/decisions`](../../docs/rti-demo/decisions/README.md).
The ones a plugin author needs:

| Decision | What it decides |
|---|---|
| [0021](../../docs/rti-demo/decisions/0021-acsi-plugin-host.md) | The FSP and SO host several plugins, behind one plugin contract |
| [0025](../../docs/rti-demo/decisions/0025-plugins-show-attached-devices-in-hmi.md) | A plugin describes what it attaches at `GET /attached`; the HMI draws it next to the FSP or SO |
| [0027](../../docs/rti-demo/decisions/0027-plugin-contract-as-openapi.md) | The plugin contract is published as `openapi.yaml`, kept in step by a test |
| [0028](../../docs/rti-demo/decisions/0028-rti-plugins-folder.md) | Plugins live in this folder; the IO server is its own stack |
| [0029](../../docs/rti-demo/decisions/0029-plugins-are-http-services.md) | Plugins are HTTP services the FSP and SO connect to, from a plugin configuration |
| [0030](../../docs/rti-demo/decisions/0030-plugin-project-layout.md) | Every plugin is a project with one layout |
| [0031](../../docs/rti-demo/decisions/0031-plugin-source-layout.md) | `server/` is the service, `plugin/` the plugin API, and the plugin depends on the server |
| [0034](../../docs/rti-demo/decisions/0034-demo-stack-plugins-sim-leds-io-opt-in.md) | The demo stack uses dr_leds by default; the IO server is opt-in |
| [0036](../../docs/rti-demo/decisions/0036-plugin-definitions-editable.md) | A plugin's URL and settings can be edited, until the FSP or SO restarts |
| [0037](../../docs/rti-demo/decisions/0037-plugin-allowed-sources-wildcards.md) | `PLUGIN_ALLOWED_SOURCES` takes wildcards; `*` alone allows any URL |

Planned changes to the plugin contract (disable, settings schema, check, clear error) are in
[`docs/rti-demo/specs`](../../docs/rti-demo/specs/README.md).

## Tests

```bash
uv run --package fsp pytest examples/rti-plugins/dr_panel/tests -m unit -q   # not a workspace member; needs FastAPI and the plugin host
uv run --package acsi-plugins pytest examples/rti-plugins/dr_leds/tests -m unit -q
```

Both connect the FSP's plugin service (`acsi_plugins`) to the plugin's app, with no network: the plugins themselves
don't need it, their tests use it to check they speak the plugin API.
