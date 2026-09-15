# Running the Test Suite

This is a step-by-step guide for running rti-demo's test suites, written for
someone new to this codebase. It covers the backend (Python/pytest) and the
HMI frontend (JavaScript/vitest) separately, since they're two independent
projects with their own dependencies.

## Overview

| Suite | Location | Tool | Command |
|-------|----------|------|---------|
| Backend unit tests | `tests/unit/` | pytest (via `uv`) | `uv run pytest tests/unit -m unit -q` |
| Backend integration tests | `tests/unit/`, `tests/integration/` | pytest (via `uv`) | requires live Docker containers - see [Integration tests](#integration-tests-docker-required) |
| Frontend unit tests | `hmi/src/**/*.test.{js,jsx}` | vitest (via `npm`) | `npm test` (from `hmi/`) |
| Frontend build check | `hmi/` | vite | `npx vite build` (from `hmi/`) |

As of this writing, the backend unit suite has 79 passing tests and the
frontend suite has 21. If your numbers are close to that after a clean
checkout, you're in a good state.

## Prerequisites

- **[uv](https://docs.astral.sh/uv/)** for the Python backend. If you don't
  have it: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Node.js + npm** for the HMI frontend (any reasonably recent Node 18+
  should work).
- Docker is only needed if you want to run the *integration* tests, not the
  unit tests covered by the commands below.

You do **not** need to manually create a Python virtualenv or run `pip
install` anywhere - `uv` manages an isolated environment per project
automatically the first time you run `uv sync` or `uv run ...`.

## Backend: Python unit tests

All commands in this section are run from `examples/rti-demo/` (this
directory - the one this file lives in).

### 1. Install dependencies

```bash
cd examples/rti-demo
uv sync
```

This creates/updates `.venv` inside `examples/rti-demo` and installs
everything listed in `pyproject.toml`, including the `pytest` /
`pytest-asyncio` dev dependencies.

### 2. Run the unit tests

```bash
uv run pytest tests/unit -m unit -q
```

The `-m unit` flag matters: this project defines two pytest markers,
`unit` (fast, fully isolated - no network, no Docker) and `integration`
(needs live Docker containers). Without `-m unit`, you'll also pick up
integration tests that fail loudly with connection-refused errors on a
machine with nothing running - that's expected, not a regression.

Expected output ends with something like:

```
79 passed, 22 deselected in ~3s
```

The "22 deselected" are the integration tests being correctly skipped by
the marker filter.

You'll see a `warning: VIRTUAL_ENV=... does not match the project
environment path` line from `uv` if you have a *different* project's
virtualenv active in your shell (e.g. the repo root's). It's harmless -
`uv` still uses the correct `examples/rti-demo/.venv` - but if it bothers
you, `deactivate` first or run `uv run --active pytest ...` instead.

You'll also see a lot of stdout noise (`serve_kwargs: ...`,
`the scheme is: ws`) from the `so` (ACSI client) tests - those tests
exercise the real `connect()` code path, which really does spin up a
background WebSocket server/thread. That's expected and harmless; the
threads are daemon threads and don't block the test run or leak into
other tests.

### 3. Run one file, or one test, while iterating

```bash
# One file
uv run pytest tests/unit/bff/test_push_relay.py -m unit -q

# One test by name (substring match)
uv run pytest tests/unit -m unit -k readvalue -q

# Full tracebacks instead of the default one-liners
uv run pytest tests/unit -m unit -q --tb=short
```

### Where things live

```
tests/
├── conftest.py                    # shared setup - see "Why does this work?" below
└── unit/
    ├── bff/test_push_relay.py     # bff/bff_server.py's WebSocket push relay
    ├── bff/test_bff_endpoint.py   # older, Docker-only integration tests for the BFF
    ├── fsp/test_bff_endpoint.py   # fsp/bff_endpoint.py (the IEC 61850 "server" role)
    └── so/test_bff_endpoint.py    # so/bff_endpoint.py (the IEC 61850 "client" role)
```

`fsp` and `so` are each tested through a `fastapi.testclient.TestClient`
wrapping the real FastAPI router from `fsp/bff_endpoint.py` /
`so/bff_endpoint.py` - no mocking of the HTTP layer, just of a few
IEC 61850-specific internals (e.g. `server.read_value`) where actually
talking to hardware/a real server would be needed otherwise.

### Why does this work? (background, not required reading)

Two things make the backend unit tests possible without pulling in the
whole rest of the monorepo:

1. **`ws61850` import.** `fsp/acsi_server.py` and `so/acsi_client.py` import
   the core `ws61850` library, which lives at the repo root's `src/`, not
   inside `examples/rti-demo`. Rather than making `examples/rti-demo` (its
   own separate `uv` project, with its own `pyproject.toml`/`uv.lock`)
   depend on the root project - which turned out to need reconciling
   several mutually-incompatible pinned versions between the two - the
   repo root's `src/` directory is added to `sys.path` in
   `tests/conftest.py`.

2. **Module name collision.** `fsp/bff_endpoint.py` and
   `so/bff_endpoint.py` are both literally named `bff_endpoint.py`. A plain
   `import bff_endpoint` from each test file would cache under the same
   `sys.modules["bff_endpoint"]` key, so whichever file's tests ran first
   would "win" and the other file would silently get handed the wrong
   module when the whole suite ran together. `tests/conftest.py` exposes
   `import_module_from_path()`, which each test file uses to load its own
   `bff_endpoint.py` under a distinct name (`fsp_bff_endpoint` /
   `so_bff_endpoint`).

You don't need to do anything for either of these - they're already wired
up in `tests/conftest.py` and the two test files. It's here so that if you
ever see an `AttributeError` or a test behaving as if it's calling the
*other* service's code, you know where to look.

### Integration tests (Docker required)

`tests/unit/bff/test_bff_endpoint.py` and the tests under
`tests/integration/` talk to real, running BFF/FSP/SO instances. To run
those:

```bash
cd examples/rti-demo
docker compose -f demo_setup/docker-compose.yml up -d   # or your compose file of choice
uv run pytest tests/unit -m integration -q
```

If you don't have Docker running, skip this section entirely - `-m unit`
(above) never touches it.

## Frontend: HMI unit tests

All commands in this section are run from `examples/rti-demo/hmi/`.

### 1. Install dependencies

```bash
cd examples/rti-demo/hmi
npm ci
```

(`npm ci` rather than `npm install` - it installs exactly what's in
`package-lock.json`, which is what you want for reproducing CI/other
people's results.)

### 2. Run the tests

```bash
npm test
```

This runs vitest once (not in watch mode) against every `*.test.js` /
`*.test.jsx` file under `src/`. Expected output ends with:

```
Test Files  2 passed (2)
     Tests  21 passed (21)
```

You'll see some `Warning: An update to MessageMonitor inside a test was
not wrapped in act(...)` noise in stderr from one of the test files - it's
a benign React Testing Library warning (an async state update finishing
just after its `act()` wrapper closed), not a failing assertion. The test
summary line is the source of truth.

To keep vitest running and re-run on file changes while you work:

```bash
npm run test:watch
```

### Where things live

```
hmi/src/
├── services/liveSocket.js         # the WebSocket push client
├── services/liveSocket.test.js
├── components/MessageMonitor.jsx  # push/fallback-polling live-message viewer
├── components/MessageMonitor.test.jsx
└── setupTests.js                  # vitest + @testing-library/jest-dom wiring
```

### 3. Verify the production build still works

Tests passing doesn't guarantee the app still *builds* - always check this
too, especially after touching anything outside a `*.test.*` file:

```bash
npx vite build
```

A clean run ends with a `dist/` output summary and no errors (two
pre-existing warnings - a duplicate `case` clause in `Header.jsx` and a
CSS-comment-syntax warning during minification - are expected and
unrelated to your changes). Clean up the output afterwards, since `dist/`
isn't meant to be committed:

```bash
rm -rf dist
```

## Running everything in one go

```bash
# From examples/rti-demo/
(cd . && uv run pytest tests/unit -m unit -q) \
  && (cd hmi && npm test) \
  && (cd hmi && npx vite build && rm -rf dist)
```

If all three steps print a passing summary with no errors, the codebase is
in a clean, verified state.
