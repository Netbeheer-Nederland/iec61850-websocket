<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 36. A plugin's definition (URL, settings) can be edited, until the FSP or SO restarts

- Status: proposed
- Date: 2026-10-22

## Context

An FSP or SO connects to the plugins in its plugin configuration, and to plugins added through `POST /api/plugins`
([0029](0029-plugins-are-http-services.md)). A plugin's definition is its `name`, `url` and `settings`. How things
stood (2026-10-22):

- **A definition couldn't be changed.** `/api/plugins` could add, reload and remove a plugin. Changing a URL or a
  setting meant removing the plugin and adding it again, which only works from a URL in `PLUGIN_ALLOWED_SOURCES`:
  none by default, so a configured plugin couldn't be changed at all without editing the configuration and
  restarting the FSP or SO.
- **A wrong URL was stuck.** A configured plugin at a URL that is wrong (another Pi's address, say) stays under
  `failed` and is tried again every 10 s, with no way to point it elsewhere from the HMI.
- **The definition wasn't visible.** `GET /api/plugins` gave a connected plugin's URL, but not its settings, and
  neither for a plugin that isn't connected.
- **The configuration is read-only in compose** (`config/plugin-configuration/`, mounted `:ro`), and is part of the
  repository.

Options considered:

1. **Remove and add again.** Already possible, but needs an allowed source even for the configured URL, and loses the
   plugin while the new one is tried.
2. **Edit and write back to the plugin configuration.** Lasting, but the FSP or SO would write a file that compose
   mounts read-only from the repository, and a plugin's own UI change would end up in Git.
3. **Edit in the running FSP or SO, as adding is** (chosen): an edit lasts until it stops; the configuration stays the
   lasting definition.

## Decision

1. **`PUT /api/plugins/{name}`** with `{url?, settings?}` changes a plugin's definition: the plugin is stopped
   (`POST <url>/stop`) and connected from the new definition (`GET <url>`, `POST <url>/start`). What the body leaves out
   stays; `settings` replaces all of them. It works for a connected plugin and for a configured or added one that isn't
   connected (`failed`); a removed one is `404`.
2. **The name stays.** A plugin describes itself with its name; another name is another plugin: remove and add.
3. **A new URL must be from an allowed source** (`403` otherwise), as for adding. The URL the plugin has already
   needs none: a configured plugin's settings can always be changed, as the configuration is trusted.
4. **A failed edit changes nothing.** When the new definition doesn't connect (`422`: unreachable, another name or
   `api`; `409`: a claimed objRef another plugin owns), the old definition is connected again and the error answered.
5. **An edit lasts until the FSP or SO stops**, as an added plugin does. The plugin configuration isn't written.
6. **`GET /api/plugins` lists `definitions`**: `{name: {url, settings}}` for every plugin in `plugins` and `failed`.
   The BFF passes it on in the `connections` push. A failed plugin's URL shows in the HMI from it.
7. **The HMI's Plugins panel has Edit** (✎) per plugin: the add form, filled with the definition, the name fixed;
   Save is the `PUT`. A refused edit keeps the form open with the instance's reason. Edit is disabled for an instance
   without `definitions`.

## Consequences

- A plugin's settings can be tried out from the HMI without restarting anything, and a configured plugin with a wrong
  URL can be pointed at an allowed one.
- An edit is lost when the FSP or SO restarts: the configuration is the lasting definition, as the HMI says.
- Settings are now readable by anyone who can list plugins (through the BFF, anyone using the HMI). Secrets don't
  belong in plugin settings; a plugin needing one reads it from its own environment.
- An edit restarts the plugin for this FSP or SO (`/stop`, `/start`), as a reload does: its state for this host starts
  over. Other FSPs and SOs using the same plugin service aren't affected.
- The contract is still version 2: `PUT` and `definitions` are additions on the FSP's and SO's side; a plugin
  implements nothing new.

## In the code

- `examples/rti-demo/modules/plugins/src/acsi_plugins/web.py` (`PluginService.edit`, `definitions`, `EditRequest`,
  the `PUT` route), `openapi.yaml` (`editPlugin`, `EditRequest`, `PluginDefinition`, `PluginList.definitions`)
- `examples/rti-demo/modules/bff/src/bff/bff_server.py` (`_fetch_plugins`)
- `examples/rti-demo/modules/hmi/src/components/PluginsPanel.jsx`, `utils/plugins.js` (`definition`),
  `services/apiService.js` (`plugin-edit`)
- Tests: `modules/plugins/tests/test_web.py`, `test_openapi.py`; `modules/bff/tests/test_push_relay.py`;
  `modules/hmi/src/components/PluginsPanel.test.jsx`, `utils/plugins.test.js`
