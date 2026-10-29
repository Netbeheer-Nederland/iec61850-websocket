<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 43. The HMI takes LOG_LEVEL and --log-level, as the FSP, SO and BFF do

- Status: proposed
- Date: 2026-10-29

## Context

The FSP, SO and BFF read `LOG_LEVEL`, and `--log-level` wins over it. The HMI had no log level: its 48 `console.*`
calls always showed, and `LOG_LEVEL` for the stack didn't reach it. Its nginx logged at the image's default level.
[Spec 0008](../specs/0008-hmi-log-level.md) asked for the same setting as the other services, and decided on a URL
parameter and a Settings page choice.

## Decision

1. **`src/utils/log.js` is the HMI's only way to the console**: `log.error`, `log.warn`, `log.info`, `log.debug`, each
   calling the console's method only at or above the level. `critical` shows errors, as `error` does. A test fails on
   any other `console.` call in `src/`.
2. **The names and fallback of `resolve_log_level`**: case-insensitive, `trace` as `debug`, a number as it is, and an
   unknown or empty value is `info`.
3. **The first source that is set wins**, even with an unknown value, as `--log-level` does over `LOG_LEVEL`:
   `?log=` in the URL (read once at load, so it survives navigation and not a reload without it), the Settings page
   (localStorage `rti-hmi-log-level`, applied without a reload), the container's `LOG_LEVEL` (`window.RTI_CONFIG`),
   the build's `VITE_LOG_LEVEL`, then `info`. The URL is on top, as for decision 0014's BFF address the Settings page
   is: a link turns on debug without changing anything stored.
4. **At build time, `--log-level` wins over `LOG_LEVEL`**, which wins over `VITE_LOG_LEVEL`. `vite.config.js` puts the
   value in `VITE_LOG_LEVEL`. Vite's CLI reads `--log-level` as its own `--logLevel` too, so with `--log-level` given,
   `vite.config.js` sets a `customLogger` at Vite's own `--logLevel` (or `info`).
5. **The container's `LOG_LEVEL` also sets nginx's error log**, in `conf.d/00-rti-log-level.conf` at http level:
   `debug` → `info` (nginx's `debug` needs a debug build), `info` → `notice`, `warning` → `warn`, `error` and
   `critical` → `error`. Unset, the file is removed and nginx keeps its default. The access log stays on.
6. **`docker-compose.yml` passes `LOG_LEVEL=${LOG_LEVEL:-info}` to every service**, so one variable sets the stack.
7. The level in use and its source are logged once at start, at `info`: `HMI log level: debug (from LOG_LEVEL)`.

## Consequences

- `LOG_LEVEL=debug docker compose up -d` makes the HMI's debug messages show, and `LOG_LEVEL=error` hides warnings.
- Debug goes to `console.debug`, which Chrome shows only with "Verbose" on.
- The two `console.log` calls are now debug: they no longer show at the default level.
- New HMI code logs through `log`; the test says where otherwise.
- `40-rti-config.sh` takes `RTI_CONFIG_JS` and `RTI_NGINX_LOG_CONF` to write elsewhere, for its test.

## In the code

- `examples/rti-demo/modules/hmi/src/utils/log.js`, `src/main.jsx`, `src/pages/Settings.jsx`, every `console.` caller in
  `src/`
- `examples/rti-demo/modules/hmi/vite.config.js`, `vite.log-level.js`
- `examples/rti-demo/modules/hmi/docker/40-rti-config.sh`
- `examples/rti-demo/docker-compose.yml`
- Tests: `src/utils/log.test.js`, `src/noConsole.test.js`, `src/pages/Settings.test.jsx`, `vite.log-level.test.js`,
  `tests/unit/test_hmi_runtime_config.py`
