<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# Plugins for the FSP and SO (`acsi_plugins`)

The FSP and SO can connect to several plugins, each linking ACSI to another integration: the IO server's LEDs and
displays, and later others such as a message bus or a historian. **A plugin is an HTTP service**, in any language, that
implements the plugin API; nothing of a plugin is installed in the FSP or SO. This package is the FSP's and SO's side:
how they talk to plugins, which plugins they connect to, and the `/api/plugins` routes. The decisions behind it are
[0021](../../../../docs/rti-demo/decisions/0021-acsi-plugin-host.md) (several plugins, one contract) and
[0029](../../../../docs/rti-demo/decisions/0029-plugins-are-http-services.md) (plugins are HTTP services).

[`openapi.yaml`](openapi.yaml) is the contract, as OpenAPI 3.1: the **plugin API** a plugin implements, the
`/api/plugins` routes, how a plugin's own routes are reached, and the plugin configuration. `tests/test_openapi.py`
keeps it in step with the code (decision [0027](../../../../docs/rti-demo/decisions/0027-plugin-contract-as-openapi.md)).

| Module | What it holds |
|---|---|
| `contract.py` | The events and their JSON (`event_json`), `ControlResult`, and `AcsiPlugin`: how the host sees a plugin |
| `remote.py` | `RemotePlugin`: speaks the plugin API to one plugin service; the allowed-sources check |
| `host.py` | `PluginHost`: passes events to every plugin, asks the owner of an objRef to answer an Operate |
| `config.py` | The plugin configuration: `PLUGINS_FILE` or `PLUGINS` |
| `web.py` | `PluginService` (connect the configured plugins, retry, add, reload, remove) and the routes |

The plugins themselves, and the IO server, are in [`examples/rti-plugins`](../../../rti-plugins/README.md) (decision
[0028](../../../../docs/rti-demo/decisions/0028-rti-plugins-folder.md)). `sim_leds` there is a small sample, and
[GETTING_STARTED.md](GETTING_STARTED.md) starts from it.

## The plugin API

A plugin serves five calls, and an optional sixth, under its base URL (`url` in the configuration, for example `http://rpi-io:9000/plugin`):

| Call | When | Answer |
|---|---|---|
| `GET <url>` | Connecting, and on reload | `{"name", "version", "api": 2, "claims": [...], "routes": "..."}` |
| `POST <url>/start` | Once per FSP or SO: `{name, role, host_url, settings}` | any 2xx |
| `POST <url>/events` | Every event: `{host, event: {"type": ..., <fields>}}` | any 2xx, within 5 s |
| `POST <url>/control` | FSP only: an Operate on a claimed objRef, `{host, obj_ref, ctl_val}` | `{"ok", "add_cause"}`, or `204` to leave it to the FSP, within 2 s |
| `POST <url>/stop` | Removal, reload, shutdown: `{name, role, host_url}` | any 2xx |
| `GET <url>/attached` | Optional: when `GET /api/plugins` is asked for, at most once a second | `{"items": [...]}`, what it attaches, within 1 s; `404`: nothing |

`host` (`name`, `role`, `host_url`) says which FSP or SO a call comes from, so one plugin service can serve several.
`host_url` is where the plugin reaches that FSP's or SO's REST API, for example to write input changes back.

**Events**:

| `type` | Fields | Where | When |
|---|---|---|---|
| `Associated` | `associate_id` | FSP, SO | An association was set up |
| `OperateReceived` | `data` | FSP | An Operate request came in |
| `OperateResponse` | `success`, `add_cause`, `obj_ref`, `value`, `data` | FSP, SO | An Operate was answered (FSP: sent; SO: received) |
| `ValueWritten` | `obj_ref`, `value`, `ok` | FSP, SO | A value was written (FSP: its own model; SO: to a server) |
| `ValueRead` | `obj_ref`, `value`, `ok` | SO | A value was read from a server |
| `ReportReceived` | `rpt_id`, `data_set`, `data` | SO | A report came in |
| `ServerStopped` | | FSP | The FSP is about to drop its connection to the SO (Disconnect; its ACSI server keeps running); it waits for the plugins (up to 5 s) |

A plugin ignores the types it doesn't know: new ones can be added without a new contract version. An event that fails
or takes longer than 5 s is logged and marks the plugin unhealthy; the other plugins still get it. To do slow work (a
blink), answer `202` first.

**Operate**, in the FSP only. A plugin lists the objRefs it owns in `claims`; at most one plugin owns an objRef, and a
second claim is refused when the plugin connects. The owner's answer to `/control` is the ACSI answer: `ok`, or a
failure with `add_cause`, a `ControlServiceStatusKind` name such as `blockedByInterlocking`. The FSP asks while it builds
its answer, so `/control` has 2 s; an error, a timeout or an answer that isn't a `ControlResult` fails the Operate. Write
and Read on an owned objRef aren't passed to plugins yet: the ACSI library has no hook for them.

**Attached** (decision [0025](../../../../docs/rti-demo/decisions/0025-plugins-show-attached-devices-in-hmi.md)):
what the plugin links its FSP or SO to (an IO server, a display, an IED), for the HMI to draw next to the FSP or SO on
Overview. Each item has a `kind` (`io`, `ied`, `display`, `other`), a `label`, a `state` (`ok`, `degraded`, `down`,
`unknown`), optionally an `address` and a `detail`, and `live` blocks: `text` (`lines`), `indicators` (`name`, `on`,
`color`) or `values` (`label`, `value`, `unit`). The FSP or SO checks and trims the answer (at most 4 items, 4 blocks
per item, 8 lines of 24 characters, 8 indicators, 6 values; anything unknown is dropped) and lists it with the plugin
in `GET /api/plugins`, as `attached` and `attached_error`. A plugin that doesn't answer in time keeps its last items,
with `attached_error`; it stays healthy.

**Routes**: when the description has `routes` (a URL, or a path on the plugin's server), every request under
`/api/plugins/<name>/` is passed on to it. The IO server gives `/api/io`, so `/api/plugins/io/leds` reaches its
`/api/io/leds`.

## Configuring plugins

An FSP or SO connects to the plugins in its **plugin configuration** at startup:

```json
{
  "host_url": "http://rti-fsp01:5001",
  "plugins": [
    {"name": "io", "url": "http://rpi-io:9000/plugin", "settings": {}},
    {"name": "historian", "url": "http://historian:8000/acsi-plugin", "settings": {"retention_days": 30}}
  ]
}
```

A plugin that can't be reached doesn't stop the FSP or SO: it is listed under `failed` in `GET /api/plugins` and tried
again every `PLUGIN_RETRY_SECONDS`, so plugin services and the FSP or SO can start in any order. The demo's
configurations are in [`config/plugin-configuration/`](../../config/plugin-configuration) (compose: `sim_leds` by
default, the IO server in `io/` with the overlay `docker-compose.io.yaml`) and `launch.py`.

| Variable | Default | Description |
|---|---|---|
| `PLUGINS_FILE` | none | The plugin configuration file |
| `PLUGINS` | none | The same JSON inline (a bare list stands for `{"plugins": [...]}`); its plugins and `host_url` win over the file's |
| `PLUGIN_HOST_URL` | the configuration's `host_url` | Where plugins reach this FSP or SO |
| `PLUGIN_RETRY_SECONDS` | `10` | How often a configured plugin that isn't connected is tried again; `0`: never |
| `PLUGIN_ALLOWED_SOURCES` | none | Comma-separated URLs that `POST /api/plugins` may add plugins from. Scheme, host and port must match exactly; the path by whole segments. The configuration itself is trusted |

## Managing plugins

```bash
curl http://localhost:5001/api/plugins                          # connected plugins, health; failed: not (yet) connected
curl http://localhost:5001/api/plugins/io/leds                  # a route of the plugin
curl -X POST http://localhost:5001/api/plugins/io/reload        # describe and start again; settings stay
curl -X DELETE http://localhost:5001/api/plugins/io             # stop it until the next start

# Add one until the FSP stops, from an allowed source
curl -X POST http://localhost:5001/api/plugins -H 'Content-Type: application/json' \
  -d '{"name": "sim_leds", "url": "http://localhost:8099/plugin", "settings": {"blink_seconds": 1}}'
```

| Answer | When |
|---|---|
| 403 | The URL isn't in `PLUGIN_ALLOWED_SOURCES` |
| 409 | The name is connected already, or the plugin claims an objRef another plugin owns |
| 422 | The plugin can't be reached or doesn't answer as the plugin API says; `detail` says why |
| 502 | (plugin routes) The plugin can't be reached |

A plugin runs in its own process, so a crash or a dependency of it can't take the FSP or SO down. It still takes part
in the FSP's Operates and sees every event: only configure plugins you trust.

## Tests

```bash
uv run --package acsi-plugins pytest examples/rti-demo/modules/plugins/tests -q
```

`tests/fake_plugin.py` is a plugin service in memory that the tests connect to.
