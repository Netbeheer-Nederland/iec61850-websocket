<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 0009. The images carry the OCI labels, and the published ones are connected to the repository

- Status: done (2026-10-29, commit f3bb194)
- Date: 2026-10-29
- Changes: Dockerfiles, `.github/workflows/images.yml`

## Goal

Every image says what it is, where its source is, which commit and version it was built from, and under which
license, in the standard `org.opencontainers.image.*` keys. On ghcr.io, each package is then connected to
`netbeheernederland/iec61850-websocket` (shown on the repository's page, with its description and license on the
package's page), also when an image is built and pushed by hand.

## Now

- No Dockerfile has a `LABEL`. The images inherit whatever their base image sets (`nginx:alpine`: `maintainer`).
- `images.yml` builds `rti-so`, `rti-fsp`, `rti-bff`, `rti-hmi` and `dr-panel` (`push: false` for now), and passes
  `docker/metadata-action`'s `labels` to `docker/build-push-action`. Those are metadata-action's defaults, taken from
  the repository: `title` is `iec61850-websocket` and `description` the repository's description for all five
  images; `source`, `url`, `version`, `created`, `revision` and `licenses` are right.
- `so`, `fsp`, `dr-panel` are multi-platform (`linux/amd64,linux/arm64`): an image index, whose own manifest has no
  annotations. ghcr.io reads a multi-platform package's description and license from the index, so even with labels
  the package page would show none.
- `dr-leds` has a Dockerfile but isn't built by `images.yml`.

## Proposal

### Which keys, and where each is set

The pre-defined annotation keys of the OCI image spec (`annotations.md`), used as labels on the image and as
annotations on the manifest and index. The old `org.label-schema.*` keys and `MAINTAINER` are not used.

| Key                                      | Value                                                                                      | Set in         |
|------------------------------------------|--------------------------------------------------------------------------------------------|----------------|
| `org.opencontainers.image.source`        | `https://github.com/netbeheernederland/iec61850-websocket`                                 | Dockerfile, CI |
| `org.opencontainers.image.title`         | the image name: `rti-so`, `rti-fsp`, `rti-bff`, `rti-hmi`, `dr-panel`, `dr-leds`           | Dockerfile, CI |
| `org.opencontainers.image.description`   | one sentence, at most 512 characters (ghcr.io's limit); see below                          | Dockerfile, CI |
| `org.opencontainers.image.licenses`      | `Apache-2.0` (an SPDX expression, at most 256 characters)                                  | Dockerfile, CI |
| `org.opencontainers.image.vendor`        | `Netbeheer Nederland`                                                                      | Dockerfile     |
| `org.opencontainers.image.url`           | the repository URL                                                                         | Dockerfile, CI |
| `org.opencontainers.image.documentation` | the module's README on `main`, e.g. `.../blob/main/examples/rti-demo/modules/so/README.md` | Dockerfile     |
| `org.opencontainers.image.version`       | the tag's version (`1.4.0`), else the branch or `pr-12`                                    | CI only        |
| `org.opencontainers.image.revision`      | the full commit SHA                                                                        | CI only        |
| `org.opencontainers.image.created`       | the build time, RFC 3339                                                                   | CI only        |

The rule: what doesn't change between builds is a `LABEL` in the Dockerfile, so a local `docker build` gets it too;
what changes per build (`version`, `revision`, `created`) comes from CI only. Putting those in the Dockerfile through
`ARG`s would make local images claim a version they aren't, and `created` would bust the layer cache on every build.

Not used: `authors` (no person or address to name; `vendor` says who), `ref.name` (the tag says it),
`base.name` and `base.digest` (see Open questions).

Descriptions, from the members' `pyproject.toml` where they have one:

- `rti-so`: "RTI demo SO: ACSI client, WebSocket passive side (IEC 61850 over WebSocket)"
- `rti-fsp`: "RTI demo FSP: ACSI server, WebSocket active side (IEC 61850 over WebSocket)"
- `rti-bff`: "RTI demo BFF: the backend for the HMI"
- `rti-hmi`: "RTI demo HMI: the web interface, served by nginx"
- `dr-panel`: "RTI demo plugin dr_panel: GPIO and I2C control of the demonstrator panel on a Raspberry Pi"
  - `dr-leds`: "RTI demo plugin dr_leds: two simulated LEDs that show what the FSP or SO does"

### The Dockerfiles

One `LABEL` instruction, in the final stage only (labels set in a build stage don't reach the image), right after
its `FROM`, so the static keys override anything inherited from the base image:

```dockerfile
FROM python:3.13-slim-bookworm AS runtime

LABEL org.opencontainers.image.source="https://github.com/netbeheernederland/iec61850-websocket" \
      org.opencontainers.image.url="https://github.com/netbeheernederland/iec61850-websocket" \
      org.opencontainers.image.documentation="https://github.com/netbeheernederland/iec61850-websocket/blob/main/examples/rti-demo/modules/so/README.md" \
      org.opencontainers.image.title="rti-so" \
      org.opencontainers.image.description="RTI demo SO: ACSI client, WebSocket passive side (IEC 61850 over WebSocket)" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.vendor="Netbeheer Nederland"
```

`source` is the one GitHub's documentation asks for: an image pushed to ghcr.io with it is connected to that
repository, whoever pushes it. The value is the repository's URL exactly, without `.git` or a path.

### The workflow

1. **Per-image title and description.** `--label` on the command line wins over `LABEL` in the Dockerfile, so
   metadata-action's defaults would overwrite them with the repository's. The `img` step sets `title` and
   `description` per image (as it sets `name`), and metadata-action gets them in its `labels:` input:

   ```yaml
   labels: |
     org.opencontainers.image.title=${{ steps.img.outputs.title }}
     org.opencontainers.image.description=${{ steps.img.outputs.description }}
     org.opencontainers.image.vendor=Netbeheer Nederland
   ```

   The same values as in the Dockerfile; a test (below) keeps them equal.
2. **Annotations on the index.** metadata-action's step gets `DOCKER_METADATA_ANNOTATIONS_LEVELS: manifest,index`
   in its `env`, and build-push-action `annotations: ${{ steps.meta.outputs.annotations }}`. ghcr.io then shows the
   description and license of the multi-platform images too. For the single-platform ones (`rti-bff`, `rti-hmi`)
   the image's labels are enough, but the same setting is used for all five.
3. `licenses` comes from the repository (metadata-action reads it from GitHub: `Apache-2.0`); no override.
4. `provenance: false` stays; the labels don't depend on it.

### dr-leds

Gets the Dockerfile labels. It isn't added to `images.yml` by this spec.

## Acceptance

- `docker build` of each of the six Dockerfiles, then `docker inspect --format '{{json .Config.Labels}}'`: the seven
  static keys with the values above, and no `version`, `revision` or `created`.
- A CI build of each of the five images: `docker buildx imagetools inspect --format '{{json .Manifest}}'` of the
  index shows `title`, `description`, `source`, `licenses`, `version`, `revision` and `created` as annotations, and
  each platform's image has the same as labels; `title` and `description` are the image's own, not the repository's.
- Once `push` is on: each package on ghcr.io is listed under the repository's Packages, with its description and
  `Apache-2.0`, the multi-platform ones included.
- An image built locally and pushed by hand to `ghcr.io/netbeheernederland/iec61850-websocket/<name>` is connected
  to the repository as well.

## Tests

`tests/unit/test_image_labels.py`, reading the files (as `test_rti_demo_io_image.py` does):

- Every Dockerfile under `examples/` has exactly one `LABEL` with the seven static keys, in its last stage, and
  `source` is the same URL everywhere.
- No Dockerfile sets `version`, `revision` or `created`.
- `description` is at most 512 characters and `licenses` matches the repository's license (`REUSE.toml`).
- For each image in `images.yml`'s `case`, `title` and `description` equal the ones in its Dockerfile.
- `images.yml` passes `annotations` to build-push-action and sets `DOCKER_METADATA_ANNOTATIONS_LEVELS` to
  `manifest,index`.

## Docs to update

A new decision, [0041](../decisions/0041-oci-image-labels.md); the specs and decisions READMEs; the rti-demo README
(the images carry the labels, CI adds version, revision and creation time) and the rti-plugins README (the `LABEL` of
a copied plugin).

## Answered

- `base.name` / `base.digest`: not now. `base.digest` is only right when the `FROM` is pinned by digest, and none is;
  both can come with pinning.
- A copied plugin: a comment above its `LABEL` says to change `source`, `url` and `documentation`.
- The GitLab mirror: its registry ignores `source`; nothing to do.
