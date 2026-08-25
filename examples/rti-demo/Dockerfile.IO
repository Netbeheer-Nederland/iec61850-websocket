# RTI Demo GPIO LED Control API Docker Image
# Build context: examples/rti-demo/

FROM python:3.13-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

# Install system dependencies for GPIO (libgpiod library)
# libgpiod-dev provides headers, gpiod provides the library and tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgpiod-dev \
    gpiod \
    sudo \
 && rm -rf /var/lib/apt/lists/*

# Create pi user with gpio group access (matching host user)
# UID 1000 = pi, GID 1000 = pi's primary group, GID 986 = gpio on Raspberry Pi
RUN groupadd -g 1000 pi && \
    groupadd -g 986 gpio && \
    useradd -m -u 1000 -g 1000 -G gpio pi && \
    echo 'pi ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers.d/pi

# Install uv
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

# Fix permissions so pi user (1000:986) can access everything
RUN chown -R pi:gpio /app && \
    chmod -R g+rwX /app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/api/io/health || exit 1

CMD ["./.venv/bin/python", "-u", "demo_IO/io_api_server/main.py"]
