# RTI Demo Docker Build Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix broken layer caching, remove a dead Dockerfile, fix a non-reproducible build, and consolidate four near-duplicate service Dockerfiles into one parameterized image for `examples/rti-demo/`.

**Architecture:** The four SO/FSP/ACSI-client/ACSI-server Dockerfiles share the same builder pattern (uv + Python) and only differ in which app subdirectory gets copied in, the port, and the run command. They are merged into a single `Dockerfile.service` driven by Docker build ARGs (`SERVICE_DIR`, `SERVICE_MODULE`, `APP_PORT`, `HEALTH_PATH`), consumed via `docker-compose.yml` `build.args`. The healthcheck is switched from a hardcoded port to `$PORT` shell-expansion, which also fixes a latent bug where `docker-compose.yml` overrides `PORT` for `rti-so` and `rti-fsp-2` but the old Dockerfiles' healthchecks stayed hardcoded to the build-time default port, so they always failed once a compose file overrode `PORT`.

**Tech Stack:** Docker (BuildKit, multi-stage builds), `uv` (Python dependency manager), Docker Compose, GitHub Actions.

**Spec:** No separate spec doc — this plan is derived directly from a Docker-build-structure review of `examples/rti-demo/` performed earlier in this conversation. The findings it implements:
1. `examples/rti-demo/Dockerfile` (bare) is dead code — unreferenced by any compose file or CI workflow, and worse than `Dockerfile.bff` which it duplicates.
2. `Dockerfile.rti-so`, `Dockerfile.rti-fsp`, `Dockerfile.acsi-ws-server`, `Dockerfile.acsi-ws-client` copy app source *before* `uv sync`, so any source change invalidates the dependency-install layer.
3. Those same four files are ~90% identical boilerplate (builder image, `apt-get install curl`, `useradd`, healthcheck shape) — worth consolidating into one parameterized Dockerfile.
4. Python version drift: `rti-so`/`rti-fsp`/`acsi-ws-server` pin `python3.11`; `acsi-ws-client`/`demo_IO`/`hmi` use `3.13`. Consolidate on `3.13`.
5. `Dockerfile.IO` mutates the lockfile at build time (`uv lock` fallback) and lacks a uv cache mount.
6. Healthcheck/port mismatches: `Dockerfile.rti-so`'s healthcheck is hardcoded to port `5001` while `docker-compose.yml` overrides `PORT=5002` for that service — the healthcheck always fails under that compose file. `Dockerfile.acsi-ws-server` itself has EXPOSE/ENV default `5001` but a healthcheck hardcoded to `5004`, an internal inconsistency. `rti-fsp-2` in `docker-compose.yml` overrides `PORT=5005` against a Dockerfile healthcheck hardcoded to `5001` — same bug.

## Global Constraints

- Every Dockerfile in this repo uses multi-stage builds (`builder` + `runtime`) — keep this shape.
- The `builder` stage uses `ghcr.io/astral-sh/uv:python<version>-bookworm-slim`; the `runtime` stage uses `python:<version>-slim`. Keep this pairing.
- `uv sync` calls must use `--mount=type=cache,target=/root/.cache/uv` and `--frozen` (never mutate `uv.lock` during a build).
- Runtime stages install `curl` (required for `HEALTHCHECK`), create a non-root `app` user via `useradd --create-home --shell /usr/sbin/nologin app`, and run as `USER app`.
- `src/ws61850` is consumed via `PYTHONPATH="/app:${PYTHONPATH}"`, not as an installed dependency — it does not need to be present when `uv sync` first resolves dependencies.
- Do not touch `Dockerfile.bff`, `hmi/Dockerfile`, or `Dockerfile.IO`'s GPIO/Raspberry-Pi-specific runtime logic (groups, devices, sudoers) — those are out of scope except for the specific `uv`/lockfile fix in Task 2.
- Do not enable the currently-commented-out `docker/build-push-action` step in `.github/workflows/images.yml` — it's intentionally disabled; only keep its (commented) reference consistent with the new Dockerfile/args so it's correct if someone re-enables it later.

---

### Task 1: Remove the dead root Dockerfile

**Files:**
- Delete: `examples/rti-demo/Dockerfile`

**Interfaces:** None — this file is not referenced by `examples/rti-demo/docker-compose.yml`, `examples/rti-demo/demo_setup/*.yml`, or `.github/workflows/images.yml` (verified by grep during the review). Deleting it has no downstream effect.

- [ ] **Step 1: Confirm nothing references the file**

Run: `grep -rn "rti-demo/Dockerfile\"" --include="*.yml" --include="*.yaml" . ; grep -rln "^FROM\|dockerfile: Dockerfile$" examples/rti-demo/docker-compose.yml examples/rti-demo/demo_setup/*.yml .github/workflows/images.yml | xargs grep -n "dockerfile: Dockerfile$"`

Expected: No output pointing at `examples/rti-demo/Dockerfile` (the bare file). (`hmi/Dockerfile` matches from a different context and is expected/fine — that's a different file.)

- [ ] **Step 2: Delete the file**

```bash
git rm examples/rti-demo/Dockerfile
```

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore(rti-demo): remove unreferenced duplicate root Dockerfile"
```

---

### Task 2: Fix `Dockerfile.IO` — reproducible lockfile + uv cache mount

**Files:**
- Modify: `examples/rti-demo/Dockerfile.IO`

**Interfaces:** None — single Dockerfile, no other file depends on its internal structure beyond `docker-compose.yml`'s existing `build.args` (`PI_USER`, `PI_UID`, `PI_GID`, `GPIO_GID`, `I2C_GID`, `SPI_GID`), which are untouched.

- [ ] **Step 1: Read current dependency-install block**

Current (`examples/rti-demo/Dockerfile.IO` lines 24-37):

```dockerfile
# Install uv (same approach as the original file)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy demo_IO project files
COPY demo_IO/pyproject.toml /app/pyproject.toml

# Create venv and install dependencies (gpiod is in pyproject.toml)
RUN uv venv && \
    if [ -f /app/uv.lock ]; then \
        uv sync --frozen --no-dev; \
    else \
        uv sync --no-dev && \
        uv lock; \
    fi
```

This silently falls back to resolving and writing a fresh `uv.lock` at build time when the lockfile is missing from the build context — a non-reproducible build (different resolution on different days/machines) that also leaves the generated lockfile stranded inside the image instead of committed to the repo.

- [ ] **Step 2: Verify whether `demo_IO/uv.lock` exists and is committed**

Run: `git ls-files examples/rti-demo/demo_IO/uv.lock`

- If it prints the path: the lockfile is already committed — proceed to Step 3 with the "lockfile exists" replacement.
- If it prints nothing: generate one first —
  ```bash
  cd examples/rti-demo/demo_IO && uv lock && cd -
  git add examples/rti-demo/demo_IO/uv.lock
  ```
  then proceed to Step 3.

- [ ] **Step 3: Replace the install block to require the committed lockfile and add a cache mount**

Edit `examples/rti-demo/Dockerfile.IO`, replacing the block from Step 1 with:

```dockerfile
# Install uv (same approach as the original file)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy demo_IO project files (uv.lock must be committed — no in-build resolve)
COPY demo_IO/pyproject.toml demo_IO/uv.lock /app/

# Create venv and install dependencies (gpiod is in pyproject.toml)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv && uv sync --frozen --no-dev
```

- [ ] **Step 4: Build to confirm the fix works**

Run: `docker build -f examples/rti-demo/Dockerfile.IO -t rti-demo-io:test examples/rti-demo`

Expected: Build succeeds, no lockfile-missing error, no `uv lock` step runs. (Ignore GPIO group/device warnings if any appear at container *run* time — this step only exercises the build.)

- [ ] **Step 5: Commit**

```bash
git add examples/rti-demo/Dockerfile.IO examples/rti-demo/demo_IO/uv.lock 2>/dev/null
git commit -m "fix(rti-demo): make Dockerfile.IO build reproducible, add uv cache mount"
```

---

### Task 3: Create the consolidated `Dockerfile.service`

**Files:**
- Create: `examples/rti-demo/Dockerfile.service`

**Interfaces:**
- Consumes (build ARGs): `PY_VERSION` (default `3.13`), `SERVICE_DIR` (required — one of `so`, `fsp`, `acsi_ws_client`, `acsi_ws_server`), `SERVICE_MODULE` (required — e.g. `so/bff_endpoint.py`), `APP_PORT` (default `5000`), `HEALTH_PATH` (default `/api/status`).
- Produces: a runtime image that listens on `$PORT` (settable at container-run time, not just build time), runs `python -u $SERVICE_MODULE`, and healthchecks `http://localhost:$PORT$HEALTH_PATH`.
- Build context must be the repo root (same as the four Dockerfiles it replaces), because it needs `src/ws61850`.

- [ ] **Step 1: Write the Dockerfile**

Create `examples/rti-demo/Dockerfile.service`:

```dockerfile
# RTI Demo shared service image (SO / FSP / ACSI WS client / ACSI WS server)
# Build context: repo root
# Required build args: SERVICE_DIR, SERVICE_MODULE, APP_PORT
# Optional build args: PY_VERSION (default 3.13), HEALTH_PATH (default /api/status)
# See docker-compose.yml for how each variant is built.

ARG PY_VERSION=3.13

# ============================================================
# Stage 1: Builder
# ============================================================
FROM ghcr.io/astral-sh/uv:python${PY_VERSION}-bookworm-slim AS builder

ARG SERVICE_DIR

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_PREFERENCE=only-system

WORKDIR /app

# Dependency layer: only pyproject.toml/uv.lock, so this stays cached
# across app-code changes (and across all four service variants' first
# build, since the lockfile is identical).
COPY examples/rti-demo/pyproject.toml examples/rti-demo/uv.lock /app/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# ws61850 is consumed via PYTHONPATH, not as an installed dependency, so
# it (and the service source) is only needed for this second sync, not
# the dependency-resolution one above.
COPY src/ws61850 /app/ws61850
COPY examples/rti-demo/demo_IO/ /app/demo_IO/
COPY examples/rti-demo/${SERVICE_DIR}/ /app/${SERVICE_DIR}/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


# ============================================================
# Stage 2: Runtime
# ============================================================
FROM python:${PY_VERSION}-slim AS runtime

ARG SERVICE_MODULE
ARG APP_PORT=5000
ARG HEALTH_PATH=/api/status

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app:${PYTHONPATH}" \
    PORT=${APP_PORT} \
    HEALTH_PATH=${HEALTH_PATH} \
    SERVICE_MODULE=${SERVICE_MODULE}

# curl is required for the health check
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /usr/sbin/nologin app

# Copy application and virtual environment
COPY --from=builder --chown=app:app /app /app

USER app

EXPOSE ${APP_PORT}

# Uses runtime $PORT/$HEALTH_PATH (shell form, not exec-array form, so
# they expand at healthcheck time) instead of the build-time defaults,
# so the check still matches when a compose file overrides PORT.
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:$PORT$HEALTH_PATH || exit 1

CMD ["sh", "-c", "python -u $SERVICE_MODULE"]
```

- [ ] **Step 2: Build all four variants locally to confirm the parameterization works**

Run each from the repo root:

```bash
docker build -f examples/rti-demo/Dockerfile.service \
  --build-arg SERVICE_DIR=so --build-arg SERVICE_MODULE=so/bff_endpoint.py --build-arg APP_PORT=5002 \
  -t rti-so:test .

docker build -f examples/rti-demo/Dockerfile.service \
  --build-arg SERVICE_DIR=fsp --build-arg SERVICE_MODULE=fsp/bff_endpoint.py --build-arg APP_PORT=5001 \
  -t rti-fsp:test .

docker build -f examples/rti-demo/Dockerfile.service \
  --build-arg SERVICE_DIR=acsi_ws_client --build-arg SERVICE_MODULE=acsi_ws_client/bff_endpoint.py --build-arg APP_PORT=5003 \
  -t rti-acsi-ws-client:test .

docker build -f examples/rti-demo/Dockerfile.service \
  --build-arg SERVICE_DIR=acsi_ws_server --build-arg SERVICE_MODULE=acsi_ws_server/bff_endpoint.py --build-arg APP_PORT=5004 \
  -t rti-acsi-ws-server:test .
```

Expected: All four builds succeed. Re-running any of them a second time should show the two `uv sync` `RUN` layers and the `COPY examples/rti-demo/pyproject.toml...` layer as cached (`CACHED` in the build output) if nothing changed, confirming the dependency layer is now stable.

- [ ] **Step 3: Verify the healthcheck respects a runtime PORT override**

```bash
docker run -d --name rti-so-porttest -e PORT=5099 rti-so:test
sleep 1
docker inspect --format='{{json .Config.Healthcheck}}' rti-so-porttest
docker exec rti-so-porttest sh -c 'echo $PORT $HEALTH_PATH'
docker rm -f rti-so-porttest
```

Expected: the `Healthcheck` config shows `curl -f http://localhost:$PORT$HEALTH_PATH`, and the `docker exec` prints `5099 /api/status` — confirming the healthcheck will curl port `5099`, not a baked-in `5002`, if the app were listening there. (The container will likely crash/exit quickly since the app itself may not read `$PORT` correctly outside compose networking — that's fine, this step only checks the env/healthcheck wiring, not full app behavior.)

- [ ] **Step 4: Commit**

```bash
git add examples/rti-demo/Dockerfile.service
git commit -m "feat(rti-demo): add consolidated parameterized Dockerfile.service"
```

---

### Task 4: Point `docker-compose.yml` at `Dockerfile.service` and delete the old per-variant Dockerfiles

**Files:**
- Modify: `examples/rti-demo/docker-compose.yml`
- Delete: `examples/rti-demo/Dockerfile.rti-so`
- Delete: `examples/rti-demo/Dockerfile.rti-fsp`
- Delete: `examples/rti-demo/Dockerfile.acsi-ws-client`
- Delete: `examples/rti-demo/Dockerfile.acsi-ws-server`

**Interfaces:**
- Consumes: `examples/rti-demo/Dockerfile.service` from Task 3 (ARGs `SERVICE_DIR`, `SERVICE_MODULE`, `APP_PORT`).
- Depends on Task 3 being committed first.

- [ ] **Step 1: Update the `rti-fsp` service**

In `examples/rti-demo/docker-compose.yml`, replace:

```yaml
  rti-fsp:
    build:
      context: ../..
      dockerfile: examples/rti-demo/Dockerfile.rti-fsp
```

with:

```yaml
  rti-fsp:
    build:
      context: ../..
      dockerfile: examples/rti-demo/Dockerfile.service
      args:
        SERVICE_DIR: fsp
        SERVICE_MODULE: fsp/bff_endpoint.py
        APP_PORT: "5001"
```

- [ ] **Step 2: Update the `rti-fsp-2` service**

Replace:

```yaml
  rti-fsp-2:
    build:
      context: ../..
      dockerfile: examples/rti-demo/Dockerfile.rti-fsp
```

with:

```yaml
  rti-fsp-2:
    build:
      context: ../..
      dockerfile: examples/rti-demo/Dockerfile.service
      args:
        SERVICE_DIR: fsp
        SERVICE_MODULE: fsp/bff_endpoint.py
        APP_PORT: "5001"
```

(Same build args as `rti-fsp` — it's the same image; `rti-fsp-2`'s `environment: PORT=5005` override still works because the healthcheck reads `$PORT` at runtime, not the build-time `APP_PORT`. Docker/Compose will reuse the cached layers, or rebuild identically, for this second service.)

- [ ] **Step 3: Update the `rti-so` service**

Replace:

```yaml
  rti-so:
    build:
      context: ../..
      dockerfile: examples/rti-demo/Dockerfile.rti-so
```

with:

```yaml
  rti-so:
    build:
      context: ../..
      dockerfile: examples/rti-demo/Dockerfile.service
      args:
        SERVICE_DIR: so
        SERVICE_MODULE: so/bff_endpoint.py
        APP_PORT: "5002"
```

- [ ] **Step 4: Update the `active-ws-acsi-client` service**

Replace:

```yaml
  active-ws-acsi-client:
    build:
      context: ../..
      dockerfile: examples/rti-demo/Dockerfile.acsi-ws-client
```

with:

```yaml
  active-ws-acsi-client:
    build:
      context: ../..
      dockerfile: examples/rti-demo/Dockerfile.service
      args:
        SERVICE_DIR: acsi_ws_client
        SERVICE_MODULE: acsi_ws_client/bff_endpoint.py
        APP_PORT: "5003"
```

- [ ] **Step 5: Update the `passive-ws-acsi-server` service**

Replace:

```yaml
  passive-ws-acsi-server:
    build:
      context: ../..
      dockerfile: examples/rti-demo/Dockerfile.acsi-ws-server
```

with:

```yaml
  passive-ws-acsi-server:
    build:
      context: ../..
      dockerfile: examples/rti-demo/Dockerfile.service
      args:
        SERVICE_DIR: acsi_ws_server
        SERVICE_MODULE: acsi_ws_server/bff_endpoint.py
        APP_PORT: "5004"
```

- [ ] **Step 6: Validate the compose file**

Run: `docker compose -f examples/rti-demo/docker-compose.yml config --quiet`

Expected: no output, exit code 0 (confirms valid YAML and that all `build.args` interpolate correctly).

- [ ] **Step 7: Build the four affected services through Compose**

Run: `docker compose -f examples/rti-demo/docker-compose.yml build rti-fsp rti-fsp-2 rti-so active-ws-acsi-client passive-ws-acsi-server`

Expected: all five builds succeed (`rti-fsp` and `rti-fsp-2` will show the second one hitting cache).

- [ ] **Step 8: Delete the now-unused Dockerfiles**

```bash
git rm examples/rti-demo/Dockerfile.rti-so examples/rti-demo/Dockerfile.rti-fsp \
       examples/rti-demo/Dockerfile.acsi-ws-client examples/rti-demo/Dockerfile.acsi-ws-server
```

- [ ] **Step 9: Commit**

```bash
git add examples/rti-demo/docker-compose.yml
git commit -m "refactor(rti-demo): consolidate SO/FSP/ACSI Dockerfiles into Dockerfile.service"
```

---

### Task 5: Update `demo_setup/docker-compose.FSP.yml` and `demo_setup/docker-compose.SO.yml`

**Files:**
- Modify: `examples/rti-demo/demo_setup/docker-compose.FSP.yml`
- Modify: `examples/rti-demo/demo_setup/docker-compose.SO.yml`

**Interfaces:** Consumes `examples/rti-demo/Dockerfile.service` from Task 3. Depends on Task 4 being committed first (so the old Dockerfiles are confirmed gone and nothing else needs them).

- [ ] **Step 1: Update `docker-compose.FSP.yml`**

Replace:

```yaml
  rti-fsp:
    build:
      context: ../../../
      dockerfile: examples/rti-demo/Dockerfile.rti-fsp
```

with:

```yaml
  rti-fsp:
    build:
      context: ../../../
      dockerfile: examples/rti-demo/Dockerfile.service
      args:
        SERVICE_DIR: fsp
        SERVICE_MODULE: fsp/bff_endpoint.py
        APP_PORT: "5001"
```

- [ ] **Step 2: Update `docker-compose.SO.yml`**

Replace:

```yaml
  rti-so:
    build:
      context: ../../../
      dockerfile: examples/rti-demo/Dockerfile.rti-so
```

with:

```yaml
  rti-so:
    build:
      context: ../../../
      dockerfile: examples/rti-demo/Dockerfile.service
      args:
        SERVICE_DIR: so
        SERVICE_MODULE: so/bff_endpoint.py
        APP_PORT: "5002"
```

- [ ] **Step 3: Validate both compose files**

```bash
docker compose -f examples/rti-demo/demo_setup/docker-compose.FSP.yml config --quiet
docker compose -f examples/rti-demo/demo_setup/docker-compose.SO.yml config --quiet
```

Expected: no output, exit code 0 for both.

- [ ] **Step 4: Build both to confirm**

```bash
docker compose -f examples/rti-demo/demo_setup/docker-compose.FSP.yml build rti-fsp
docker compose -f examples/rti-demo/demo_setup/docker-compose.SO.yml build rti-so
```

Expected: both succeed, and (since Task 4 already built the same image/args combination) these should mostly hit cache.

- [ ] **Step 5: Commit**

```bash
git add examples/rti-demo/demo_setup/docker-compose.FSP.yml examples/rti-demo/demo_setup/docker-compose.SO.yml
git commit -m "refactor(rti-demo): point demo_setup compose files at Dockerfile.service"
```

---

### Task 6: Update `.github/workflows/images.yml` matrix

**Files:**
- Modify: `.github/workflows/images.yml`

**Interfaces:** Consumes `examples/rti-demo/Dockerfile.service` (Task 3). The `docker/build-push-action` step stays commented out per the Global Constraints — this task only fixes the `img` step's outputs (dockerfile path + build args) so the workflow is correct if/when that step is re-enabled, and updates the commented block to pass `build-args`.

- [ ] **Step 1: Read the current `img` step**

Current (`.github/workflows/images.yml`):

```yaml
      - id: img
        run: |
          case "${{ matrix.image }}" in
            so)          c=. ; f=examples/rti-demo/Dockerfile.rti-so         ; n=ws61850-so ;;
            fsp)         c=. ; f=examples/rti-demo/Dockerfile.rti-fsp        ; n=ws61850-fsp ;;
            acsi_client) c=. ; f=examples/rti-demo/Dockerfile.acsi-ws-client ; n=ws61850-acsi-ws-client ;;
            acsi_server) c=. ; f=examples/rti-demo/Dockerfile.acsi-ws-server ; n=ws61850-acsi-ws-server ;;
            bff)         c=examples/rti-demo ; f=examples/rti-demo/Dockerfile.bff ; n=rti-demo-bff ;;
            io)          c=examples/rti-demo ; f=examples/rti-demo/Dockerfile.IO  ; n=rti-demo-io ; p=linux/amd64,linux/arm64 ;;
            hmi)         c=examples/rti-demo/hmi ; f=examples/rti-demo/hmi/Dockerfile ; n=rti-demo-hmi ;;
          esac
          {
            echo "ctx=$c"
            echo "file=$f"
            echo "name=$n"
            echo "platforms=${p:-linux/amd64}"
          } >> "$GITHUB_OUTPUT"
```

- [ ] **Step 2: Replace it with a version that emits build args for the four consolidated variants**

```yaml
      - id: img
        run: |
          case "${{ matrix.image }}" in
            so)          c=. ; f=examples/rti-demo/Dockerfile.service ; n=ws61850-so ;
                         a="SERVICE_DIR=so|SERVICE_MODULE=so/bff_endpoint.py|APP_PORT=5002" ;;
            fsp)         c=. ; f=examples/rti-demo/Dockerfile.service ; n=ws61850-fsp ;
                         a="SERVICE_DIR=fsp|SERVICE_MODULE=fsp/bff_endpoint.py|APP_PORT=5001" ;;
            acsi_client) c=. ; f=examples/rti-demo/Dockerfile.service ; n=ws61850-acsi-ws-client ;
                         a="SERVICE_DIR=acsi_ws_client|SERVICE_MODULE=acsi_ws_client/bff_endpoint.py|APP_PORT=5003" ;;
            acsi_server) c=. ; f=examples/rti-demo/Dockerfile.service ; n=ws61850-acsi-ws-server ;
                         a="SERVICE_DIR=acsi_ws_server|SERVICE_MODULE=acsi_ws_server/bff_endpoint.py|APP_PORT=5004" ;;
            bff)         c=examples/rti-demo ; f=examples/rti-demo/Dockerfile.bff ; n=rti-demo-bff ;;
            io)          c=examples/rti-demo ; f=examples/rti-demo/Dockerfile.IO  ; n=rti-demo-io ; p=linux/amd64,linux/arm64 ;;
            hmi)         c=examples/rti-demo/hmi ; f=examples/rti-demo/hmi/Dockerfile ; n=rti-demo-hmi ;;
          esac
          {
            echo "ctx=$c"
            echo "file=$f"
            echo "name=$n"
            echo "platforms=${p:-linux/amd64}"
            echo "args<<EOF"
            [ -n "$a" ] && tr '|' '\n' <<<"$a"
            echo "EOF"
          } >> "$GITHUB_OUTPUT"
```

(`args` is emitted as a multi-line `GITHUB_OUTPUT` value — one `KEY=value` per line — matching the format `docker/build-push-action`'s `build-args:` input expects. It's empty for `bff`/`io`/`hmi`.)

- [ ] **Step 3: Update the commented-out build-push-action block to use it**

Replace:

```yaml
#      - uses: docker/build-push-action@v6
#        with:
#          context: ${{ steps.img.outputs.ctx }}
#          file: ${{ steps.img.outputs.file }}
#          platforms: ${{ steps.img.outputs.platforms }}
#          push: ${{ github.event_name != 'pull_request' }}
#          tags: ${{ steps.meta.outputs.tags }}
#          labels: ${{ steps.meta.outputs.labels }}
#          cache-from: type=gha,scope=${{ matrix.image }}
#          cache-to: type=gha,mode=max,scope=${{ matrix.image }}
#          provenance: false
```

with:

```yaml
#      - uses: docker/build-push-action@v6
#        with:
#          context: ${{ steps.img.outputs.ctx }}
#          file: ${{ steps.img.outputs.file }}
#          build-args: ${{ steps.img.outputs.args }}
#          platforms: ${{ steps.img.outputs.platforms }}
#          push: ${{ github.event_name != 'pull_request' }}
#          tags: ${{ steps.meta.outputs.tags }}
#          labels: ${{ steps.meta.outputs.labels }}
#          cache-from: type=gha,scope=${{ matrix.image }}
#          cache-to: type=gha,mode=max,scope=${{ matrix.image }}
#          provenance: false
```

- [ ] **Step 4: Validate the workflow YAML**

Run: `python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/images.yml'))" && echo OK`

(Or `yamllint .github/workflows/images.yml` if available.) Expected: `OK` / no errors.

- [ ] **Step 5: Manually trace the `case` logic for each of the four keys**

Confirm by inspection that `so`, `fsp`, `acsi_client`, `acsi_server` each set `f=examples/rti-demo/Dockerfile.service` and a distinct, correct `a=` string matching what Task 4's compose `args:` blocks use for the same service.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/images.yml
git commit -m "ci(rti-demo): point image matrix at consolidated Dockerfile.service"
```

---

### Task 7: Full-stack verification

**Files:** None (verification only).

**Interfaces:** None.

- [ ] **Step 1: Build every rti-demo image from `docker-compose.yml` in one pass**

Run: `docker compose -f examples/rti-demo/docker-compose.yml build`

Expected: `bff-server`, `rti-hmi`, `rti-fsp`, `rti-fsp-2`, `rti-so`, `active-ws-acsi-client`, `passive-ws-acsi-server` all build successfully. (`rti-io` may fail locally if not on a Raspberry Pi with the right host packages — that's expected and unrelated to this plan's changes; skip/ignore failures scoped to `rti-io` specifically, but they should be the *same* failures that existed before this plan, not new ones.)

- [ ] **Step 2: Bring the stack up and check health**

```bash
docker compose -f examples/rti-demo/docker-compose.yml up -d bff-server rti-fsp rti-so active-ws-acsi-client passive-ws-acsi-server
sleep 35
docker compose -f examples/rti-demo/docker-compose.yml ps
```

Expected: `rti-fsp`, `rti-so`, `active-ws-acsi-client`, and `passive-ws-acsi-server` all show `healthy` (not `unhealthy` or stuck `starting`) — this is the concrete regression check for the healthcheck/`$PORT` fix from Task 3, in particular for `rti-so` which previously had a hardcoded/overridden port mismatch.

- [ ] **Step 3: Tear down**

```bash
docker compose -f examples/rti-demo/docker-compose.yml down -v
```

- [ ] **Step 4: Re-run Task 1's grep to confirm no leftover references to deleted files**

Run: `grep -rn "Dockerfile.rti-so\|Dockerfile.rti-fsp\|Dockerfile.acsi-ws-client\|Dockerfile.acsi-ws-server" . --include="*.yml" --include="*.yaml"`

Expected: no output.

- [ ] **Step 5: Final commit (if any verification-driven fixups were needed)**

If Steps 1-4 required any code changes to pass, stage and commit them with a message describing what verification caught. If nothing needed fixing, no commit is needed for this task.

---

## Self-Review Notes

- **Spec coverage:** All 6 numbered findings in the Spec section map to tasks: #1 → Task 1, #2 → Task 3 (reorders copy-before-sync), #3 → Task 3 (consolidation), #4 → Task 3 (`PY_VERSION=3.13` default), #5 → Task 2, #6 → Task 3's `$PORT`/`$HEALTH_PATH` shell-expansion healthcheck, verified end-to-end in Task 7 Step 2.
- **Placeholder scan:** No TBD/TODO markers; every step has literal file content or literal commands.
- **Type/name consistency:** `SERVICE_DIR`, `SERVICE_MODULE`, `APP_PORT`, `HEALTH_PATH` are used with identical names and casing across Task 3 (Dockerfile definition), Task 4 (main compose), Task 5 (demo_setup compose), and Task 6 (CI matrix).
