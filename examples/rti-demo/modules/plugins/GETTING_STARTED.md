<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# Getting started: writing a plugin

A plugin links the FSP or SO to another integration: it hears what happens on the ACSI side (an association, an
Operate, a write, a report), can serve its own routes, and can answer the Operates on objRefs it owns. This guide walks
through the sample plugin `sim_leds`, which shows those events on two simulated LEDs, red and green, and then shows how
to make your own. The contract itself is in the [README](README.md), and as OpenAPI 3.1 in [`openapi.yaml`](openapi.yaml)
(the `/api/plugins` routes, what your plugin source must serve, the manifest and the events); the decisions behind it
are [0021](../../../../docs/rti-demo/decisions/0021-acsi-plugin-host.md) and
[0027](../../../../docs/rti-demo/decisions/0027-plugin-contract-as-openapi.md).

## Before you start

From the repository root:

```bash
uv sync --all-packages
```

## 1. The sample: `examples/rti-plugins/sim_leds/`

The sample lives with the other plugins, in [`examples/rti-plugins`](../../../rti-plugins/README.md) (decision
[0028](../../../../docs/rti-demo/decisions/0028-rti-plugins-folder.md)).

| File | What it does |
|---|---|
| `plugin.json` | The manifest: name, version, contract version (`api`), entry class, and the files to download |
| `__init__.py` | Makes the folder a package (`acsi_sim_leds_plugin` once loaded) |
| `leds.py` | `SimulatedLeds`: two LEDs in memory, blinking, and a history of what changed them |
| `plugin.py` | `SimLedsPlugin`: the events it reacts to and its routes |
| `tests/` | Its tests; not in `files`, so not downloaded |

What the LEDs show, in the FSP and in the SO:

| Event | Red | Green |
|---|---|---|
| `Associated` | | on |
| `OperateResponse`, success | off | blinks |
| `OperateResponse`, failed | on, with the `AddCause` in the history | |
| `ValueWritten`, ok | off | blinks |
| `ValueWritten` or `ValueRead`, failed | on | |
| `ReportReceived` (SO) | | blinks |
| `ServerStopped` (FSP) | off | off |

Its routes, under `/api/plugins/sim_leds/`:

| Route | |
|---|---|
| `GET /leds` | Both LEDs, and the last 50 changes with the reason for each |
| `POST /leds/{color}` | `{"on": true}` or `{"on": false}`: set `red` or `green` by hand |
| `POST /leds/reset` | Both off |

Its one setting, `blink_seconds` (default `0.3`), comes from the install request.

The whole plugin is a subclass of `AcsiPlugin` that overrides what it needs:

```python
class SimLedsPlugin(AcsiPlugin):
    async def start(self, ctx):          # once, when loaded: ctx.settings, ctx.role ("fsp" or "so"), ctx.logger
        ...
    async def stop(self):                # once, when removed or reloaded
        ...
    async def on_event(self, event):     # every event; match on its type
        match event:
            case Associated(associate_id=associate_id):
                self.leds.set("green", True, f"associated {associate_id}")
            ...
    def router(self):                    # routes under /api/plugins/<name>/
        ...
```

## 2. Run its tests

```bash
uv run --package acsi-plugins pytest examples/rti-plugins/sim_leds/tests -q
```

`tests/test_sim_leds.py` installs the sample the way the FSP does (download from an allowed source, load,
start), sends it events through the plugin host, and reads the LEDs through its routes. It needs no FSP, SO or
network: use it as the template for your own plugin's tests, and as the fast way to try a change.

## 3. Install it in an FSP

The FSP and SO download a plugin from a URL: `<source_url>/plugin.json`, then each file in its `files` list. Any
plain file server will do, but only from a source in `PLUGIN_ALLOWED_SOURCES`.

Serve the sample folder (port 8099; the SO's WebSocket uses 8765):

```bash
python3 -m http.server 8099 --bind 127.0.0.1 --directory examples/rti-plugins/sim_leds
```

In a second terminal, start an FSP that allows that source and keeps its plugins in a scratch folder:

```bash
PLUGIN_ALLOWED_SOURCES=http://localhost:8099 PLUGIN_STORAGE=/tmp/fsp-plugins \
  uv run --package fsp python -m fsp.bff_endpoint
```

Install the plugin, then use it:

```bash
curl -X POST http://localhost:5001/api/plugins -H 'Content-Type: application/json' \
  -d '{"name": "sim_leds", "source_url": "http://localhost:8099", "settings": {"blink_seconds": 1}}'

curl http://localhost:5001/api/plugins                     # loaded plugins and their health
curl http://localhost:5001/api/plugins/sim_leds/leds       # the LEDs
curl -X POST http://localhost:5001/api/plugins/sim_leds/leds/red \
  -H 'Content-Type: application/json' -d '{"on": true}'
```

The plugin stays installed: it is kept in `PLUGIN_STORAGE` with its source and settings, and loaded again when the FSP
starts.

## 4. See it react to the demo

The events come when the FSP and SO talk to each other, so run the whole demo and allow your source in all of them;
`launch.py` passes your `PLUGIN_ALLOWED_SOURCES` on (it allows none of its own):

```bash
cd examples/rti-demo
PLUGIN_ALLOWED_SOURCES=http://localhost:8099 uv run python launch.py
```

Install `sim_leds` in the FSP (port 5001) and in the SO (port 5000) as in step 3, then start the FSP's server, connect
the SO and write or operate from the HMI. Follow along with:

```bash
watch -n 0.5 'curl -s http://localhost:5000/api/plugins/sim_leds/leds'
```

## 5. Change it

Edit a file in `examples/rti-plugins/sim_leds/`, then load the new version: the FSP downloads it again and restarts the plugin,
keeping its settings.

```bash
curl -X POST http://localhost:5001/api/plugins/sim_leds/reload
curl -X DELETE http://localhost:5001/api/plugins/sim_leds   # or remove it, files and all
```

When something goes wrong, the answer says why:

| Answer | Usually |
|---|---|
| `403` | The source isn't in `PLUGIN_ALLOWED_SOURCES` (scheme, host and port must match exactly: `localhost` isn't `127.0.0.1`) |
| `409` | A plugin with that name is loaded already (reload it instead), or it claims an objRef another plugin owns |
| `422` | It can't be downloaded or loaded: a file in `files` is missing, the name in `plugin.json` isn't the one you asked for, or the code raised on import (`detail` has the error) |
| `"healthy": false` in `GET /api/plugins` | `on_event` raised or took longer than 5 s; `last_error` says what, and the FSP's log has the traceback |

## 6. Make your own

1. Copy the sample: `cp -r examples/rti-plugins/sim_leds examples/rti-plugins/historian` (or a folder of your own,
   outside this repository).
2. In `plugin.json`, set `name` (lowercase letters, digits and `_`; it is loaded as `acsi_<name>_plugin` and served
   under `/api/plugins/<name>/`), `version`, `entry` (`module:Class`) and `files`: every file the plugin needs, in one
   flat folder. Keep `"api": 1`. The rules are the `PluginManifest` schema in [`openapi.yaml`](openapi.yaml).
3. Import your own modules relatively (`from .leds import ...`). From the host you can import `acsi_plugins`,
   `fastapi` and `pydantic`; a plugin can't bring its own dependencies.
4. Its `tests/` came along: rename `test_sim_leds.py`, and change the name, events and routes to your plugin's. The
   test serves the folder it sits in, so it needs no other change.

### Answering an Operate (FSP)

A plugin can own objRefs: an Operate on one goes to the plugin's `handle_control`, whose answer is the ACSI answer.
`claims()` is read before `start()`, so the objRefs are fixed in the code, not in the settings. For example, in
`sim_leds/plugin.py`, refuse an Operate on a breaker while the red LED is on:

```python
from acsi_plugins import ControlResult


class SimLedsPlugin(AcsiPlugin):
    ...

    def claims(self):
        return ["LD0/CSWI1.Pos.Oper.ctlVal"]

    def handle_control(self, obj_ref, ctl_val):
        if self.leds.state["red"]:
            return ControlResult(False, "blockedByInterlocking")
        return None  # leave it to the FSP's own check
```

`handle_control` is synchronous and has 2 s; `add_cause` is a `ControlServiceStatusKind` name. At most one plugin owns an
objRef. Writes and reads on an owned objRef aren't passed to the plugin (yet): it sees them only as events.

### Things to keep in mind

- A plugin runs inside the FSP or SO, with its rights. Allow only sources you trust.
- Everything of a plugin runs on the web app's event loop: don't block in `on_event` or a route. Use `async` I/O, or
  `asyncio.to_thread` for blocking calls.
- Each event has 5 s. A slow or failing plugin is marked unhealthy; the others still get the event.
- `stop()` should end whatever `start()` began (connections, tasks): a reload calls `stop()` on the old instance first.
