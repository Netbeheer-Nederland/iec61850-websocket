# IEC 61850 WebSocket Proof-of-Concept

> Experimental reference implementation for IEC 61850 Phase 2 / RTI-style communication over WebSockets.

⚠️ **Project status:**  
This repository contains an **experimental proof of concept**.
It is **not production-ready** and is intended for exploration, learning, and architectural validation.

## Overview

This project explores how **IEC 61850-based information models and messages** can be transported using **modern web
technologies**, specifically **WebSockets**, while remaining aligned with:

- IEC 61850 concepts and data modeling
- ASN.1-based encoding/decoding
- Secure communication patterns (TLS, OAuth-based concepts)
- Event-driven, asynchronous communication

The codebase is intentionally kept small and explicit, serving as a **reference and discussion vehicle**, not a full
protocol stack.

---

## What problem does this PoC solve?

IEC 61850 is powerful but traditionally bound to MMS/TCP, and this PoC shows how to:

### In scope

- ASN.1 schema loading and message encoding/decoding
- WebSocket-based client/server communication
- Demonstration of message flows
- Security concepts at PoC level
- Clear separation between protocol, transport, and examples

### Explicitly out of scope

- Production-grade robustness
- Performance optimization (however a performance test is a key goal for this PoC)
- Complete IEC 61850 profile coverage
- Formal conformance testing
- Long-term API stability

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

## Repository structure

```
iec61850-websocket/
├─ pyproject.toml
├─ README.md
├─ src/
│  └─ ws61850/
│     ├─ iec61850/                 # Client/server logic and IEC 61850 data model helpers
│     │  ├─ client/                # IEC 61850 WebSocket client implementations
│     │  ├─ server/                # IEC 61850 WebSocket server implementations
│     │  ├─ data_model/            # IEC 61850 data model abstractions and helpers
│     ├─ endpoint/                 # WebSocket endpoint implementation
│     ├─ security/
│     │  ├─ tls.py                 # TLS configuration container and helpers
│     │  └─ oauth.py               # OAuth utilities for client identification
│     └─ asn1/                     # ASN.1 schema, encode/decode, formatters, and tests
├─ tests/                          # Functional and performance-oriented test suites
│  ├─ unit/                        # Unit-level tests
│  ├─ integration/                 # Integration and protocol-level tests
│  ├─ performance/                 # Performance and load tests
│  └─ conftest.py                  # Shared pytest configuration and fixtures
├─ examples/                       # Example clients/servers and interactive demos
├─ docs/                           # Generated and hand-written documentation (e.g. Doxygen, specs)
│  └─ protocol_specification/      # IEC61850 WebSocket protocol specification
└─ scripts/                        # Helper scripts (setup, tooling, test helpers)
```

---

## Getting started

### Prerequisites

- **UV** - [Install UV](https://docs.astral.sh/uv/getting-started/installation/)
- **Python 3.10-3.12** (3.12 recommended) - [Download Python](https://www.python.org/downloads/)
- **Git** - [Install Git](https://git-scm.com/downloads)
- **Docker** - [Install Docker](https://docs.docker.com/get-docker/)
- **Docker Compose** - [Install Docker Compose](https://docs.docker.com/compose/install/)
- **sfssl** - [Install sfssl](https://github.com/cloudflare/cfssl/releases) – used for TLS certificate generation
- **doxygen** - [Install doxygen](https://www.doxygen.nl) - used to generate documentation (optional)

- Basic understanding of:
    - Async Python
    - WebSockets
    - IEC 61850 terminology (Logical Node, Data Object)

### Setup environment

```shell
# Clone the repository
# 1. Clone and enter the project
git clone https://github.com/Netbeheer-Nederland/iec61850-websocket.git
cd iec61850-websocket
```

```bash
# 2. Create and activate a virtual environment
uv venv
uv sync
```

```shell
# 3. Add the development environment to uv 
uv sync -e dev
```


