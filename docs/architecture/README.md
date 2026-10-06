# Development Documentation

Architecture and developer guides for the `ws61850` library. To install and set up the project, see
[../getting-started.md](../getting-started.md).

## Contents

| Document | What it covers |
|---|---|
| [endpoint-architecture.md](endpoint-architecture.md) | Module layout of `ws61850.endpoint`, class responsibilities, `is_direct` semantics, reused infrastructure |
| [logging.md](logging.md) | Logger names, log levels emitted at each layer, and how to configure log output |
| [data-model-architecture.md](data-model-architecture.md) | Data model class design, protocol coupling to ASN1, builder/loader pattern, CDC registry, bugs fixed |

## Context

The endpoint layer was refactored from a single 859-line `WebSocketEndpoint` class controlled by a runtime `mode` string into two focused concrete classes (`PassiveEndpoint`, `ActiveEndpoint`) with shared infrastructure extracted into reusable helpers. The backward-compatible `WebSocketEndpoint` shim has since been removed (commit `c710a2d`); the old migration guide is in [../archive/migration-guide.md](../archive/migration-guide.md).

See the individual documents for details.
