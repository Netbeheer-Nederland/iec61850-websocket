<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 21. The FSP and SO host several plugins, behind one plugin contract

- Status: proposed
- Date: 2026-10-09

## Context

The FSP and SO can load exactly one plugin, the IO plugin ([0011](0011-io-separate-project-runtime-plugin.md),
[0018](0018-io-module-names.md)). The ACSI server should be able to pass its operations on to more integrations
than the Raspberry Pi hardware: for example a message bus, a historian, a field protocol such as Modbus, or a
process simulator. Each of those would be its own plugin. The current shape doesn't allow that:

- **The loader knows one package.** `load_io_plugin_modules` loads `rti_io_plugin` from one folder
  (`IO_PLUGIN_STORAGE`) and checks one fixed file list (`IO_PLUGIN_REQUIRED_FILES`). The FSP and SO each have their
  own copy of this code.
- **The ACSI callbacks know the IO plugin's functions.** The FSP's connect, operate-received, operate-response,
  stop and write paths, and eleven calls in the SO, call `sync_to_io_device`, `write_to_lcd` and
  `blink_led_task` directly, each with its own load-and-check block. The names they pass (`"connected"`,
  `"oper_rcv"`, `"oper_send"`, `"stopped"`) are events, not IEC 61850 objects, but they go through the same
  objRef mapping (`io_mapping.json`). A second plugin would need a second copy of every one of these blocks.
- **One global switch**, `_use_io_plugin` (FSP) or `_use_io_client` (SO), turns the plugin on or off as a whole.
  A plugin that fails once is switched off silently.
- **Plugins only watch.** The FSP's `control_handler` (`acsi_server.py`) checks the type of `ctlVal` and answers
  `OK`. No plugin can carry out an Operate or Write, refuse one, or supply the value for a Read. ACSI is mapped to
  the integration only as a side effect, after the answer has been sent.
- **Routes can't be removed.** The plugin's router is added to the app with `include_router`. FastAPI can't take
  routes out again, so a plugin can't be unloaded, and a reload keeps the old routes
  ([0011](0011-io-separate-project-runtime-plugin.md)).

Three ways to support more plugins were considered:

1. **Copy the IO pattern for each plugin**: another package name, folder, file list, set of `get_*_dynamic`
   functions and callback blocks per plugin. No new concepts, but the FSP and SO grow with every integration and
   every plugin needs a change to both.
2. **An in-process plugin host with one contract** (chosen). The FSP and SO know the contract; each plugin
   implements it.
3. **Plugins as separate services**, called over HTTP or gRPC. Isolates a plugin's crashes, dependencies and
   (downloaded) code from the FSP and SO, but adds a network hop to every Operate and Write, a service to run per
   integration, and a protocol to version. Too heavy for the demo now; the contract below doesn't rule it out
   later, since a plugin can be a thin client to such a service.

## Decision

1. **One contract, in a shared package.** A new workspace package, `acsi_plugins`
   (`examples/rti-demo/modules/plugins`), defines what a plugin is and holds the plugin host. The FSP and SO both
   use it, so the loader code is no longer copied. A plugin subclasses `AcsiPlugin`, with a do-nothing default for
   each of:
   - `start(ctx)` and `stop()`;
   - `on_event(event)`, for typed events: `Associated` and `OperateResponse` (FSP and SO), `OperateReceived` and
     `ServerStopped` (FSP), `ValueWritten` (FSP: its own model; SO: to a server), and `ValueRead` and
     `ReportReceived` (SO);
   - in the FSP only, `handle_control(obj_ref, ctl_val)` for the objRefs it lists in `claims()`, answering a
     `ControlResult(ok, add_cause)`, or `None` to leave the Operate to the default check;
   - `router()`, its own REST routes, if it has any.

   A downloadable plugin has a **manifest**, `plugin.json`: name, version, contract version (`api`), entry class,
   files. The `PluginContext` it gets in `start` holds its name, the role (`fsp` or `so`), its settings, its source,
   and a logger named `acsi_plugins.<name>`.
2. **Two dispatch rules.**
   - **Events go to every plugin.** Each call runs with a timeout (5 s) and its own error handling. A slow or failing
     plugin is logged and marked unhealthy; it doesn't hold up the handshake or the other plugins, and it isn't
     switched off. All plugin coroutines run on the **web app's event loop**, whichever thread an event comes from,
     not on the ACSI runtime loop ([0009](0009-asyncio-runtime-in-own-thread.md)): the FSP replaces that loop on
     every start, and there is none while the server is stopped.
   - **An objRef has at most one owner.** The host builds an objRef → plugin table from `claims()` when plugins
     load. A second plugin claiming the same objRef is refused at load, with a message naming both. An **Operate**
     on an owned objRef goes to its owner, whose answer is the ACSI answer: `ok`, or a failure with its `AddCause`
     (a `ControlServiceStatusKind` name; an unknown name is sent as `unknown`). The library asks for that answer
     synchronously while it builds its response, so `handle_control` is synchronous and runs in a worker thread
     with a timeout (2 s); an owner that raises, hangs or answers something else fails the Operate. An objRef no
     plugin owns behaves as before.
3. **Each plugin in its own place.** A downloaded plugin goes to `PLUGIN_STORAGE/<name>/` and is loaded as the
   package `acsi_<name>_plugin`: the name says what a plugin plugs into (the ACSI server), not where it comes
   from, and is the same for every integration. The IO plugin is loaded as `acsi_io_plugin` (was `rti_io_plugin`,
   [0018](0018-io-module-names.md)); its source package `rti_io.plugin` keeps its name. The folder stays flat, and the
   plugin server applies the check from [0019](0019-io-server-serves-only-plugin-files.md). The file list comes
   from the manifest, and the IO server serves each file as it is (no longer in a JSON envelope). The source and
   settings are kept next to the
   files (`install.json`), so a downloaded plugin is loaded again, the same way, when the service starts. Plugins
   installed in the image are found through the entry point group `acsi.plugins`.
4. **Routes that can be unloaded.** The FSP and SO mount one fixed route, `/api/plugins/{name}/{path}`, which
   passes the request to that plugin's own sub-application. Unloading or reloading a plugin replaces it; nothing is
   left behind in the main app. Management: `GET /api/plugins` (loaded plugins, version, health, claimed objRefs,
   and the plugins that failed at startup), `GET /api/plugins/{name}`, `POST /api/plugins`
   (`{name, source_url, settings}`, downloads and loads), `POST /api/plugins/{name}/reload` (downloads again; the
   settings stay), `DELETE /api/plugins/{name}` (also deletes the files). A plugin can't have its own `POST /reload`.
5. **Which plugins to load** at start-up: the ones downloaded before, the installed ones, and the ones listed in
   `PLUGINS` (a JSON list of name, source and settings). A plugin that fails is listed, not raised; the service
   starts. The IO plugin's settings are `io_url` (default `IO_URL`, else the server it came from) and `acsi_url`
   (default `ACSI_BASE_URL`).
6. **Trusted sources only.** A plugin is downloaded only from a URL under one in `PLUGIN_ALLOWED_SOURCES`: scheme,
   host and port equal, the path a whole-segment prefix. Default: empty, so only installed plugins load until a
   source is allowed. Compose and `launch.py` allow the IO server.
7. **The IO plugin becomes the first implementation.** `rti_io.plugin` gets a `plugin.json` and a `plugin.py`
   with `RtiIoPlugin`, built on its existing `client.py`, `mapping.py` and `utils.py`, doing per event what the FSP
   and SO did before. When it starts, it connects to the IO server and enables the input sync, as
   `/api/io-plugin/connect` did. The names it looks up in `io_mapping.json` for events (`connected`, `oper_rcv`,
   ...) stay as they are, but are now the plugin's own: the FSP and SO no longer know them. Its mapping stays its
   own: each plugin maps objRefs to its own targets (a GPIO pin, a topic, a register), and the host only needs
   `claims()`.

## Consequences

- Adding an integration is writing a plugin; the FSP and SO don't change. The IO-specific blocks in their ACSI
  callbacks and routes are replaced by one `plugin_host.emit(...)` each, and the FSP's control handler asks the host
  first.
- Plugins can now **take part** in an Operate: a plugin that owns an objRef can refuse it with a real `AddCause`.
  That also means a plugin's bug can fail an Operate, not only an LED; the timeout keeps it from hanging.
- **Write and Read aren't passed to an owner yet.** A remote SetDataValues or GetDataValues is handled inside the
  ACSI library (`DataAccessService`), which has no hook for it. Plugins see writes as events. Giving an owner Write
  and Read needs such a hook in `ws61850`: a follow-up decision.
- Plugins can be unloaded and reloaded. This lifts the one-way limit in
  [0011](0011-io-separate-project-runtime-plugin.md).
- **Breaking, without a transition:** the FSP, SO and IO server change together, and none of them keeps what the
  older ones used. The IO plugin's routes move from `/api/io/*` to `/api/plugins/io/*`. The `/api/io-plugin/*` endpoints (`connect`, `disconnect`, `reload`, `upload`,
  `files`, `status`, `connection-status`, `check-server`), the FSP's switch `POST /api/io-plugin`
  (`{"enabled": ...}`) and the SO's `POST /api/io-client` are replaced by the `/api/plugins` endpoints. The old paths
  are gone (`404`). In the repository
  (2026-10-09) only the IO plugin's own tests called these; the HMI and BFF don't. `_use_io_plugin` and
  `_use_io_client` go: a plugin is on when it is loaded.
- Supersedes the load name `rti_io_plugin` in [0018](0018-io-module-names.md); the rest of 0018 stands. The
  plugin's files use relative imports (0018), so the new name needs no change inside them.
- `IO_PLUGIN_STORAGE`, `IO_PLUGIN_REQUIRED_FILES` and `IO_SERVER_URL` give way to `PLUGIN_STORAGE`, the manifest and
  the plugin's settings; the old names aren't read. A plugin downloaded before into the old flat folder isn't found;
  install it again.
- The IO server ends what [0018](0018-io-module-names.md) kept for older FSPs and SOs: `IO_CLIENT_FILES_DIR` and
  `IO_CLIENT_VERSION` aren't read, and a file name from before 0018 is `404`, not `410`.
- The FSP and SO images contain `acsi_plugins`; a change to it rebuilds both.
- Plugins still run inside the FSP and SO process, with its rights. A downloaded plugin is still code from
  another server ([0011](0011-io-separate-project-runtime-plugin.md)); the allow-list narrows where it comes from
  but doesn't check what it does. Pinning a manifest hash, or option 3 above, are possible follow-ups.
- Follow-up decisions: Write and Read hooks in the library (above), whether events and handlers need an order
  between plugins (now: none, and one owner per objRef), and whether the HMI shows and manages plugins.
- Review one month after the IO plugin runs on the contract, with a second plugin (a simulator) as the test that
  the contract is not shaped to IO alone.

## In the code

- `examples/rti-demo/modules/plugins/src/acsi_plugins/`: `contract.py` (plugin, events, `ControlResult`),
  `host.py` (`PluginHost`), `loader.py` (manifest, allowed sources, download, import), `web.py` (`PluginService`,
  `/api/plugins`); how it works and how to write a plugin: its `README.md`
- `examples/rti-demo/modules/io/rti_io/plugin/` (`plugin.json`, `plugin.py`; `router.py` takes a prefix);
  `examples/rti-demo/modules/io/rti_io/server/plugin_files.py` (serves files as they are)
- `examples/rti-demo/modules/fsp/src/fsp/acsi_server.py` (`handle_control`, `install_control_hook`)
- `plugin_host` and `plugin_service`, and their use in the ACSI callbacks and routes, in
  `modules/fsp/src/fsp/bff_endpoint.py` and `modules/so/src/so/bff_endpoint.py`
- `PLUGIN_ALLOWED_SOURCES` in `examples/rti-demo/docker-compose.yml` and `launch.py`
- Tests: `modules/plugins/tests/`, `modules/io/tests/test_plugin_contract.py`, `modules/fsp/tests/test_plugins.py`,
  `modules/so/tests/test_plugins.py`
