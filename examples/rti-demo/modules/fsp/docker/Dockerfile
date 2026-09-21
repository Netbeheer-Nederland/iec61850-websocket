# RTI Demo FSP (ACSI Server / WS Active) Docker Image - Multi-stage
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

# Workspace root files (needed for the shared uv.lock), ws61850 core, and
# this module's own source - editable installs need the real source tree
# present before `uv sync` runs (setuptools' egg_info step reads src/).
COPY pyproject.toml uv.lock ./
COPY src/ ./src/
COPY examples/rti-demo/modules/fsp/ ./examples/rti-demo/modules/fsp/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package fsp


# ============================================================
# Stage 2: Runtime
# ============================================================
FROM python:3.11-slim AS runtime

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=5001 \
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

EXPOSE 5001

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:5001/api/status || exit 1

CMD ["python", "-u", "-m", "fsp.bff_endpoint"]
