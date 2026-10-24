<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 0001. Call a plugin's own routes from its Details

- Status: done (2026-10-24)
- Date: 2026-10-24
- Changes: HMI

## Goal

Try a plugin's own routes (the IO server's `/api/io/leds`, say) from the HMI, without curl and without knowing the
instance's port, while the HMI still knows nothing of any one plugin.

## Now

- A plugin with `routes` in its description has them served under `/api/plugins/{name}/{path}` on its FSP or SO, for
  GET, POST, PUT, PATCH and DELETE (contract: *Plugin routes*). The answer is the plugin's own.
- The Plugins panel's Details shows `Routes: /api/plugins/{name}/`, or `-`, and nothing to call them with.
- The BFF's `/api/execute` passes any method and path to an instance; the HMI's API catalog (`apiService.js`) has no
  entry for plugin routes, and `fillPath` encodes `/` in a path parameter, so `{path}` can't hold `leds/1`.

## Proposal

### HMI

1. In Details, for a plugin with routes, a **Request** line: a method select (GET, POST, PUT, PATCH, DELETE), a path
   field prefixed with `/api/plugins/{name}/`, a separate query field (`on=1&color=red`), a body field (a JSON
   object, in the JsonEditor, shown for POST, PUT and PATCH) and **Send**. The BFF's `/api/execute` takes a body only
   as a JSON object, so an array or a bare value is refused before sending.
2. The answer below it: **OK** with the body pretty-printed when it is JSON, as text otherwise, cut at 20 000
   characters with a note; or **Failed** with the instance's error. The BFF doesn't pass on the plugin's status on
   success, and gives it inside the error text on failure (`404 Client Error: ...`), so there is no separate status.
3. A method other than GET asks first (`window.confirm`): "POST /api/plugins/io/leds may change the plugin's state.
   Send?".
4. The form refuses `POST reload` (and, once there are any, the other reserved names, see the
   [specs README](README.md)): that is the instance's own route, not the plugin's. `GET reload` reaches the plugin,
   as the contract says.
5. One request at a time per panel; the form and last answer per plugin are kept while the page is open (not
   stored).
6. `apiService.js`: an entry `plugin-route` (`/api/plugins/{name}/{path*}`); a `{key*}` parameter is encoded per
   segment, keeping `/`. `executeApiCall` takes `options.method` (instead of the catalog's) and `options.query`.

### FSP, SO, BFF

No change. A failing plugin answer reaches the HMI as the BFF's 500 with the instance's reason, as for other calls;
the HMI shows it as the answer, not as the panel's alert.

## Acceptance

- On a plugin with routes, Details has the Request line; without routes it doesn't.
- `GET leds` with query `on=1` on `io` calls `/api/execute` with `{method: 'GET', path: '/api/plugins/io/leds?on=1'}`
  and shows the answer.
- `leds/1` stays `/api/plugins/io/leds/1`, not `leds%2F1`.
- POST asks first; cancelled, nothing is sent.
- A body that isn't JSON is refused before sending, as in the add form.

## Tests

PluginsPanel.test.jsx: request line shown only with routes; GET sends the call and shows status and body; POST
confirms; nested path kept; invalid JSON body refused; `reload` refused. apiService test: per-segment encoding.

## Docs to update

Wireframe (`design/wireframe.html`, plugins panel: the Request line in the opened io row and the ⓘ text), HMI README
(Plugins panel).

## Open questions

Answered:

- Non-GET requests from the HMI: allowed, after a confirm.
- Query parameters: a separate field.
