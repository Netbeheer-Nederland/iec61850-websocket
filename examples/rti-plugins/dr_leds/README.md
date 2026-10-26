<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# dr_leds

A sample plugin of the rti-demo's FSP and SO: two simulated LEDs, red and green, that show what the FSP or SO does.
It implements the plugin API in [`openapi.yaml`](../../rti-demo/modules/plugins/openapi.yaml) (decision
[0029](../../../docs/rti-demo/decisions/0029-plugins-are-http-services.md)), needs only FastAPI and imports nothing of
the FSP or SO. Its layout is the one every plugin has (decision
[0030](../../../docs/rti-demo/decisions/0030-plugin-project-layout.md)). The walk-through is
[`GETTING_STARTED.md`](../../rti-demo/modules/plugins/GETTING_STARTED.md).

```text
examples/rti-plugins/dr_leds/
├── pyproject.toml, uv.lock   # its own uv project, dr-leds; script dr-leds
├── docker-compose.yaml       # its own stack, on the external network rti-network
├── docker/
│   ├── Dockerfile            # built from this folder
│   └── Dockerfile.dockerignore
├── tests/                    # the FSP's plugin service connected to the app
└── src/dr_leds/
    ├── server/               # the service: leds.py, app.py (/leds-api), main.py
    └── plugin/               # the plugin API under /plugin: plugin.py
```

## Run it

```bash
cd examples/rti-plugins/dr_leds
uv run dr-leds                                  # http://127.0.0.1:8099/plugin

docker network create rti-network 2>/dev/null || true
docker compose up -d                             # http://dr-leds:8099/plugin on rti-network
```

and add it to the FSP's or SO's plugin configuration:

```json
{"name": "dr_leds", "url": "http://localhost:8099/plugin", "settings": {"blink_seconds": 1}}
```

| Variable | Default | |
|---|---|---|
| `HOST` | `127.0.0.1` (`0.0.0.0` in the image) | Where it listens |
| `PORT` | `8099` | |
| `DR_LEDS_CLAIMS` | none | ObjRefs it claims (comma-separated); an Operate on one is refused while red is on |

Its `GET /plugin/attached` reports the two LEDs, so the HMI's Overview and Traffic draw them next to the FSP or SO (decision
[0025](../../../docs/rti-demo/decisions/0025-plugins-show-attached-devices-in-hmi.md)).

## Tests

```bash
uv run --package acsi-plugins pytest examples/rti-plugins/dr_leds/tests -m unit -q
```
