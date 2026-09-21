# rti-demo module restructure: migration plan

Branch: `restructure-rti-demo-modules`

Goal (see prior discussion): give each buildable module (`bff`, `fsp`, `so`,
`demo_IO`, `hmi`) its own `src/`, `pyproject.toml`, `docker/Dockerfile` and
`tests/`, unified under a single root **uv workspace** so `ws61850` (the core
library at repo `src/`) becomes a real declared dependency instead of a
Dockerfile-level `COPY` + hand-set `PYTHONPATH`.

Target layout:

```
examples/rti-demo/
  modules/
    bff/      { src/bff/, docker/Dockerfile, pyproject.toml, tests/ }
    fsp/      { src/fsp/, docker/Dockerfile, pyproject.toml, tests/ }
    so/       { src/so/,  docker/Dockerfile, pyproject.toml, tests/ }
    demo_io/  { src/demo_io/, pyproject.toml, tests/ }
    hmi/      (unchanged - already has its own src/, Dockerfile, package.json)
  config/     launch_config.json.example, models/
  docker-compose.yml
  tests/integration/   (stays central - genuinely cross-module)
```

Each numbered step below should land as its **own commit**, verified (tests +
a docker build of whatever it touched) before moving to the next. Do not
batch steps - a broken intermediate state should always be one `git revert`
away, not tangled up with three other changes.

---

## Step 0 - Establish the uv workspace (no files moved yet) - DONE

Added `[tool.uv.workspace]` to the **repo root** `pyproject.toml` with
`members = ["examples/rti-demo"]`. This immediately exposed real version
conflicts between the two previously-independent projects (a single
workspace resolves one shared environment, so it can't hold two versions
of the same package) - resolved as follows, each verified against both
projects' full test suites:

- **`flask`, `flask-cors`, `werkzeug`**: removed entirely from
  `examples/rti-demo/pyproject.toml`. Nothing in rti-demo imports them -
  `grep` for `import flask`/`from flask`/`werkzeug` across the whole
  module came back empty, and CORS is handled via FastAPI's own
  `CORSMiddleware` (confirmed in `bff/bff_server.py`), not `flask-cors`.
  Leftover from an earlier Flask-based implementation. Zero-risk removal.
- **`aiohttp`**: root was `==3.13.3`, rti-demo needed `>=3.14.1` → bumped
  root to `==3.14.1`.
- **`websockets`**: root was `==16.0`, rti-demo needed `>=16.1` → bumped
  root to `==16.1`.
- **`requests`**: root was `==2.32.5` (newer), rti-demo was `==2.31.0`
  (older) → bumped rti-demo to `==2.32.5` (root's already-vetted version).
- **`idna`** (transitive, surfaced only after the above were fixed): root
  pinned `==3.11`; rti-demo's `httpx2>=2.13.0` transitively requires
  `idna>=3.18` → bumped root to `==3.18` (matching what rti-demo's own
  lock already resolved to).

Also deleted `examples/rti-demo/.venv` and `examples/rti-demo/uv.lock` -
now stale, since the workspace uses one shared `.venv`/`uv.lock` at the
repo root. Confirmed `cd examples/rti-demo && uv run pytest` still works
unmodified (doesn't recreate a local venv/lock - correctly resolves
against the workspace root's), and `uv run --package rti-demo pytest
examples/rti-demo/tests` works from the repo root too.

**Verified**: clean `rm -rf .venv && uv sync` from repo root, then both
`uv run pytest tests/unit` (core, 183 passed / 1 pre-existing unrelated
failure - confirmed via `git stash` earlier in the session, not caused by
this) and `cd examples/rti-demo && uv run pytest -m unit` (130 passed).

## Step 1 - Migrate `so` (simplest: no `demo_IO` dependency)

- Create `examples/rti-demo/modules/so/{src/so/, pyproject.toml, docker/Dockerfile, tests/}`.
- Move `so/*.py` → `modules/so/src/so/`, add `so/__init__.py` if not present.
- `modules/so/pyproject.toml`: only `so`'s actual runtime deps (fastapi,
  uvicorn, websockets, PyJWT, python-multipart, httpx2 - check against
  actual imports, don't just copy the shared list) plus a path/workspace
  dependency on `ws61850`.
- Move `tests/unit/so/*` → `modules/so/tests/`, drop the
  `import_module_from_path`/`sys.path.insert` workaround in favor of a
  normal package import now that `so` is an installable package.
- New `modules/so/docker/Dockerfile`, build context = repo root (needed for
  `ws61850`), using `uv sync --package so`.
- Add `so` to the workspace `members` list.
- Update `docker-compose.yml`'s `rti-so` service: new `context`/`dockerfile`.
- **Verify**: `uv run pytest modules/so/tests -m unit`, `docker compose build rti-so`,
  `docker compose up rti-so` + the existing integration test
  (`tests/integration/test_so_fsp.py`) against it.

## Step 2 - Migrate `fsp` (needs `demo_IO`, so do this after Step 4 if you'd
rather not carry a temporary cross-reference - see note below)

- Same shape as Step 1: `modules/fsp/{src/fsp/, pyproject.toml, docker/Dockerfile, tests/}`.
- `fsp`'s Dockerfile currently also `COPY`s `demo_IO/` - until Step 4 lands,
  keep that as a relative `COPY ../demo_IO` from repo root (still works,
  just not yet using the workspace path); revisit once `demo_IO` is a
  workspace member too.
- Move `tests/unit/fsp/*` → `modules/fsp/tests/`.
- Update `docker-compose.yml`'s two FSP services (`rti-fsp01`, `rti-fsp02`).
- **Verify**: unit tests, `docker compose build rti-fsp01 rti-fsp02`,
  `tests/integration/test_so_fsp.py` (now against the fully migrated `so` +
  `fsp`).

## Step 3 - Migrate `bff`

- `modules/bff/{src/bff/, pyproject.toml, docker/Dockerfile, tests/}`.
- `bff` doesn't need `ws61850` - simplest Dockerfile of the three, build
  context can shrink back to just `modules/bff/` *unless* you want every
  module's Dockerfile to share one repo-root-context convention for
  consistency (recommended - see "Open decisions" below).
- Move `tests/unit/bff/*` → `modules/bff/tests/`.
- Update `docker-compose.yml`'s `rti-bff` service.
- **Verify**: unit tests, `docker compose build rti-bff`, full stack
  `docker compose up` + a manual HMI smoke test (Connections/Traffic pages
  load, a live SO/FSP pair shows connected).

## Step 4 - Migrate `demo_IO` → `modules/demo_io`

- Rename for naming consistency (`demo_IO` → `demo_io`), move under
  `modules/`.
- It already has its own `pyproject.toml` and `io_api_server`/`io_client`
  split - mostly a directory move + import path updates (grep for
  `demo_IO` across `fsp/`, `so/`, `bff/`, `Dockerfile.IO`,
  `docker-compose.yml`).
- Update `fsp`'s dependency on it (the dynamic-import helpers in
  `fsp/bff_endpoint.py` that load IO-plugin code) and `Dockerfile.IO`.
- **Verify**: `docker compose build demo_io rti-fsp01`, IO-plugin smoke test
  if you have the hardware/mock available, otherwise at least confirm the
  dynamic-import fallback path (`_use_io_client=False`) still works cleanly
  when `demo_io` isn't present.

## Step 5 - `hmi`

- Already fits the target shape. Only decide: move it under `modules/hmi`
  for consistency, or leave it where it is since it's not part of the uv
  workspace at all (different toolchain - npm, not uv) and gains nothing
  from the move besides a tidier top-level listing.
- If moved: update `docker-compose.yml`'s `context: hmi` → `context: modules/hmi`.
- **Verify**: `docker compose build rti-hmi`, `npx vitest run` still passes
  from its new path.

## Step 6 - `config/`

- Move `launch_config.json.example` and `models/` to a top-level
  `examples/rti-demo/config/`.
- Update `launch.py`'s path references and `docker-compose.yml`'s volume
  mount for `models/` (currently mounted into the FSP containers).
- **Verify**: `python launch.py` (or whatever the actual entry point is) still
  finds the config; FSP containers still load `model_1.py`/`model_2.py`.

## Step 7 - Cleanup

- Delete the now-empty old `bff/`, `fsp/`, `so/`, `demo_IO/` top-level dirs
  and the old `Dockerfile.bff`/`Dockerfile.rti-fsp`/`Dockerfile.rti-so`/
  `Dockerfile.IO`/`Dockerfile` (root) once every service in
  `docker-compose.yml` points at the new per-module Dockerfiles.
- Update `README.md`, `TESTING.md`, and any docs (including the wireframe's
  design notes if they reference file paths) for the new layout.
- **Verify**: `git grep` for the old path fragments (`examples/rti-demo/bff/`,
  `examples/rti-demo/fsp/`, etc.) to catch anything missed - CI configs,
  `.dockerignore`, editor configs.

## Step 8 - Full-stack verification

- `docker compose build` (all services, from a clean state - `docker compose
  build --no-cache` at least once to rule out stale-layer false confidence).
- `docker compose up`, run `tests/integration -m integration` against the
  live stack.
- Full unit suite across every module workspace member:
  `uv run pytest` from repo root should now discover and run all of them
  in one invocation (that's the payoff of the workspace).
- Manual HMI smoke test of the pages touched most in this session
  (Connections, Setup, Traffic, ACSI Server, ACSI Client).

---

## Open decisions (resolve before Step 1)

1. **Build context convention**: standardize every module's Dockerfile on
   repo-root context (like `fsp`/`so` need today for `ws61850`), or let
   `bff`/`demo_io` (which don't need `ws61850`) use a narrower context? Repo
   root everywhere is simpler to reason about; narrower contexts build
   marginally faster. Recommend: repo root everywhere, for consistency -
   the build-time cost difference is small.
2. **`hmi` in the workspace or not**: it's a different toolchain entirely
   (npm/vite, not uv) - moving it under `modules/` is purely cosmetic
   consistency, not a functional requirement. Low priority either way.
3. **Lockfile granularity**: one root `uv.lock` for the whole workspace
   (recommended - simpler, one resolution, per-module `pyproject.toml`
   still scopes what each *image* installs via `uv sync --package X`), vs.
   fully independent lockfiles per module (more isolation, more files to
   keep in sync, more CI time), Recommend the workspace-lockfile approach
   described throughout this plan.

## Rollback

Every step is an isolated commit on this branch; `git revert <sha>` undoes
any single step cleanly since later steps don't rewrite earlier ones'
files. If the whole effort stalls partway, `initial-refactor` (or `main`)
is untouched throughout - this branch can simply be abandoned.
