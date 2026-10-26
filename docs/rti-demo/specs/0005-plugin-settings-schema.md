<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 0005. A plugin describes its settings as JSON Schema

- Status: draft
- Date: 2026-10-24
- Changes: plugin contract, plugin host, HMI, sample plugins

## Goal

Know what settings a plugin takes, with their types and defaults, while adding or editing it in the HMI, and catch a
wrong setting before the plugin is restarted with it.

## Now

- Settings are free JSON (`PluginEntry.settings`, `additionalProperties: true`), passed to the plugin in
  `POST <url>/start`. What a plugin accepts is only in its README.
- The HMI's settings field is a CodeMirror JSON editor (JsonEditor) that marks syntax errors, not wrong settings.
- A plugin that rejects its settings fails its `/start`: the add or edit is refused (422) with its reason, after the
  plugin was stopped and connected again.
- `PluginDescription` says "Other fields are ignored", so a new optional field doesn't break older hosts.

## Proposal

### Plugin contract and host

1. `PluginDescription` gets an optional **`settings_schema`**: a JSON Schema (2020-12) object for the `settings`.
   Leaving it out means "any object", as now. `api` stays 2.
2. The host keeps it per plugin and gives it in `GET /api/plugins` (`PluginStatus.settings_schema`, `null` when
   none).
3. The host doesn't validate settings itself: the plugin stays the judge, as its `/start` is. (See open questions.)
4. A plugin that can't be reached has no schema, so editing it has none either.

### HMI

1. JsonEditor takes an optional `schema`. With it: errors from the schema marked in the editor (as syntax errors are,
   through `@codemirror/lint`), completion of property names, and hover with each property's `description`.
2. The add form has no schema until the plugin is known; a **Fill defaults** button appears in the edit form when
   the schema has `default`s the settings lack.
3. Save with schema errors asks first ("The settings don't match io's schema: ... Save anyway?"): the schema is
   advice, the plugin decides.
4. Details shows "Settings schema: yes / no".

### Sample plugins

dr_leds and dr_panel describe their settings (`write_inputs`, `blink_seconds`, ...), so the HMI has an example.

## Acceptance

- A plugin with `settings_schema` has it in `GET /api/plugins`; one without has `null`, and nothing else changes.
- Editing a plugin with a schema marks a property of the wrong type and completes property names.
- Saving with schema errors asks; confirmed, the `PUT` is sent as before.

## Tests

modules/plugins: test_remote.py (schema read, kept, invalid schema type ignored with a warning), test_openapi.py.
HMI: JsonEditor with schema (lint marks, completion), PluginsPanel (confirm on schema errors, Fill defaults). Plugins:
their describe tests.

## Docs to update

`openapi.yaml` (`PluginDescription.settings_schema`, `PluginStatus.settings_schema`), plugins README and
GETTING_STARTED (how to describe settings), dr_leds and dr_panel READMEs, a new decision, wireframe (edit form with a
marked setting), HMI README.

## Open questions

- Which library validates the schema in the browser: a small JSON Schema validator (`@cfworker/json-schema`), or
  `codemirror-json-schema`, which brings lint, completion and hover together? Both add to the lazily loaded editor
  chunk only.
- Should the host also validate (and refuse with 422 before stopping the plugin), so a wrong edit doesn't interrupt a
  running plugin? That needs a Python validator (`jsonschema`) in the plugin host.
