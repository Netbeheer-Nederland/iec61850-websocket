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
    io/       { pyproject.toml, docker/Dockerfile, io_api_server/, io_client/ }
    hmi/      { package.json, docker/Dockerfile, src/ }
  config/     launch_config.json.example, models/
  docker-compose.yml
  tests/integration/   (stays central - genuinely cross-module)
```

(This reflects the layout as it stands after Steps 0-9 below; `demo_io` was
renamed to `io` in Step 9, and `hmi`'s Dockerfile moved into its own
`docker/` folder in Step 10, so every module now has an identical
`docker/Dockerfile` convention.)

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

## Step 6 - `config/` - DONE

Moved `launch_config.json.example` and `models/` to
`examples/rti-demo/config/`. Updated:

- `docker-compose.yml`'s `./models:/models` volume mounts (both FSP
  services) → `./config/models:/models` (container-side path unchanged -
  `MODELPATH=/models/model_N.py` still points at the same place inside
  the container).
- `launch.py`'s `--config` default and `save_config()`'s default
  parameter → `config/launch_config.json`. Turned out to be dead code
  either way - `load_config()`/`save_config()` are defined but never
  actually called anywhere in the file, and the parsed `--config` value
  is stored in a dict that's never read back. Updated the path for
  correctness/consistency regardless, in case that ever gets wired up.
- `examples/rti-demo/.gitignore`'s `bff/connections.json` entry (a stale
  leftover from the Steps 1-4 move, missed at the time) →
  `modules/bff/src/bff/connections.json`.
- Root `.dockerignore`'s `examples/rti-demo/models` entry →
  `examples/rti-demo/config/models`.

**Verified**: `docker compose config --quiet`, `python3 -c "import ast;
ast.parse(...)"` on `launch.py`, and a live `docker compose up
rti-fsp01` confirming the model still loads correctly from the new
mount path (`modelSource: '/models/model_1.py'`, `modelName: 'IED_2'`).

## Step 7 - Cleanup - DONE

The old flat `bff/`/`fsp/`/`so/`/`demo_IO/`/`hmi/` dirs and top-level
`Dockerfile*` files were already gone by the end of Steps 1-5 (each step
`git mv`'d its module out and removed its old Dockerfile as it went,
rather than leaving that for a separate pass). This step was the final
`git grep` sweep for anything missed, plus a stray leftover
`examples/rti-demo/__pycache__`/`.pytest_cache` (untracked, deleted).

Found and fixed, beyond what earlier steps already caught:

- Root `pyproject.toml`'s own comment referencing `Dockerfile.IO` by its
  old name/location.
- Five `.adoc` files under `docs/rti-demo/` (`RTI_DEMO.adoc`,
  `includes/bff.adoc`, `includes/demo_setup.adoc`, `includes/so.adoc`)
  and four per-module `README.md`s (`modules/{bff,fsp,so}/README.md`,
  `modules/demo_io/io_client/README_IO.md`) - directory-tree diagrams,
  `docker build -f ...` examples, and "run without Docker" instructions
  were all still describing the pre-migration flat layout (e.g. `python
  bff_endpoint.py` / `pip install -e .` instead of `uv run --package so
  python -m so.bff_endpoint`). Updated all of them to the new
  `modules/<name>/` paths and `uv run --package <name> ...` invocations.
- A real, if minor, bug: `bff.adoc`'s "Docker Integration" section named
  the container `bff-server` in two places - the actual
  `docker-compose.yml` service has always been `rti-bff`. Pre-existing
  inaccuracy, unrelated to path moves, fixed while already in the file.

**Not fixed** (pre-existing staleness unrelated to this restructure, out
of scope for a path-migration cleanup pass): a handful of remaining
`docker-compose` (old, deprecated hyphenated CLI form, vs. today's
`docker compose`) and generic `pip install -e .` references scattered
across `docs/rti-demo/includes/{so,fsp,demo_io}.adoc` and
`examples/rti-demo/README.md` - these predate the module restructure and
aren't path fragments this migration broke.

**Verified**: the `git grep` sweep for every old path pattern
(`examples/rti-demo/{bff,fsp,so,demo_IO,hmi}/`, `Dockerfile.bff`,
`Dockerfile.rti-fsp`, `Dockerfile.rti-so`, `Dockerfile.IO`) now comes back
empty repo-wide (excluding this plan doc's own history section); a clean
`rm -rf .venv && uv sync --all-packages` plus all three modules' full
unit suites (so 72, fsp 17, bff 41) and the root `ws61850` suite (183
passed, the same 1 pre-existing unrelated failure) still pass; `docker
compose config --quiet` still validates.

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

## Step 9 - Rename `demo_io` to `io` - DONE

Requested separately from the numbered plan, after Step 7's cleanup pass -
renamed the module (directory, package, container, hostname, and the
functional `DEMO_IO_URL` env var) to `io`/`rti-io`, matching the short
naming already used by `bff`/`fsp`/`so`.

- `git mv modules/demo_io modules/io`.
- `docker-compose.yml`: `container_name`/`rti.service`/`rti.host` →
  `rti-io`, build context/volume mount → `modules/io`/`/app/io`,
  `DEMO_IO_URL` → `IO_URL` (the one env var `io_router.py` actually reads).
- `launch.py`, `images.yml`, `.dockerignore`, root `pyproject.toml`'s
  workspace-exclusion comment: same path/name updates.
- `io_client_file_server.py`'s `IO_CLIENT_FILES_DIR` default path.
- `test_imports.py`: dropped an already-dead `import demo_IO` test block
  (no such package structure ever existed, even pre-rename).
- `io_api_server/pyproject.toml`: a separate, nested pyproject.toml
  distinct from `modules/io/pyproject.toml`, confirmed unreferenced by the
  actual Docker build and its `DEMO_IO_API_KEY(_FILE)` vars never read
  anywhere - renamed anyway for consistency (`name`, `[tool.demo_io]` →
  `[tool.io_api_server]`, env var names).
- `scripts/setup_raspberry_docker.sh`: fixed three stale
  `docker-compose build/up demo_io` lines → `docker compose build/up io`.
- `scripts/set_docker_user.sh`: comment update.
- Also `chmod +x` both scripts in `scripts/` - they were tracked
  non-executable (`100644`) despite their own usage docs showing direct
  `./scripts/foo.sh` invocation; pre-existing, unrelated to the rename,
  fixed alongside it since it was flagged in the same pass.

Deliberately left the ~75+ generic descriptive "demo_IO" mentions in
`io_router.py`, `async_client_io.py`, `mapping_manager.py`, and various
READMEs/docs untouched - prose/docstrings/labels, not paths or identifiers
that affect behavior, out of scope for this pass.

**Verified**: `uv sync --all-packages`, unit tests for so/fsp/bff all
pass, `docker compose config --quiet` valid, `docker compose build rti-io`
succeeds, and `docker compose up rti-io` correctly creates a container
named `rti-io` (fails only on missing `/dev/gpiochip0`, a Pi-only hardware
device unavailable on this dev machine - unrelated to the rename).

## Step 10 - `hmi`'s Dockerfile into `docker/` - DONE

Resolves open decision 2 below (partially - `hmi` was already under
`modules/` since Step 5; this closes the remaining `docker/Dockerfile`
convention gap). `git mv modules/hmi/Dockerfile modules/hmi/docker/Dockerfile`.
Build context stays `modules/hmi` (so the Dockerfile's relative `COPY . .`
etc. are unaffected) - only `docker-compose.yml`'s `dockerfile:` key and
`images.yml`'s build-file path changed, to `docker/Dockerfile`. Also fixed
two stale Dockerfile-path references in `README.md`'s project-structure
tree and `demo_setup.adoc` (including two `demo_io` → `io` references
missed by Step 9).

**Verified**: `docker compose config --quiet` and `docker compose build
rti-hmi` both succeed from the new location.

---

## Open decisions

1. ~~Build context convention~~ - resolved: `bff`/`fsp`/`so` all build from
   repo-root context now (`fsp`/`so` need it for `ws61850`; `bff` doesn't
   strictly need it but matches the others for consistency). `io` builds
   from its own narrower context (`modules/io`) since it's fully
   independent of the workspace anyway.
2. ~~`hmi` in `modules/` or not~~ - resolved: moved under `modules/` in
   Step 5, and given the same `docker/Dockerfile` layout as the other
   modules in Step 10, for full consistency across all five modules.
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
