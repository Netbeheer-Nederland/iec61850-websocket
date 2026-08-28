# SO: IEC 61850 ACSI Client Implementation

This folder contains the **SO (System Operator)** implementation - an **IEC 61850 ACSI Client** that uses WebSocket in passive mode to connect to ACSI servers for substation automation monitoring and control.

## Overview

The SO directory implements a complete **IEC 61850 ACSI (Abstract Communication Service Interface) Client** that:

- Connects to IEC 61850 servers via WebSocket (passive mode)
- Provides REST API endpoints for client management (BFF - Backend for Frontend)
- Retrieves and navigates server directory structures
- Reads data values from connected servers
- Writes data values to connected servers
- Manages multiple connections and communication points
- Integrates with IO devices via `demo_IO` service

### Architecture

```
+------------------+     +---------------------+     +------------------+
|                  |     |                     |     |                  |
|   External       |<--->|   bff_endpoint.py   |<--->|   acsi_client.py  |
|   Client/API     |     |   (REST API)        |     |   (WebSocket)     |
|   (Port 5002)    |     |   FastAPI           |     |   IEC 61850 Client|
|                  |     |                     |     |   (Passive Mode)  |
+------------------+     +----------+----------+     +----------+----------+
                                    |                        |
                                    v                        v
                            +--------------------+    +-------------------+
                            |   Server Directory  |    |   demo_IO Client   |
                            |   Navigation        |    |   (IO Integration) |
                            +--------------------+    +-------------------+
```

### Directory Structure

```
so/
├── acsi_client.py                      # Core IEC 61850 WebSocket client implementation (passive mode)
│                                        # - ACSIClientRuntime: Runtime state management
│                                        # - ACSIClient: Main client controller
│                                        # - WebSocket connection management
│                                        # - Model building and caching
│                                        # - Server directory navigation
│
├── bff_endpoint.py                     # REST API (FastAPI) for client management
│                                        # - Connection management (connect/disconnect)
│                                        # - Server directory operations
│                                        # - Model operations (get server/model tree)
│                                        # - Data operations (read/write values)
│                                        # - Action/message logging
│                                        # - IO client integration
│
└── README.md                           # This file
```

## Key Components

### 1. acsi_client.py - IEC 61850 WebSocket Client (Passive Mode)

The core client implementation that handles:

- **WebSocket connection lifecycle** (connect, disconnect, reconnect)
- **IEC 61850 client instantiation** using ws61850 library
- **Server directory navigation** (get server tree, logical devices, logical nodes)
- **Model building and caching** from connected servers
- **Async event loop management** for concurrent operations
- **Runtime state tracking** (status, connections, errors)
- **Message logging** (received and sent messages)
- **Action tracking** for audit purposes
- **Report handling** with callbacks for real-time updates

#### Key Classes

| Class | Purpose |
|-------|---------|
| `ModelInfo` | Manages model building state and data for each communication point |
| `ACSIClientRuntime` | Manages client runtime state, connections, model, actions, messages |
| `ACSIClient` | Main client controller with WebSocket endpoint integration |

### 2. bff_endpoint.py - REST API (Backend for Frontend)

A **FastAPI** application that provides REST endpoints for managing the ACSI client. Acts as a bridge between HTTP clients and the WebSocket-based IEC 61850 client in passive mode. For complete API documentation, see [BFF_API.md](./BFF_API.md).

---

## Quick Start

### Prerequisites

- Python 3.11+
- Docker (optional, for containerized deployment)
- A running IEC 61850 server (FSP or other ACSI server)
- Required Python packages (see below)

### Option 1: Docker (Recommended)

#### Build and Run (from repository root)

```bash
# Build the Docker image
docker build -t rti-demo-so -f examples/rti-demo/so/Dockerfile .

# Run the container
docker run --rm -p 5002:5002 rti-demo-so

# With custom network (for multi-container setup)
docker network create rti-network
docker run --rm -p 5002:5002 --network rti-network --name rti-so rti-demo-so
```

#### Build and Run (from so directory)

```bash
# Build from so directory
docker build -t rti-demo-so -f Dockerfile ../..

# Run with network
docker run --rm -p 5002:5002 --network rti-network --name rti-so rti-demo-so
```

#### API Health Check

```bash
curl http://localhost:5002/api/iec61850client/status
```

### Option 2: Direct Python Execution (Without Docker)

#### Install Dependencies

From repository root:

```bash
# Install package and dependencies
python -m pip install -e .
python -m pip install Flask==3.0.0 Flask-CORS==4.0.0
```

#### Run SO API

From `rti-demo/so`:

```bash
# Default port (5002)
python bff_endpoint.py

# Custom port (Linux/macOS/WSL/Git Bash)
PORT=5002 python bff_endpoint.py

# Custom port (Windows PowerShell)
$env:PORT="5002"
python .\bff_endpoint.py
```

#### Health Check

```bash
curl http://localhost:5002/api/iec61850client/status
```

---

## IO Client Integration

The SO client integrates with the `demo_IO` service for controlling physical IO devices through IEC 61850 objects.

### Connect to demo_IO

```bash
curl -X POST http://localhost:5002/api/io/connect \
  -H "Content-Type: application/json" \
  -d '{"base_url": "http://demo-io:8080"}'
```

### Check/Disconnect IO

```bash
# Check connection
curl http://localhost:5002/api/io/connection

# Disconnect
curl -X POST http://localhost:5002/api/io/disconnect
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | 5002 | REST API port |
| `DEMO_IO_URL` | None | demo_IO service URL (for auto-connect) |

### Connection Defaults

- **Host**: localhost
- **Port**: 8765
- **CP**: cp1 (communication point)

---

## Testing

Run tests from repository root:

```bash
pip install pytest pytest-asyncio
python -m pytest -q rti-demo/tests/unit/
```

---

## Model Status Values

| Status | Description |
|--------|-------------|
| `idle` | No model building in progress |
| `building` | Model is being built from server |
| `ready` | Model is ready for use |
| `error` | Error occurred during model building |

## Connection Status Values

| Status | Description |
|--------|-------------|
| `disconnected` | Not connected to any server |
| `connecting` | Connection attempt in progress |
| `connected` | Successfully connected to server |
| `disconnecting` | Disconnection in progress |
| `error` | Connection error occurred |

---

## Integration

### With FSP (Server)

FSP connects to SO as a WebSocket client (SO in passive mode):

```
SO (Server, Port 5002) <--HTTP--> External Clients
SO (WS Server, Passive) <--WebSocket--> FSP (Client)
```

### With demo_IO

SO integrates with `demo_IO` to control physical IO devices through IEC 61850 objects.

**Flow**: Write to IEC 61850 object -> SO sends to FSP -> FSP updates -> demo_IO controls physical device

### Typical Setup

```
+-----------+    +-----------+    +-----------+
|           |    |           |    |           |
|  Client   +--->+   SO      +--->+   FSP     |
|  (HTTP)   |    | (BFF)     |    | (Server)  |
|           |    | Port 5002 |    | Port 5001 |
+-----------+    +-----+-----+    +-----+-----+
                  |                 |           |
                  +-----------------+           |
                                    |           |
                                    v           v
                              +-----------+-----------+
                              | Physical Devices   |
                              +-----------+-----------+
                                    (via demo_IO or direct)
```

---

## Files Reference

| File | Purpose | Key Classes/Functions |
|------|---------|---------------------|
| `acsi_client.py` | WebSocket client (passive mode) | ModelInfo, ACSIClientRuntime, ACSIClient |
| `bff_endpoint.py` | REST API | FastAPI app, endpoint routes |
| `BFF_API.md` | API docs | Endpoint specifications |
| `Dockerfile` | Container | Multi-stage build (if exists) |

---

## License

Part of the **RTI_DEMO** project. See main project for licensing information.
