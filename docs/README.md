<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# Documentation

Project documentation that spans more than one module. How to run or change a single example or demo service is in
that module's own README under `examples/` (see [examples/README.md](../examples/README.md)).

## Start here

| Document | What it covers |
|---|---|
| [getting-started.md](getting-started.md) | Install the prerequisites on Ubuntu or Fedora, set up the project, check that it works |

## Contents

```
docs/
├─ README.md                              # this index
├─ getting-started.md                     # installation and first run
├─ architecture/                          # how the ws61850 library is built
│  ├─ endpoint-architecture.md            #   WebSocket endpoints (passive/active), is_direct
│  ├─ data-model-architecture.md          #   IED data model, builders, JSON loading, CDC registry
│  └─ logging.md                          #   logger names and levels, configuring output
├─ protocol_specification/
│  ├─ RTI_2.0_Protocol_Specification.md   # RTIv2 protocol specification
│  ├─ example_messages/                   # example JSON messages
│  └─ media/                              # figures referenced by the spec
├─ rti-demo/                              # the RTI demo as a whole
│  ├─ README.md                           #   system overview: components, communication, data model, flows
│  ├─ design/                             #   HMI style guide, log kinds, playbook design, wireframe, whiteboard
│  ├─ decisions/                          #   architecture decision records (why it is built this way)
│  └─ images/                             #   architecture diagrams (also used by the module READMEs)
├─ scl/
│  └─ rti_v1.0.scd                        # SCL file used for the PoC
├─ doxygen/
│  └─ Doxyfile                            # Doxygen configuration for the API reference
├─ LICENSES/                              # full texts of the third-party packages' licenses
└─ THIRD_PARTY_LICENSES.txt               # which third-party package uses which license
```

## Generate the API reference (Doxygen)

From the repository root, run:

```bash
doxygen docs/doxygen/Doxyfile
```

The HTML is written to `docs/doxygen/html/index.html` (not tracked in git). Install `doxygen` first; see
[getting-started.md](getting-started.md#7-doxygen-optional).
