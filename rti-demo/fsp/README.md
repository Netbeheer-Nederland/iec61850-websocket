This folder contains the developments from MZ Automation.

## FSP Docker Startup

Use these steps to build and run the FSP endpoint container.

### Prerequisites

1. Docker Desktop is installed and running.
2. The `docker` command is available in your terminal.

Quick check:

```bash
docker version
```

### Build and Run (from repo root)

From the `iec61850-websocket` repository root:

```bash
docker build -t rti-demo-fsp -f rti-demo/fsp/Dockerfile .
docker run --rm -p 5001:5001 rti-demo-fsp
```

### Build and Run (from rti-demo/fsp)

If your current directory is `rti-demo/fsp`:

```bash
docker build -t rti-demo-fsp -f Dockerfile ../..
####docker run --rm -p 5001:5001 rti-demo-fsp
docker run --rm -p 5001:5001 --network rti-demo_rti-network --name rti-server rti-demo-fsp

```

### Common Docker Issue

If you get `docker: command not found` or `The term 'docker' is not recognized`:

1. Install Docker Desktop.
2. Start Docker Desktop.
3. Open a new terminal and run:

```bash
docker version
```

Only run the build command after `docker version` works.

### API Health Check

When the container is running, verify the API status endpoint:

```bash
curl http://localhost:5001/api/iec61850server/status
```

Expected startup logs include messages from `bff_endpoint.py` indicating app initialization and startup port.

## FSP Unit Tests

Install test dependencies (once):

```bash
pip install pytest pytest-asyncio
```

Run endpoint unit tests from repository root:

```bash
python -m pytest -q rti-demo/tests/unit/test_bff_endpoint.py
```

Current test file:

- `rti-demo/tests/unit/test_bff_endpoint.py`

