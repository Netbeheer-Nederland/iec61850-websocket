<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 25. Plugins describe what they attach as data; the HMI draws it next to the FSP or SO

- Status: proposed
- Date: 2026-10-11

## Context

Since [0021](0021-acsi-plugin-host.md) the FSP and SO host plugins, and a plugin links its connection point to
something outside the ACSI: the IO plugin to one or more IO servers ([0022](0022-io-plugin-own-package.md),
[0024](0024-ssd1306-oled-display-device.md)), a future plugin perhaps to an IED. The HMI should show that: next to
each FSP and SO, a small box per attached IO server or IED, with whether it is reachable and a little of what it
shows (an LED, a value, a display's text). How things stand (2026-10-11):

- **The FSP and SO list their plugins.** `GET /api/plugins` (`acsi_plugins/web.py`, `PluginHost.status`) gives
  each plugin's `name`, `version`, `source`, `claims`, `routes`, `healthy` and `last_error`. That says how the plugin
  runs, not what it is attached to: `healthy` turns false only when `on_event` fails or is slow, not when the IO
  server is unreachable.
- **The BFF polls once for every HMI tab.** `push_relay_loop` polls each connected SO and FSP every 2 s and
  broadcasts changes over `/ws` (`_relay_new_messages`, `_relay_acsi_client_list`, ...), so N tabs cost one poll
  ([0005](0005-push-channel-central-poll.md)). The HMI reaches the FSP and SO only through the BFF
  ([0004](0004-bff-single-gateway-execute-proxy.md)).
- **The HMI draws the topology.** `InstanceVisualization` draws the SO, the FSPs and the activity on the links
  between them, on Overview, Model and Traffic.
- **What an IO server shows is readable.** `GET /api/io/devices` on the IO server has every device's state; the IO
  plugin knows the text it last wrote to a display.

Four options were considered:

1. **Show the plugin list** (name, health) through `/api/execute`. No contract change, but it shows plugins, not what
   they attach, and every tab would poll every instance.
2. **The HMI calls each plugin's own routes** (`/api/plugins/io/...`). The HMI would have to know each plugin's API:
   a new plugin means an HMI change.
3. **Plugins ship HMI widgets** (JavaScript loaded at runtime). Runs downloaded code in every operator's browser,
   needs a build and a version per plugin, and goes around the BFF.
4. **Plugins describe what they attach, as data; the HMI draws every plugin's the same way** (chosen).

## Decision

1. **A plugin may say what it attaches.** `AcsiPlugin` gets an optional `attached()`, returning a list of items
   (default none):

   ```python
   [
       {
           "kind": "io",                      # io | ied | display | other: the icon
           "label": "IO server (Pi 1)",
           "address": "http://rti-io:9000",
           "state": "ok",                     # ok | degraded | down | unknown: the colour
           "detail": "6 devices",
           "live": [
               {"type": "indicators", "items": [{"name": "led1", "on": True, "color": "green"}]},
               {"type": "values", "items": [{"label": "pot1", "value": 42.0, "unit": "%"}]},
           ],
       },
       {
           "kind": "display",
           "label": "OLED",
           "address": "http://rti-pi2:9000",
           "state": "ok",
           "live": [{"type": "text", "lines": ["FSP Connected: 3"]}],
       },
   ]
   ```

   `attached()` is synchronous and does no I/O: it returns what the plugin already knows. A plugin that needs to ask
   something keeps it up to date itself (point 5).
2. **A little live content, of three types.** `live` holds blocks the HMI can draw without knowing the plugin:

   | `type` | Holds | At most |
   |---|---|---|
   | `text` | `lines` | 8 lines of 24 characters |
   | `indicators` | `items`: `name`, `on`, `color` (`green`, `red`, `yellow`, `blue`, `white`) | 8 |
   | `values` | `items`: `label`, `value` (number or short text), `unit` | 6 |

   At most 4 items per plugin. The plugin host checks and trims what `attached()` returns (too many items, lines or
   characters are cut, an unknown `kind`, `state` or `type` is dropped), so one plugin can't flood the poll or the
   page. Everything is plain text: the HMI never renders it as HTML.
3. **The FSP and SO return it with the plugin list.** Each plugin in `GET /api/plugins` gets `attached`. If
   `attached()` raises, the plugin's list is empty and `attached_error` says why; its `healthy` doesn't change.
4. **The BFF relays it in the central poll.** `push_relay_loop` gets `_relay_attached`: for each connected SO and
   FSP, `GET /api/plugins`, and on a change, a broadcast `{"type": "attached", "target": "<host:port>", "data":
   {<plugin>: [...]}}`, as `_relay_acsi_client_list` does. Nothing new for the HMI to poll.
5. **The IO plugin reports one item per IO server.** With the named servers of 0024, that is the default server and,
   say, the OLED's Pi. A background task asks each server `GET /api/io/health` and `GET /api/io/devices` every 2 s,
   and only while `attached()` has been called in the last 10 s: with no HMI open, it asks nothing. LEDs become
   `indicators`, potentiometers and buttons `values`, and a display shows the text the plugin last wrote to it
   (`text`). A server that doesn't answer is `down`, with the last answer kept and greyed.
6. **The HMI draws a box per item.** `InstanceVisualization` draws each attached item next to its FSP or SO node: the
   icon for its `kind`, its `label`, the colour for its `state`, and its `live` blocks small underneath (LED dots,
   values, a text box sized like the display). Clicking it opens the details: `address`, `detail`, the plugin's
   `version`, `healthy` and `last_error`. Overview shows the boxes; Model and Traffic keep their focus and can turn
   them on by a prop. The HMI draws every plugin's items the same way: a new plugin needs no HMI change.

## Consequences

- What each FSP and SO is attached to is visible on Overview: a Pi that is unplugged shows `down` next to its FSP,
  and the OLED's text, the LEDs and the potentiometers show as they change.
- **Live means within the poll.** The BFF polls every 2 s and the IO plugin asks its servers every 2 s, so what the
  HMI shows can be up to about 4 s behind. A blink shorter than that may never show. That is enough to see the demo
  follow along; the hardware itself is the real-time view.
- **More traffic, only while someone looks.** Each connected FSP and SO answers one more request per poll. The IO
  plugin asks each IO server two requests per 2 s, but only while an HMI tab is open. `/ws` carries a message only
  when something changed.
- **The contract grows by one optional method**, so plugins without it keep working and show no box. The host's
  trimming means a plugin can't break the page or the BFF's poll with large content.
- The three `live` types limit what a plugin can show. A plugin that needs more (a chart, a picture) needs a new
  type, which is a change to the contract, the host's checks and the HMI, decided like this one.
- `sim_leds` (`modules/plugins/samples/`) gets `attached()` too, with its two LEDs as `indicators`, as the example
  for plugin authors in `GETTING_STARTED.md`.
- Review one month after it runs: whether 2 s plus 2 s feels live enough in the demo, whether the limits in point 2
  fit what plugins want to show, and whether the IO servers notice the extra requests.

## In the code

- `examples/rti-demo/modules/plugins/src/acsi_plugins/contract.py` (`attached()`), `host.py` (checks and trims in
  `status`), `web.py` (`attached`, `attached_error` in `GET /api/plugins`)
- `examples/rti-demo/modules/io-plugin/src/acsi_io_plugin/plugin.py` (`attached()`, the background task)
- `examples/rti-demo/modules/plugins/samples/sim_leds/plugin.py`; `GETTING_STARTED.md`, `README.md` of `plugins`
- `examples/rti-demo/modules/bff/src/bff/bff_server.py` (`_relay_attached` in `push_relay_loop`)
- `examples/rti-demo/modules/hmi/src/components/InstanceVisualization.jsx` (the boxes), its `/ws` handling, a
  details panel; `Overview.jsx`
- Tests: the host's trimming and the error case (`modules/plugins/tests/`), the IO plugin's items and that it asks
  nothing while not looked at (`modules/io-plugin/tests/`), the relay on change only (`modules/bff/tests/`), and the
  boxes, states and live blocks (`InstanceVisualization.test.jsx`)
