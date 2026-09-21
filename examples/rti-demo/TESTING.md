# Running the Test Suite

This is a step-by-step guide for running rti-demo's test suites, written for
someone new to this codebase. It covers the backend (Python/pytest) and the
HMI frontend (JavaScript/vitest) separately, since they're two independent
projects with their own dependencies.

## Overview

| Suite | Location | Tool | Command |
|-------|----------|------|---------|
| Backend unit tests | `modules/{bff,fsp,so}/tests/` | pytest (via `uv`) | `uv run --package so pytest modules/so/tests -m unit -q` (repeat per module, or see below) |
| Backend integration tests | `tests/integration/` | pytest (via `uv`) | requires live Docker containers - see [Integration tests](#integration-tests-docker-required) |
| Frontend unit tests | `hmi/src/**/*.test.{js,jsx}` | vitest (via `npm`) | `npm test` (from `hmi/`) |
| Frontend build check | `hmi/` | vite | `npx vite build` (from `hmi/`) |

`bff`, `fsp` and `so` are each their own package under `modules/`, with
their own `pyproject.toml` and `tests/` - part of a single uv workspace
rooted at the repo root (see the repo root's `pyproject.toml`), alongside
the `ws61850` core library itself. There's no more single combined
`examples/rti-demo` Python project/venv.

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

All commands in this section are run from the **repo root** (not
`examples/rti-demo`) - `bff`, `fsp` and `so` are workspace members of the
single uv workspace rooted there, alongside the `ws61850` core library.

### 1. Install dependencies

```bash
uv sync --all-packages
```

This creates/updates one shared `.venv` at the repo root and installs
every workspace member together - `ws61850`, `bff`, `fsp` and `so` - each
as an editable install, so `from so.acsi_client import ...` etc. resolve
normally with no `sys.path` hacks. (A bare `uv sync`, without
`--all-packages`, only installs the *root* project's own dependencies -
use `--all-packages`, or `--package <name>` for just one module, to get
`bff`/`fsp`/`so` installed too.)

`demo_IO` (Raspberry Pi GPIO/I2C hardware packages) is deliberately **not**
part of this workspace - it builds via its own fully independent
Docker-stage venv (`modules/demo_io/docker/Dockerfile`), since its
dependencies (`gpiozero`, `gpiod`, `Adafruit-ADS1x15`, ...) won't
resolve/install on a non-Pi dev machine.

### 2. Run the unit tests

Each module's tests run scoped to that module (`--package <name>` tells
uv which workspace member's environment/dependencies to use):

```bash
uv run --package bff pytest examples/rti-demo/modules/bff/tests -m unit -q
uv run --package fsp pytest examples/rti-demo/modules/fsp/tests -m unit -q
uv run --package so  pytest examples/rti-demo/modules/so/tests  -m unit -q
```

The `-m unit` flag matters: this project defines two pytest markers,
`unit` (fast, fully isolated - no network, no Docker) and `integration`
(needs live Docker containers, and lives separately under
`examples/rti-demo/tests/integration/` - see below).

You can also `cd` into a module directory first and drop the `--package`
flag and path prefix - uv resolves the enclosing workspace automatically:

```bash
cd examples/rti-demo/modules/so
uv run pytest -m unit -q
```

You'll see a lot of stdout noise (`serve_kwargs: ...`, `the scheme is:
ws`) from the `so` (ACSI client) tests - those tests exercise the real
`connect()` code path, which really does spin up a background WebSocket
server/thread. That's expected and harmless; the threads are daemon
threads and don't block the test run or leak into other tests.

### 3. Run one file, or one test, while iterating

```bash
# One file
uv run --package bff pytest examples/rti-demo/modules/bff/tests/test_push_relay.py -m unit -q

# One test by name (substring match)
uv run --package so pytest examples/rti-demo/modules/so/tests -m unit -k readvalue -q

# Full tracebacks instead of the default one-liners
uv run --package fsp pytest examples/rti-demo/modules/fsp/tests -m unit -q --tb=short
```

### Where things live

```
examples/rti-demo/modules/
├── bff/
│   ├── pyproject.toml
│   ├── src/bff/bff_server.py, ConnectionManager.py, bffClient.py, ...
│   ├── docker/Dockerfile
│   └── tests/test_push_relay.py, test_connection_manager_ids.py, ...
├── fsp/
│   ├── pyproject.toml
│   ├── src/fsp/bff_endpoint.py, acsi_server.py, model.py
│   ├── docker/Dockerfile
│   └── tests/test_bff_endpoint.py
├── so/
│   ├── pyproject.toml
│   ├── src/so/bff_endpoint.py, acsi_client.py
│   ├── docker/Dockerfile
│   └── tests/test_bff_endpoint.py, test_acsi_client.py
└── demo_io/   # not a workspace member - see above
```

`fsp` and `so` are each tested through a `fastapi.testclient.TestClient`
wrapping the real FastAPI router from `fsp.bff_endpoint` /
`so.bff_endpoint` - no mocking of the HTTP layer, just of a few
IEC 61850-specific internals (e.g. `server.read_value`) where actually
talking to hardware/a real server would be needed otherwise.

### Integration tests (Docker required)

The tests under `examples/rti-demo/tests/integration/` (including
`test_bff_connections.py`, formerly `tests/unit/bff/test_bff_endpoint.py`)
talk to real, running BFF/FSP/SO instances. To run those:

```bash
cd examples/rti-demo
docker compose up -d
uv run pytest tests/integration -m integration -q
```

(That last command still works run from `examples/rti-demo/` even though
it has no `pyproject.toml` of its own anymore - uv resolves the enclosing
workspace at the repo root automatically.)

If you don't have Docker running, skip this section entirely - the unit
test commands above never touch it.

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
# From the repo root
(uv run --package bff pytest examples/rti-demo/modules/bff/tests -m unit -q) \
  && (uv run --package fsp pytest examples/rti-demo/modules/fsp/tests -m unit -q) \
  && (uv run --package so pytest examples/rti-demo/modules/so/tests -m unit -q) \
  && (cd examples/rti-demo/hmi && npm test) \
  && (cd examples/rti-demo/hmi && npx vite build && rm -rf dist)
```

If all three steps print a passing summary with no errors, the codebase is
in a clean, verified state.
