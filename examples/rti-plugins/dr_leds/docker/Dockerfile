# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
#
# SPDX-License-Identifier: Apache-2.0

# The sample plugin dr_leds (decision 0030); any architecture.
# Build from the project root (examples/rti-plugins/dr_leds):
#   docker build -f docker/Dockerfile -t dr-leds .
# Dockerfile.dockerignore, next to this file, applies to that build.

FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /app
# Dependencies first, so source changes don't invalidate this layer.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

FROM python:3.13-slim

# OCI labels (decision 0041); CI adds version, revision and created.
# source connects the image to the repository on ghcr.io.
# A copy of this plugin in another repository changes source, url and documentation.
LABEL org.opencontainers.image.source="https://github.com/netbeheernederland/iec61850-websocket" \
      org.opencontainers.image.url="https://github.com/netbeheernederland/iec61850-websocket" \
      org.opencontainers.image.documentation="https://github.com/netbeheernederland/iec61850-websocket/blob/main/examples/rti-plugins/dr_leds/README.md" \
      org.opencontainers.image.title="dr-leds" \
      org.opencontainers.image.description="Sample RTI demo plugin dr_leds: two simulated LEDs that show what the FSP or SO does" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.vendor="Netbeheer Nederland"

COPY --from=build /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8099
RUN useradd --system --no-create-home --shell /usr/sbin/nologin app
USER app
EXPOSE 8099
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8099/plugin', timeout=2)"]
CMD ["dr-leds"]
