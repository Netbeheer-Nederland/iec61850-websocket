<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 22. The IO plugin is its own package, installed with the FSP and SO

- Status: proposed
- Date: 2026-10-10

## Context

`modules/io` holds two things that run in different places
([0011](0011-io-separate-project-runtime-plugin.md), [0018](0018-io-module-names.md)):

| | `rti_io.server` | `rti_io.plugin` |
|---|---|---|
| Runs in | the IO container, on the Raspberry Pi | the FSP and SO |
| Needs | `gpiozero`, `gpiod`, `smbus2`, `Adafruit-ADS1x15` | `acsi_plugins`, `fastapi`, `pydantic`, `httpx2` |
| Reaches the other | serves the plugin's files at `GET /api/io-plugin/files` | over HTTP, to `IO_URL` |

0011 kept them together so the FSP and SO would download a client that always matches the IO server it came from.
Since [0021](0021-acsi-plugin-host.md) the IO plugin is one plugin among others, and keeping it inside the
hardware project now costs more than it gives (2026-10-10):

- **It sits outside the workspace it belongs to.** `modules/io` isn't a member of the root uv workspace, because of
  the hardware packages. The plugin depends on `acsi_plugins`, a workspace package, but `modules/io/pyproject.toml`
  can't declare it. Its tests run under another package (`uv run --package fsp pytest
  examples/rti-demo/modules/io/tests`) and put `modules/io` on `sys.path` themselves. Working on the plugin means
  working in the hardware project, with its own `uv.lock` and `.venv`.
- **It is the only plugin that has to be downloaded.** The FSP and SO can load a plugin installed in the image
  (entry point group `acsi.plugins`, 0021), but the IO plugin can't be installed there: it isn't a package the
  workspace can build. So every demo run needs `PLUGIN_ALLOWED_SOURCES` pointing at the IO server, and the FSP and
  SO run code downloaded at runtime for their one built-in integration.
- **The IO server serves code.** `plugin_files.py` and the path check of
  [0019](0019-io-server-serves-only-plugin-files.md) exist only to hand out the plugin's files, on a server without
  authentication.
- **The plugin still reaches into the server.** `_register_input_callback` in `rti_io/plugin/router.py` imports
  `rti_io.server.io_controller`, which only works when the server and the plugin share a process. They never do
  now: in the FSP and SO the import fails and the route logs a warning. Input changes reach the FSP and SO the
  other way, from the IO server to `acsi_url`.
- **The matching version no longer protects much.** 0021 made the FSP, SO and IO server change together, with no
  transition between versions. They are released and deployed as one demo.
- **Runtime download is shown elsewhere.** The sample plugin `sim_leds` (`modules/plugins/samples/`) shows how a
  plugin is downloaded and loaded; the IO plugin doesn't need to be the example of it.

Three options were considered:

1. **Keep it as it is.** No work, but the points above stay.
2. **Its own workspace package, still downloaded from the IO server.** Fixes the tests and the dependency, but the
   IO image has to copy files from outside `modules/io` (a wider Docker build context), and the IO server keeps
   serving code.
3. **Its own workspace package, installed in the FSP and SO images** (chosen).

## Decision

1. **A package of its own.** The IO plugin moves from `modules/io/rti_io/plugin/` to
   `examples/rti-demo/modules/io-plugin/`, a member of the root uv workspace:

   | | |
   |---|---|
   | Folder | `modules/io-plugin/` (`src/acsi_io_plugin/`, `tests/`) |
   | Distribution | `acsi-io-plugin` |
   | Import package | `acsi_io_plugin`, the name 0021 already loads it under |
   | Dependencies | `acsi-plugins`, `fastapi`, `pydantic`, `httpx2`: no hardware packages |
   | Entry point | `[project.entry-points."acsi.plugins"] io = "acsi_io_plugin.plugin:RtiIoPlugin"` |

   It keeps `client.py`, `mapping.py`, `router.py`, `utils.py`, `plugin.py` and `io_mapping.json`. Its tests move
   with it and import it as a package, without `sys.path`.
2. **Installed, not downloaded.** The FSP and SO depend on `acsi-io-plugin`, and their images copy
   `modules/io-plugin` as they copy `modules/plugins`. The plugin host finds it through the entry point and starts
   it at start-up, with its settings from `PLUGINS` (0021, point 5). `plugin.json` goes: an installed plugin has no
   manifest.
3. **Where it connects.** With no server to come from, `io_url` comes from the settings or `IO_URL`. Without either,
   the plugin starts, logs that it has no IO server and does nothing, so the FSP and SO run without IO
   ([0017](0017-hardware-is-optional.md)); an IO server that doesn't answer is logged the same way, and
   `POST /api/plugins/io/connect` or `/reload` connects later. Because the plugin now starts by itself, not from an
   install request with `settings.acsi_url`, the service also says where the IO server writes input changes back
   to: `ACSI_BASE_URL`. Compose sets both for every FSP and the SO (`http://rti-io:9000`, `http://rti-fsp01:5001`,
   ...); `launch.py` sets `localhost` addresses, or the container names (`rti-io`, `rti-<type>`) when it starts
   containers, and follows a port given on the command line.
4. **The IO server is only the hardware server.** `modules/io` keeps `rti_io.server`, its own uv project and its
   own image (0011 stands for those). `GET /api/io-plugin/files`, `plugin_files.py` and `IO_PLUGIN_FILES_DIR` go.
5. **Each service its own mapping.** A downloaded plugin had its own copy of `io_mapping.json` in
   `PLUGIN_STORAGE`, and `POST /api/plugins/io/mappings/save` wrote to that copy. Installed, the package folder is
   shared by every FSP and SO run from the same checkout, and saving there would change a file in git. So the plugin
   reads and saves the file in its setting `mapping_file`, else `IO_MAPPING_FILE`, seeded once from the shipped
   file when it doesn't exist yet (as the IO server does with `IO_CONFIG_FILE`); without either, the shipped file.
   `launch.py` sets `config/plugins/<service>/io_mapping.json` (git-ignored). In a container each service has its
   own copy of the package, so compose sets none.
6. **No server code in the plugin.** The `rti_io.server` import in `router.py` goes, and with it the in-process
   input callbacks that never ran in the FSP or SO. Inputs keep reaching the FSP and SO from the IO server through
   `acsi_url`.

## Consequences

- The plugin is linted, tested and locked like the other workspace packages, in CI too. `modules/io` has only
  hardware code, and its tests only the server's.
- The FSP and SO start the IO plugin on every start, also without IO hardware: `GET /api/plugins` always lists
  `io` (`source: "installed"`). The plugin host's own tests hide installed plugins, so they don't depend on what the
  workspace installs.
- The FSP and SO run no downloaded code by default. `PLUGIN_ALLOWED_SOURCES` is empty in compose and in
  `launch.py` unless the caller sets it, e.g. for a plugin under development
  (`modules/plugins/GETTING_STARTED.md`); `launch.py`'s `_plugin_env` and the port test change with it.
- **The version link of 0011 goes.** The plugin's version follows the FSP and SO, not the IO server it talks to. An
  IO server and FSP from different commits can disagree on the IO API; the demo deploys them together, as 0021
  already requires. Superseded in 0011: the IO server shipping the client, and "the IO client version always
  matches the IO server it came from".
- **Breaking, without a transition**, as in 0021: `GET /api/io-plugin/files` is gone (`404`), and so is
  `IO_PLUGIN_FILES_DIR`. A downloaded `io` plugin in `PLUGIN_STORAGE` from before is loaded from there and wins over
  the installed one until it is removed (`DELETE /api/plugins/io`) or `PLUGIN_STORAGE` is cleared.
- 0019 no longer applies: the route it secured is removed. Its lesson stays for any server that hands out plugin
  files.
- Superseded in 0018: the source package `rti_io.plugin`; the plugin is `acsi_io_plugin` everywhere. The rest of
  0018 stands. Superseded in 0021: point 7's "`rti_io.plugin` gets a `plugin.json`", and point 3's note that the
  IO server serves each file as it is.
- The FSP and SO images grow by the plugin (a few Python files) and rebuild when it changes. The IO image no longer
  rebuilds for a plugin change.
- A plugin for other hardware is installed the same way, or downloaded as 0021 allows: the host doesn't change.
- Review one month after the move: whether a mismatch between IO server and IO plugin versions occurred, and
  whether anything still expects `/api/io-plugin/files`.

## In the code

- `examples/rti-demo/modules/io-plugin/` (`pyproject.toml` with the entry point, `src/acsi_io_plugin/`, `tests/`)
- Root `pyproject.toml` (workspace member), `uv.lock`
- `modules/fsp/pyproject.toml`, `modules/so/pyproject.toml` (dependency); their `docker/Dockerfile` (copy
  `modules/io-plugin`)
- `resolve_mapping_path` in `acsi_io_plugin/mapping.py`; `RtiIoPlugin.start` in `acsi_io_plugin/plugin.py`
- `examples/rti-demo/docker-compose.yml` (`IO_URL` and `ACSI_BASE_URL`; no `PLUGIN_ALLOWED_SOURCES`), `launch.py`
  (`_plugin_env`, `_with_port`, `RTILauncher._docker_env`)
- `.github/workflows/ci.yml` (the plugin's tests), `.github/workflows/images.yml` (a plugin change rebuilds the FSP
  and SO images)
- Tests: `modules/io-plugin/tests/` (`test_installed.py`, `test_mapping_file.py`, and the plugin's tests moved from
  `modules/io/tests`), `modules/io/tests/test_no_plugin_files.py`, `test_plugins.py` of the FSP and SO,
  `tests/unit/test_rti_demo_launch.py`, `tests/unit/test_rti_demo_ports.py`
- Removed: `modules/io/rti_io/plugin/`, `modules/io/rti_io/server/plugin_files.py`,
  `modules/io/tests/test_plugin_files.py`
