<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# RTI plugins

What can be attached to the FSP and SO of the [rti-demo](../rti-demo/README.md): plugins, and the components they talk
to. Each folder is one integration. The plugin host that runs them is part of the FSP and SO and stays in the demo
([`modules/plugins`](../rti-demo/modules/plugins/README.md)). Its contract, as OpenAPI 3.1, is
[`openapi.yaml`](../rti-demo/modules/plugins/openapi.yaml). Plugins depend on the host; the host never depends on
anything here. The decision behind this layout is
[0028](../../docs/rti-demo/decisions/0028-rti-plugins-folder.md).

| Folder | What it is | How it gets to the FSP or SO | Runs on |
|---|---|---|---|
| [`io/plugin`](io/plugin/README.md) | The IO plugin, `acsi_io_plugin`: links ACSI to the IO server's devices | Installed in the FSP and SO images (decision 0022) | wherever the FSP and SO run |
| [`io/server`](io/server/README.md) | The IO server, `rpi_io` (image `rti-io`): the LEDs, buttons, potentiometers and displays | Not a plugin: a service the IO plugin calls at `IO_URL` | the Raspberry Pi; mock mode elsewhere |
| [`sim_leds`](sim_leds/plugin.py) | A sample plugin: two simulated LEDs | Downloaded from a plugin source | wherever the FSP and SO run |

To write your own plugin, start with
[`GETTING_STARTED.md`](../rti-demo/modules/plugins/GETTING_STARTED.md), which walks through `sim_leds`.

## The IO server: its own stack

The IO server is the one component here that isn't Python inside the FSP or SO. It is built for and runs on the
Raspberry Pi, apart from the demo stack, so it has its own compose file. Both stacks join the external network
`rti-network`, where the FSPs and SO reach it as `http://rti-io:9000`.

```bash
docker network create rti-network 2>/dev/null || true

cd examples/rti-plugins/io/server
docker compose up -d                                                        # on the Raspberry Pi
docker compose -f docker-compose.yml -f docker-compose.no-devices.yml up -d # anywhere else (mock mode)
```

Without an IO server, the IO plugin logs that it can't connect and stays loaded; the rest of the demo works.
`launch.py io` in the demo still starts it as a local process, so one machine can run everything. The Pi's scripts
(Docker setup, the build user and groups, GPIO simulation) are in [`io/server/scripts`](io/server/scripts).

## Tests

```bash
uv run --package acsi-io-plugin pytest examples/rti-plugins/io/plugin/tests -m unit -q
uv run --package fsp pytest examples/rti-plugins/io/server/tests -m unit -q   # not a workspace member; needs FastAPI
uv run --package acsi-plugins pytest examples/rti-plugins/sim_leds/tests -m unit -q
```
