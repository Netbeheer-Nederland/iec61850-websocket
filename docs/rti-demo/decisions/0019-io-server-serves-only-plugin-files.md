<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 19. The IO server serves only the IO plugin's own files

- Status: accepted
- Date: 2026-10-07

## Context

The FSP and SO download the IO plugin from the IO server with `GET /api/io-plugin/files/{filename}`
([0011](0011-io-separate-project-runtime-plugin.md), [0018](0018-io-module-names.md)). The route took the name as a
path (`{filename:path}`) and joined it to the plugin folder with `os.path.join`, without checking the result. A name
with `..` stepped out of the folder, and an absolute name replaced the folder altogether:

| Request | Answered with |
|---|---|
| `GET /api/io-plugin/files/..%2Fserver%2Fio_config.json` | the IO server's device configuration |
| `GET /api/io-plugin/files/%2Fetc%2Fhostname` | `/etc/hostname` |

The IO server has no authentication and listens on `0.0.0.0:9000`. Anyone on the network could read any file the IO
server's process can read. Started with `launch.py`, that's the developer's own home directory, SSH keys included.
In Docker it's the container: as `pi` on a Raspberry Pi, and as root with `docker-compose.no-devices.yml`, which
resets `user:`.

## Decision

- The route serves a file only when it is a **regular file directly in the plugin folder**. The server resolves the
  requested path (following `..` and symlinks) and compares its parent with the resolved plugin folder. Anything
  else gets `404`: a name with a path separator, `..`, an absolute path, a subfolder, a directory, or a symlink that
  leads out of the folder.
- A refused name gets the same `404` as a file that doesn't exist, so the answer doesn't tell whether something
  exists outside the folder.
- The plugin folder stays flat. The IO plugin's files are all at its top level, and the FSP and SO ask for them by
  plain file names (`IO_PLUGIN_REQUIRED_FILES`).

## Consequences

- The IO server no longer discloses files outside the plugin folder. Tests pin the requests above, an encoded `..`,
  a subfolder and a symlink (`examples/rti-demo/modules/io/tests/test_plugin_files.py`).
- A future IO plugin can't use subfolders without changing this check.
- The IO server still has no authentication, and its other endpoints change devices and save their configuration
  for anyone who can reach port 9000. This record doesn't change that. The demo assumes a trusted network. Before
  the IO server runs on a network that isn't trusted, it needs authentication or a bind address limited to the
  hosts that use it.

## In the code

- `get_io_client_file_path` and `api_get_io_client_file` in `examples/rti-demo/modules/io/rti_io/server/plugin_files.py`
