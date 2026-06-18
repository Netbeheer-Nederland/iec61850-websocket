# RTI Demo BFF Server Docker Image
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=5000

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY rti-demo/bff/ /app/bff/

RUN pip install fastapi uvicorn docker

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

CMD ["python", "-u", "bff/bff_server.py"]