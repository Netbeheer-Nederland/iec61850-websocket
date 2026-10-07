<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 8. Certificates as file: references to a mounted directory

- Status: accepted
- Date: 2026-10-07

## Context

The first seed `connections.json` contained PEM text, including a private key, inline. That put a key in git and
in every image, and made swapping certificates mean editing JSON.

## Decision

- A TLS or OAuth certificate field may hold `file:<name>` instead of PEM text. The SO and FSP resolve it against
  `TLS_CERT_DIR` (default `/certs`) with `ws61850.security.tls.resolve_pem`.
- Docker Compose bind-mounts `testing/certs` (or `RTI_CERTS_DIR`) read-only at `/certs` in the BFF, SO and FSPs.
- The BFF lists the files there with `GET /api/certs` (name, kind, common name); the HMI's TLS dialog offers them
  in a dropdown.
- The seed connections hold no keys or certificates.
- The BFF only lists the files; it doesn't depend on ws61850.

## Consequences

- No private keys in the repository's configuration or in the images.
- Using other certificates means pointing `RTI_CERTS_DIR` at another directory.
- Inline PEM still works, for setups without a mounted directory.

## In the code

- `src/ws61850/security/tls.py` (`resolve_pem`), `modules/bff/src/bff/cert_store.py`
- `modules/hmi/src/components/TLSConfigModal.jsx`, `testing/certs/`
