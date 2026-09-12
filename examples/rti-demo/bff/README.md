# RTI Demo BFF (Backend For Frontend) - Complete Documentation

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Folder Structure](#folder-structure)
4. [HMI to BFF Connection](#hmi-to-bff-connection)
5. [BFF to SO/FSP Connection Flow](#bff-to-sofsp-connection-flow)
6. [Core Components](#core-components)
7. [API Endpoints](#api-endpoints)
8. [Security Features](#security-features)
9. [Configuration Files](#configuration-files)
10. [Docker Integration](#docker-integration)
11. [Usage Examples](#usage-examples)
12. [Key Design Patterns](#key-design-patterns)

---

## Overview

The **BFF (Backend For Frontend)** layer in the RTI Demo serves as an intermediary between the **HMI (Human Machine Interface)** and the **ACSI services** (RTI-SO and RTI-FSP). It provides a unified REST API that abstracts the complexity of direct service communication, connection management, authentication, and data transformation.

### Purpose
- **Abstraction**: Hide the complexity of multiple ACSI endpoints (SO and FSP) behind a single, consistent API
- **Security**: Centralize authentication, authorization, and TLS configuration
- **Aggregation**: Combine multiple backend calls into single frontend requests
- **Transformation**: Adapt backend responses to frontend-expected formats
- **Connection Management**: Maintain and monitor connections to multiple RTI services

---

## Architecture

```
+-----------------------------------------------------------------------+
|                        RTI Demo System Architecture                     |
+-----------------------------------------------------------------------+
|                                                                       |
|  +-----------------+      +-----------------+      +-------------+  |
|  |                 |      |                 |      |             |  |
|  |   Web Browser   |----->|   HMI (React)    |----->|    BFF      |  |
|  |   (User)        |      |   (Port 3001)   |      | (Port 5000)|  |
|  |                 |      |                 |      |             |  |
|  +-----------------+      +-----------------+      +------+------+  |
|                                                        |         |
|                 +--------------------------------------+         |
|                 |                                          |         |
|                 v                                          v         |
|  +----------------------+              +----------------------+       |
|  |                      |              |                      |       |
|  |   RTI-FSP (FSP-1)   |<----+-------|   RTI-FSP (FSP-2)   |       |
|  |   (ACSI-Server)      |  HTTP/REST   |   (ACSI-Server)      |       |
|  |   Port: 5001/5005    |              |   Port: 5005         |       |
|  |                      |              |                      |       |
|  +----------------------+              +----------------------+       |
|                                                      |                 |
|                                                      v                 |
|                                             +----------------------+    |
|                                             |                      |    |
|                                             |   RTI-SO (Client)    |    |
|                                             |   (ACSI-Client)      |    |
|                                             |   Port: 5002         |    |
|                                             |                      |    |
|                                             +----------------------+    |
|                                                                       |
|  +-----------------+                                                  |
|  |                 |                                                  |
|  |  IDP Server     |<-------------------------------------------------+
|  | (Keycloak/OAuth) |         TLS/OAuth Configuration                    |
|  |  Port: 8443     |                                                  |
|  |                 |                                                  |
|  +-----------------+                                                  |
|                                                                       |
|  +-----------------+                                                  |
|  |                 |                                                  |
|  |  Demo I/O       |<-------------------------------------------------+
|  |  (GPIO Control) |         Physical I/O Operations                     |
|  |  Port: 8000     |                                                  |
|  |                 |                                                  |
|  +-----------------+                                                  |
+-----------------------------------------------------------------------+
```

### Data Flow

HMI (React) -> HTTP REST -> BFF (FastAPI) -> HTTP/REST -> RTI-FSP (ACSI-Server)
                          BFF (FastAPI) -> HTTP/REST -> RTI-SO (ACSI-Client)

The BFF translates between:
- **Frontend**: JSON over HTTP REST
- **Backend**: JSON over HTTP/REST (to FSP/SO services)

Note: The FSP and SO services use WebSocket internally for ACSI communication, but expose REST APIs that the BFF consumes.

---

## Folder Structure

```
bff/
+-- __pycache__/              # Python cache files (generated)
+-- bff_server.py            # Main FastAPI application (1256 lines)
+-- ConnectionManager.py      # Manages connections to RTI endpoints (388 lines)
+-- DataManager.py           # Data read/write operations (55 lines)
+-- bffClient.py             # HTTP client for BFF-to-backend communication (24 lines)
+-- pydantic_models.py       # Request/Response data models (93 lines)
+-- connections.json         # Persistent connection configurations
+-- README.md                # This file
```

---

## HMI to BFF Connection

### Frontend Integration

The HMI (React application) connects to the BFF using the apiService.js module located at:
```
hmi/src/services/apiService.js
```

**Key Functions**:

1. **getBffBaseUrl()** - Retrieves BFF host/port from localStorage

2. **executeApiCall(apiId, targetValue, bodyOverride, options)** - Main API execution

3. **ensureBffHealthy()** - Health check before operations

### API Definitions

The HMI defines all available backend API endpoints in API_DEFINITIONS:
- Data operations: read, write, operate
- Model operations: model-tree, data-definition
- Control operations: operate, urcb-read, brcb-read, etc.
- OAuth: reconfigure-oauth, oauth-status
- Status: health, status

### Communication Pattern

The HMI uses two modes to communicate with the BFF:

**Mode 1: Direct API Calls**
```
HMI -> GET/POST /api/data/read -> BFF -> Returns data directly
```

**Mode 2: Dynamic Execution via /api/execute (Primary)**
```
HMI -> POST /api/execute { target: "127.0.0.1:5001", method: "POST", path: "/api/readvalue", body: {...} }
     -> BFF -> Forwards to target service -> Returns result
```

The dynamic execution mode allows the HMI to target specific backend services and have the BFF enrich requests with OAuth tokens automatically.

---

## BFF to SO/FSP Connection Flow

### Step-by-Step Data Read Operation

1. **HMI Request**: User clicks Read button, HMI calls executeApiCall
2. **BFF Receives**: FastAPI /api/execute endpoint processes request
3. **BFF Forwards**: BffClient sends HTTP request to RTI-FSP
4. **RTI-FSP Processes**: Validates objRef, reads ACSI data via WebSocket
5. **BFF Returns**: Formats response and sends back to HMI
6. **HMI Updates**: Displays data to user

### Special OAuth Handling

When HMI calls /api/reconfig-oauth, BFF automatically enriches request with OAuth fields from connections.json, allowing HMI to trigger OAuth reconfiguration without knowing sensitive credentials.

---

## Core Components

### 1. bff_server.py (Main Application)
- Framework: FastAPI with async support
- Port: 5000 (default)
- Route groups: Health, Endpoints, Connections, Data, Operate, Execute, Reports, Stats

### 2. ConnectionManager.py
- Manages all connections to RTI endpoints
- Connection types: RTI-FSP, RTI-SO, IDP-Server
- Features: Load/save connections, add/update/delete, health monitoring, auto-discovery

### 3. DataManager.py
- Executes data operations against connected endpoints
- Methods: call_remote_service, read_data, write_data, operate

### 4. bffClient.py
- HTTP client wrapper for BFF-to-backend communication
- Connection pooling, error handling, JSON parsing

### 5. pydantic_models.py
- Data validation and OpenAPI schema generation
- Models: Connection, TLS, OAuth, Data requests

---

## API Endpoints

### Health & Status
- GET /api/health - Health check with target reachability

### Endpoints Management  
- GET /api/endpoints - Get all configured and discovered endpoints

### Connection Management
- GET /api/connections - Get all connections
- POST /api/add-connection - Create new connection
- DELETE /api/delete-connection/{name} - Delete connection
- PUT /api/edit-connection/{name} - Update connection

### TLS Configuration
- POST /api/connections/tls-config - Update TLS for connection
- GET /api/connections/tls-config - Get TLS config

### OAuth Configuration
- POST /api/connections/oauth-config - Update OAuth for connection
- GET /api/connections/oauth-config - Get OAuth config
- GET /api/connections/oauth-status - Get OAuth enable status

### Data Operations
- POST /api/data/read - Read data from connection
- POST /api/data/write - Write data to connection

### Control Operations
- POST /api/operate - Perform control operation

### Dynamic Execution
- POST /api/execute - Execute any API on registered target

### Reports
- GET /api/reports - List available reports
- POST /api/reports/export - Export reports data

### Statistics
- GET /api/stats - Get system statistics

---

## Security Features

### 1. TLS Encryption
- Per-connection TLS configuration
- Supports TLSv1.2 and TLSv1.3
- Passive mode: server_key + server_cert
- Active mode: server_ca (CA certificate)

### 2. OAuth 2.0 Authentication
- Integration with IDP servers (Keycloak)
- Per-connection OAuth configuration
- Automatic token enrichment for requests
- Token refresh support

### 3. CORS Support
- Allows cross-origin requests from HMI

### 4. Input Validation
- Pydantic models for all request types
- Required field validation
- Type checking

---

## Configuration Files

### connections.json
Persistent storage of all connection configurations with:
- Connection details (host, port, type, acsi role, ws_mode)
- OAuth configuration
- TLS configuration
- Status and properties info

### Dockerfile.bff
Multi-stage Docker build with:
- Builder stage using uv for dependency management
- Runtime stage with minimal image
- Health check configuration

---

## Docker Integration

The BFF service in docker-compose.yml:
- Container: bff-server
- Port: 5000:5000
- Network: rti-network
- Volumes: connections.json persistence, Docker socket for discovery
- Depends on: Healthy bff-server for HMI

All services communicate through rti-network Docker network.

---

## Usage Examples

### Starting the BFF Server

**With Docker**:
```bash
docker-compose up bff-server
```

**Without Docker**:
```bash
python -m pip install fastapi uvicorn httpx requests
python bff_server.py
```

### Health Check
```bash
curl http://localhost:5000/api/health
```

### Dynamic Execution
```bash
curl -X POST http://localhost:5000/api/execute \
  -H "Content-Type: application/json" \
  -d '{"target": "127.0.0.1:5001", "method": "POST", "path": "/api/readvalue", "body": {"objRef": "LD0/LLN0$ST$Mod"}}'
```

### Managing Connections
```bash
# Create
curl -X POST http://localhost:5000/api/add-connection \
  -d '{"name": "my-fsp", "host": "192.168.1.100", "port": 5001, "type": "RTI-FSP", "acsi": "server", "ws_mode": "active"}'

# List
curl http://localhost:5000/api/connections

# Delete
curl -X DELETE http://localhost:5000/api/delete-connection/my-fsp
```

---

## Key Design Patterns

1. **Backend For Frontend Pattern** - Primary architectural pattern
2. **Adapter Pattern** - DataManager and BffClient adapt between frontend/backend
3. **Singleton Pattern** - Global managers instantiated once
4. **Factory Pattern** - ConnectionManager.add_connection creates connections
5. **Proxy Pattern** - BFF proxies requests to backend services

---

## Summary

The BFF folder provides a critical middleware layer that:
- Simplifies HMI interaction with multiple ACSI services
- Secures communication with TLS and OAuth
- Manages connections to RTI-FSP (ACSI-Server) and RTI-SO (ACSI-Client)
- Aggregates multiple backend calls
- Transforms data formats
- Monitors service health
- Proxies requests through unified REST API

Built on FastAPI (Python), it communicates with:
- Frontend: React HMI via HTTP REST (port 5000)
- Backend: RTI-FSP and RTI-SO via HTTP/REST (ports 5001, 5002, etc.)
- Identity: Keycloak via OAuth 2.0 (port 8443)
