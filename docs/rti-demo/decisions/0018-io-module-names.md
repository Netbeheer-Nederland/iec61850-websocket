<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 18. Names for the IO module: `io` for the role, `rti_io` for the code

- Status: accepted
- Date: 2026-10-07

## Context

The IO module's Python side was named `io`, which Python's standard library already uses: `import io` always gets
the standard module, so `modules/io` could never be imported by its own name. It only worked because the server ran
as a script and the FSP and SO loaded the plugin files by bare module names (`async_client_io`, `io_router`,
`io_utils`, `mapping_manager`), names that any other module on the path could clash with.

The downloadable part had four names: `io_plugin` (code, `/api/io-plugin/...`, `IO_PLUGIN_STORAGE`), `io_client`
(its folder), `io_router` (the module that is mounted) and "ACSI IO Client" (its README). `async_client_io.py` held
two identical async clients (`AsyncIOClient`, `AsyncDemoIOClient`) and a class named `ConnectionError`, which hid
Python's built-in one. Compose and `launch.py` gave the service two different `rti.type` labels.

## Decision

- `io` stays the **role** name, the same as `bff`, `fsp` and `so`: the folder `modules/io`, the `launch.py` service,
  the image and container `rti-io`, port 9000.
- The **code** is the package `rti_io` (distribution `rti-io`), in two parts:
  - `rti_io.server`: the IO server (was `io_api_server`), started with `python -m rti_io.server.main`;
  - `rti_io.plugin`: the IO plugin (was `io_client`), files `client.py`, `router.py`, `mapping.py`, `utils.py`,
    `io_mapping.json`.
- **"IO plugin"** is the one term for the part the FSP and SO download. They load it as the package
  `rti_io_plugin`, with relative imports inside it, so nothing it contains takes a bare top-level module name.
- One async client, `AsyncIOClient`, plus the synchronous wrapper `DemoIOClient`; the error class is
  `IOConnectionError`. The `rti.type` label is `RTI-IO`, like `RTI-BFF`, `RTI-FSP` and `RTI-SO`.

## Consequences

- The FSP or SO and the IO server must come from the same version. Serving the old file names as aliases would not
  help: the old loader imports the files by bare names, and the new files use relative imports, so it can't load
  them. A request for an old file name gets `410 Gone` with a message saying so.
- `IO_CLIENT_FILES_DIR` and `IO_CLIENT_VERSION` still work, as fallbacks for `IO_PLUGIN_FILES_DIR` and
  `IO_PLUGIN_VERSION`.
- Supersedes the file names in [0011](0011-io-separate-project-runtime-plugin.md); its decision (a separate project,
  a plugin loaded at runtime) stands.

## In the code

- `examples/rti-demo/modules/io/rti_io/server/`, `examples/rti-demo/modules/io/rti_io/plugin/`
- `load_io_plugin_modules` in `modules/fsp/src/fsp/bff_endpoint.py` and `modules/so/src/so/bff_endpoint.py`
