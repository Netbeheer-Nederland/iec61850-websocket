# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
#
# SPDX-License-Identifier: Apache-2.0

# RTI Demo SO (ACSI Client / WS Passive) Docker Image - Multi-stage
# Build context: repo root (needed for the shared uv workspace lock and
# the ws61850 core library at src/) - see docker-compose.yml.

# ============================================================
# Stage 1: Builder
# ============================================================
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

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
# acsi-plugins, the plugin host: a workspace member this one depends on, so
# installed with the dependencies - whole, like the ws61850 core in src/.
COPY examples/rti-demo/modules/plugins/ ./examples/rti-demo/modules/plugins/

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
FROM python:3.13-slim-bookworm AS runtime

# OCI labels (decision 0041); CI adds version, revision and created.
# source connects the image to the repository on ghcr.io.
LABEL org.opencontainers.image.source="https://github.com/netbeheernederland/iec61850-websocket" \
      org.opencontainers.image.url="https://github.com/netbeheernederland/iec61850-websocket" \
      org.opencontainers.image.documentation="https://github.com/netbeheernederland/iec61850-websocket/blob/main/examples/rti-demo/modules/so/README.md" \
      org.opencontainers.image.title="rti-so" \
      org.opencontainers.image.description="RTI demo SO: ACSI client, WebSocket passive side (IEC 61850 over WebSocket)" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.vendor="Netbeheer Nederland"

WORKDIR /app

ARG APP_PORT=5000
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
# mkdir into it (e.g. PLUGIN_STORAGE, /app/plugins) without this.
RUN chown app:app /app

USER app

EXPOSE 5000

# Shell form (not exec-array) so $PORT/$HEALTH_PATH expand at healthcheck
# time against the runtime env, not the build-time ARG default - matters
# when docker-compose.yml overrides PORT (e.g. a second so/fsp instance).
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:$PORT$HEALTH_PATH || exit 1

CMD ["python", "-u", "-m", "so.bff_endpoint"]
