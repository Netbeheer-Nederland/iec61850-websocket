# RTI Demo IEC 61850 Client Docker Image
# Build context: iec61850-websocket/ (repo root)

FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=5002

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install ws61850 package from repository sources
COPY pyproject.toml /app/repo/
COPY src/ /app/repo/src/
RUN pip install /app/repo

# Copy SO (Standalone Client) modules
COPY rti-demo/so/ /app/so/

# Install Flask and Flask-CORS dependencies
RUN pip install Flask==3.0.0 Flask-CORS==4.0.0

EXPOSE 5002

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:5002/api/iec61850client/status || exit 1

CMD ["python", "-u", "so/bff_endpoint.py"]
