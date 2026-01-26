# IEC 61850 WebSocket Proof-of-Concept

This project is a **proof-of-concept (PoC)** that exposes IEC 61850 information and events to modern applications using
**WebSockets**. It demonstrates how IEC 61850 data can be consumed by web, analytics, or control platforms without requiring IEC 61850
protocol stacks on the client side.

The PoC is intentionally small, readable, and hackable.

---

## What problem does this PoC solve?

IEC 61850 is powerful but traditionally bound to MMS/TCP, and this PoC shows how to:

- Acquire or simulate IEC 61850 data
- Map it to a simple JSON representation
- Publish updates over WebSockets
- Enable near-real-time consumption by web UIs, dashboards, or integration services

---

## High-level architecture

**Flow:**

1. IEC 61850 source
    - Simulated Logical Nodes *or*
    - Real device / gateway *or*
    - Recorded data (PCAP / JSON)

2. Python backend
    - Reads / produces IEC 61850-like data
    - Normalizes it into a simple internal model
    - Publishes updates via WebSockets

3. WebSocket clients
    - Browser UI
    - Monitoring tools
    - Other backend services

---

## Project goals (PoC scope)

✔ Simple, readable Python code  
✔ Explicit separation of concerns  
✔ Push-based (event driven) updates  
✔ No heavy IEC 61850 stack required on the client

🚫 Not production-ready  
🚫 No full IEC 61850 conformance  
🚫 Security kept intentionally minimal

---

## Repository structure

```
iec61850-websocket/
├─ pyproject.toml
├─ README.md
├─ src/
│  └─ ws61850/
│     ├─ __init__.py
│     ├─ iec61850/
│     │  ├─ client/
│     │  ├─ server/
│     │  ├─ data_model/
│     │  └─ __init__.py
│     ├─ endpoint/
│     ├─ security/
│     │  ├─ tls.py
│     │  └─ oauth.py
│     └─ asn1/
├─ tests/
│  ├─ unit/
│  ├─ integration/
│  ├─ performance/
│  └─ conftest.py
├─ examples/
├─ docs/
└─ scripts/
```
---

## Getting started

### 1. Prerequisites

- Python **3.10+**
- `uv` **or** `pip`
- Basic understanding of:
  - Async Python
  - WebSockets
  - IEC 61850 terminology (Logical Node, Data Object)

---

### 2. Setup environment

Using **uv** (recommended):

```bash
uv venv
uv sync

