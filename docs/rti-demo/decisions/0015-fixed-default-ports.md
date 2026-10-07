<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 15. Fixed default ports, pinned by a test

- Status: accepted
- Date: 2026-10-07

## Context

Ports are set in many places: code defaults, Dockerfiles, Docker Compose, `launch.py`, Vite, nginx, seed
connections, integration tests and docs. The old set clashed: the HMI used 3000, IO and Keycloak both used 8080.

## Decision

| Service  | Port                                                                                               |
|----------|----------------------------------------------------------------------------------------------------|
| HMI      | 8080 (nginx listens on 80 in the container)                                                        |
| BFF      | 3000                                                                                               |
| RTI-SO   | 5000 REST, 8765 WebSocket                                                                          |
| RTI-FSP  | 5001, second instance 5005                                                                         |
| IO       | 9000                                                                                               |
| Keycloak | 8081 (`KC_HTTP_PORT`, the same inside and outside the container, so the token issuer is identical) |

A service listens on the same port; however, it's started (directly, `launch.py` or Docker). `PORT` overrides it.
`tests/unit/test_rti_demo_ports.py` reads every place that sets a port and fails when one disagrees.

## Consequences

- A port change is a change to that table in the test plus every place it then reports.
- Existing installations keep old ports in saved browser settings and in the `bff-config` volume; the
  rti-demo README describes the upgrade.

## In the code

- `tests/unit/test_rti_demo_ports.py`
- `examples/rti-demo/README.md` ("Upgrading from the old ports")
