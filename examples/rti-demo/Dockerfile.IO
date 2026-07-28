# RTI Demo GPIO LED Control API Docker Image
# Build context: iec61850-websocket/examples/rti-demo/demo_IO

FROM python:3.11-slim

WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy application code
COPY . /app/demo_IO

# Install Python dependencies
RUN pip install --no-cache-dir -r /app/demo_IO/requirements.txt

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/api/io/health || exit 1

# Run the application
CMD ["python", "-u", "demo_IO/main.py"]
