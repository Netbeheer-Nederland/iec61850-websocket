<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# RTI HMI - React Frontend

The React-based HMI (Human Machine Interface) of the RTI demo: a web interface for monitoring and controlling the RTI
services (RTI-SO and RTI-FSP). It talks only to the BFF (`examples/rti-demo/modules/bff`).

## Contents

1. [Run it](#run-it)
2. [Technology stack](#technology-stack)
3. [Pages](#pages)
4. [Source layout](#source-layout)
5. [Talking to the BFF](#talking-to-the-bff)
6. [Browser support](#browser-support)

## Run it

```bash
cd examples/rti-demo/modules/hmi
npm install
npm run dev          # development server on http://localhost:3000
npm test             # unit tests (vitest)
npm run build        # production build in dist/
npm run preview      # serve the production build
```

With Docker, `docker compose up -d rti-hmi` from `examples/rti-demo` serves the production build with nginx on
http://localhost:3001 (`docker/Dockerfile`, `nginx.conf`).

### BFF address

The HMI calls the BFF directly from the browser, so the address must be one the user's browser can reach (an IP
address or host name, not a container name such as `rti-bff`). The first that is set wins:

1. **Settings page** - saved per browser in localStorage; overrides everything below. Clear the site data to go back
   to the configured default.
2. **Runtime (Docker)** - `BFF_HOST` / `BFF_PORT` on the `rti-hmi` container. At start-up
   `docker/40-rti-config.sh` writes them to `/config.js`, so one image serves any setup. With
   `examples/rti-demo/docker-compose.yml`, set `HMI_BFF_HOST` / `HMI_BFF_PORT` in the shell or in
   `examples/rti-demo/.env`.
3. **Build time** - `VITE_BFF_HOST` / `VITE_BFF_PORT`, baked into the bundle by Vite: in `modules/hmi/.env.local` for
   `npm run dev`, or as Docker build args (`--build-arg VITE_BFF_HOST=...`; compose passes them through).
4. **Built-in** - `localhost:5000`.

```bash
# development server against a BFF on another machine
echo 'VITE_BFF_HOST=192.168.100.10' > .env.local
npm run dev

# Docker: same image, address chosen when the container starts
HMI_BFF_HOST=192.168.100.10 HMI_BFF_PORT=5000 docker compose up -d rti-hmi
```

`src/config.js` resolves the default; `public/config.js` is the empty runtime configuration outside Docker.

## Technology stack

- React 19 with functional components and hooks
- React Router 7 for client-side navigation
- Vite 8 for the development server and production build; Vitest for tests
- State in React hooks and context; settings, pinned demo actions and monitor states in localStorage
- A WebSocket to the BFF (`/ws`, `src/services/liveSocket.js`) for live pushes: connections, actions, playbook runs

## Pages

| Route | File | Purpose |
|---|---|---|
| `/overview` (default) | `Overview.jsx` | Live, read-only status overview - SO/FSP graphic |
| `/acsi-client` | `ACSIClient.jsx` | SO interface, tree view, controls |
| `/acsi-server` | `ACSIServer.jsx` | FSP interface, tree view, data write |
| `/connections` | `Connections.jsx` | Register, edit and delete instances |
| `/model` | `Model.jsx` | IEC 61850 model viewer, SCL upload |
| `/traffic` | `Traffic.jsx` | Traffic monitoring, timeline, demo buttons and playbooks |
| `/data` | `Data.jsx` | Simple data visualization (placeholder) |
| `/tools` | `Tools.jsx` | SCL Model Factory, XML parsing |
| `/reports` | `Reports.jsx` | Reports and logging (placeholder) |
| `/diagnostics` | `Diagnostics.jsx` | System log across the BFF and all instances |
| `/settings` | `Settings.jsx` | BFF configuration |

`/` and unknown routes redirect to `/overview`.

### Overview (`/overview`)
**File**: `src/pages/Overview.jsx`

**Purpose**: Default landing page showing live status of all registered instances as a graphic - read-only. The instance table, and registering, editing and deleting instances, all live on the Connections page instead.

**Features**:
* Visual instance visualization (InstanceVisualization) showing SO, FSP, and their connections
* SO circle turns green and shows a live badge counting its connected FSPs (connectedFsps > 0)
* No instance table - when nothing is registered, an empty-state hint points to the Connections page
* Updates live from the BFF's connections push - no manual refresh button
* Default route (redirects from `/`)

### ACSI Client (`/acsi-client`)
**File**: `src/pages/ACSIClient.jsx`

**Purpose**: Interface for ACSI-Client (RTI-SO) operations - acts as a client connecting to external servers.

**Features**:
* WebSocket connection management (host, port, CP)
* IEC 61850 data model tree visualization
* Context menu for right-click operations on data objects
* Control operations (for controllable CDC types: SPC, DPC, APC, INC, ENC, BSC, ING, ASG, CTE, ENG)
* Data write operations via modal dialog
* BRCB (Buffered Report Control Block) configuration
* TLS configuration support
* OAuth authentication integration
* Monitoring panel's Activity Log (the instance's actions log) - each entry labelled System or ACSI (service call), filterable by kind and by severity; an ACSI entry made through the SO also names the WebSocket frame range it produced (shown under the call on Traffic); Start/Stop is remembered per instance (localStorage), so monitoring left on resumes after switching pages
* Real-time data updates

### ACSI Server (`/acsi-server`)
**File**: `src/pages/ACSIServer.jsx`

**Purpose**: Interface for ACSI-Server (RTI-FSP) operations - acts as a server providing the IEC 61850 data model.

**Features**:
* Server configuration (host, port, CP, mode)
* IEC 61850 data model tree visualization with expandable nodes
* Data write operations with value modification
* Tree expansion state persistence
* TLS configuration support
* OAuth authentication integration
* Monitoring panel's Activity Log (the instance's actions log) - each entry labelled System or ACSI (service call), filterable by kind and by severity; an ACSI entry made through the SO also names the WebSocket frame range it produced (shown under the call on Traffic); Start/Stop is remembered per instance (localStorage), so monitoring left on resumes after switching pages
* Status information display

### Connections (`/connections`)
**File**: `src/pages/Connections.jsx`

**Purpose**: The only place that lists instances in a table, and the only place to register, edit or delete one - Overview only shows the live graphic.

**Features**:
* List all configured connections in a sortable table format, with a Connected/Disconnected status badge per row (green when connected, red when disconnected)
* Register new instances via the shared ConnectionModal dialog (same modal ACSI Client/Server's own Edit flow doesn't use - this is the only entry point)
* Edit existing instances
* Delete instances (with confirmation)
* Connection type selection (RTI-SO, RTI-FSP, IDP-Server, Custom)
* ACSI role / WebSocket mode fixed automatically by type (Custom stays editable)
* List updates live from the BFF's connections push - no manual refresh button
* Saves go straight to the BFF (POST /api/add-connection, PUT /api/edit-connection/:name, DELETE /api/delete-connection/:name) - not just local/localStorage state

### Model (`/model`)
**File**: `src/pages/Model.jsx`

**Purpose**: IEC 61850 model visualization and management page.

**Features**:
* Connection selection for model loading
* IEC 61850 data model tree display
* SCL file upload for model generation
* Model persistence and retrieval
* Tree expansion state management
* Visual instance connection graph, updated live from the BFF's connections push (no manual refresh button)
* Model upload status tracking

### Traffic (`/traffic`)
**File**: `src/pages/Traffic.jsx`

**Purpose**: Traffic monitoring and data access dashboard.

**Features**:
* Visual instance visualization showing all SO, FSP, and their connections
* Live link activity on each SO-FSP line, counted from that FSP's own frames (pushed by the BFF whether or not a monitor is running): its cp, a dot per frame batch travelling towards the FSP (request) or back (response, report), request / response / report / error counters and the last service with its result and time; the line turns red while the last service failed. Reset counters zeroes them
* Only instances the BFF can reach are drawn - an SO or FSP it can't reach is left out of the topology, and an FSP it can't reach only keeps a timeline lane while the timeline still holds rows for it (one that dropped mid-demo; a stale entry gets none). An FSP the BFF reaches but whose WebSocket to the SO is closed stays on the picture, its line red with an X, "link down" and how long it has been so; its timeline lane, demo buttons row (buttons disabled) and report values (last known values, dimmed) carry a "link down" or "unreachable" badge. The timeline gets a row when a link goes down, becomes unreachable and comes back up ("link back up after 42s"), timed by the browser's clock; the "Links" filter hides them. Changes are seen through the BFF's connection checks, and only while Traffic is open
* Clicking an FSP focuses its link - the other links dim and only that FSP's message monitor is listed (the SO's stays); clicking it again, the SO, or Show all shows every link again. On Traffic the circles focus instead of opening the ACSI Client/Server pages
* Report Values (received by the SO) - per FSP, the latest value of every data attribute the reports the SO received carried (rptID, time), with the values the newest report changed highlighted. Read from the SO's own frame log - a report frame's cp (its `associateId`) says which FSP it came from. Shares the timeline's entries, so its Stop / Clear apply here too; focusing an FSP narrows it. BER-encoded reports are counted but not decoded
* Playbook - a bar above the demo buttons row: pick a built-in or saved playbook, Run it in the BFF with a ✓ / ✗ mark per step as it goes, Stop the run (a wait or drop in progress ends at once), Download / Upload a playbook file, and Delete a saved one. Record turns clicks on the demo buttons, including an **All FSPs** click, into playbook steps as they happen - a refusal (the button's failed mark) is kept as a step with `expect: fail`; a click that didn't get through to its SO, or one on an SO other than the recording's, isn't recorded, with a note saying so. Stop recording asks for a name and title, then saves the playbook in the BFF with `pace: 2s`. Any other open HMI follows a run live over the WebSocket, the same way it sees this one's. The demo buttons themselves: one-click buttons for a demo, a row per FSP. Each is an SO service call (Read, Write or Operate on one data object) pinned from a Data Access Panel on the SO endpoint with **Pin as demo action**, under the FSP behind the panel's cp. **Enable report** and **Disable report** are pinned the same way from the ACSI Client page's RCB Configure dialog; they read the RCB and write its own configuration back with rptEna on / off (the SO resets any field a write leaves out), and leave an RCB already in that state alone - two calls on the timeline (Get / Set BRCB or URCB values). Actions on different FSPs with the same label also get an **All FSPs** button that runs them all at once - each FSP keeps its own data object, since the FSPs' models differ. Each button shows a running / ok / failed mark (the reason in its tooltip) and is disabled while its SO or cp isn't connected; Edit unpins. Saved in this browser (localStorage). Once any are pinned, the Data Access Panels start collapsed
* Timeline - every SO-FSP exchange merged into one list, drawn as a sequence diagram (a lane per SO and FSP, with the FSP's cp): an ACSI call the SO made is an arrow from the SO to the FSP it went to (service, ok / failed / no response, SO and FSP frame counts), a report an arrow back, a read/write an FSP served on its own a box in its lane. Clicking a row shows the call's frames on both ends side by side. Calls are paired with their frames by ids, not clocks: the SO's frames by the call's correlation (messageSeqFrom..To on its cp), the FSP's by the same cp + invokeId. A run of reports with nothing else between them shows as one row per FSP and report ID ("report Events1 ×21", its first and last time and the average spacing; expanding it shows the newest 50 frames), so a 1 s integrity report doesn't push the rest off. Newest first; Calls / Reports / Local filters; focusing an FSP (topology or lane header) narrows it to that FSP. Runs by default - Stop is remembered (localStorage); Clear empties only the timeline, not the instances' logs
* Multiple collapsible Data Access Panels, with **Pin as demo action** on an SO endpoint
* Dynamic panel management (add/remove)
* Per-instance message monitors (collapsed by default - the timeline shows the same traffic merged)
* Real-time message monitoring, newest-first by default with a toggle for oldest-first (same control as the Monitoring panels' Activity Log)
* Each message monitor's Start/Stop is remembered per instance (host:port, localStorage), so monitoring left on resumes after switching pages
* Each message monitor shows two kinds of entry, each with a kind badge and a kind filter (All / WebSocket / ACSI): WebSocket frames (the instance's message log) and ACSI service entries (the kind "acsi" part of its actions log, pushed live by the BFF as `actions` events). A read/write through an SO shows up as its frames on both the SO and the FSP; a read/write aimed directly at an FSP is local model access with no frames, so it shows up as an ACSI entry on that FSP's monitor. Each ACSI call made through the SO is one entry (e.g. `GetDataValues LD0/LLN0.Mod.stVal [ST] - ok`, level from the response: serviceError = error, none = warn) linked to the frames it produced - the row shows their count, and expanding it lists them. System entries stay on the ACSI Client/Server pages. Clear empties the monitor and the instance's frame log, but leaves its actions log (and so the Activity Log) alone
* FSP message monitors only shown for FSPs with an active connection (connectedClients > 0), same threshold used to light up the instance visualization above
* Connection health monitoring
* Instance visualization updates live from the BFF's connections push - no manual refresh button

### Data (`/data`)
**File**: `src/pages/Data.jsx`

**Purpose**: Data visualization and display page.

**Features**:
* Simple data display interface
* Placeholder for data visualization components

### Tools (`/tools`)
**File**: `src/pages/Tools.jsx`

**Purpose**: Utility tools for SCL file processing and model generation.

**Features**:
* **SCL Model Factory**: Parse SCL (Substation Configuration Language) XML files
  - File upload and validation
  - IED (Intelligent Electronic Device) extraction
  - AccessPoint extraction
  - Model tree generation
  - Python code generation for RTI-FSP models
* File size display
* Parse error handling
* Model preview

### Reports (`/reports`)
**File**: `src/pages/Reports.jsx`

**Purpose**: Reports and logging page.

**Features**:
* Simple reports interface
* Placeholder for reporting functionality

### Diagnostics (`/diagnostics`)
**File**: `src/pages/Diagnostics.jsx`

**Purpose**: "Is the system healthy?" - the system log across the whole demo, reachable from the sidebar.

**Features**:
* Reads the BFF's `GET /api/diagnostics`: the BFF's own events (an instance coming up or dropping, TLS/OAuth re-apply results, the startup IDP check) merged with every reachable RTI-SO/RTI-FSP's System entries
* Errors and warnings first, then newest first; header counts errors/warnings
* Source filter (BFF or an instance) and severity filter - debug hidden by default ("All but debug"), "Errors & warnings", "All levels"
* BFF events name the instance they concern
* Re-read every 5s while the page is open - no refresh button
* ACSI service and WebSocket entries are on Traffic, not here

### Settings (`/settings`)
**File**: `src/pages/Settings.jsx`

**Purpose**: Application configuration and settings management.

**Features**:
* BFF server configuration (host, port)
* Settings persistence using localStorage
* Form validation
* Default settings management
* Connection to BFF health check

## Source layout

```
src/
├── App.jsx, main.jsx        # routes, connections state, live socket wiring
├── config.js                # default BFF address (runtime config, VITE_BFF_*, localhost:5000)
├── pages/                   # one component per route (see Pages)
├── components/              # shared UI: Tree, modals (Connection, TLS, OAuth, BRCB, Control, WriteValue),
│                            # DataAccessPanel, MessageMonitor, ActionLogPanel, InstanceVisualization,
│                            # TrafficTimeline, ReportValues, DemoActionsBar, PlaybookBar, Sidebar, Header
├── hooks/                   # Traffic state: useTrafficTimeline, useLinkActivity, useFspPresence,
│                            # useDemoActions, usePlaybookRun, usePlaybookRecorder, persistent flags
├── services/                # apiService.js (BFF REST), liveSocket.js (BFF WebSocket)
├── utils/                   # sclParser.js, modelUtils.js, timeline.js, reports.js, fspLinks.js,
│                            # demoActions.js, playbooks.js
└── assets/styles.css
```

Tests sit next to the code they cover (`*.test.jsx`, `*.test.js`).

`utils/sclParser.js` parses SCL (Substation Configuration Language) XML and generates the Python `model.py` used by an
RTI-FSP (`generateModelPyCode(sclContent, options)`); the Tools page uses it. `utils/modelUtils.js` turns model data into
the tree the pages display (`transformModelToTree(modelData)`).

## Talking to the BFF

* Frontend communicates exclusively with BFF server
* BFF host and port configurable via Settings page
* All configuration persisted in browser localStorage
* Connection management centralized and shared across all pages
* Connections list is live: App.jsx fetches `/api/connections` once for first paint, then applies the BFF's `connections` pushes over `/ws` (sent only when the list changes, checked every 2s). It refetches whenever that socket (re)connects, so changes missed while it was down still show up - no page has a manual refresh button for connections
* API endpoints defined in apiService.js, executed through /api/execute BFF endpoint

The HMI makes two kinds of call, both to the BFF:

1. **The BFF's own API**, called directly: `/api/health`, `/api/connections` (plus `add-connection`,
   `edit-connection/{name}`, `delete-connection/{name}` and the per-connection TLS and OAuth settings),
   `/api/diagnostics`, `/api/playbooks/...`, `/api/idp/discovery`, and the `/ws` push channel.
2. **Calls on an SO or FSP instance**, sent as `POST /api/execute` with `{ target, method, path, body }`. The BFF
   forwards the request to the instance at `target` (`host:port`). The instance paths are listed in `API_DEFINITIONS`
   in `src/services/apiService.js`: read, write, select and operate, model tree, data definition, dataset directory,
   BRCB/URCB read and write, start and stop (FSP), actions and message logs, TLS and OAuth reconfiguration, and
   properties.

The OpenAPI docs list every endpoint: BFF at http://localhost:5000/docs, FSP at http://localhost:5001/docs, SO at
http://localhost:5002/docs.

`src/services/apiService.js` exports:

- `executeApiCall(apiId, targetValue, bodyOverride, options)` - run an `API_DEFINITIONS` entry through `/api/execute`
  (or directly, with `options.useDirect`)
- `getApiById(id)` - look up an `API_DEFINITIONS` entry
- `getBffBaseUrl()` - BFF URL from the Settings (localStorage), default `http://localhost:5000`
- `buildBffApiUrl(path, targetValue)` - full BFF URL for a path
- `ensureBffHealthy()` - check that the BFF answers
- `getAutoRefreshIntervalMs()` - polling interval from the Settings, default 5000 ms
- `buildTargetValue(host, port)`, `getDefaultTargetFromEndpoint(endpoint)` - build the `target` of an execute call

## Browser support

Current Chrome (recommended), Firefox, Edge and Safari. The HMI needs ES modules and async/await.
