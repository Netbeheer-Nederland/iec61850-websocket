# BFF API Documentation

This document lists all REST API endpoints exposed by `bff_endpoint.py` in the `rti-demo/fsp` folder. Each endpoint includes its HTTP method, path, usage, parameters, and expected return values.

---



## 2. Get Server Status
- **GET** `/api/iec61850server/status`
  - **Description:** Returns the current status of the IEC 61850 WebSocket server.
  - **Returns:**
    - On success: `{ "ok": true, ...status fields... }`
    - On error: `{ "ok": false, "error": "..." }`, HTTP 500

---

## 3. Get Connections
- **GET** `/api/iec61850server/connections`
  - **Description:** Returns TPA (Three Part Address) and connection info for all connected clients.
  - **Returns:**
    - On success: `{ "ok": true, "server_role": "ACSI_Server", "ws_mode": "passive", "connected_clients": <int>, "connections": [ ... ] }`
    - On error: `{ "ok": false, "error": "..." }`, HTTP 500

---

## 4. Get Model Descriptor
- **GET** `/api/iec61850server/model`
  - **Description:** Returns the current loaded model descriptor for UI rendering.
  - **Returns:**
    - On success: `{ "status": "ready", "model": { ... } }`
    - On error: `{ "ok": false, "error": "..." }`, HTTP 500

---

## 5. Update IED Model
- **POST** `/api/iec61850server/update-iedmodel`
  - **Description:** Updates `model.py` in the fsp directory and reloads the IED model.
  - **Body:** JSON `{ "modelPy": <string> }`
  - **Returns:**
    - On success: `{ "ok": true, "source": <str>, "ied": <str> }`
    - On error: `{ "ok": false, "error": "..." }`, HTTP 400

---

## 6. Start Server
- **POST** `/api/iec61850server/start`
  - **Description:** Starts the IEC 61850 WebSocket server.
  - **Body:** JSON `{ "host": <str>, "port": <int>, "mode": "server", "cp": <str> }` (all optional)
  - **Returns:**
    - On success: `{ "ok": true, "status": "starting", "host": <str>, "port": <int> }`
    - On error: `{ "ok": false, "error": "..." }`, HTTP 400

---

## 7. Stop Server
- **POST** `/api/iec61850server/stop`
  - **Description:** Stops the IEC 61850 WebSocket server.
  - **Returns:**
    - On success: `{ "ok": true, "status": "stopped" }` or `{ "ok": true, "status": "stopping" }`
    - On error: `{ "ok": false, "error": "..." }`, HTTP 500

---

## 8. Get Server Actions
- **GET** `/api/iec61850server/actions`
  - **Description:** Returns the logged server actions.
  - **Returns:** `{ "actions": [ ... ] }` or `{ "ok": false, "error": "..." }`, HTTP 500

---

## 9. Clear Server Actions
- **POST** `/api/iec61850server/actions/clear`
  - **Description:** Clears the server action log.
  - **Returns:** `{ "ok": true }` or `{ "ok": false, "error": "..." }`, HTTP 500

---

## 10. Get Protocol Messages
- **GET** `/api/iec61850server/messages`
  - **Description:** Returns the logged protocol messages.
  - **Returns:** `{ "messages": [ ... ] }` or `{ "ok": false, "error": "..." }`, HTTP 500

---

## 11. Clear Protocol Messages
- **POST** `/api/iec61850server/messages/clear`
  - **Description:** Clears the protocol message log.
  - **Returns:** `{ "ok": true }` or `{ "ok": false, "error": "..." }`, HTTP 500

---

## 12. Read Value
- **POST** `/api/iec61850server/readvalue`
  - **Description:** Reads a value from the server IED model.
  - **Body:** JSON `{ "objRef": <str>, "fc": <str> (optional) }`
  - **Returns:**
    - On success: `{ "ok": true, "success": true, "objRef": <str>, "fc": <str>, "values": [ ... ] }`
    - On error: `{ "ok": false, "error": "..." }`, HTTP 400/404/500/503/504

---

## 13. Write Value
- **POST** `/api/iec61850server/writevalue`
  - **Description:** Writes a value in the server IED model.
  - **Body:** JSON `{ "objRef": <str>, "value": <any>, "fc": <str> (optional), "dataType": <str> (optional) }`
  - **Returns:**
    - On success: `{ "ok": true, "success": true, "objRef": <str>, "fc": <str>, "value": <any>, "dataType": <str> }`
    - On error: `{ "ok": false, "error": "..." }`, HTTP 400/404/500/503/504

---

## Notes
- All endpoints return JSON.
- Error responses include an `ok: false` and an `error` message.
- Some endpoints may return HTTP 400, 404, 500, 503, or 504 depending on the error.
- Authentication is not described in this file (see implementation for details if needed).
