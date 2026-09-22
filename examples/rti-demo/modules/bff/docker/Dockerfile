# RTI Demo BFF (Backend for Frontend) Docker Image - Multi-stage
# Build context: repo root (kept consistent with fsp/so, which need it for
# the shared uv workspace lock and the ws61850 core library at src/ - bff
# itself doesn't depend on ws61850, but shares the same build convention).

# ============================================================
# Stage 1: Builder
# ============================================================
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_PREFERENCE=only-system

WORKDIR /app

# Dependency layer: workspace root files (shared uv.lock), ws61850 core,
# and just this member's pyproject.toml (uv needs it on disk to resolve
# `--package bff` against the workspace, but not its actual source yet).
# Kept separate from the COPY below so this layer - and the potentially
# slow `uv sync` dependency install - stays cached across bff/ source
# changes, instead of invalidating on every edit.
COPY pyproject.toml uv.lock ./
COPY src/ ./src/
COPY examples/rti-demo/modules/bff/pyproject.toml ./examples/rti-demo/modules/bff/pyproject.toml

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --package bff

# Now bring in the actual source and finish the editable install - this
# second sync only needs to link bff's own files in, not reinstall deps.
COPY examples/rti-demo/modules/bff/ ./examples/rti-demo/modules/bff/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package bff


# ============================================================
# Stage 2: Runtime
# ============================================================
FROM python:3.11-slim-bookworm

WORKDIR /app

ARG APP_PORT=5000
ARG HEALTH_PATH=/api/health

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=${APP_PORT} \
    HEALTH_PATH=${HEALTH_PATH} \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /usr/sbin/nologin app

COPY --from=builder --chown=app:app /app /app
RUN chown app:app /app

# Writable location for runtime state (connections.json). Kept outside the
# root-owned WORKDIR and the code bind mount; backed by a named volume in
# docker-compose.yml. Created before the USER switch so 'app' owns it and the
# fresh volume inherits that ownership - no host UID matching required.
RUN mkdir -p /config && chown app:app /config

USER app

EXPOSE 5000

# Shell form (not exec-array) so $PORT/$HEALTH_PATH expand at healthcheck
# time against the runtime env, not the build-time ARG default. Longer
# timeout/start-period/retries than the other modules' Dockerfiles - bff
# historically needed more startup slack; kept even though the docker.sock
# dependency that motivated it has since been removed, to avoid changing
# live behavior as a side effect of deduplicating this from compose.
HEALTHCHECK --interval=30s --timeout=30s --start-period=30s --retries=5 \
    CMD curl -f http://localhost:$PORT$HEALTH_PATH || exit 1

CMD ["python", "-u", "-m", "bff.bff_server"]
