# IEC 61850 WebSocket Proof-of-Concept

⚠️ **Project status:**  
This repository contains an **experimental proof of concept**.
It is **not production-ready** and is intended for exploration, learning, and architectural validation.

It contains a reference implementation RealTI-style for IEC 61850 communication over WebSockets.

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

Two parties exchange IEC 61850 ACSI services over a WebSocket. Either party can be the WebSocket server, independent of
which one holds the data model:

```
IEC61850Client  <-- ACSI services, reports -->  IEC61850Server
      |                                                |
  endpoint (PassiveEndpoint = WebSocket server, ActiveEndpoint = WebSocket client)
      |                                                |
  TPAA association, OAuth 2.0 bearer tokens, TLS
      |                                                |
  ASN.1 messages, JSON (JER) or BER encoded  <== WebSocket ==>
```

- `ws61850.endpoint` runs the WebSocket side and the TPAA association; `is_direct` says who starts it (see
  [docs/architecture/endpoint-architecture.md](docs/architecture/endpoint-architecture.md)).
- `ws61850.iec61850` holds the IEC 61850 client and server and the IED data model (see
  [docs/architecture/data-model-architecture.md](docs/architecture/data-model-architecture.md)).
- `ws61850.asn1` and `ws61850.protocol` encode and decode the messages defined by the ASN.1 schema.
- The RTI demo in `examples/rti-demo` builds a complete system on top: RTI-FSP (IEC 61850 server), RTI-SO (IEC 61850
  client), a BFF and a React HMI.

---

## Repository structure

```
iec61850-websocket/
├─ pyproject.toml, uv.lock         # uv workspace: ws61850 plus the rti-demo bff, fsp and so modules
├─ src/ws61850/
│  ├─ endpoint/                    # PassiveEndpoint / ActiveEndpoint, association handling, routing
│  ├─ transport/                   # WebSocket transport, reconnect policy, sessions, auth strategies
│  ├─ iec61850/
│  │  ├─ client/                   # IEC61850Client
│  │  ├─ server/                   # IEC61850Server, control and report handling
│  │  ├─ services/                 # ACSI services: directory, data access, control, reports
│  │  └─ data_model/               # IED model classes, builders, JSON loader, CDC registry
│  ├─ protocol/                    # message types, factory and codec shared by client and server
│  ├─ asn1/                        # ASN.1 schema and encode/decode
│  ├─ security/                    # TLS configuration, OAuth 2.0 (tokens, JWKS, JWT validation)
│  └─ shared/                      # errors, references, tree rendering
├─ tests/
│  ├─ unit/                        # unit tests (pytest), run in CI
│  ├─ integration/                 # FT1-FT8 functional scenarios
│  ├─ performance/                 # FT20-FT23 encoding, multiple clients, OAuth + TLS
│  └─ security/                    # FT30-FT31 TLS and OAuth
├─ testing/                        # test support: certificates, IED models, helpers
├─ examples/                       # library examples and the RTI demo (see examples/README.md)
├─ docs/                           # getting started, architecture, protocol specification (see docs/README.md)
└─ scripts/keycloak/               # Keycloak (IDP-Server) for the OAuth scenarios
```

---

## Getting started

### Prerequisites

- **UV** - [Install UV](https://docs.astral.sh/uv/getting-started/installation/)
- **Python 3.10-3.12** (3.12 recommended) - [Download Python](https://www.python.org/downloads/), or use a package
  manager like `apt`, `brew`, or `chocolatey`. including the libraries python3-dev, python3-bitstruct.
- **Git** - [Install Git](https://git-scm.com/downloads)
- **Docker** - [Install Docker](https://docs.docker.com/get-docker/)
- **Docker Compose** - [Install Docker Compose](https://docs.docker.com/compose/install/)
- **cfssl** - [Install cfssl](https://github.com/cloudflare/cfssl/releases) – used for TLS certificate generation
- **doxygen** - [Install doxygen](https://www.doxygen.nl) - used to generate documentation (optional)

- Basic understanding of:
    - Async Python
    - WebSockets
    - IEC 61850 terminology (Logical Node, Data Object)

---

### Setup environment

If the prerequisites are already installed, the environment can be set up using the following commands:

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

```bash
# 3. Build the project
uv build
```

or for a more detailed setup see [docs/getting-started.md](docs/getting-started.md).

---

## Running tests

The unit tests run in CI and are the quickest check that everything works:

```bash
uv run pytest tests/unit -q
```

The functional and performance scenarios in `tests/` are intended to be run from the repository root with `uv`.
Start by installing dependencies with `uv sync`, then open the markdown description for the scenario you want to run in
`tests/integration/`, `tests/performance/`, or `tests/security/`.

Most tests follow the same pattern: start the passive side first, for example
`uv run python tests/performance/FT20/ws_server.py`, and then start the active side in
another terminal, for example `uv run python tests/performance/FT20/ws_client.py`.

Some scenarios also require extra setup such as generated TLS certificates in `testing/certs/` or a local Keycloak
instance started with `docker compose -f scripts/keycloak/docker-compose.yml up`; those prerequisites are documented in
the corresponding test markdown files.

---

## Examples

Example clients, servers, and interactive demos live under the `examples/` directory in this repository. It also
describes how to run them in the [README](examples/README.md).

## Where next

| You want to... | Read |
|---|---|
| install and verify the project | [docs/getting-started.md](docs/getting-started.md) |
| understand or change the library | [docs/architecture/](docs/architecture/README.md) |
| run the examples or the RTI demo | [examples/README.md](examples/README.md), [examples/rti-demo/README.md](examples/rti-demo/README.md) |
| read the protocol | [docs/protocol_specification/](docs/protocol_specification/RTI_2.0_Protocol_Specification.md) |
| contribute a change | [CONTRIBUTING.md](CONTRIBUTING.md) |

## Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull
requests to us.

## License

This project is licensed under the Apache License, version 2.0 – see LICENSE for details

## Licenses third-party code

This project includes third-party code, which is licensed under their own respective Open-Source licenses.
SPDX-License-Identifier headers are used to show which license is applicable. The license texts are in
[docs/LICENSES](docs/LICENSES).
