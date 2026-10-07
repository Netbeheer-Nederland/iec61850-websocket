<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 14. Where the HMI finds the BFF

- Status: accepted
- Date: 2026-10-07

## Context

The HMI is a static bundle that runs in the user's browser, so the BFF address has to be one the browser can reach.
That differs per setup: `localhost` on a laptop, the Raspberry Pi's address on a LAN. Rebuilding the image per
setup isn't practical.

## Decision

The HMI takes the first of:

1. the address saved on the HMI's Settings page (`localStorage`);
2. runtime config: `window.RTI_CONFIG` from `/config.js`, which the container writes at start from `BFF_HOST` and
   `BFF_PORT` (Compose: `HMI_BFF_HOST`, `HMI_BFF_PORT`);
3. build time: `VITE_BFF_HOST`, `VITE_BFF_PORT`;
4. `localhost:3000`.

Each field falls back on its own. No HMI source file other than `src/config.js` holds a BFF address.

## Consequences

- One image works on every host; the address is set when the container starts.
- An address saved in a browser stays there after the defaults change, until the user changes it or clears the site
  data.

## In the code

- `modules/hmi/src/config.js`, `modules/hmi/docker/40-rti-config.sh`
- `tests/unit/test_rti_demo_ports.py` (`test_hmi_takes_the_bff_address_from_config_js`)
