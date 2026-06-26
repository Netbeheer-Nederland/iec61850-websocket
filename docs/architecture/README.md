# Development Documentation

Architecture and developer guides for the `ws61850` library.

## Contents

| Document | What it covers |
|---|---|
| [setup.md](setup.md) | Step-by-step installation guide for Ubuntu and Fedora (all prerequisites, project setup, verification) |
| [endpoint-architecture.md](endpoint-architecture.md) | Module layout of `ws61850.endpoint`, class responsibilities, `is_direct` semantics, reused infrastructure |
| [migration-guide.md](migration-guide.md) | How to update code from the old `WebSocketEndpoint` shim to `PassiveEndpoint` / `ActiveEndpoint` |
| [logging.md](logging.md) | Logger names, log levels emitted at each layer, and how to configure log output |
| [data-model-architecture.md](data-model-architecture.md) | Data model class design, protocol coupling to ASN1, builder/loader pattern, CDC registry, bugs fixed |

## Context

The endpoint layer was refactored from a single 859-line `WebSocketEndpoint` class controlled by a runtime `mode` string into two focused concrete classes (`PassiveEndpoint`, `ActiveEndpoint`) with shared infrastructure extracted into reusable helpers. The backward-compatible `WebSocketEndpoint` shim remains for existing callers.

See the individual documents for details.
