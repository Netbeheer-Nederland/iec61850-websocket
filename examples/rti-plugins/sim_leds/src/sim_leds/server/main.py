# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""Run sim_leds: sim-leds, or python -m sim_leds.server.main.

HOST (default 127.0.0.1) and PORT (default 8099) say where it listens; an FSP
or SO configures {"name": "sim_leds", "url": "http://<host>:8099/plugin"}.
"""

import os

import uvicorn

from .app import create_app


def main() -> None:
    uvicorn.run(
        create_app(),
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8099")),
    )


if __name__ == "__main__":
    main()
