# IEC 61850 Standalone Client (SO)

This directory contains a standalone IEC 61850 WebSocket client application that can connect to an IEC 61850 server and perform read/write operations on data values.

## Structure

- **acsi_client.py**: Core IEC 61850 client module handling connection lifecycle, async event loop management, and ACSI operations
- **bff_endpoint.py**: Flask-based Backend for Frontend (BFF) providing REST API endpoints for client control
- **BFF_API.md**: Complete API documentation for all available endpoints
- **Dockerfile**: Container configuration for running the client application
- **README.md**: This file

## Quick Start

### Prerequisites

- Python 3.9+
- IEC 61850 WebSocket server running (e.g., from the FSP folder)

### Installation

1. Navigate to the SO directory:
   ```bash
   cd rti-demo/so
   ```

2. Install dependencies:
   ```bash
   pip install flask ws61850
   ```

### Running the Client

#### As a Python Module

```bash
python bff_endpoint.py
```

The BFF API will start on `http://0.0.0.0:5002` by default.

#### Using Docker

**Prerequisites:**
1. Docker Desktop is installed and running.
2. The `docker` command is available in your terminal.

Quick check:
```bash
docker version
```

**Build and Run (from repo root):**
From the `iec61850-websocket` repository root:
```bash
docker build -t rti-demo-so -f rti-demo/so/Dockerfile .
docker run --rm -p 5002:5002 rti-demo-so
```

**Build and Run (from rti-demo/so):**
If your current directory is `rti-demo/so`:
```bash
docker build -t rti-demo-so -f Dockerfile ../..
docker run --rm -p 5002:5002 rti-demo-so
```

**Common Docker Issues:**
If you get `docker: command not found` or `The term 'docker' is not recognized`:
1. Install Docker Desktop.
2. Start Docker Desktop.
3. Open a new terminal and run:
```bash
docker version
```

Only run the build command after `docker version` works.

**API Health Check:**
When the container is running, verify the API status endpoint:
```bash
curl http://localhost:5002/api/iec61850client/status
```

Expected response includes the current client status and connection information.

## API Usage

### Connect to Server

```bash
curl -X POST http://localhost:5002/api/iec61850client/connect \
  -H "Content-Type: application/json" \
  -d '{"host": "localhost", "port": 8765, "cp": "cp1"}'
```

### Read a Value

```bash
curl -X POST http://localhost:5002/api/iec61850client/readvalue \
  -H "Content-Type: application/json" \
  -d '{"objRef": "LD0/DGEN1.DEROpSt.stVal"}'
```

### Write a Value

```bash
curl -X POST http://localhost:5002/api/iec61850client/writevalue \
  -H "Content-Type: application/json" \
  -d '{"objRef": "LD0/DGEN1.DEROpSt.stVal", "value": 1}'
```

### Get Status

```bash
curl http://localhost:5002/api/iec61850client/status
```

### Disconnect

```bash
curl -X POST http://localhost:5002/api/iec61850client/disconnect
```

## Core Components

### ACSIClient

The `ACSIClient` class manages:
- **Connection Lifecycle**: Initiates and maintains connections to IEC 61850 servers
- **Async Event Loop**: Runs in a separate thread with asyncio event loop
- **State Management**: Tracks client status, error conditions, and model data
- **Message Logging**: Records all sent/received protocol messages
- **Action Logging**: Tracks user actions and operations

### Key Methods

- `connect(host, port, cp)`: Establish connection to server
- `disconnect()`: Close connection to server
- `read_value(objRef)`: Read a value from the server
- `write_value(objRef, value)`: Write a value to the server
- `get_status()`: Get current client status
- `get_actions()`: Get logged actions
- `get_messages()`: Get logged protocol messages

## Status Values

- `disconnected`: Not connected to server
- `connecting`: Connection in progress
- `connected`: Successfully connected to server
- `disconnecting`: Disconnection in progress
- `error`: Connection or operation error

## Configuration

The client can be configured via environment variables:

- `PORT`: BFF API server port (default: 5002)

## Environment Variables

```bash
PORT=5002 python bff_endpoint.py
```

## Logging

All actions and protocol messages are logged in memory with configurable retention limits:
- **Actions**: Last 200 entries
- **Messages**: Last 500 entries

Logs are accessible via the API endpoints:
- `GET /api/iec61850client/actions`
- `GET /api/iec61850client/messages`

## Error Handling

The client provides detailed error messages for:
- Connection failures
- Invalid server parameters
- Read/write timeout errors
- Message parsing errors
- Protocol violations

All error responses include:
- HTTP status code
- JSON error object with error message

## SO Unit Tests

Install test dependencies (once):

```bash
pip install pytest pytest-cov flask
```

Run endpoint unit tests from repository root:

```bash
python -m pytest -v rti-demo/tests/unit/so/test_bff_endpoint.py
```

Run with coverage report:

```bash
python -m pytest --cov=rti_demo/so --cov-report=html rti-demo/tests/unit/so/test_bff_endpoint.py
```

Current test file:

- `rti-demo/tests/unit/so/test_bff_endpoint.py`

Test coverage includes:
- Endpoint availability and HTTP method validation
- JSON response format verification
- Parameter validation and error handling
- Connection state management

## See Also

- [FSP Server Documentation](../fsp/README.md)
- [BFF API Documentation](./BFF_API.md)
