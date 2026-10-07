<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 1. Record architecture decisions

- Status: accepted
- Date: 2026-10-07

## Context

The rti-demo grew over several iterations (milestone 1, the module restructure, the playbooks, the logging kinds,
the port change). Most of the reasons behind its shape lived only in code comments, commit messages and finished
plans under `docs/archive/`. A developer who joins now sees the result, not why it is that way.

## Decision

Record each significant design decision of the rti-demo as an architecture decision record (ADR) in this folder:

- one Markdown file per decision, `NNNN-title-in-kebab-case.md`, numbered in order;
- sections: *Context*, *Decision*, *Consequences*, and *In the code* (where to look);
- a status: `proposed`, `accepted`, `superseded by NNNN` or `deprecated`;
- an accepted record isn't rewritten. A change of mind is a new record that supersedes the old one.

Records 0002 to 0017 were written afterwards, on 2026-10-07, from the code and the existing docs. They describe
decisions already in place.

## Consequences

- The index in [README.md](README.md) is the entry point; add a line there for every new record.
- A change that reverses a decision needs a new record, so the reason for the change is kept as well.
