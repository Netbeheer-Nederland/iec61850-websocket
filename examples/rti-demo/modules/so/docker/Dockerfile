# RTI Demo SO (ACSI Client / WS Passive) Docker Image - Multi-stage
# Build context: repo root (needed for the shared uv workspace lock and
# the ws61850 core library at src/) - see docker-compose.yml.

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
# `--package so` against the workspace, but not its actual source yet).
# Kept separate from the COPY below so this layer - and the potentially
# slow `uv sync` dependency install - stays cached across so/ source
# changes, instead of invalidating on every edit.
COPY pyproject.toml uv.lock ./
COPY src/ ./src/
COPY examples/rti-demo/modules/so/pyproject.toml ./examples/rti-demo/modules/so/pyproject.toml

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --package so

# Now bring in the actual source and finish the editable install - this
# second sync only needs to link so's own files in, not reinstall deps.
COPY examples/rti-demo/modules/so/ ./examples/rti-demo/modules/so/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package so


# ============================================================
# Stage 2: Runtime
# ============================================================
FROM python:3.11-slim AS runtime

WORKDIR /app

ARG APP_PORT=5002
ARG HEALTH_PATH=/api/status

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=${APP_PORT} \
    HEALTH_PATH=${HEALTH_PATH} \
    PATH="/app/.venv/bin:$PATH"

# curl is required for the health check
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /usr/sbin/nologin app

COPY --from=builder --chown=app:app /app /app

# WORKDIR created /app as root before the COPY above - COPY --chown only
# applies to what it copies in, not retroactively to the pre-existing
# directory node itself, so /app stays root-owned and the app user can't
# mkdir into it (e.g. the IO-plugin dynamic-loading directory) without this.
RUN chown app:app /app

USER app

EXPOSE 5002

# Shell form (not exec-array) so $PORT/$HEALTH_PATH expand at healthcheck
# time against the runtime env, not the build-time ARG default - matters
# when docker-compose.yml overrides PORT (e.g. a second so/fsp instance).
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:$PORT$HEALTH_PATH || exit 1

CMD ["python", "-u", "-m", "so.bff_endpoint"]
