<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# Plugins for the FSP and SO (`acsi_plugins`)

The FSP and SO can host several plugins, each linking ACSI to another integration: the IO server's LEDs and LCDs, and
later others such as a message bus or a historian. This package holds what they share: the contract a plugin
implements, the host that runs the plugins, the loader that downloads them, and the `/api/plugins` routes. The
decision behind it is [0021](../../../../docs/rti-demo/decisions/0021-acsi-plugin-host.md).

| Module | What it holds |
|---|---|
| `contract.py` | `AcsiPlugin`, the events, `ControlResult`, `PluginContext` |
| `host.py` | `PluginHost`: passes events to every plugin, asks the owner of an objRef to answer an Operate |
| `loader.py` | The manifest, the allowed sources, downloading, importing as `acsi_<name>_plugin` |
| `web.py` | `PluginService` (install, reload, remove, load at startup) and the routes |

`samples/sim_leds/` is a sample plugin (two simulated LEDs); [GETTING_STARTED.md](GETTING_STARTED.md) starts from it.

## What a plugin gets

**Events**, to every plugin. Each runs with a timeout (5 s); a plugin that fails or is too slow is logged and marked
unhealthy, and the other plugins still get the event.

| Event | Where | When |
|---|---|---|
| `Associated(associate_id)` | FSP, SO | An association was set up |
| `OperateReceived(data)` | FSP | An Operate request came in |
| `OperateResponse(success, add_cause, obj_ref, value, data)` | FSP, SO | An Operate was answered (FSP: sent; SO: received) |
| `ValueWritten(obj_ref, value, ok)` | FSP, SO | A value was written (FSP: its own model; SO: to a server) |
| `ValueRead(obj_ref, value, ok)` | SO | A value was read from a server |
| `ReportReceived(rpt_id, data_set, data)` | SO | A report came in |
| `ServerStopped()` | FSP | The ACSI server is about to stop; the FSP waits for the plugins (up to 5 s) |

**Operate**, in the FSP only. A plugin lists the objRefs it owns in `claims()`; at most one plugin owns an objRef, and a
second claim is refused when the plugin loads. An Operate on an owned objRef goes to the owner's `handle_control`.
It returns `ControlResult(ok, add_cause)`, where `add_cause` is a `ControlServiceStatusKind` name such as
`blockedByInterlocking`, or `None` to leave the Operate to the FSP's default check. `handle_control` is synchronous,
because the ACSI library asks for the answer while it builds its response, and runs with a timeout (2 s). An owner that
raises or hangs fails the Operate.

Write and Read on an owned objRef aren't passed to plugins yet: the ACSI library has no hook for them.

**Routes**: a plugin's `router()` is served under `/api/plugins/<name>/`. Its routes aren't added to the app itself.
FastAPI can't remove them, so the FSP or SO passes each request on to the plugin's own small app, which goes away when
the plugin is removed.

All plugin coroutines run on the web app's event loop, whichever thread an event comes from.

## Writing a plugin

```python
from acsi_plugins import AcsiPlugin, ControlResult, ValueWritten


class HistorianPlugin(AcsiPlugin):
    async def start(self, ctx):
        self.url = ctx.settings["url"]
        ctx.logger.info(f"Writing to {self.url}")

    async def on_event(self, event):
        if isinstance(event, ValueWritten) and event.ok:
            ...  # store event.obj_ref, event.value

    def claims(self):
        return ["LD0/CSWI1.Pos.Oper.ctlVal"]

    def handle_control(self, obj_ref, ctl_val):
        return ControlResult(False, "blockedByInterlocking")
```

A downloadable plugin is a flat folder with `__init__.py`, its modules (importing each other relatively), and a
manifest `plugin.json`:

```json
{"name": "historian", "version": "1.0.0", "api": 1, "entry": "plugin:HistorianPlugin",
 "files": ["__init__.py", "plugin.py"]}
```

The source serves the manifest at `<source_url>/plugin.json` and each file, as it is, at `<source_url>/<file>`. A
plugin installed with the image registers its class under the entry point group `acsi.plugins` instead.

The IO plugin (`modules/io/rti_io/plugin/plugin.py`) is a complete example; `samples/sim_leds/` is a small one,
and [GETTING_STARTED.md](GETTING_STARTED.md) walks through writing, serving, installing and testing a plugin.

## Using plugins

```bash
# Install: download from an allowed source, load and start
curl -X POST http://localhost:5001/api/plugins -H 'Content-Type: application/json' \
  -d '{"name": "io", "source_url": "http://rti-io:9000/api/io-plugin/files", "settings": {"acsi_url": "http://rti-fsp01:5001"}}'

curl http://localhost:5001/api/plugins                     # loaded plugins, health; failed: startup failures
curl http://localhost:5001/api/plugins/io/leds             # a route of the plugin
curl -X POST http://localhost:5001/api/plugins/io/reload   # download again and restart; settings stay
curl -X DELETE http://localhost:5001/api/plugins/io        # stop, remove, delete its files
```

| Answer | When |
|---|---|
| 403 | The source isn't in `PLUGIN_ALLOWED_SOURCES` |
| 409 | The name is loaded already, or the plugin claims an objRef another plugin owns |
| 422 | The plugin can't be downloaded or loaded; `detail` says why |

A downloaded plugin is kept with its source and settings, and loaded again when the service starts.

## Settings

| Variable | Default | Description |
|---|---|---|
| `PLUGIN_STORAGE` | `/app/plugins` | Where downloaded plugins are kept, one folder each |
| `PLUGIN_ALLOWED_SOURCES` | none | Comma-separated URLs plugins may be downloaded from. Scheme, host and port must match exactly; the path by whole segments |
| `PLUGINS` | none | JSON list of plugins to load at startup: `[{"name": "io", "source": "...", "settings": {...}}]` |

The plugins run in the FSP's or SO's process, with its rights: only allow sources you trust.

## Tests

```bash
uv run --package acsi-plugins pytest examples/rti-demo/modules/plugins/tests -q
```
