<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 13. Demo playbooks run in the BFF

- Status: accepted
- Date: 2026-10-07

## Context

A demo is a series of steps: link an FSP, read, write, operate, enable a report, wait. It should be repeatable from
the HMI, from the command line and as an integration test. Details:
[2026-10-05-demo-playbook-design.md](../../archive/specs/2026-10-05-demo-playbook-design.md).

## Decision

- A playbook is a YAML (or JSON) list of steps. The runner is in the BFF package (`bff/playbook.py`) and calls the
  BFF the same way the HMI does, so every step shows on the Traffic page.
- `playbooks/run.py` (CLI) and the integration test use the same runner.
- Storage: built-in playbooks from `examples/rti-demo/playbooks` (read-only) and saved ones (recordings, uploads) on
  the `bff-config` volume. A built-in name can't be overwritten.
- The BFF does all YAML parsing and writing; the HMI exchanges JSON with it.
- One run at a time, in a worker thread; progress goes to the browsers as `playbook-run` events on `/ws`.
- A recording stores the steps in order with a fixed pace, not the time between clicks.

## Consequences

- A recording made in the HMI runs unchanged from the CLI and in CI.
- No YAML library in the HMI.
- A second run while one is going is refused.

## In the code

- `modules/bff/src/bff/playbook.py`, `playbook_store.py`, `playbook_runs.py`
- `examples/rti-demo/playbooks/`, `modules/hmi/src/components/PlaybookBar.jsx`
