<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 41. Every image carries the OCI labels; static ones in the Dockerfile, per-build ones from CI

- Status: proposed
- Date: 2026-10-29

## Context

The six images (`rti-so`, `rti-fsp`, `rti-bff`, `rti-hmi`, `dr-panel`, `dr-leds`) had no `LABEL`, so an image said
nothing about what it is or where it came from, and an image pushed to ghcr.io isn't connected to the repository unless
it carries `org.opencontainers.image.source`. `images.yml` passed `docker/metadata-action`'s default labels, which are
the repository's: every image was titled `iec61850-websocket`, with the repository's description. The multi-platform
images (`rti-so`, `rti-fsp`, `dr-panel`, `dr-leds`) are an image index, and ghcr.io reads a multi-platform package's
description and license from the index's annotations, which there were none of.

[Spec 0009](../specs/0009-image-labels.md) asked for the labels.

## Decision

1. **The pre-defined keys of the OCI image spec**, `org.opencontainers.image.*`; not the old `org.label-schema.*` or
   `MAINTAINER`.
2. **What doesn't change between builds is a `LABEL` in the Dockerfile**, in the final stage, right after its `FROM`:
   `source` and `url` (`https://github.com/netbeheernederland/iec61850-websocket`), `documentation` (the module's
   README on `main`), `title` (the image name), `description` (one sentence, at most 512 characters), `licenses`
   (`Apache-2.0`) and `vendor` (`Netbeheer Nederland`). A local `docker build` has them too, and an image pushed by
   hand is connected to the repository.
3. **What changes per build comes from CI only**: `version`, `revision` and `created`, from metadata-action. Not as
   `ARG`s in the Dockerfile: a local image would claim a version it isn't, and `created` would break the layer cache.
4. **CI repeats `title`, `description` and `vendor`**, as labels and annotations: `--label` wins over the
   Dockerfile's `LABEL`, and metadata-action's defaults would put the repository's back. The values are in the `case`
   of the `img` step, next to the image's name.
5. **Annotations on each platform's manifest and on the index**
   (`DOCKER_METADATA_ANNOTATIONS_LEVELS: manifest,index`), for every image.
6. `tests/unit/test_image_labels.py` keeps it so: every Dockerfile under `examples/` has the seven static keys in its
   last stage and none of the per-build ones, `licenses` is the project's license, and `images.yml` builds each
   Dockerfile with the same title and description.

Not used: `authors` (`vendor` says who), `ref.name` (the tag says it), `base.name` and `base.digest`. `base.digest` is
only right for a `FROM` pinned by digest, and none is; both can come with pinning.

## Consequences

- Once `images.yml` pushes, each package on ghcr.io is listed under the repository, with its own description and
  license, the multi-platform ones included.
- A new image needs the `LABEL` and a line in the `img` step with the same title and description; the test fails
  otherwise.
- A plugin copied from `examples/rti-plugins` to another repository (decision 0030) has to change `source`, `url` and
  `documentation`; a comment above its `LABEL` says so.
- Changing the repository's name or owner changes the labels in six Dockerfiles and the test's `REPO`.
- The GitLab mirror's registry ignores `source`; nothing changes there.

## In the code

- `examples/rti-demo/modules/{so,fsp,bff,hmi}/docker/Dockerfile`, `examples/rti-plugins/{dr_panel,dr_leds}/docker/Dockerfile`
- `.github/workflows/images.yml`
- `tests/unit/test_image_labels.py`
