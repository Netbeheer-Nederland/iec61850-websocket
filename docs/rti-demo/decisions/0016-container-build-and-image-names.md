<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 16. Container builds and image names

- Status: accepted
- Date: 2026-10-07

## Context

The SO, FSP and BFF depend on the ws61850 library in the repository's `src/` and share one uv lock. Images should
be buildable locally and also published to GitHub, and the demo should run too without retagging.

## Decision

- One uv workspace at the repository root (members `bff`, `fsp`, `so`; one `uv.lock`). Each Dockerfile installs
  its member with `uv sync --package <name>`, from the committed lock.
- The BFF, SO and FSP images build from the repository root (they need the lock and `src/`); the HMI and IO images
  build from their own module folder.
- Multi-stage builds; the runtime stage has no build tools. Health checks read `$PORT` when they run, so one image
  serves several instances (the second FSP on 5005).
- Images are named `${RTI_IMAGE_REPO}/rti-<role>:${RTI_IMAGE_TAG}`. The default repo is
  `netbeheer-nederland/iec61850-websocket`; the published one is `ghcr.io/netbeheer-nederland/iec61850-websocket`.
- The services join the external network `rti-network`, which Keycloak (a separate Compose project under
  `scripts/keycloak`) also joins.

## Consequences

- A local `docker compose build` produces exactly the images the demo runs.
- `rti-network` must exist before `docker compose up` (`docker network create rti-network`).
- The `io` image is built and locked separately; see [0011](0011-io-separate-project-runtime-plugin.md).

## In the code

- `examples/rti-demo/docker-compose.yml`, `modules/*/docker/Dockerfile`, root `pyproject.toml`
- `.github/workflows/images.yml`
