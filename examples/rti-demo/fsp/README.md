# FSP: IEC 61850 ACSI Server Implementation

This folder contains the **FSP (Functional Server Platform)** implementation - an **IEC 61850 ACSI Server** that provides WebSocket-based communication for substation automation and power system control. Developed by MZ Automation.

## Overview

The FSP directory implements a complete **IEC 61850 ACSI (Abstract Communication Service Interface) Server** that:

- Exposes IEC 61850 data model via WebSocket (passive mode)
- Provides REST API endpoints for server management (BFF - Backend for Frontend)
- Manages IED (Intelligent Electronic Device) models
- Handles read/write operations on data objects
- Supports dynamic model reloading
- Integrates with IO devices via `demo_IO` service

### Architecture

```
+------------------+     +---------------------+     +------------------+
|                  |     |                     |     |                  |
|   External       |<--->|   bff_endpoint.py   |<--->|   acsi_server.py  |
|   Client/API     |     |   (REST API)        |     |   (WebSocket)     |
|   (Port 5001)    |     |   FastAPI           |     |   IEC 61850 Server|
|                  |     |                     |     |                  |
+------------------+     +----------+----------+     +----------+----------+
                                    |                        |
                                    v                        v
                            +--------------------+    +-------------------+
                            |   model.py         |    |   demo_IO Client   |
                            |   (IED Model)      |    |   (IO Integration) |
                            +--------------------+    +-------------------+
```

### Directory Structure

```
fsp/
├── acsi_server.py                      # Core IEC 61850 WebSocket server implementation
│                                        # - ACSIServerRuntime: Runtime state management
│                                        # - ACSIServer: Main server controller
│                                        # - WebSocket lifecycle management
│                                        # - Model loading and caching
│
├── bff_endpoint.py                     # REST API (FastAPI) for server management
│                                        # - Server lifecycle control (start/stop)
│                                        # - Model operations (read/write/update)
│                                        # - Connection management
│                                        # - Action/message logging
│                                        # - IO client integration
│
├── model.py                            # Auto-generated IED model
│                                        # - Generated from: rti_v1.0.scd
│                                        # - Contains DataAttributes, DataObjects
│                                        # - IEC 61850 data model definitions
│
├── check_syntax.py                     # Python syntax validation utility
│
├── run_bff.py                          # Simple BFF endpoint runner
│
├── start_bff.bat                       # Windows batch file for quick startup
│
├── test_start.py                       # Startup validation tests
│
├── BFF_API.md                          # Complete REST API documentation
│                                        # - All endpoint specifications
│                                        # - Curl examples
│                                        # - Request/response formats
│
├── Dockerfile                          # Docker container configuration
│                                        # - Multi-stage build
│                                        # - Port 5001 exposed
│
└── README.md                           # This file
```

## Key Components

### 1. acsi_server.py - IEC 61850 WebSocket Server

The core server implementation that handles:

- **WebSocket endpoint lifecycle** (start, stop, connection management)
- **IEC 61850 server instantiation** using ws61850 library
- **Model loading and caching** from `model.py`
- **Async event loop management** for concurrent operations
- **Runtime state tracking** (status, connections, errors)
- **Message logging** (received and sent messages)
- **Action tracking** for audit purposes

#### Key Classes

| Class | Purpose |
|-------|---------|
| `ACSIServerRuntime` | Manages server runtime state, connections, model, actions, messages |
| `ACSIServer` | Main server controller with WebSocket endpoint integration |

#### Server Status Flow

```
stopped --> starting --> listening --> stopping --> stopped
                      ^
                      |
                      v
                 (error state)
```

### 2. bff_endpoint.py - REST API (Backend for Frontend)

A **FastAPI** application that provides REST endpoints for managing the ACSI server. Acts as a bridge between HTTP clients and the WebSocket-based IEC 61850 server.

#### Key Features

- **Server lifecycle management** (start, stop, status)
- **Model operations** (read values, write values, update model)
- **Connection management** (list connections, status)
- **Message/action logging** (view, clear logs)
- **IO client integration** (connect to demo_IO service)
- **CORS support** for web-based clients
- **Pydantic validation** for request bodies

#### API Endpoint Categories

| Category | Endpoints | Purpose |
|----------|-----------|---------|
| **Status** | GET `/api/iec61850server/status` | Server status |
| | GET `/api/iec61850server/connections` | Connection info |
| **Model** | GET `/api/iec61850server/model` | Model descriptor |
| | POST `/api/iec61850server/update-iedmodel` | Update model |
| **Lifecycle** | POST `/api/iec61850server/start` | Start server |
| | POST `/api/iec61850server/stop` | Stop server |
| **Operations** | POST `/api/iec61850server/readvalue` | Read value |
| | POST `/api/iec61850server/writevalue` | Write value |
| **Logging** | GET `/api/iec61850server/actions` | View actions |
| | POST `/api/iec61850server/actions/clear` | Clear actions |
| | GET `/api/iec61850server/messages` | View messages |
| | POST `/api/iec61850server/messages/clear` | Clear messages |
| **IO Client** | POST `/api/io/connect` | Connect to demo_IO |
| | GET `/api/io/connection` | IO connection status |
| | POST `/api/io/disconnect` | Disconnect from demo_IO |

### 3. model.py - IED Model

Auto-generated Python file containing the **IEC 61850 data model** for the server.

- **Source**: Generated from `rti_v1.0.scd` SCL file
- **Generator**: `generate_mode_from_scl.py`
- **Contents**: DataAttribute, DataObject definitions for all IEC 61850 objects
- **Purpose**: Defines the data model that the server exposes to clients

#### Model Features

- **Logical Devices**: LD0, LD1, etc.
- **Logical Nodes**: LLN0, LPHD, GGIO, etc.
- **Data Objects**: Mod, Beh, Health, etc.
- **Data Attributes**: stVal, q, t, etc.
- **Functional Constraints**: ST, MX, CO, SP, etc.

---

## Quick Start

### Prerequisites

- Python 3.11+
- Docker (optional, for containerized deployment)
- Required Python packages (see below)

### Option 1: Docker (Recommended)

#### Build and Run (from repository root)

```bash
# Build the Docker image
docker build -t rti-demo-fsp -f examples/rti-demo/fsp/Dockerfile .

# Run the container
docker run --rm -p 5001:5001 rti-demo-fsp

# With custom network (for multi-container setup)
docker network create rti-network
docker run --rm -p 5001:5001 --network rti-network --name rti-fsp rti-demo-fsp
```

#### Build and Run (from fsp directory)

```bash
# Build from fsp directory
docker build -t rti-demo-fsp -f Dockerfile ../..

# Run with network
docker run --rm -p 5001:5001 --network rti-network --name rti-server rti-demo-fsp
```

#### API Health Check

```bash
curl http://localhost:5001/api/iec61850server/status
```

### Option 2: Direct Python Execution (Without Docker)

#### Install Dependencies

From repository root:

```bash
# Install package and dependencies
python -m pip install -e .
python -m pip install Flask==3.0.0 Flask-CORS==4.0.0
```

#### Run FSP API

From `rti-demo/fsp`:

```bash
# Default port (5001)
python bff_endpoint.py

# Custom port (Linux/macOS/WSL/Git Bash)
PORT=5001 python bff_endpoint.py

# Custom port (Windows PowerShell)
$env:PORT="5001"
python .\bff_endpoint.py
```

#### Health Check

```bash
curl http://localhost:5001/api/iec61850server/status
```

### Option 3: Using run_bff.py

```bash
python run_bff.py
```

### Option 4: Using start_bff.bat (Windows)

```cmd
start_bff.bat
```

---

## API Usage

### Server Lifecycle

#### Start the IEC 61850 Server

```bash
curl -X POST http://localhost:5001/api/iec61850server/start \
  -H "Content-Type: application/json" \
  -d '{
    "host": "0.0.0.0",
    "port": 8765,
    "mode": "server",
    "cp": "cp1"
  }'
```

Parameters are optional (defaults shown above).

**Response:**
```json
{
  "ok": true,
  "status": "starting",
  "host": "0.0.0.0",
  "port": 8765
}
```

#### Stop the IEC 61850 Server

```bash
curl -X POST http://localhost:5001/api/iec61850server/stop
```

**Response:**
```json
{
  "ok": true,
  "status": "stopped"
}
```

#### Check Server Status

```bash
curl http://localhost:5001/api/iec61850server/status
```

#### List Connections

```bash
curl http://localhost:5001/api/iec61850server/connections
```

### Model Operations

#### Get Model Descriptor

```bash
curl http://localhost:5001/api/iec61850server/model
```

#### Update IED Model

```bash
curl -X POST http://localhost:5001/api/iec61850server/update-iedmodel \
  -H "Content-Type: application/json" \
  -d '{"modelPy": "from ws61850... import IedModel\nmodel = IedModel(...)"}'
```

### Data Operations

#### Read Value

```bash
curl -X POST http://localhost:5001/api/iec61850server/readvalue \
  -H "Content-Type: application/json" \
  -d '{"objRef": "LD0/LLN0$ST$Mod", "fc": "ST"}'
```

#### Write Value

```bash
curl -X POST http://localhost:5001/api/iec61850server/writevalue \
  -H "Content-Type: application/json" \
  -d '{"objRef": "LD0/LLN0$ST$Mod", "value": "ON", "fc": "ST", "dataType": "BOOLEAN"}'
```

### Logging

#### Get/Clear Actions and Messages

```bash
# Get actions
curl http://localhost:5001/api/iec61850server/actions

# Clear actions
curl -X POST http://localhost:5001/api/iec61850server/actions/clear

# Get messages
curl http://localhost:5001/api/iec61850server/messages

# Clear messages
curl -X POST http://localhost:5001/api/iec61850server/messages/clear
```

---

## IO Client Integration

The FSP server integrates with the `demo_IO` service for controlling physical IO devices through IEC 61850 objects.

### Connect to demo_IO

```bash
curl -X POST http://localhost:5001/api/io/connect \
  -H "Content-Type: application/json" \
  -d '{"base_url": "http://demo-io:8080"}'
```

### Check/Disconnect IO

```bash
# Check connection
curl http://localhost:5001/api/io/connection

# Disconnect
curl -X POST http://localhost:5001/api/io/disconnect
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | 5001 | REST API port |
| `CP` | cp1 | Communication point identifier |
| `DEMO_IO_URL` | None | demo_IO service URL (for auto-connect) |

### Server Defaults

- **Host**: 0.0.0.0 (all interfaces)
- **Port**: 8765
- **Mode**: server (ACSI Server)
- **CP**: cp1 (communication point)

---

## Testing

### Run Syntax Check

```bash
python check_syntax.py
```

### Run Startup Tests

```bash
python test_start.py
```

### Run Unit Tests

```bash
pip install pytest pytest-asyncio
python -m pytest -q rti-demo/tests/unit/test_bff_endpoint.py
```

---

## Docker Deployment

### Docker Compose Example

```yaml
version: '3.8'

services:
  rti-fsp:
    build:
      context: .
      dockerfile: examples/rti-demo/fsp/Dockerfile
    ports:
      - "5001:5001"
      - "8765:8765"
    environment:
      - PORT=5001
      - CP=cp1
    networks:
      - rti-network
    depends_on:
      - demo-io

  demo-io:
    build:
      context: .
      dockerfile: examples/rti-demo/demo_IO/Dockerfile.IO
    ports:
      - "8080:8080"
    networks:
      - rti-network

networks:
  rti-network:
    driver: bridge
```

---

## Model Generation

The `model.py` is auto-generated from SCL files.

- **Source**: `rti_v1.0.scd`
- **Generator**: `generate_mode_from_scl.py`
- **Command**: `python generate_mode_from_scl.py rti_v1.0.scd -o examples/rti-demo/fsp/model.py`

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| **Port 5001 in use** | Use different port: `PORT=5002 python bff_endpoint.py` |
| **Port 8765 in use** | Change WebSocket port in start request |
| **Docker not found** | Install Docker Desktop and ensure it's running |
| **Module not found** | Run `pip install -e .` from repository root |
| **Server not starting** | Check logs, verify model.py exists and is valid |

### Debug Commands

```bash
# Check server status
curl http://localhost:5001/api/iec61850server/status

# Check connections
curl http://localhost:5001/api/iec61850server/connections

# View actions
curl http://localhost:5001/api/iec61850server/actions

# View messages
curl http://localhost:5001/api/iec61850server/messages
```

---

## Integration

### With demo_IO

FSP integrates with `demo_IO` to control physical IO devices through IEC 61850 objects.

**Flow**: Write to IEC 61850 object -> Mapped to IO device -> demo_IO controls physical device

### With SO (Client)

SO connects to FSP as a WebSocket client:

```
FSP (Server, Port 8765) <--WebSocket--> SO (Client)
FSP (BFF, Port 5001) <--HTTP--> External Clients
```

---

## Files Reference

| File | Purpose | Key Classes/Functions |
|------|---------|---------------------|
| `acsi_server.py` | WebSocket server | ACSIServerRuntime, ACSIServer |
| `bff_endpoint.py` | REST API | FastAPI app, endpoint routes |
| `model.py` | IED model | Generated data model |
| `check_syntax.py` | Validation | Syntax checking |
| `run_bff.py` | Runner | Simple execution |
| `start_bff.bat` | Windows startup | Batch script |
| `test_start.py` | Tests | Startup validation |
| `BFF_API.md` | API docs | Endpoint specifications |
| `Dockerfile` | Container | Multi-stage build |

---

## API Documentation

Complete API documentation: [BFF_API.md](./BFF_API.md)

Related documentation:
- [demo_IO README](../demo_IO/README.md) - IO device control
- [SO README](../so/README.md) - Client implementation

---

## Version History

- **v1.0.0** - Complete ACSI Server with REST API, dynamic model reloading, IO integration, Docker support

---

## License

Part of the **RTI_DEMO** project. See main project for licensing information.
