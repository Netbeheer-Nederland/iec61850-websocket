# RTI Demo GPIO LED Control API Docker Image
# Build context: rti-demo/

FROM python:3.13-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

# Install system dependencies for GPIO
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgpiod-dev \
    liblgpio1 \
    swig \
    gcc \
    g++ \
    build-essential \
    python3-dev \
 && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy demo_IO project files
COPY demo_IO/pyproject.toml /app/pyproject.toml

# Install dependencies from pyproject.toml using uv
# If no uv.lock exists, generate it; otherwise use frozen mode
RUN if [ -f /app/uv.lock ]; then \
    uv sync --frozen --no-dev; \
else \
    uv sync --no-dev && \
    uv lock; \
fi

# Copy application code
COPY demo_IO/ /app/demo_IO/

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/api/io/health || exit 1

CMD ["./.venv/bin/python", "-u", "demo_IO/main.py"]
