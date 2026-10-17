# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""Sample plugin: shows what the FSP or SO does on two simulated LEDs
(decisions 0029 and 0030).

- sim_leds.server: the LEDs and their routes, /leds-api (the script sim-leds,
  or python -m sim_leds.server.main);
- sim_leds.plugin: the plugin API under /plugin, which the FSP and SO connect to.

It needs only FastAPI; it doesn't import anything of the FSP or SO.
"""
