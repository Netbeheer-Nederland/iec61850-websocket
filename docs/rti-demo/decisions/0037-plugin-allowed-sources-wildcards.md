<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 37. Allowed plugin sources take wildcards; `*` alone allows any URL, and is the default

- Status: proposed
- Date: 2026-10-23

## Context

`POST /api/plugins` adds a plugin, and `PUT /api/plugins/{name}` moves one to a new URL, only from a URL in
`PLUGIN_ALLOWED_SOURCES` ([0021](0021-acsi-plugin-host.md), [0029](0029-plugins-are-http-services.md),
[0036](0036-plugin-definitions-editable.md)): scheme, host and port equal, the path by whole segments. How things stood
(2026-10-23):

- **Chicken and egg.** To add a plugin from the HMI, its URL had to be allowed first, which means changing the FSP's or
  SO's environment and restarting it. By then the plugin could as well have gone in the plugin configuration, so adding
  and moving from the HMI was of little use.
- **A lab has many addresses.** Plugins run on Raspberry Pis and laptops on one network, with addresses from DHCP. Every
  address had to be listed, exactly.
- **The check guards something else now.** 0021 allowed sources because plugins were downloaded and run. Since 0029 a
  plugin is a service the FSP or SO calls: the risk is a caller pointing it at a server of their own, which then gets
  every event and answers Operates on the objRefs it claims. The FSP's and SO's API has no authentication yet, so the
  allowed sources are the only gate.

Options considered:

1. **Wildcards in an allowed URL** (chosen): one entry for a network or a port, set once per deployment.
2. **CIDR ranges** (`http://192.168.0.0/24`): exact for networks, but `/24` is also a path, and the path is part of an
   allowed URL already. `192.168.0.*` covers the common case without the ambiguity.
3. **`*` alone** (chosen, with 1, and as the default): turns the check off, so the HMI can add and move plugins without
   any setup; narrowing it is a setting away.
4. **Allow the servers in the plugin configuration**: helps a plugin moving on its own server only.
5. **Editing the allowed sources from the HMI**: without authentication, whoever can add a plugin could widen the list
   too, so it would guard nothing.
6. **Authorization on `/api/plugins`** (a role, through Keycloak): the lasting answer, left for a decision of its own
   when the FSP and SO check tokens.

## Decision

1. **`*` in the host of an allowed URL**: as the whole host it stands for any host (`http://*:9000`); as one
   dot-separated part, for any one part (`http://192.168.0.*:8000`, `http://*.lab.test:9000`). A part is matched whole:
   `192.168.0.*` doesn't match `192.168.0.5.evil.test`. Host names are matched without regard to case.
2. **`*` as the port** stands for any port, and for none (`http://rpi-io:*`).
3. **The scheme and the path are matched as before**: the scheme equal, the path by whole segments.
4. **An entry that is just `*`** allows any `http` or `https` URL. The FSP or SO logs a warning at startup when it is
   set.
5. **`*` is the default.** Unset, `PLUGIN_ALLOWED_SOURCES` is `*`, so the HMI can add and move plugins out of the box;
   set but empty, it allows none. Compose doesn't set it, and `launch.py` passes it on only when the caller set it.
6. **The HMI says what is accepted** in the Plugins panel's form: the URL must be allowed by the instance's
   `PLUGIN_ALLOWED_SOURCES`, which can have wildcards or be `*`.

## Consequences

- A lab sets `PLUGIN_ALLOWED_SOURCES=http://192.168.0.*:8000` (say) once, and plugins on any Pi there can be added and
  moved from the HMI without a restart.
- By default anyone who can reach the FSP's or SO's API (through the BFF, anyone using the HMI) can connect it to any
  server, which then gets its events and can answer Operates. That suits the demo on a closed network; anywhere else
  `PLUGIN_ALLOWED_SOURCES` has to be narrowed (an exact URL, a network with wildcards, or empty), until
  authorization on `/api/plugins` (option 6) guards it.
- This replaces 0021's default of no allowed sources.
- Existing entries mean what they did, except that a host name now matches without regard to case, and a URL with user
  info (`http://user@host`) is matched by its host.
- The plugin contract doesn't change.

## In the code

- `examples/rti-demo/modules/plugins/src/acsi_plugins/remote.py` (`is_allowed`, `ANY_SOURCE`), `web.py`
  (`PluginService.from_env`), `openapi.yaml` (`addPlugin`, `editPlugin`)
- `examples/rti-demo/launch.py` (`_plugin_env`)
- `examples/rti-demo/modules/hmi/src/components/PluginsPanel.jsx` (the form's hint)
- Tests: `modules/plugins/tests/test_remote.py`, `test_web.py`; `tests/unit/test_rti_demo_launch.py`,
  `test_rti_demo_ports.py`
