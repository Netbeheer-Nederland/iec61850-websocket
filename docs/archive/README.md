<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# Archive

Plans, specs and guides for work that is finished. They are kept as a record of how and why things changed, not as
instructions: file paths and steps in them describe the repository at the time and may no longer exist. Each file
starts with a note on what became of it.

| Document | What it was |
|---|---|
| [migration-guide.md](migration-guide.md) | Porting code from the removed `WebSocketEndpoint` shim to `PassiveEndpoint` / `ActiveEndpoint` |
| [plans/2026-09-module-restructure-plan.md](plans/2026-09-module-restructure-plan.md) | Moving the rti-demo services into `examples/rti-demo/modules/` with one uv workspace |
| [plans/2026-09-13-rti-demo-docker-optimization.md](plans/2026-09-13-rti-demo-docker-optimization.md) | Multi-stage Dockerfiles for the rti-demo modules |
| [specs/2026-10-05-demo-playbook-design.md](specs/2026-10-05-demo-playbook-design.md) | Design of the HMI Playbook block |
| [plans/2026-10-05-demo-playbook.md](plans/2026-10-05-demo-playbook.md) | Implementation plan for the HMI Playbook block |
