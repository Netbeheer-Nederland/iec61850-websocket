<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# rti-demo architecture decisions

Why the rti-demo is built the way it is. Each record describes one decision: its context, what was decided, the
consequences, and where to find it in the code. The format is in [0001](0001-record-architecture-decisions.md).

| # | Decision | Status |
|---|---|---|
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions | accepted |
| [0002](0002-five-separate-services.md) | Five separate services: HMI, BFF, SO, FSP and IO | accepted |
| [0003](0003-so-passive-fsp-active.md) | The SO listens, the FSPs dial out | accepted |
| [0004](0004-bff-single-gateway-execute-proxy.md) | The BFF is the HMI's only backend, with a generic execute proxy | accepted |
| [0005](0005-push-channel-central-poll.md) | One central poll in the BFF, pushed to the browsers over /ws | accepted |
| [0006](0006-connections-json-source-of-truth.md) | connections.json is the source of truth, on a volume, seeded once | accepted |
| [0007](0007-bff-reapplies-security-config.md) | The SO and FSP keep TLS and OAuth in memory; the BFF re-applies them | accepted |
| [0008](0008-certificates-as-file-references.md) | Certificates as file: references to a mounted directory | accepted |
| [0009](0009-asyncio-runtime-in-own-thread.md) | The ACSI runtime runs on its own event loop thread | accepted |
| [0010](0010-models-as-python-modules.md) | IED models are Python modules, generated from SCL in the HMI | accepted |
| [0011](0011-io-separate-project-runtime-plugin.md) | IO is a separate project; its client is a plugin loaded at runtime | accepted |
| [0012](0012-log-kinds-tagged-at-source.md) | Log entries carry a kind, set where they are written | accepted |
| [0013](0013-playbooks-run-in-the-bff.md) | Demo playbooks run in the BFF | accepted |
| [0014](0014-hmi-bff-address-resolution.md) | Where the HMI finds the BFF | accepted |
| [0015](0015-fixed-default-ports.md) | Fixed default ports, pinned by a test | accepted |
| [0016](0016-container-build-and-image-names.md) | Container builds and image names | accepted |
| [0017](0017-hardware-is-optional.md) | Raspberry Pi hardware is optional | accepted |

To add a decision, copy the layout of an existing record, take the next number, and add a line to this table.
