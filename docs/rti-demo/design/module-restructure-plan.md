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

## Steps 1-4 - Migrate `so`, `fsp`, `bff`, `demo_IO` - DONE (one combined pass)

Step 1 (`so` alone) turned out to be blocked by something the plan didn't
anticipate: **uv workspaces don't support a member's directory being
nested inside another separate member's directory**, and don't support
nested `[tool.uv.workspace]` declarations at all (`error: Nested
workspaces are not supported`). With `examples/rti-demo` (still holding
the not-yet-migrated `fsp`/`bff`) registered as one member and
`examples/rti-demo/modules/so` registered as another, uv's per-package
dependency resolution for `so` misidentified `examples/rti-demo` as its
containing project instead of the true repo-root workspace, so `so`'s
`iec61850-websocket = { workspace = true }` reference failed to resolve.
That forced migrating all four together instead of one at a time, so
there was never a moment with old-flat-and-new-modules coexisting as
separate workspace members.

**A second, sharper version of the same issue** surfaced once `so`/`fsp`/
`bff` were the only registered members: it turned out **any**
`pyproject.toml` sitting in a parent directory of a workspace member
blocks uv's discovery from reaching the true workspace root above it -
even one with no `[project]` table at all (uv logs `WARN pyproject.toml
does not contain a project table` and falls back to treating that
directory as an independent, non-workspace project root). Fix:
`examples/rti-demo/pyproject.toml` was deleted entirely (it had already
been stripped down to just `[tool.pytest.ini_options]` for the
integration tests) - that config moved to a plain `pyproject.toml` isn't
needed for pytest, so it's just gone; `cd examples/rti-demo && uv run
pytest tests/integration ...` still works unmodified, since uv resolves
the enclosing workspace at the repo root automatically when there's no
competing pyproject.toml in between.

What actually landed, per module:

- **`so`**: `so/*.py` → `modules/so/src/so/`, `from acsi_client import
  ACSIClient` → `from so.acsi_client import ACSIClient`. Deps: fastapi,
  uvicorn, httpx2, `iec61850-websocket` (workspace source) - `websockets`/
  `PyJWT`/`asn1tools`/`aiohttp` etc. all come along transitively via
  `ws61850` and were never imported directly, so they're not redeclared.
- **`fsp`**: same shape; `from acsi_server import ACSIServer` → `from
  fsp.acsi_server import ACSIServer`. Deps: fastapi, uvicorn, httpx2,
  `python-multipart` (file upload endpoints), `iec61850-websocket`. The
  `demo_IO` cross-reference the original plan worried about doesn't
  actually exist as a Python import - `fsp.bff_endpoint` loads IO-plugin
  code dynamically from a filesystem directory (`IO_PLUGIN_STORAGE`) at
  runtime, never a static `import demo_IO`, so there was no ordering
  constraint with Step 4 after all.
- **`bff`**: `from bffClient import BffClient` / `from ConnectionManager
  import ConnectionManager` / `from pydantic_models import *` → `bff.`-
  qualified. Deps: fastapi, uvicorn, requests, httpx2 (missed on the
  first pass - `ConnectionManager.py` imports it even though
  `bff_server.py` doesn't - caught by the Docker smoke test crashing with
  `ModuleNotFoundError: No module named 'httpx2'`), `docker` (for the
  `DockerClient` health-check integration). Does **not** depend on
  `ws61850` - bff never imports it. Its one genuinely cross-cutting test
  file, `test_bff_endpoint.py` (a live-container integration test, not a
  unit test), moved to `examples/rti-demo/tests/integration/
  test_bff_connections.py` instead of `modules/bff/tests/` - it doesn't
  belong mixed in with bff's isolated unit tests.
- **`demo_IO` → `modules/demo_io`**: directory move + `Dockerfile.IO` →
  `modules/demo_io/docker/Dockerfile` (its own COPY paths de-prefixed to
  match its own narrower build context). Deliberately **not** added to
  the uv workspace - needs Raspberry Pi hardware packages (`gpiozero`,
  `gpiod`, `Adafruit-ADS1x15`, `smbus2`) that won't resolve on a non-Pi
  dev machine, and it already builds via its own fully independent
  Docker-stage venv, never sharing the shared workspace env. Also trimmed
  its own `pyproject.toml`'s unused `flask`/`flask-cors`/`werkzeug`/
  `python-dotenv` (same dead-weight finding as Step 0, confirmed via the
  same grep-for-imports check) and fixed its `name` field (`"rti-demo"` →
  `"demo-io"` - it was a straight copy of the old shared pyproject.toml).

Every unit test file's `sys.path.insert`/`import_module_from_path`
boilerplate was deleted - `bff`/`fsp`/`so` being real installed packages
means `from so.acsi_client import ACSIClient` etc. just works, and the
module-name-collision problem `import_module_from_path` existed to solve
(both `fsp/bff_endpoint.py` and `so/bff_endpoint.py` being literally
named `bff_endpoint.py`) no longer exists either - they're
`fsp.bff_endpoint` and `so.bff_endpoint` now, distinct names.
`tests/conftest.py` (the `sys.path`-for-`ws61850` + `import_module_from_path`
helper file) was deleted entirely as a result - nothing references it
anymore.

`docker-compose.yml`, `launch.py` (entry_point paths), the root and
per-module Dockerfiles, and the old top-level `Dockerfile*` files were
all updated/removed to match. One more real bug caught by the Docker
smoke tests (not a migration-path issue, but found while verifying them):
`WORKDIR /app` creates that directory as root *before* the later `COPY
--chown=app:app` runs, and `--chown` only applies to what's copied in,
not retroactively to the pre-existing directory node - so `/app` stayed
root-owned and the non-root `app` user couldn't `mkdir` into it (e.g.
fsp/so's IO-plugin dynamic-loading directory). Fixed with an explicit
`RUN chown app:app /app` after the COPY, in all three Dockerfiles.

**Verified**: `rm -rf .venv && uv sync --all-packages` clean from repo
root; all three modules' full unit suites (so: 72, fsp: 17, bff: 41, all
passing) plus the root `ws61850` suite (183 passed / 1 pre-existing
unrelated failure) and the 17 integration tests collecting correctly;
`docker compose build` for all five services (bff, fsp01, fsp02, so, hmi,
demo_io); a live `docker compose up` of bff+fsp01+fsp02+so with a real
FSP→SO WebSocket association (`acsi_client_list: ["cp1"]`) and a BFF
proxy call through to the SO, both working end to end.

Not yet done: per-module `README.md` files (`modules/{bff,fsp,so,demo_io}/README.md`)
still have some stale example paths/commands from before the move -
`TESTING.md` and the root `README.md`'s Docker section were updated, but
the per-module READMEs' prose wasn't fully audited. Low priority - low
risk of anyone being misled by it in practice, since it's usage
documentation, not anything executable.

## Step 5 - `hmi` - DONE

Moved to `modules/hmi` for consistency with the other four. Updated:
`docker-compose.yml` (`context: hmi` → `context: modules/hmi`),
`TESTING.md`'s frontend section, three `.adoc` doc files
(`RTI_DEMO.adoc`, `includes/demo_setup.adoc`, `includes/hmi.adoc`), and
`.github/workflows/images.yml` (its path filters and the build-context
case statement for `so`/`fsp`/`bff`/`io`/`hmi` were all still pointing at
pre-Step-1-4 paths - that workflow's actual `docker/build-push-action`
step is commented out/dormant, so this wasn't breaking CI today, but was
already fully stale and would have failed the moment someone re-enabled
it). Left the workflow's `acsi_client`/`acsi_server` matrix entries
alone - they reference `examples/rti-demo/acsi_ws_client`/`acsi_ws_server`,
which don't exist anywhere in the repo and were already dead before this
migration touched anything.

Also caught and fixed a real regression risk in `.dockerignore`: it had a
stale `examples/rti-demo/bff/connections.json` exclusion rule that
pointed nowhere (the file had already moved), so it was a silent no-op -
updating the path to the new, correct location would have started
actually excluding bff's seed `connections.json` from the build context,
breaking the fallback-connections behavior confirmed working in the
Steps 1-4 Docker smoke test. Removed the exclusion entirely instead, with
a comment explaining why it's deliberately shipped in the image.

**Verified**: `docker compose config --quiet` (compose file still valid),
`docker compose build rti-hmi` from the new location, `npx vitest run`
(59 passed) + `npx vite build` from `modules/hmi/`, and a rebuild +
smoke test of `bff` confirming its seed `connections.json` (3 targets)
still ships after the `.dockerignore` fix.

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

## Open decisions

1. ~~Build context convention~~ - resolved: `bff`/`fsp`/`so` all build from
   repo-root context now (`fsp`/`so` need it for `ws61850`; `bff` doesn't
   strictly need it but matches the others for consistency). `demo_io`
   builds from its own narrower context (`modules/demo_io`) since it's
   fully independent of the workspace anyway.
2. **`hmi` in `modules/` or not**: still open, still low priority. It's a
   different toolchain entirely (npm/vite, not uv) - moving it under
   `modules/` (Step 5) is purely cosmetic consistency, not a functional
   requirement.
3. ~~Lockfile granularity~~ - resolved: one shared `uv.lock` at the repo
   root, one shared `.venv`, `so`/`fsp`/`bff` each an editable workspace
   member with their own `pyproject.toml` scoping their own dependency
   *list* (not a separate resolution). `uv sync --package X` (used in each
   Dockerfile) installs just that member + its deps into that same shared
   lock's view.

## Rollback

Every step is an isolated commit on this branch; `git revert <sha>` undoes
any single step cleanly since later steps don't rewrite earlier ones'
files. If the whole effort stalls partway, `initial-refactor` (or `main`)
is untouched throughout - this branch can simply be abandoned.
