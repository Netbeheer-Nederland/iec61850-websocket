# RTI Demo GPIO LED Control API Docker Image - Multi-stage
# Build context: examples/rti-demo/

# ============================================================
# Stage 1: Builder
# ============================================================
FROM python:3.13-slim AS builder

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# libgpiod-dev + gcc are needed here only to build the gpiod Python bindings.
# They are NOT copied into the runtime stage.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgpiod-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

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

# Copy application code
COPY demo_IO/io_api_server/ /app/demo_IO/


# ============================================================
# Stage 2: Runtime
# ============================================================
FROM python:3.13-slim AS runtime

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    PATH="/app/.venv/bin:$PATH"

# Runtime GPIO tooling + curl for the health check
# (curl was missing from the original single-stage file, so the
# HEALTHCHECK below was likely failing silently before this fix)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgpiod3 \
    gpiod \
    sudo \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create pi user with gpio group access (matching host user)
# UID 1000 = pi, GID 1000 = pi's primary group, GID 986 = gpio on Raspberry Pi
RUN groupadd -g 1000 pi && \
    groupadd -g 986 gpio && \
    groupadd -g 988 i2c && \
    useradd -m -u 1000 -g 1000 -G gpio,i2c  pi && \
    echo 'pi ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers.d/pi

# Copy application and virtual environment
COPY --from=builder --chown=pi:gpio /app /app

# Fix permissions so pi user (1000:986) can access everything
RUN chmod -R g+rwX /app

# NOTE: kept running as root, matching the original file (no USER
# directive there). The pi/gpio user is set up and owns /app, but the
# container still needs privileged/device access from docker-compose.yml
# either way, so only switch to `USER pi` after confirming GPIO chip
# access still works for your setup.

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/api/io/health || exit 1

CMD ["python", "-u", "demo_IO/io_api_server/main.py"]
