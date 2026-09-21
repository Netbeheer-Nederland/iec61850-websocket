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

COPY pyproject.toml uv.lock ./
COPY src/ ./src/
COPY examples/rti-demo/modules/bff/ ./examples/rti-demo/modules/bff/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package bff


# ============================================================
# Stage 2: Runtime
# ============================================================
FROM python:3.11-slim-bookworm

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=5000 \
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

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

CMD ["python", "-u", "-m", "bff.bff_server"]
