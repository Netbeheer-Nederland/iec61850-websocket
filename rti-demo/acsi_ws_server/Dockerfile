# RTI Demo IEC 61850 Server Docker Image
# Build context: iec61850-websocket/ (repo root)

FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=5001

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install ws61850 package from repository sources
COPY pyproject.toml /app/repo/
COPY src/ /app/repo/src/
RUN pip install /app/repo

# Copy FSP (Backend-for-Frontend) modules
COPY rti-demo/acsi_ws_server/ /app/acsi_ws_server/

RUN pip install fastapi uvicorn

EXPOSE 5001

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:5004/api/iec61850server/status || exit 1

CMD ["python", "-u", "acsi_ws_server/bff_endpoint.py"]