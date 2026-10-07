<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 10. IED models are Python modules, generated from SCL in the HMI

- Status: accepted
- Date: 2026-10-07

## Context

Each FSP serves an IEC 61850 data model. The ws61850 library builds models in Python (`IedModel` with builders);
SCL files are the standard description.

## Decision

- An FSP loads its model from the Python file `MODELPATH` points at (`config/models/model_1.py`,
  `model_2.py`). The file defines `ied` or `build_ied_model()`. It's loaded with `importlib` without registering it
  in `sys.modules`, so a reload picks up a new version (model hot-swap).
- The HMI's Tools page parses SCL in the browser (`sclParser.js`) and generates that Python model code.
- Docker Compose mounts `config/models` into the FSPs.

## Consequences

- A model can be changed without rebuilding an image.
- A model file is executed code: only load models from a trusted source.
- The FSP doesn't read SCL itself; the SCL support is in the HMI.

## In the code

- `modules/fsp/src/fsp/acsi_server.py` (`load_current_runtime_model`), `modules/fsp/src/fsp/model.py`
- `modules/hmi/src/utils/sclParser.js`, `examples/rti-demo/config/models/`
- [docs/architecture/data-model-architecture.md](../../architecture/data-model-architecture.md)
