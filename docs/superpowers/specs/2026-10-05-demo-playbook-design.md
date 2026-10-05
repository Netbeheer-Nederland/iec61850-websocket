# Demo Playbook in the HMI - design

Date: 2026-10-05 · Status: approved in conversation, spec under review

## Goal

Traffic's **Demo Actions** block becomes **Demo Playbook**. The pinned
one-click buttons stay exactly as they are; on top of them the HMI can:

- **record** a playbook: clicking pinned buttons while recording builds a
  `playbooks/run.py` playbook, step by step;
- **save** it in the BFF, and **load** a saved or built-in playbook
  (including `playbooks/demo.yaml`) - or download / upload it as a file;
- **run** a loaded playbook in the BFF, with the same runner the CLI and the
  integration test use, and see each step's progress (✓ / ✗ and message).

## Decisions

| Question | Decision |
|---|---|
| Pinned buttons | Kept unchanged. A playbook is a recording of clicks on them. |
| File format | The existing run.py playbook YAML - a recording also runs from the CLI and as the integration test, and demo.yaml loads in the HMI. |
| Where a playbook runs | In the BFF, so every step type and expectation works (link, unlink, drop, `reports`, `linked`). |
| Where the runner lives | Moved from `playbooks/run.py` into the BFF package as `bff/playbook.py`; `playbooks/run.py` stays as the CLI. |
| Storage | In the BFF: built-in playbooks from the repo (read-only) plus saved ones on the `bff-config` volume; plus file download / upload in the HMI. |
| Timing in recordings | Not recorded. A recording is the steps in order with `pace: 2s`; `wait` steps can be edited in afterwards. |
| YAML in the HMI | None. The BFF parses and writes all YAML; the HMI exchanges JSON with it (and raw text for upload / download). No YAML dependency in the HMI. |

## Part 1 - BFF

### Runner move

- `examples/rti-demo/playbooks/run.py`'s loading, validation, `control_value`,
  `so_answer`, `BffTransport`, `StepResult`, `Runner` and `parse_duration`
  move to `examples/rti-demo/modules/bff/src/bff/playbook.py`. New in the
  module:
  - `parse_playbook(text: str, fmt: "yaml" | "json") -> dict` - parse + validate
    text (used by `load_playbook` and by the upload endpoint);
  - `dump_playbook(data: dict) -> str` - YAML text, key order kept
    (`name`, `so`, `pace`, `steps`; in a step `label`, the action, `expect`).
  - `Runner` gains a `stop: threading.Event | None` argument: checked before
    each step, and every sleep (`pace`, `wait`, `drop`'s `for`, link polling)
    waits on it instead of `time.sleep`, so Stop interrupts a wait. A stopped
    run ends with the steps not yet run left out of the results.
  - `Runner` gains an `on_step(index, label)` callback, called when a step
    starts, so the HMI can mark it running.
- `playbooks/run.py` keeps `main()` and the CLI unchanged, and re-exports the
  moved names (`from bff.playbook import *`-style explicit imports), so
  `tests/test_playbook.py` and `tests/integration/test_playbook.py` (which load
  `run.py` by path) keep working unchanged.
- `bff` declares `pyyaml` as a dependency (run.py only got it transitively).

### Storage

- **Built-in:** the Dockerfile copies `examples/rti-demo/playbooks/*.yaml` to
  `/app/playbooks/` (env `BFF_PLAYBOOKS_BUILTIN_DIR`, default: the repo's
  `examples/rti-demo/playbooks/` when run from source). Read-only.
- **Saved:** `BFF_PLAYBOOKS_DIR`, default `/config/playbooks/` in compose
  (on the existing `bff-config` volume), created on first save.
- A playbook's **name** is its file name without `.yaml`; names match
  `^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$` (no paths). A saved playbook may not take
  a built-in's name. Saves write atomically (temp file + rename), as
  `connections.json` does.

### Endpoints

| Endpoint | Does |
|---|---|
| `GET /api/playbooks` | `{playbooks: [{name, title, steps, builtin}]}` - `title` is the playbook's `name:` field, `steps` the count. A file that no longer validates is listed with `error` instead of `steps`. |
| `GET /api/playbooks/{name}` | `{name, builtin, playbook, labels}` - the parsed playbook, plus each step's display label as the runner would show it. |
| `GET /api/playbooks/{name}/file` | The YAML text, `Content-Disposition: attachment` (download). |
| `PUT /api/playbooks/{name}` | Body either `{playbook: {...}}` (a recording) or `{text, format: "yaml" \| "json"}` (an upload). Validated with the runner's validation; 400 with its message on a bad playbook or name, 409 on a built-in name. Saved as YAML. |
| `DELETE /api/playbooks/{name}` | Saved ones only (409 for built-in, 404 unknown). |
| `POST /api/playbooks/{name}/run` | Body `{pace?, keep_going?}`. Starts the run in a worker thread; 409 while another run is going. Returns the initial run state. |
| `POST /api/playbooks/run/stop` | Sets the stop event; does nothing when no run is going. |
| `GET /api/playbooks/run` | The current (or last) run state, or `null`. |

### Running

- One run at a time, in a worker thread (`asyncio.to_thread`) - the runner is
  synchronous (`requests`, sleeps).
- The transport is `BffTransport("http://localhost:$PORT")`: every step goes
  through the BFF's own `/api/execute`, the same path an HMI click takes, so
  Traffic shows each call. The playbook's own `bff:` field is ignored here.
- **Run state:**
  `{name, state: "running" | "passed" | "failed" | "stopped" | "error", current, steps: [{index, label, status: "pending" | "running" | "ok" | "failed", message, seconds}], error}`.
  `error` is for a playbook that couldn't run (a `PlaybookError`, e.g. an FSP
  not registered) - run.py's exit code 2.
- Every change (step started, step done, run ended) is broadcast over `/ws`
  as `{type: "playbook-run", data: <run state>}`, from the worker thread via
  `asyncio.run_coroutine_threadsafe(ws_hub.broadcast(...), loop)`.

## Part 2 - HMI

### Layout

The Traffic block's title becomes **Playbook**. Inside: the playbook bar
and step list on top, then `DemoActionsBar` (the pinned buttons) as today.

```
Playbook                                                      ▲
┌──────────────────────────────────────────────────────────────────┐
│ [playbook ▾] [▶ Run] [■ Stop]  [⬇ Download] [⬆ Upload] [🗑]  [● Record] │
│  1 ✓ FSP01 dials the SO · already linked on cp1 (0.1s)           │
│  2 ✓ FSP02 dials the SO · linked: FSP01, FSP02                   │
│  3 ⟳ Reporting off to start with                                 │
│  4 · Read status on both FSPs                                    │
├──────────────────────────────────────────────────────────────────┤
│ All FSPs   [Read status (2)] …                         [Edit]    │
│ FSP01 cp1  [Read status] [Setpoint 50] …                         │
└──────────────────────────────────────────────────────────────────┘
```

### Load and run

- The dropdown lists `GET /api/playbooks`, built-in ones marked, broken ones
  disabled with their error as tooltip. Picking one fetches it and shows its
  steps (number + label, `·` pending). The last picked name is remembered in
  localStorage (a convenience).
- **Run** posts `/run`; disabled while any run is going (also one started from
  another browser). **Stop** posts `/run/stop`, shown while running.
- Step marks follow the run state: `·` pending, spinner running, `✓` / `✗` with
  the message and seconds. The run state comes from `playbook-run` messages on
  the live socket (`services/liveSocket.js`), and from `GET /api/playbooks/run`
  when the page loads - a reloaded or second HMI shows a run in progress. If the
  run is of another playbook than the one shown, the bar switches to it.
- A run ending in `error` shows the error above the step list.
- **Download** opens `/api/playbooks/{name}/file`. **Upload** reads a
  `.yaml` / `.yml` / `.json` file and `PUT`s `{text, format}` under the file's
  base name; a 400 / 409 message is shown next to the bar. **Delete** (saved
  only) asks for confirmation.

### Record

- **● Record** starts a recording: the button turns red (**■ Stop recording**),
  Run / Load are disabled, and the step list shows the recorded steps as they
  are added.
- While recording, every click on a pinned button - including **All FSPs** -
  still runs as today, and also adds one step once it has finished:
  - service → step: `read`, `write`, `operate`, `enable-report`,
    `disable-report`;
  - `label`: the pin's label;
  - `fsp`: the FSP name the bar shows for the row (`fspOf`); for All FSPs a
    list, with `ref` / `rcb` / `value` as a map from FSP name to value where
    the FSPs' values differ;
  - `ref` (or `rcb` for the report services, plus `type` from the pin's
    `rcbType`), `fc`, `value`, `cdc`, and `type` from the pin's `valueType`
    for a write;
  - an operate records the pin's origin `{orCat: 1, orIdent: "0"}`, so replay
    sends what the click sent (run.py's default is `{orCat: 2, orIdent: playbook}`);
  - if the FSP refused the click, the step gets `expect: fail` (replay then
    checks it is refused again); a click that failed for another reason (SO
    unreachable, request error) is not recorded, and a note says so.
- The first recorded click fixes the SO (`so:` = its name). A click on a pin
  for another SO runs but isn't recorded; a note says so (run.py drives one
  SO).
- **■ Stop recording** with no steps just ends it. Otherwise it asks for a
  name (default `recording-YYYYMMDD-HHMM`) and a title, and `PUT`s
  `{playbook: {name: <title>, so, pace: "2s", steps}}`. The saved playbook is
  then the one selected. Cancel discards the recording (after a confirm).

Example step from a pinned read:

```yaml
- label: Read status
  read: {fsp: FSP01, ref: LD0/LLN0.Mod.stVal, fc: st}
```

### Code

- `utils/playbooks.js` - `actionToStep(action, fspName, result)`,
  `groupToStep(actions, fspOf, results)`, and the BFF calls (list, get, save,
  upload, delete, run, stop, run state) through `services/apiService.js`.
- `hooks/usePlaybookRun.js` - the run state: initial `GET`, then
  `playbook-run` socket messages.
- `hooks/usePlaybookRecorder.js` - a page-wide store like `useDemoActions`
  (recording on / off, the SO, the steps), so `DemoActionsBar` and
  `PlaybookBar` share it.
- `components/PlaybookBar.jsx` - the bar and step list.
- `components/DemoActionsBar.jsx` - after a click's results are in, reports
  them to the recorder (single button: one action; All FSPs: the group).
  Otherwise unchanged.
- `pages/Traffic.jsx` - block title and `PlaybookBar` above `DemoActionsBar`.

## Docs

- `docs/rti-demo/includes/hmi.adoc` - the Demo Playbook block: recording,
  load / run, storage.
- `examples/rti-demo/playbooks/README.md` - running from the HMI, where saved
  playbooks live, that a recording is a regular playbook.
- `modules/bff/README.md` - the playbook endpoints and the two env vars.

## Testing

- **BFF unit tests** (`modules/bff/tests`): list (built-in + saved, broken
  file), get, file download, put (recording, YAML / JSON upload, bad playbook
  400, bad name 400, built-in name 409), delete (saved, built-in 409), run
  (state transitions, 409 while running, stop interrupts a wait, `error` on a
  `PlaybookError`) - with a fake transport and temp dirs.
- **Runner**: `tests/test_playbook.py` passes unchanged after the move; new
  cases for `stop` and `on_step`, `parse_playbook` / `dump_playbook`
  round-trip.
- **HMI (vitest)**: `actionToStep` / `groupToStep` for every service, per-FSP
  maps, refused → `expect: fail`; `PlaybookBar` load / run / progress / error /
  upload error with API and socket mocked; recording through `DemoActionsBar`
  clicks, other-SO note, save; existing `DemoActionsBar` and `Traffic` tests
  pass.
- **Integration**: `demo.yaml` run through `POST /api/playbooks/demo/run`
  against the stack, polled to `passed`.

## Out of scope

- Editing a playbook's steps in the HMI (edit the YAML and upload it).
- Recording timing, and recording anything other than pinned-button clicks
  (link / drop are written by hand).
- Running more than one playbook at a time, or one playbook against several
  SOs.
