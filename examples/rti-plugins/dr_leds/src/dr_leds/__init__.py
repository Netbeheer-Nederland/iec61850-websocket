# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""Sample plugin: shows what the FSP or SO does on two simulated LEDs
(decisions 0029 and 0030).

- dr_leds.server: the LEDs and their routes, /leds-api (the script dr-leds,
  or python -m dr_leds.server.main);
- dr_leds.plugin: the plugin API under /plugin, which the FSP and SO connect to.

It needs only FastAPI; it doesn't import anything of the FSP or SO.
"""
