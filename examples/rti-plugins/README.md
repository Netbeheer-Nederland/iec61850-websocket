<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# RTI plugins

The plugins the FSP and SO of the [rti-demo](../rti-demo/README.md) can connect to. **A plugin is an HTTP service**
that implements the plugin API in [`openapi.yaml`](../rti-demo/modules/plugins/openapi.yaml) (tag *Plugin API*); an
FSP or SO connects to it from its plugin configuration. Nothing here is installed in the FSP or SO, and nothing here
imports them: each plugin runs, is built and is released on its own. The decisions behind this are
[0028](../../docs/rti-demo/decisions/0028-rti-plugins-folder.md) (this folder) and
[0029](../../docs/rti-demo/decisions/0029-plugins-are-http-services.md) (plugins are HTTP services).

| Folder | What it is | Its plugin URL | Runs on |
|---|---|---|---|
| [`io/server`](io/server/README.md) | The IO server, `rpi_io` (image `rti-io`): the LEDs, buttons, potentiometers and displays, and the IO plugin | `http://rti-io:9000/plugin` | the Raspberry Pi; mock mode elsewhere |
| [`sim_leds`](sim_leds/sim_leds.py) | A sample plugin: two simulated LEDs, FastAPI only | `http://localhost:8099/plugin` | anywhere |

To write your own plugin, start with [`GETTING_STARTED.md`](../rti-demo/modules/plugins/GETTING_STARTED.md), which walks
through `sim_leds`. A new integration is a new folder here (or anywhere else) and an entry in the FSP's or SO's plugin
configuration:

```json
{"host_url": "http://rti-fsp01:5001", "plugins": [{"name": "io", "url": "http://rti-io:9000/plugin"}]}
```

## The IO server: its own stack

The IO server is built for and runs on the Raspberry Pi, apart from the demo stack, so it has its own compose file. Both
stacks join the external network `rti-network`, where the FSPs and SO reach its plugin API as
`http://rti-io:9000/plugin`.

```bash
docker network create rti-network 2>/dev/null || true

cd examples/rti-plugins/io/server
docker compose up -d                                                        # on the Raspberry Pi
docker compose -f docker-compose.yml -f docker-compose.no-devices.yml up -d # anywhere else (mock mode)
```

While the IO server isn't reachable, the FSPs and SO list it as failed and try again every 10 s; the rest of the demo
works. `launch.py io` in the demo starts it as a local process, so one machine can run everything. The Pi's scripts
(Docker setup, the build user and groups, GPIO simulation) are in [`io/server/scripts`](io/server/scripts).

## Tests

```bash
uv run --package fsp pytest examples/rti-plugins/io/server/tests -m unit -q   # not a workspace member; needs FastAPI and the plugin host
uv run --package acsi-plugins pytest examples/rti-plugins/sim_leds/tests -m unit -q
```

Both connect the FSP's plugin service (`acsi_plugins`) to the plugin's app, with no network: the plugins themselves
don't need it, their tests use it to check they speak the plugin API.
