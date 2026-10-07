<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 1. Record architecture decisions

- Status: accepted
- Date: 2026-10-07

## Context

The rti-demo grew over several iterations, and most of the reasons behind its shape lived only in code comments, commit
messages.
A developer who joins now sees the result, not why it is that way.

## Decision

Record each significant design decision of the rti-demo as an architecture decision record (ADR) in this folder:

- one Markdown file per decision, `NNNN-title-in-kebab-case.md`, numbered in order;
- sections: *Context*, *Decision*, *Consequences*, and *In the code* (where to look);
- a status: `proposed`, `accepted`, `superseded by NNNN` or `deprecated`;
- an accepted record isn't rewritten. A change of mind is a new record that supersedes the old one.

## Consequences

- The index in [README.md](README.md) is the entry point; add a line there for every new record.
- A change that reverses a decision needs a new record, so the reason for the change is kept as well.
