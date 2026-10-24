<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# Getting started: writing a plugin

A plugin links the FSP or SO to another integration: it hears what happens on the ACSI side (an association, an
Operate, a write, a report), can serve its own routes, and can answer the Operates on objRefs it owns. **A plugin is an
HTTP service** that implements the plugin API; the FSP or SO connects to it. You can write it in any language. This
guide walks through the sample plugin `sim_leds`, which shows those events on two simulated LEDs, red and green, and
then shows how to make your own. The contract is in the [README](README.md), and as OpenAPI 3.1 in
[`openapi.yaml`](openapi.yaml) (tag *Plugin API*); the decision behind it is
[0029](../../../../docs/rti-demo/decisions/0029-plugins-are-http-services.md).

## Before you start

From the repository root:

```bash
uv sync --all-packages
```

## 1. The sample: `examples/rti-plugins/sim_leds/`

The sample lives with the other plugins, in [`examples/rti-plugins`](../../../rti-plugins/README.md), and has the
layout every plugin has (decisions [0030](../../../../docs/rti-demo/decisions/0030-plugin-project-layout.md) and
[0031](../../../../docs/rti-demo/decisions/0031-plugin-source-layout.md): `server/` is the service, `plugin/` the plugin
API, and only the server's app factory imports the plugin):

| File | What it does |
|---|---|
| `src/sim_leds/server/` | The service: `leds.py` (`SimulatedLeds`: two LEDs in memory, blinking, and a history of what changed them), `app.py` (the FastAPI app, with its own routes under `/leds-api`), `main.py` (the script `sim-leds`) |
| `src/sim_leds/plugin/` | The plugin API under `/plugin`: `plugin.py` |
| `tests/` | Its tests: the FSP's plugin service connected to the app |
| `pyproject.toml`, `uv.lock` | Its own uv project, `sim-leds`, not in the repository's workspace |
| `docker/Dockerfile`, `docker/Dockerfile.dockerignore` | Its image, built from the project folder |
| `docker-compose.yaml` | Its own stack, on the network `rti-network` (a plugin with hardware adds `docker-compose.pi.yaml`) |

It needs only FastAPI: it imports nothing of the FSP or SO. What the LEDs show, in the FSP and in the SO:

| Event | Red | Green |
|---|---|---|
| `Associated` | | on |
| `OperateResponse`, success | off | blinks |
| `OperateResponse`, failed | on, with the `add_cause` in the history | |
| `ValueWritten`, ok | off | blinks |
| `ValueWritten` or `ValueRead`, failed | on | |
| `ReportReceived` (SO) | | blinks |
| `ServerStopped` (FSP) | off | off |

Its routes, under `/api/plugins/sim_leds/` in the FSP or SO:

| Route | |
|---|---|
| `GET /leds` | Both LEDs, and the last 50 changes with the reason for each |
| `POST /leds/{color}` | `{"on": true}` or `{"on": false}`: set `red` or `green` by hand |
| `POST /leds/reset` | Both off |

Its one setting, `blink_seconds` (default `0.3`), comes from the plugin configuration with `/start`.

The plugin API is five routes, and an optional sixth:

```python
plugin = APIRouter(prefix="/plugin")  # in create_plugin_router(leds)

@plugin.get("")                       # who it is: name, version, "api": 2, claims, routes
def describe(): ...

@plugin.post("/start")                # once per FSP or SO: role, host_url, settings
def start(request: StartRequest): ...

@plugin.post("/events")               # every event; match on event["type"], ignore the rest
async def on_event(request: EventRequest): ...

@plugin.post("/control")              # an Operate on a claimed objRef: {"ok", "add_cause"}, or 204
def control(request: ControlRequest): ...

@plugin.post("/stop")                 # when the FSP or SO removes it, reloads it or stops
async def stop(host: Host): ...

@plugin.get("/attached")              # optional: what it attaches, for the HMI's Overview and Traffic
def attached(): ...
```

## 2. Run its tests

```bash
uv run --package acsi-plugins pytest examples/rti-plugins/sim_leds/tests -q
```

`tests/test_sim_leds.py` connects the FSP's plugin service to the sample's app (no network), sends it events through
the plugin host, and reads the LEDs through the FSP's `/api/plugins/sim_leds/` routes. It needs no FSP, SO or server:
use it as the template for your own plugin's tests, and as the fast way to try a change.

## 3. Connect an FSP to it

Run the plugin (port 8099; the SO's WebSocket uses 8765):

```bash
cd examples/rti-plugins/sim_leds
uv run sim-leds                       # or: docker compose up -d (http://sim-leds:8099/plugin on rti-network)
```

In a second terminal, start an FSP whose plugin configuration has it:

```bash
cd examples/rti-demo
PLUGINS='[{"name": "sim_leds", "url": "http://localhost:8099/plugin", "settings": {"blink_seconds": 1}}]' \
PLUGIN_HOST_URL=http://localhost:5001 \
  uv run --package fsp python -m fsp.bff_endpoint
```

Then use it:

```bash
curl http://localhost:5001/api/plugins                     # connected plugins and their health
curl http://localhost:5001/api/plugins/sim_leds/leds       # the LEDs
curl -X POST http://localhost:5001/api/plugins/sim_leds/leds/red \
  -H 'Content-Type: application/json' -d '{"on": true}'
```

For a lasting configuration, put the same JSON in a file and point `PLUGINS_FILE` at it, as compose does
(`config/plugin-configuration/`). The demo stack connects every FSP and SO to its own `sim_leds` by default, run by the
overlay `docker-compose.leds.yaml`. Start order doesn't matter: an FSP whose plugin isn't up yet tries again every 10 s.

To add a plugin to a running FSP without restarting it, post it (and edit it later, with
`PUT /api/plugins/sim_leds`, see step 5). An FSP or SO allows any URL by default; `PLUGIN_ALLOWED_SOURCES` narrows that:

```bash
uv run --package fsp python -m fsp.bff_endpoint
curl -X POST http://localhost:5001/api/plugins -H 'Content-Type: application/json' \
  -d '{"name": "sim_leds", "url": "http://localhost:8099/plugin"}'
```

## 4. See it react to the demo

The events come when the FSP and SO talk to each other, so run the whole demo; any URL is allowed by default, and
`launch.py` passes your `PLUGIN_ALLOWED_SOURCES` on when you set one (`http://localhost:8099`, say):

```bash
cd examples/rti-demo
uv run python launch.py
```

Add `sim_leds` to the FSP (port 5001) and the SO (port 5000) as at the end of step 3, then start the FSP's server,
connect the SO and write or operate from the HMI. Follow along with:

```bash
watch -n 0.5 'curl -s http://localhost:5000/api/plugins/sim_leds/leds'
```

## 5. Change it

Edit `src/sim_leds/plugin/plugin.py` and restart the plugin. Its description is read when it connects, so
after changing `claims` or `routes`, reload it in the FSP. To try other settings, or move it to another URL, edit its
definition (the Edit button in the HMI's Plugins panel does the same):

```bash
curl -X PUT http://localhost:5001/api/plugins/sim_leds -H 'Content-Type: application/json' \
  -d '{"settings": {"blink_seconds": 1}}'                   # until the FSP restarts; then the configuration again
curl -X POST http://localhost:5001/api/plugins/sim_leds/reload
curl -X DELETE http://localhost:5001/api/plugins/sim_leds   # or remove it until the FSP restarts
```

When something goes wrong, the answer says why:

| Answer | Usually |
|---|---|
| `403` | The URL isn't in `PLUGIN_ALLOWED_SOURCES` (scheme, host and port must match exactly: `localhost` isn't `127.0.0.1`; `http://*:8099` allows any host on that port, `*` any URL; unset is `*`) |
| `409` | A plugin with that name is connected already (reload it instead), or it claims an objRef another plugin owns |
| `422` | It can't be reached, its `name` isn't the one you asked for, its `api` isn't 2, or `/start` failed (`detail` has the error) |
| `"failed"` in `GET /api/plugins` | A configured plugin that isn't connected (yet), with why; it is tried again |
| `"healthy": false` in `GET /api/plugins` | `/events` or `/control` failed or took too long; `last_error` says what |
| `"attached_error"` in `GET /api/plugins` | `/attached` failed, took more than 1 s, or didn't answer `{"items": [...]}`; the last items stay |

## 6. Make your own

1. Copy the sample: `cp -r examples/rti-plugins/sim_leds examples/rti-plugins/historian` (or a folder of your own,
   outside this repository), or start from [`openapi.yaml`](openapi.yaml) in any language: generate a server stub from
   the *Plugin API* tag.
2. In `describe`, set `name` (lowercase letters, digits and `_`; it is served under `/api/plugins/<name>/`, and the
   configuration must use the same name), `version`, `claims` and `routes`. Keep `"api": 2`.
3. Handle the events you need in `/events` and answer quickly: start slow work after answering (`202`). Ignore types
   you don't know.
4. Rename the package (`src/sim_leds`), the project and its script in `pyproject.toml`, and run `uv lock`. Keep the
   layout: the service in `server/`, the plugin API in `plugin/`.
5. Its `tests/` came along: rename `test_sim_leds.py`, and change the module, name, events and routes to your plugin's.
6. Add it to the FSP's or SO's plugin configuration.

### Answering an Operate (FSP)

A plugin can own objRefs: list them in `claims`, and an Operate on one goes to the plugin's `/control`, whose answer is
the ACSI answer. The sample claims the objRefs in `SIM_LEDS_CLAIMS` and refuses an Operate while the red LED is on:

```python
@plugin.post("/control")
def control(request: ControlRequest):
    if leds.state["red"]:
        return {"ok": False, "add_cause": "blockedByInterlocking"}
    return Response(status_code=204)  # leave it to the FSP's own check
```

`/control` has 2 s; `add_cause` is a `ControlServiceStatusKind` name. At most one plugin owns an objRef. Writes and reads
on an owned objRef aren't passed to the plugin (yet): it sees them only as events.

### Showing what it attaches (HMI)

A plugin can say what it links its FSP or SO to, and the HMI draws a box per item next to the FSP or SO on Overview and Traffic
(decision [0025](../../../../docs/rti-demo/decisions/0025-plugins-show-attached-devices-in-hmi.md)). The sample shows
its two LEDs:

```python
@plugin.get("/attached")
def attached():
    return {"items": [{
        "kind": "other",                  # io | ied | display | other: the icon
        "label": "Simulated LEDs",
        "state": "ok",                    # ok | degraded | down | unknown: the colour
        "live": [{"type": "indicators", "items": [
            {"name": color, "on": on, "color": color} for color, on in leds.state.items()
        ]}],
    }]}
```

`live` blocks are `text` (`lines`: a display), `indicators` (`name`, `on`, `color`: LEDs) or `values` (`label`,
`value`, `unit`). It is asked about every 2 s, with 1 s to answer: answer with what you know, don't ask other services
first. The FSP or SO trims what is too much (see the plugins [README](README.md)). Without the route (`404`) the plugin
shows no boxes.

### Things to keep in mind

- One plugin service can serve several FSPs and SOs: each call names its `host`. Keep what you need per host.
- `/events` has 5 s. A slow or failing plugin is marked unhealthy; the others still get the event.
- `/stop` should end what `/start` began for that host: a reload calls `/stop` first.
- The FSP or SO sends every event to the plugin and lets it decide Operates on its objRefs: only configure plugins you
  trust, and serve them on a network you trust.
