<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 25. Plugins describe what they attach as data, at `GET <url>/attached`; the HMI draws it next to the FSP or SO

- Status: proposed
- Date: 2026-10-11, revised 2026-10-22 for plugins as HTTP services ([0029](0029-plugins-are-http-services.md))

## Context

A plugin links its FSP or SO to something outside the ACSI: the IO server to its LEDs, buttons, potentiometers and
displays ([0024](0024-ssd1306-oled-display-device.md)), a future plugin perhaps to an IED. The HMI should show that:
next to each FSP and SO, a small box per attached IO server, display or IED, with whether it is working and a little
of what it shows (an LED, a value, a display's text).

The first version of this decision (2026-10-11) was written for in-process plugins: an `attached()` method on
`AcsiPlugin`, a background task in the IO plugin asking the IO servers, and a separate `attached` message from the
BFF. None of it was built. Since then a plugin is an HTTP service the FSP and SO connect to (0029), and the IO server
is that plugin itself. How things stand (2026-10-22):

- **The FSP and SO list their plugins.** `GET /api/plugins` (`acsi_plugins/web.py`, `PluginHost.status`) gives each
  plugin's `name`, `version`, `url`, `claims`, `routes`, `healthy` and `last_error`, and the plugins that can't be
  reached under `failed`. That says how the plugin runs, not what it is attached to.
- **The BFF already pushes that list.** Its central poll ([0005](0005-push-channel-central-poll.md)) reads every
  connected SO's and FSP's `GET /api/plugins` every 2 s and puts it on their entries in the `connections` push, as
  `plugins`; it is broadcast only when something changed. The HMI shows it as a plugin badge on Overview and Traffic
  and a Plugins panel on the ACSI Client and ACSI Server pages.
- **The HMI draws the topology.** `InstanceVisualization` draws the SO, the FSPs and the links between them, on
  Overview, Model and Traffic.
- **The plugin knows what it attaches.** The IO server reads its own devices; it knows the text it last wrote to a
  display. `sim_leds` holds its two LEDs in memory.

Four options were considered:

1. **Show the plugin list only.** Done (the plugin badge and Plugins panel), but it shows plugins, not what they
   attach.
2. **The HMI calls each plugin's own routes** (`/api/plugins/io/...`). The HMI would have to know each plugin's API:
   a new plugin means an HMI change.
3. **Plugins ship HMI widgets** (JavaScript loaded at runtime). Runs downloaded code in every operator's browser,
   needs a build and a version per plugin, and goes around the BFF.
4. **Plugins describe what they attach, as data, at one more route of the plugin API; the HMI draws every plugin's
   the same way** (chosen).

## Decision

1. **A plugin may say what it attaches**, at an optional `GET <url>/attached` of the plugin API:

   ```json
   {
     "items": [
       {
         "kind": "io",
         "label": "IO server",
         "address": "http://rti-io:9000",
         "state": "ok",
         "detail": "6 devices",
         "live": [
           {"type": "indicators", "items": [{"name": "led1", "on": true, "color": "green"}]},
           {"type": "values", "items": [{"label": "pot1", "value": 42.0, "unit": "%"}]}
         ]
       },
       {
         "kind": "display",
         "label": "lcd1",
         "state": "ok",
         "live": [{"type": "text", "lines": ["FSP Connected: cp1"]}]
       }
     ]
   }
   ```

   `kind` is `io`, `ied`, `display` or `other` (the icon); `state` is `ok`, `degraded`, `down` or `unknown` (the
   colour); `label` is required, `address`, `detail` and `live` are optional. The plugin answers with what it already
   knows, within 1 s; it doesn't ask other services while the FSP or SO waits. A plugin without the route answers
   `404`: it attaches nothing, and that is not an error. The contract version stays 2: the route is optional, and a
   plugin without it keeps working.
2. **A little live content, of three types.** `live` holds blocks the HMI can draw without knowing the plugin:

   | `type` | Holds | At most |
   |---|---|---|
   | `text` | `lines` | 8 lines of 24 characters |
   | `indicators` | `items`: `name`, `on`, `color` (`green`, `red`, `yellow`, `blue`, `white`) | 8 |
   | `values` | `items`: `label`, `value` (number or short text), `unit` | 6 |

   At most 4 items per plugin and 4 `live` blocks per item. The FSP and SO check and trim what a plugin answers (too
   many items, blocks, lines or characters are cut; an item without a `label` or with an unknown `kind` or `state`,
   and a block of an unknown `type`, are dropped; an unknown `color` becomes `white`), so one plugin can't flood the
   poll or the page. Everything is plain text: the HMI never renders it as HTML.
3. **The FSP and SO return it with the plugin list.** Each plugin in `GET /api/plugins` gets `attached` (the checked
   items) and `attached_error`. The host asks every connected plugin's `/attached` when the list is asked for, all at
   once, with a 1 s timeout, and at most once a second: a second ask within that second gets the last answer. A
   plugin that doesn't answer in time, or answers something that isn't `{"items": [...]}`, keeps its last items and
   gets `attached_error`; its `healthy` doesn't change. Plugins under `failed` have none.
4. **The BFF passes it on unchanged.** It is part of `plugins` on each SO's and FSP's entry in the `connections`
   push, so a change (an LED, a value, a display's text, a state) is broadcast in the next poll. There is no separate
   `attached` message and nothing new for the HMI to poll.
5. **The IO server reports its devices.** One `io` item for the server: its LEDs as `indicators`, its buttons and
   potentiometers as `values`, `ok` while every configured device is up and `degraded` when some aren't (`detail`
   says how many), `down` while it isn't initialised. One `display` item per display device, with the text the
   plugin last wrote to it (`text`). It reads its own devices: no background task, nothing asked while nobody asks.
   The IO server doesn't know an LED's colour, so it reports `green`.
6. **`sim_leds` reports its two LEDs**, as one `other` item with `indicators` (`green`, `red`), as the example for
   plugin authors in `GETTING_STARTED.md`.
7. **The HMI draws a box per item.** On Overview and Traffic, `InstanceVisualization` draws each attached item next to
   its FSP or SO: the icon for its `kind`, coloured for its `state`, its `label`, a left edge coloured for its plugin's
   state as the FSP or SO sees it (green connected and running, orange unhealthy or not answering `/attached`, red
   disconnected - a disconnected plugin gets one box of its own), and its `live` blocks small underneath (LED dots,
   values, a text box like the display). Clicking a box opens its details: `address`, `detail`, the plugin's name,
   `version`, `healthy`, `last_error` and `attached_error`. Model keeps its focus; it can turn the boxes on by a prop
   (`showAttached`). The HMI draws every plugin's items the same way: a new plugin needs no HMI change.

## Consequences

- What each FSP and SO is attached to is visible on Overview and Traffic: an IO server whose devices didn't come up shows
  `degraded` next to its FSP, and the display's text, the LEDs and the potentiometers show as they change. A plugin
  that is down shows no boxes; its plugin badge is red.
- **Live means within the poll.** The BFF polls every 2 s and the host asks at most once a second, so what the HMI
  shows can be up to about 3 s behind. A blink shorter than that may never show. That is enough to see the demo
  follow along; the hardware itself is the real-time view.
- **A little more traffic, all the time.** The BFF polls whether or not a tab is open, so each connected plugin gets
  one `GET /attached` per poll, about every 2 s; for the IO server that is a read of its own devices. `/ws` carries a
  message only when something changed.
- **The contract grows by one optional route**, so plugins without it keep working and show no box. The host's
  checks mean a plugin can't break the page or the BFF's poll with large content, and its 1 s timeout keeps a slow
  plugin from holding up `GET /api/plugins` for long.
- The three `live` types limit what a plugin can show. A plugin that needs more (a chart, a picture) needs a new type,
  which is a change to the contract, the host's checks and the HMI, decided like this one.
- Replaces the first version's `AcsiPlugin.attached()`, the IO plugin's background task (the IO server is the plugin
  now and reads its devices directly) and the BFF's `attached` message (the `plugins` push already carries it).
- Review one month after it runs: whether 2 s plus 1 s feels live enough in the demo, and whether the limits in
  point 2 fit what plugins want to show.

## In the code

- `examples/rti-demo/modules/plugins/`: `src/acsi_plugins/attached.py` (the checks and trimming), `contract.py`
  (`AcsiPlugin.attached`), `remote.py` (`GET <url>/attached`), `host.py` (`refresh_attached`, `attached` and
  `attached_error` in `status`), `web.py` (`GET /api/plugins` refreshes first); `openapi.yaml`, `GETTING_STARTED.md`,
  `README.md`; `tests/test_attached.py`, `test_openapi.py`, `fake_plugin.py`
- `examples/rti-plugins/rpi_io/src/rpi_io/plugin/plugin.py` (`/plugin/attached`, the displays' last text);
  `tests/test_plugin.py`
- `examples/rti-plugins/sim_leds/src/sim_leds/plugin/plugin.py` (`/plugin/attached`); `tests/test_sim_leds.py`
- `examples/rti-demo/modules/hmi/src/components/InstanceVisualization.jsx` (the boxes and their details),
  `utils/plugins.js` (`attachedItems`), `pages/Overview.jsx`; their tests
