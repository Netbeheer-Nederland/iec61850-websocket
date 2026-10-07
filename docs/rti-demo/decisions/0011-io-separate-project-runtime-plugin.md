<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 11. IO is a separate project; its client is a plugin loaded at runtime

- Status: accepted
- Date: 2026-10-07

## Context

The IO service drives Raspberry Pi hardware (`gpiod`, `gpiozero`, `smbus2`, `Adafruit-ADS1x15`). Those packages
don't install everywhere, and the SO and FSP must run without IO.

## Decision

- `modules/io` is a standalone uv project with its own `pyproject.toml` and `uv.lock`, not a member of the root
  uv workspace. Its image builds from `modules/io`.
- The IO server ships the IO client (`io_client/`: router, mapping manager, async client, `io_mapping.json`) as
  files. An SO or FSP downloads them on `POST /api/io-plugin/connect`, into `IO_PLUGIN_STORAGE`, loads them and
  adds the IO router to its running FastAPI app.
- Adding the router is one-way: FastAPI can add routes at runtime but not remove them.
- `io_mapping.json` links devices to IEC 61850 objects (a button to `DERAvail.stVal`, a potentiometer to
  `TotW`, LEDs to connection events).

## Consequences

- The SO and FSP images don't need the hardware packages, and the root workspace installs anywhere.
- The IO client version always matches the IO server it came from.
- The SO and FSP execute code they download from the IO server: only connect to a trusted IO server.
- Without the IO service, the demo runs without hardware feedback.

## In the code

- `modules/io/` (`rti_io/server/plugin_files.py`, `rti_io/plugin/`); file and package names: [0018](0018-io-module-names.md)
- `modules/fsp/src/fsp/bff_endpoint.py`, `modules/so/src/so/bff_endpoint.py` (`load_io_plugin_modules`,
  `_try_include_io_router`)
- Root `pyproject.toml` (workspace members; `io` excluded)
