# Client BFF API Documentation

This document lists all REST API endpoints exposed by `bff_endpoint.py` in the `rti-demo/so` folder. Each endpoint includes its HTTP method, path, usage, parameters, expected return values, and a curl example for testing.

---

## 1. Get Client Status
- **GET** `/api/iec61850client/status`
  - **Description:** Returns the current status of the IEC 61850 WebSocket client.
  - **Curl Example:**
    ```bash
    curl http://localhost:5002/api/iec61850client/status
    ```
  - **Returns:**
    - On success: `{ "status": "connected|disconnected|connecting", "host": <str>, "port": <int>, "cp": <str>, "error": <str|null>, "modelStatus": <str>, "modelError": <str|null> }`
    - On error: `{ "ok": false, "error": "..." }`, HTTP 500

---

## 2. Get Connections
- **GET** `/api/iec61850client/connections`
  - **Description:** Returns connection information to the server.
  - **Curl Example:**
    ```bash
    curl http://localhost:5002/api/iec61850client/connections
    ```
  - **Returns:**
    - On success: `{ "ok": true, "status": <str>, "connected": <bool>, "server_role": "ACSI_Client", "ws_mode": "passive", "connection": { "peer_address": <str>, "peer_port": <int>, "local_role": "ACSI_Client", "ws_mode": "passive", "remote_role": "ACSI_Server", "cp": <str> } }`
    - On error: `{ "ok": false, "error": "..." }`, HTTP 500

---

## 3. Connect to Server
- **POST** `/api/iec61850client/connect`
  - **Description:** Connects to an IEC 61850 WebSocket server.
  - **Curl Example:**
    ```bash
    curl -X POST http://localhost:5002/api/iec61850client/connect \
      -H "Content-Type: application/json" \
      -d '{"host": "localhost", "port": 8765, "cp": "cp1"}'
    ```
  - **Body:** JSON `{ "host": <str>, "port": <int>, "cp": <str> }` (all optional; defaults: localhost, 8765, cp1)
  - **Returns:**
    - On success: `{ "ok": true, "status": "connecting", "host": <str>, "port": <int>, "cp": <str> }`
    - On error: `{ "ok": false, "error": "..." }`, HTTP 400/503

---

## 4. Disconnect from Server
- **POST** `/api/iec61850client/disconnect`
  - **Description:** Disconnects from the IEC 61850 WebSocket server.
  - **Curl Example:**
    ```bash
    curl -X POST http://localhost:5002/api/iec61850client/disconnect
    ```
  - **Returns:**
    - On success: `{ "ok": true, "status": "disconnected" }` or `{ "ok": true, "status": "disconnecting" }`
    - On error: `{ "ok": false, "error": "..." }`, HTTP 500

---

## 5. Get Client Actions
- **GET** `/api/iec61850client/actions`
  - **Description:** Returns the logged client actions.
  - **Curl Example:**
    ```bash
    curl http://localhost:5002/api/iec61850client/actions
    ```
  - **Returns:** `{ "actions": [ ... ] }` or `{ "ok": false, "error": "..." }`, HTTP 500

---

## 6. Clear Client Actions
- **POST** `/api/iec61850client/actions/clear`
  - **Description:** Clears the client action log.
  - **Curl Example:**
    ```bash
    curl -X POST http://localhost:5002/api/iec61850client/actions/clear
    ```
  - **Returns:** `{ "ok": true }` or `{ "ok": false, "error": "..." }`, HTTP 500

---

## 7. Get Protocol Messages
- **GET** `/api/iec61850client/messages`
  - **Description:** Returns the logged protocol messages.
  - **Curl Example:**
    ```bash
    curl http://localhost:5002/api/iec61850client/messages
    ```
  - **Returns:** `{ "messages": [ ... ] }` or `{ "ok": false, "error": "..." }`, HTTP 500

---

## 8. Clear Protocol Messages
- **POST** `/api/iec61850client/messages/clear`
  - **Description:** Clears the protocol message log.
  - **Curl Example:**
    ```bash
    curl -X POST http://localhost:5002/api/iec61850client/messages/clear
    ```
  - **Returns:** `{ "ok": true }` or `{ "ok": false, "error": "..." }`, HTTP 500

---

## 9. Read Value
- **POST** `/api/iec61850client/readvalue`
  - **Description:** Reads a value from the connected server.
  - **Curl Example:**
    ```bash
    curl -X POST http://localhost:5002/api/iec61850client/readvalue \
      -H "Content-Type: application/json" \
      -d '{"objRef": "LD0.LLN0.Mod.stVal"}'
    ```
  - **Body:** JSON `{ "objRef": <str> }`
  - **Returns:**
    - On success: `{ "ok": true, "success": true, "objRef": <str>, "value": <any> }`
    - On error: `{ "ok": false, "error": "..." }`, HTTP 400/404/500/503/504

---

## 10. Write Value
- **POST** `/api/iec61850client/writevalue`
  - **Description:** Writes a value to the connected server.
  - **Curl Example:**
    ```bash
    curl -X POST http://localhost:5002/api/iec61850client/writevalue \
      -H "Content-Type: application/json" \
      -d '{"objRef": "LD0.LLN0.Mod.stVal", "value": "on"}'
    ```
  - **Body:** JSON `{ "objRef": <str>, "value": <any> }`
  - **Returns:**
    - On success: `{ "ok": true, "success": true, "objRef": <str>, "value": <any> }`
    - On error: `{ "ok": false, "error": "..." }`, HTTP 400/404/500/503/504

---

## Notes
- All endpoints return JSON.
- Error responses include an `ok: false` and an `error` message.
- Some endpoints may return HTTP 400, 404, 500, 503, or 504 depending on the error.
- Status values: `connecting`, `connected`, `disconnecting`, `disconnected`, `error`
- Model status values: `idle`, `building`, `ready`, `error`
