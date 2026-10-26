<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 0008. The HMI takes LOG_LEVEL, as the FSP, SO and BFF do

- Status: draft
- Date: 2026-10-25
- Changes: HMI (bundle, container, dev server)

## Goal

Set how much the HMI logs the same way as for the other services: `LOG_LEVEL` in the environment, or a log level on
the command line. One value for the whole stack (`LOG_LEVEL=debug docker compose up`) then also reaches the HMI.

## Now

- The FSP, SO and BFF read `LOG_LEVEL` at start, and `--log-level` on their command line wins over it
  (`resolve_log_level` in each `bff_endpoint.py` / `bff_server.py`). Names are case-insensitive: `critical`, `error`,
  `warning`, `info`, `debug`, `trace` (as `debug`), or a number; an unknown or empty value is `info`.
- The HMI has no log level. Its code calls `console.error` (38), `console.warn` (8) and `console.log` (2) directly,
  and the browser always shows them all.
- The HMI's container runs nginx. `docker/40-rti-config.sh` writes `/config.js` (`window.RTI_CONFIG`) from `BFF_HOST`
  and `BFF_PORT` when the container starts; `src/config.js` reads it, then the build-time `VITE_BFF_*`, then a
  default. nginx logs every request, and its error log at its default level.
- `npm run dev` (Vite) has its own `--logLevel` (`info`, `warn`, `error`, `silent`) for the dev server's output only.
- `docker-compose.yml` sets no `LOG_LEVEL` for any service.

## Proposal

### The level and where it comes from

The same names and fallback as `resolve_log_level`, in a new `src/utils/log.js`. Highest first; as for the BFF
address, with the URL on top:

1. **The URL**: `?log=debug` on any page, for a link that turns on debug without changing anything. It lasts while
   the page is open (navigating within the HMI keeps it); a reload without it drops it.
2. **The Settings page**, kept in the browser's localStorage, for one user while looking into a problem.
3. **Runtime**: `LOG_LEVEL` of the container. `40-rti-config.sh` adds `logLevel` to `window.RTI_CONFIG`.
4. **Build time**: `VITE_LOG_LEVEL`, or `LOG_LEVEL` in the environment of `npm run dev` / `npm run build`
   (`vite.config.js` passes it on with `define`).
5. `info`.

### The command line

- `npm run dev -- --log-level debug` and `npm run build -- --log-level debug`: `vite.config.js` reads `--log-level`
  from the command line and it wins over `LOG_LEVEL`, as in the Python services. Vite's own `--logLevel` stays as it
  is.
- `LOG_LEVEL=debug npm run dev` does the same from the environment.

### The bundle

- `log.js` exports `log.error`, `log.warn`, `log.info`, `log.debug`, which call the console's method only at or above
  the level. `critical` shows errors only, like `error`.
- Every direct `console.*` call in `src/` goes through `log`. The two `console.log` calls become `log.debug`. A test
  checks that no `console.` call is left in `src/` outside `log.js` and the tests.
- The level in use is logged once at start, at `info`: "HMI log level: debug (from LOG_LEVEL)".

### The container

- `40-rti-config.sh` writes `logLevel` from `LOG_LEVEL`, escaped as `BFF_HOST` is; left out when unset or empty.
- nginx's error log follows it: `debug` → `info` (nginx's `debug` needs a debug build), `info` → `notice`, `warning`
  → `warn`, `error` and `critical` → `error`. The access log stays on at every level.
- `docker-compose.yml` passes `LOG_LEVEL=${LOG_LEVEL:-info}` to the HMI, and to the FSPs, SO and BFF where it is
  missing, so one variable sets the whole stack.

### Settings page

A "Log level" select under the BFF address: "From the server (info)" and the six names. The choice is kept in
localStorage and applies straight away, without a reload. While `?log=` is in the URL, the select says the URL's
level is in use.

## Acceptance

- `LOG_LEVEL=debug` on the container: the HMI's debug messages show in the browser console, and the start message
  says the level and where it comes from. `LOG_LEVEL=error`: warnings no longer show.
- `npm run dev -- --log-level warning` wins over `LOG_LEVEL=debug`.
- A level chosen on the Settings page wins over `LOG_LEVEL` and stays after a reload; "From the server" goes back to
  it.
- `?log=debug` wins over both, until the page is reloaded without it.
- An unknown value (`LOG_LEVEL=loud`) is `info`, and the start message says so.
- No `LOG_LEVEL`: the HMI behaves as today, except the two `console.log` calls, which are now debug.

## Tests

- `log.test.js`: name resolution (case, numbers, `trace`, unknown, empty), the order of the sources (URL, Settings,
  runtime, build time, default), and which console methods are called at each level.
- `Settings.test.jsx`: the select stores and clears the choice, which applies without a reload.
- A test that `src/` has no `console.` calls outside `log.js` and the tests.
- `40-rti-config.sh`: `/config.js` with and without `LOG_LEVEL`, and the nginx error log level it sets (a shell test,
  as for `BFF_HOST`).
- `vite.config.js`: `--log-level` wins over `LOG_LEVEL`.

## Docs to update

HMI README (configuration: `LOG_LEVEL`, `--log-level`, the order), `examples/rti-demo/README.md` (one `LOG_LEVEL` for
the stack), `docs/architecture/logging.md` (the HMI), the wireframe (Settings).

## Answered

- The Settings page choice: yes, as source 2.
- A URL parameter: yes, `?log=<level>`, as source 1.
- Sending the HMI's errors to the BFF (to the Diagnostics activity log): no.
