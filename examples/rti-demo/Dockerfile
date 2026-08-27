# RTI Demo UI Server - Multi-stage Docker Image

# ============================================================
# Stage 1: Builder
# ============================================================
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_PREFERENCE=only-system

WORKDIR /app

# Install dependencies from the lock file
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# Copy application files
COPY . /app

# Install the project and dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev


# ============================================================
# Stage 2: Runtime
# ============================================================
FROM python:3.11-slim-bookworm AS runtime

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=5000 \
    PATH="/app/.venv/bin:$PATH"

# curl is required for the health check
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /usr/sbin/nologin app

# Copy application and virtual environment
COPY --from=builder --chown=app:app /app /app

USER app

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

CMD ["python", "-u", "bff/bff_server.py"]

