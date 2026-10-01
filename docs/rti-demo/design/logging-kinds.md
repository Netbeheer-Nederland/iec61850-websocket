# rti-demo logging: system, WebSocket and ACSI service logs

Status: **in progress** (2026-10-01) - phases 1-2 implemented; see Phasing.

Goal: make the three kinds of log entry the SO/FSP produce - **system**,
**WebSocket** and **ACSI service** - distinguishable at the source, and give
each a clear place in the HMI, so a user can answer "what's on the wire",
"what is this instance doing" and "is the system healthy" without digging
through one mixed list.

---

## Current state

Each SO and FSP keeps two in-memory logs, exposed over its own REST API:

| Log | Endpoint | Written by | Shape | Shown in HMI |
|---|---|---|---|---|
| **Messages** | `GET /api/messages` | `_log_message()` from the endpoint's send/recv callbacks (`so/acsi_client.py`, `fsp/acsi_server.py`) | `{id, timestamp, direction, service_type, category, message, preview, cp}` - one raw WebSocket frame each; `category` is request / response / associate / unknown | Traffic's per-instance message monitors (`MessageMonitor.jsx`), pushed live by the BFF (`push_relay_loop`) |
| **Actions** | `GET /api/actions-logs` | `_log_action(message, level, detail)` - ~150 call sites across `so/bff_endpoint.py`, `so/acsi_client.py`, `fsp/bff_endpoint.py`, `fsp/acsi_server.py` | `{id, time, level, message, detail}`; `level` is debug / info / warn / error | ACSI Client / ACSI Server "Monitoring" panel (`ActionLogPanel.jsx`), polled every 5s |

Both are `deque`s (messages `maxlen=500`, actions `maxlen=200`) and are lost on
restart. Separately, every module writes Python `logging` output to its
container's stdout, which the HMI never shows.

The problem is the **actions** log: it mixes two different things in one
free-text list. A freshly restarted SO, after one read, looks like this:

```
 1 info  Connection initiated                                  <- system
 3 debug Reconfig connection request: connection=SO, ...       <- system
 6 debug Reconfiguring passive endpoint with TLS               <- system
12 info  Connection reconfigured: enable_tls=True              <- system
13 info  Readvalue request: objRef=LD0/LLN0.Mod.stVal, fc=st   <- ACSI service
14 info  Client readvalue                                      <- ACSI service
```

Consequences:

- ACSI service activity is buried among lifecycle/TLS/OAuth/model-reload
  events, and the only way to tell them apart is reading the text.
- A read/write aimed directly at an FSP is local model access - it produces no
  WebSocket frame, so it never appears on Traffic, only as an action-log line
  on the ACSI Server page.
- The WebSocket log itself is fine (and since `553bd00` it records the SO's
  outgoing requests too), but nothing links a frame to the service call it
  belongs to.

---

## Proposal

### Three kinds

| Kind | Scope | Examples |
|---|---|---|
| **system** | Instance lifecycle and configuration - not about any one service call | startup/shutdown, endpoint start/stop, connect/disconnect handling, TLS/OAuth reconfiguration, model build/hot-swap, unexpected exceptions |
| **websocket** | Transport - what actually went over the wire | raw request/response/report frames, associate handshake |
| **acsi** | One entry per ACSI service call, **whether or not it crossed the wire** | `GetDataValues LD0/LLN0.Mod.stVal [ST] -> 0`, `SetDataValues ... failed: ...`, `Operate rejected: missing value` |

Rule of thumb: if the entry would still make sense with no WebSocket at all,
it's **acsi** (a service) or **system** (everything else); if it *is* the
WebSocket traffic, it's **websocket**.

### Tag at the source, not by text matching

- Add a `kind` argument to `_log_action(message, level, detail, kind)` -
  `"system"` or `"acsi"` - and set it explicitly at every call site. No
  default that silently guesses: a missing `kind` should be a test failure,
  so new call sites can't drift into the wrong bucket.
- `_log_message()` entries are `kind: "websocket"` by construction.
- Do **not** classify by matching message strings in the BFF or HMI - it
  breaks the moment someone rewords a message.

### Common fields

Every entry, in either log, carries:

| Field | Notes |
|---|---|
| `id` | per-log monotonic sequence, as today |
| `time` | as today (unify `time` / `timestamp` naming while touching this) |
| `kind` | `system` / `websocket` / `acsi` |
| `level` | debug / info / warn / error (websocket frames: `info`, or `error` for a negative response) |
| `cp` | connection point, when there is one |
| `service` | ACSI service name (`getDataValues`, ...) - acsi and websocket only |
| `correlation` | links an acsi entry to its websocket frames - see below |

### Storage

Keep **two stores**:

- `messages` stays the websocket log - high volume, large raw payloads, already
  pushed live.
- `actions` holds system + acsi, now distinguishable by `kind`.

Merging everything into one store would let a burst of frames evict the
(much rarer) system and acsi entries from a single bounded deque. If system
noise later turns out to evict acsi entries within `actions`, split it per kind
then.

### Linking a service call to its frames

An acsi entry made through the SO should expand to show the request/response
frames it produced. The natural key is `(cp, invokeId)`, which every frame
carries. **Caveat:** in the frames captured while writing this note, the
request and response both had `invokeId: 0` - so either the demo reuses
invoke ids, or the key needs something else (e.g. the acsi entry recording the
frame `id`s it sent/received). Verify before relying on it - see Open
questions.

A local FSP read/write simply has no linked frames - it still gets a proper
acsi entry, which is how it finally shows up next to SO-driven reads instead
of nowhere useful.

---

## Where each kind is shown

Each page answers one question:

| Page | Question | Shows |
|---|---|---|
| **Traffic** (all instances) | What's happening between SO and FSPs? | **websocket + acsi**, per-instance cards as today, with kind filter chips. acsi entries expand to their linked frames. This is where reads/writes belong. |
| **ACSI Client / ACSI Server** (one instance) | What is this instance doing, and why did it fail? | **system + acsi** for that instance - the existing Monitoring panel, with a kind filter next to the existing level filter. |
| **Diagnostics** (new nav entry) | Is the system healthy? | **system** across all instances, plus the BFF's own events (health checks, TLS/OAuth re-sync failures from `connection_manager.status_monitor`). Warnings/errors first. |

`pages/Diagnostics.jsx` already exists as an unused 66-line placeholder with
no sidebar entry - reuse it rather than adding a new route.

Container stdout (Python `logging`) stays out of the HMI - it's for
developers, via `docker logs`.

### Visual differentiation

- **Kind** gets an icon + text label on each row (e.g. `fa-gear` System,
  `fa-plug` WebSocket, `fa-cubes` ACSI) and as filter chips.
- **Level** keeps its existing color coding.
- Don't encode kind with color: color already means level, and the style
  guide reserves status color for ok / not-ok (`style-guide.md`, Status
  indicators). Two independent channels - icon for kind, color for level -
  keep both readable at a glance.

---

## Phasing

Each phase is its own commit (or small series), verified before the next.

1. **(done)** **Tag `kind` on the actions log.** Add the `kind` argument, set it at all
   ~150 `_log_action` call sites (SO + FSP), add `kind: "websocket"` to
   `_log_message` entries, and add a kind filter to `ActionLogPanel`. Most of
   the value for the least change - the ACSI Client/Server panels can already
   separate system from service activity.
2. **(done)** **acsi entries on Traffic.** Have the BFF relay actions with
   `kind: "acsi"` the same way it relays messages, and show them in Traffic's
   monitors alongside frames, with kind chips.
3. **Correlation.** Settle the `invokeId` question, record the link, and let
   acsi rows on Traffic expand to their frames.
4. **Diagnostics page.** Wire `Diagnostics.jsx` into the sidebar with system
   entries from all instances plus BFF events.
5. Update `hmi.adoc` and `wireframe.html` alongside each phase that changes
   what a page shows.

---

## Open questions

- **invokeId uniqueness** - captured frames showed `invokeId: 0` on both request
  and response. Does the client increment it per call, per cp, or never? If
  not unique, correlate by recorded frame ids instead.
- **Debug level** - the SO logs a lot of `debug` system entries on TLS/OAuth
  reconfiguration. Hide debug by default in the panels?
- **Retention** - both logs are in-memory and bounded. Is "since last
  restart, last N entries" enough for a demo, or should system/acsi entries be
  persisted (e.g. for the Diagnostics page)?
- **BFF events** - does the BFF need its own small actions log for the
  Diagnostics page, or should it only aggregate the instances' system entries?
