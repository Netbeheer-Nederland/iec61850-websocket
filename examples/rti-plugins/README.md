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
[0029](../../docs/rti-demo/decisions/0029-plugins-are-http-services.md) (plugins are HTTP services) and
[0030](../../docs/rti-demo/decisions/0030-plugin-project-layout.md) (the layout of a plugin).

| Folder | What it is | Its plugin URL | Runs on |
|---|---|---|---|
| [`io`](io/README.md) | The IO plugin, `rpi_io` (image `rti-io`): the IO server with the LEDs, buttons, potentiometers and displays, and the plugin API | `http://rti-io:9000/plugin` | the Raspberry Pi; mock mode elsewhere |
| [`sim_leds`](sim_leds/README.md) | A sample plugin: two simulated LEDs, FastAPI only | `http://localhost:8099/plugin` | anywhere |

## The layout of a plugin

Every plugin is its own project, with the same layout (decision 0030; the same as the dr-st7789v display's):

```text
<plugin>/
├── pyproject.toml, uv.lock   # its own uv project (not in the repository's workspace), with a script that starts it
├── README.md
├── docker-compose.yaml       # its own stack, on the external network rti-network; runs anywhere
├── docker-compose.pi.yaml    # only with hardware: the overlay that passes the Raspberry Pi's devices in
├── docker/
│   ├── Dockerfile            # built from the project folder: docker build -f docker/Dockerfile .
│   └── Dockerfile.dockerignore
├── src/<package>/
│   ├── server/               # the service: what the plugin is about, with its own routes
│   └── plugin/               # the plugin API (decision 0029) under /plugin, which the FSP and SO connect to
└── tests/
```

To write your own plugin, start with [`GETTING_STARTED.md`](../rti-demo/modules/plugins/GETTING_STARTED.md), which walks
through `sim_leds`. A new integration is a new folder here (or anywhere else) and an entry in the FSP's or SO's plugin
configuration:

```json
{"host_url": "http://rti-fsp01:5001", "plugins": [{"name": "io", "url": "http://rti-io:9000/plugin"}]}
```

## Their own stacks

Each plugin has its own compose file, apart from the demo stack; the IO plugin is built for and runs on the Raspberry
Pi. All stacks join the external network `rti-network`, where the FSPs and SO reach the plugins' APIs as
`http://rti-io:9000/plugin` and `http://sim-leds:8099/plugin`.

```bash
docker network create rti-network 2>/dev/null || true

cd examples/rti-plugins/io
docker compose up -d                                                      # anywhere (mock mode)
docker compose -f docker-compose.yaml -f docker-compose.pi.yaml up -d     # on the Raspberry Pi

cd ../sim_leds
docker compose up -d
```

While a plugin isn't reachable, the FSPs and SO list it as failed and try again every 10 s; the rest of the demo
works. `launch.py io` in the demo starts the IO plugin as a local process, so one machine can run everything. The Pi's scripts
(Docker setup, the build user and groups, GPIO simulation) are in [`io/scripts`](io/scripts).

## Tests

```bash
uv run --package fsp pytest examples/rti-plugins/io/tests -m unit -q   # not a workspace member; needs FastAPI and the plugin host
uv run --package acsi-plugins pytest examples/rti-plugins/sim_leds/tests -m unit -q
```

Both connect the FSP's plugin service (`acsi_plugins`) to the plugin's app, with no network: the plugins themselves
don't need it, their tests use it to check they speak the plugin API.
