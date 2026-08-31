# RTI HMI - React Frontend

This is the React-based HMI (Human Machine Interface) for the IEC 61850 RTI Demo application, providing a modern web interface for monitoring and controlling RTI services (FSP and SO).

## Table of Contents
1. [Available Pages](#available-pages)
2. [Utilities](#utilities)
3. [Services](#services)
4. [Features](#features)
5. [Available Scripts](#available-scripts)
6. [Installation](#installation)
7. [Routing Structure](#routing-structure)
8. [Integration Notes](#integration-notes)
9. [API Dependencies](#api-dependencies)
10. [Browser Support](#browser-support)

---

## Available Pages

### 1. Setup (`/setup`)
**File**: `Setup.jsx` (16KB)

**Purpose**: Initial landing page providing an overview of all configured connections and their status.

**Features**:
- Visual instance visualization showing SO, FSP, and connections
- Connection health status monitoring
- Connection management (add, edit, delete)
- OAuth and TLS configuration access
- Auto-checks all connection health on page load
- Default route (redirects from `/`)

---

### 2. ACSI Client (`/acsi-client`)
**File**: `ACSIClient.jsx` (46KB)

**Purpose**: Interface for ACSI-Client (RTI-SO) operations - acts as a client connecting to external servers.

**Features**:
- WebSocket connection management (host, port, CP)
- IEC 61850 data model tree visualization
- Context menu for right-click operations on data objects
- Control operations (for controllable CDC types: SPC, DPC, APC, INC, ENC, BSC, ING, ASG, CTE, ENG)
- Data write operations via modal dialog
- BRCB (Buffered Report Control Block) configuration
- TLS configuration support
- OAuth authentication integration
- Protocol message monitoring
- Real-time data updates

---

### 3. ACSI Server (`/acsi-server`)
**File**: `ACSIServer.jsx` (33KB)

**Purpose**: Interface for ACSI-Server (RTI-FSP) operations - acts as a server providing the IEC 61850 data model.

**Features**:
- Server configuration (host, port, CP, mode)
- IEC 61850 data model tree visualization with expandable nodes
- Data write operations with value modification
- Tree expansion state persistence
- TLS configuration support
- OAuth authentication integration
- Protocol message monitoring
- Status information display

---

### 4. Connections (`/connections`)
**File**: `Connections.jsx` (7KB)

**Purpose**: Central connection management interface for configuring all RTI service endpoints.

**Features**:
- List all configured connections in table format
- Add new connections via modal dialog
- Edit existing connections
- Delete connections
- Connection type selection (RTI-SO, RTI-FSP, IDP-Server)
- ACSI role configuration (server/client)
- WebSocket mode selection (active/passive)
- Refresh connections list
- Connection persistence using localStorage

---

### 5. Model (`/model`)
**File**: `Model.jsx` (15KB)

**Purpose**: IEC 61850 model visualization and management page.

**Features**:
- Connection selection for model loading
- IEC 61850 data model tree display
- SCL file upload for model generation
- Model persistence and retrieval
- Tree expansion state management
- Visual instance connection graph
- Model upload status tracking

---

### 6. Traffic (`/traffic`)
**File**: `Traffic.jsx` (18KB)

**Purpose**: Traffic monitoring and data access dashboard.

**Features**:
- Visual instance visualization showing all SO, FSP, and their connections
- Multiple collapsible Data Access Panels
- Dynamic panel management (add/remove)
- Real-time message monitoring
- Connection health monitoring
- Connection reload functionality

---

### 7. Data (`/data`)
**File**: `Data.jsx` (3KB)

**Purpose**: Data visualization and display page.

**Features**:
- Simple data display interface
- Placeholder for data visualization components

**Note**: This appears to be a simpler alternative to the ACSI-specific pages for general data viewing.

---

### 8. Tools (`/tools`)
**File**: `Tools.jsx` (18KB)

**Purpose**: Utility tools for SCL file processing and model generation.

**Features**:
- **SCL Model Factory**: Parse SCL (Substation Configuration Language) XML files
  - File upload and validation
  - IED (Intelligent Electronic Device) extraction
  - AccessPoint extraction
  - Model tree generation
  - Python code generation for RTI-FSP models
- File size display
- Parse error handling
- Model preview

---

### 9. Reports (`/reports`)
**File**: `Reports.jsx` (1.5KB)

**Purpose**: Reports and logging page.

**Features**:
- Simple reports interface
- Placeholder for reporting functionality

---

### 10. Diagnostics (`/diagnostics`)
**File**: `Diagnostics.jsx` (1.6KB)

**Purpose**: System diagnostics and health monitoring page.

**Features**:
- Simple diagnostics interface
- Placeholder for diagnostic tools

---

### 11. Settings (`/settings`)
**File**: `Settings.jsx` (6KB)

**Purpose**: Application configuration and settings management.

**Features**:
- BFF server configuration (host, port)
- Settings persistence using localStorage
- Form validation
- Default settings management
- Connection to BFF health check

---

## Utilities

### `sclParser.js` (28KB)
**Purpose**: Comprehensive SCL (Substation Configuration Language) XML file parser.

**Capabilities**:
- XML parsing and validation
- IED (Intelligent Electronic Device) extraction
- AccessPoint extraction
- Data object extraction
- Model tree generation
- Python code generation for RTI-FSP models
- Generate complete `model.py` files with proper structure

**Exported Functions**:
- `generateModelPyCode(sclContent, options)` - Main function to generate Python model code from SCL

### `modelUtils.js` (4KB)
**Purpose**: Model data transformation utilities.

**Exported Functions**:
- `transformModelToTree(modelData)` - Convert model data to tree structure for display

---

## Services

### `apiService.js` (8KB)
**Purpose**: Centralized service for all HMI ↔ BFF communication.

**Key Features**:
- Standardized API call execution through `/api/execute` endpoint
- API endpoint definitions for all backend operations
- BFF base URL configuration from localStorage
- Target value building (host:port)
- Health check functionality
- Direct and dynamic API execution modes

**Exported Functions**:
- `getApiById(id)` - Get API definition by ID
- `getBffBaseUrl()` - Get configured BFF base URL
- `buildBffApiUrl(path, targetValue)` - Build complete API URL
- `executeApiCall(apiId, targetValue, bodyOverride, options)` - Main API execution function
- `ensureBffHealthy()` - Verify BFF is accessible
- `buildTargetValue(host, port)` - Create target identifier string
- `getDefaultTargetFromEndpoint(endpoint)` - Get target from endpoint object

**API Definitions** (25+ endpoints):
- Connection management: connect, disconnect
- Model operations: model-tree, data-definition
- Data operations: read, write, operate
- Dataset operations: dataset-directory
- Logs: actions-logs, clear-logs
- Status: status, health
- Control: operate
- Report Control Blocks: urcb-read, brcb-read, brcb-write, urcb-write
- ACSI Server: start, stop, model, update-iedmodel
- OAuth: reconfigure-oauth, oauth-status, messages, clear_messages

---

## Features

- **React 18** with functional components and hooks
- **React Router v6** for client-side SPA navigation
- **Vite** for fast development, HMR, and optimized production builds
- **State management** using React hooks (useState, useEffect, useCallback, useRef, useMemo)
- **Responsive design**
- **Form handling** with controlled components
- **Modal dialogs** for complex operations
- **Context menus** for right-click interactions
- **Real-time monitoring** of connections and messages
- **Local storage persistence** for settings and connections

---

## Available Scripts

### `npm run dev`
Runs the app in development mode with Hot Module Replacement (HMR). Open [http://localhost:3000](http://localhost:3000) to view it in the browser. Auto-refreshes on code changes.

### `npm run build`
Builds the app for production to the `dist` folder. Optimized and minified for deployment.

### `npm run preview`
Serves the production build locally for testing. Useful for verifying the build before deployment.

---

## Installation

```bash
# Navigate to the hmi folder
cd path/to/rti-demo/hmi

# Install dependencies
npm install

# Start development server
npm run dev

# Or build for production
npm run build
```

---

## Routing Structure

The application uses React Router v6 with the following route structure:

```
/
├── /setup (default)              → Setup.jsx
├── /connections                → Connections.jsx
├── /model                       → Model.jsx
├── /traffic                     → Traffic.jsx
├── /data                        → Data.jsx
├── /reports                     → Reports.jsx
├── /diagnostics                 → Diagnostics.jsx
├── /tools                       → Tools.jsx
├── /settings                    → Settings.jsx
├── /acsi-client                 → ACSIClient.jsx
├── /acsi-server                 → ACSIServer.jsx
└── * (404)                      → Redirects to /setup
```

**Navigation**: The `Sidebar` component provides navigation links to all pages. The `Header` component displays the current BFF connection status.

---

## Integration Notes

- The frontend communicates exclusively with the **BFF (Backend For Frontend)** server
- BFF host and port are configurable via the **Settings** page
- All configuration is persisted in browser **localStorage**
- Connection management is centralized and shared across all pages
- API endpoints are defined in `apiService.js` and executed through the `/api/execute` BFF endpoint

---

## API Dependencies

The React frontend expects the following API endpoints from the BFF (port 5000):

### Health & Status
- `GET /api/health` - BFF health check
- `GET /api/endpoints` - List all configured endpoints
- `GET /api/connections` - List all connections

### Connection Management
- `POST /api/add-connection` - Create new connection
- `PUT /api/edit-connection/{name}` - Update connection
- `DELETE /api/delete-connection/{name}` - Delete connection

### Data Operations
- `POST /api/data/read` - Read data from connection
- `POST /api/data/write` - Write data to connection
- `POST /api/operate` - Perform control operation

### Model Operations
- `POST /api/model/tree` - Get model tree
- `POST /api/getDataDefinition` - Get data definitions
- `POST /api/model` - Get complete model
- `POST /api/update-iedmodel` - Update IED model

### ACSI Operations
- `POST /api/start` - Start ACSI server
- `POST /api/stop` - Stop ACSI server
- `POST /api/connect` - Connect to ACSI endpoint
- `POST /api/disconnect` - Disconnect from ACSI endpoint

### Report Control Blocks (RCB)
- `POST /api/urcb-read` - Read Unbuffered RCB
- `POST /api/brcb-read` - Read Buffered RCB
- `POST /api/urcb-write` - Write Unbuffered RCB
- `POST /api/brcb-write` - Write Buffered RCB

### OAuth Configuration
- `POST /api/reconfig-oauth` - Reconfigure OAuth settings
- `GET /api/oauth-status` - Get OAuth enable/disable status
- `GET /api/messages` - Get OAuth messages
- `POST /api/clear_messages` - Clear OAuth messages

### Dynamic Execution
- `POST /api/execute` - Execute any API on registered target (primary endpoint used by HMI)

These endpoints are implemented in the BFF server (`bff_server.py`).

---

## Browser Support

- **Chrome** (recommended)
- **Firefox**
- **Edge**
- **Safari** (latest versions)

The app uses modern JavaScript features (ES6+ modules, async/await, React 18) and requires a recent browser version.
