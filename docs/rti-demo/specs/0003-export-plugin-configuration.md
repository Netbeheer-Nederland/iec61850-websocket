<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 0003. Download an instance's plugin configuration

- Status: draft
- Date: 2026-10-24
- Changes: HMI

## Goal

Make every plugin change made in the HMI last, in one step: get the whole plugin configuration of an SO or FSP as
it now runs, to put in `config/plugin-configuration/`.

## Now

- Adds and edits last until the instance restarts. Decision
  [0036](../decisions/0036-plugin-definitions-editable.md) chose not to write them back to the configuration: compose
  mounts it read-only from the repository, and an HMI change would end up in Git.
- Copy as configuration (⧉) gives one plugin's entry. With several changed plugins, each is copied and merged by hand.
- `GET /api/plugins` has every plugin's definition (`definitions`), connected or not. It doesn't have the instance's
  `host_url`.

## Proposal

### HMI

1. A header action **Export** (icon `fa-download`) in the Plugins panel, enabled when the instance lists
   definitions.
2. It downloads `<instance>.json`, a `PluginsConfig`:

   ```json
   {
     "plugins": [
       { "name": "io", "url": "http://rpi-io:9000/plugin" },
       { "name": "display", "url": "http://pi:8000/plugin", "settings": { "rotate": 90 } }
     ]
   }
   ```

   One entry per definition, as Copy makes it (`configEntry`), in the order of the panel's rows. `host_url` is left
   out: the instance's environment (`PLUGIN_HOST_URL`) or its existing file gives it, and the note under the
   button says so.
3. The file name is the instance's name from the BFF (`rti-fsp01.json`), matching the files in
   `config/plugin-configuration/`.
4. A removed plugin isn't in `definitions`, so it isn't in the file: the export is what runs now.

### FSP, SO, BFF

No change.

## Acceptance

- Export downloads a JSON file with every definition, settings only where there are some.
- It is disabled for an instance without definitions.
- The file loads as the instance's `PLUGINS_FILE` (checked by the plugin host's config test with an exported file).

## Tests

plugins.test.js: `pluginsConfig(status)` builds the file from `definitions`. PluginsPanel.test.jsx: Export creates a
download with that content (`URL.createObjectURL` spied). modules/plugins tests/test_config.py: an exported file
without `host_url` loads.

## Docs to update

Wireframe (Export in the panel header, ⓘ text), HMI README, `examples/rti-demo/README.md` (the paragraph on making a
change last).

## Open questions

- Should the instance give its `host_url` in `GET /api/plugins`, so the export is a complete file? That is a small
  contract change; without it, the export replaces the `plugins` of a file and keeps its `host_url`.
- A file with every instance's plugins at once (a zip, or a page per instance)?
