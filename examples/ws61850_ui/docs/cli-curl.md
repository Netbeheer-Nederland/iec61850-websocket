# BFF curl reference

All examples assume the BFF is running on `http://localhost:8100` (the default `BFF_PORT` from `.env.example`).

---

## The two targets

The BFF manages two independent, concurrent processes — each with its own WebSocket connection, thread, and event loop.
Every `/api/*` endpoint accepts an optional `"target"` field in the JSON body (or `?target=` query param for GETs).
Omitting it defaults to `rti-so`.

| Target          | Transport role                                | IEC 61850 role | Demo component |
|-----------------|-----------------------------------------------|----------------|----------------|
| `rti-so` *(default)* | `ws_server` — listens for inbound connections | `iec_client` | RTI-SO: BFF accepts connections from RTI-FSP |
| `rti-fsp`       | `ws_client` — dials out to a remote endpoint  | `iec_server`   | RTI-FSP: BFF connects to RTI-SO and serves a data model |

> Old target names `server-client` and `client-server` are accepted as aliases for backwards compatibility.

---

## Starting both processes

```bash
BFF=http://localhost:8100

# Target 1: rti-so (ws_server + iec_client)
# BFF opens a WebSocket listener on port 9000; RTI-FSP connects to us.
curl -s -X POST $BFF/api/connect \
  -H "Content-Type: application/json" \
  -d '{
    "target":    "rti-so",
    "port":      9000,
    "cp":        "cp1",
    "is_server": true
  }' | python3 -m json.tool
```

```bash
BFF=http://localhost:8100

# Target 2: rti-fsp (ws_client + iec_server)
# BFF dials out to RTI-SO at rti-so:9100; acts as IEC 61850 server.
# is_server=false  → transport role ws_client (dials out)
# application_role → IEC 61850 role on that link
curl -s -X POST $BFF/api/connect \
  -H "Content-Type: application/json" \
  -d '{
    "target":           "rti-fsp",
    "url":              "rti-so",
    "port":             9100,
    "cp":               "cp1",
    "is_server":        false,
    "application_role": "iec_server"
  }' | python3 -m json.tool

# Note: is_direct defaults to false (reverse/ws61850 mode).
# Pass "is_direct": true only when connecting to a legacy direct-mode endpoint.
```

---

## Checking status of both targets

```bash
# Both targets in one call
curl -s $BFF/api/statuses | python3 -m json.tool
# → {"rti-so": {...}, "rti-fsp": {...}}

# Individual targets
curl -s "$BFF/api/status?target=rti-so"  | python3 -m json.tool
curl -s "$BFF/api/status?target=rti-fsp" | python3 -m json.tool
```

Expected `state` values during the connection lifecycle:

| State           | Meaning                                       |
|-----------------|-----------------------------------------------|
| `not-connected` | No process started                            |
| `listening`     | `ws_server` waiting for an inbound connection |
| `connecting`    | `ws_client` dialling out                      |
| `connected`     | WebSocket + IEC handshake complete            |
| `error`         | Failed — check `detail.error`                 |

---

## Connection lifecycle

```bash
# rti-so: BFF listens (ws_server + iec_client)
curl -s -X POST $BFF/api/connect \
  -H "Content-Type: application/json" \
  -d '{"target": "rti-so", "port": 9000, "cp": "cp1", "is_server": true}' \
  | python3 -m json.tool
```

```bash
# rti-fsp: BFF dials out (ws_client + iec_server)
curl -s -X POST $BFF/api/connect \
  -H "Content-Type: application/json" \
  -d '{"target": "rti-fsp", "url": "rti-so", "port": 9100, "cp": "cp1", "application_role": "iec_server"}' \
  | python3 -m json.tool
```

```bash
# Connect with TLS + OAuth
curl -s -X POST $BFF/api/connect \
  -H "Content-Type: application/json" \
  -d '{
    "target":   "rti-so",
    "url":      "device.example.com",
    "port":     443,
    "cp":       "cp1",
    "security": {"enableTLS": true, "enableOAuth": true}
  }' | python3 -m json.tool
```

```bash
# Disconnect rti-so target
curl -s -X POST $BFF/api/disconnect \
  -H "Content-Type: application/json" \
  -d '{"target": "rti-so"}' | python3 -m json.tool
```

```bash
# Disconnect rti-fsp target
curl -s -X POST $BFF/api/disconnect \
  -H "Content-Type: application/json" \
  -d '{"target": "rti-fsp"}' | python3 -m json.tool
```

---

## Model browsing

```bash
# Get model build status (triggers build if not yet started)
curl -s "$BFF/api/model?target=rti-so" | python3 -m json.tool

# Force rebuild
curl -s -X POST $BFF/api/model/rebuild \
  -H "Content-Type: application/json" \
  -d '{"target": "rti-so"}' | python3 -m json.tool

# List a logical device's directory
curl -s "$BFF/api/ld/LD0?target=rti-so" | python3 -m json.tool

# Get logical node details
curl -s "$BFF/api/ln/LD0/MMXU1?target=rti-so" | python3 -m json.tool

# Get data object definition (sub-DOs, DAs)
curl -s "$BFF/api/dodef/LD0/MMXU1/TotW?target=rti-so" | python3 -m json.tool
```

---

## Data read / write

```bash
# List functional constraints for a data object
curl -s -X POST $BFF/api/getfcs \
  -H "Content-Type: application/json" \
  -d '{"objRef": "LD0/MMXU1.TotW", "target": "rti-so"}' | python3 -m json.tool

# Read a value (fc = functional constraint)
curl -s -X POST $BFF/api/readvalue \
  -H "Content-Type: application/json" \
  -d '{"objRef": "LD0/MMXU1.TotW.mag.f", "fc": "MX", "target": "rti-so"}' | python3 -m json.tool

# Write a value
curl -s -X POST $BFF/api/writevalue \
  -H "Content-Type: application/json" \
  -d '{"objRef": "LD0/MMXU1.TotW.mag.f", "fc": "MX", "value": 1500.0, "dataType": "float", "target": "rti-so"}' \
  | python3 -m json.tool
```

---

## Control (select-before-operate)

```bash
# Select a controllable object
curl -s -X POST $BFF/api/control/select \
  -H "Content-Type: application/json" \
  -d '{"objRef": "LD0/CSWI1.Pos.Oper", "target": "rti-so"}' | python3 -m json.tool

# Operate — use ctlNum returned by select
curl -s -X POST $BFF/api/control/operate \
  -H "Content-Type: application/json" \
  -d '{"objRef": "LD0/CSWI1.Pos.Oper", "ctlVal": true, "ctlNum": 1, "target": "rti-so"}' \
  | python3 -m json.tool

# Cancel a pending control
curl -s -X POST $BFF/api/control/cancel \
  -H "Content-Type: application/json" \
  -d '{"objRef": "LD0/CSWI1.Pos.Oper", "target": "rti-so"}' | python3 -m json.tool
```

---

## Report control blocks (RCB)

```bash
# Read URCB values
curl -s -X POST $BFF/api/rcb/values \
  -H "Content-Type: application/json" \
  -d '{"rcbRef": "LD0/LLN0.RP.urcb01", "rcbType": "URCB", "target": "rti-so"}' | python3 -m json.tool

# Read BRCB values
curl -s -X POST $BFF/api/rcb/values \
  -H "Content-Type: application/json" \
  -d '{"rcbRef": "LD0/LLN0.BR.brcb01", "rcbType": "BRCB", "target": "rti-so"}' | python3 -m json.tool

# Enable reporting on a URCB
curl -s -X POST $BFF/api/rcb/set \
  -H "Content-Type: application/json" \
  -d '{"rcbRef": "LD0/LLN0.RP.urcb01", "rcbType": "URCB", "values": {"RptEna": true}, "target": "rti-so"}' \
  | python3 -m json.tool
```

---

## Diagnostics

All diagnostic endpoints accept `?target=rti-so`, `?target=rti-fsp`, or no target (returns both merged).

```bash
# Action log — last 200 operations with timing, one target
curl -s "$BFF/api/actions?target=rti-so"  | python3 -m json.tool
curl -s "$BFF/api/actions?target=rti-fsp" | python3 -m json.tool

# Action log — both targets merged and sorted by id
curl -s $BFF/api/actions | python3 -m json.tool

# WebSocket message log — last 500 frames
curl -s "$BFF/api/messages?target=rti-so"  | python3 -m json.tool
curl -s "$BFF/api/messages?target=rti-fsp" | python3 -m json.tool

# Drain buffered report-update events (clears the queue)
curl -s "$BFF/api/report-updates?target=rti-so"  | python3 -m json.tool
curl -s "$BFF/api/report-updates?target=rti-fsp" | python3 -m json.tool

# Clear message log (one target or both)
curl -s -X POST $BFF/api/messages/clear \
  -H "Content-Type: application/json" \
  -d '{"target": "rti-so"}' | python3 -m json.tool

# Get / set message retention limit (50–5000)
curl -s $BFF/api/messages/settings | python3 -m json.tool
curl -s -X POST $BFF/api/messages/settings \
  -H "Content-Type: application/json" \
  -d '{"limit": 1000}' | python3 -m json.tool
```

---

## Scripted helpers

```bash
BFF=http://localhost:8100

# Poll a target until connected
wait_connected() {
  local TARGET=$1
  echo "Waiting for $TARGET..."
  until curl -s "$BFF/api/status?target=$TARGET" \
        | python3 -c "import sys,json; s=json.load(sys.stdin); sys.exit(0 if s.get('state') in ('connected','listening') else 1)"
  do sleep 2; done
  echo "$TARGET connected."
}

wait_connected rti-so
wait_connected rti-fsp

# Pretty-print all current statuses
curl -s $BFF/api/statuses | python3 -m json.tool
```
