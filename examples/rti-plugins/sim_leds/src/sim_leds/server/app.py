# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The sim_leds app: the LEDs' own routes and the plugin API.

Routes, under /api/plugins/sim_leds/ in the FSP or SO:
- GET  /leds              the LEDs and what changed them;
- POST /leds/{color}      {"on": true|false}, set one by hand;
- POST /leds/reset        both off.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel

from ..plugin import create_plugin_router
from .leds import COLORS, SimulatedLeds


class LedState(BaseModel):
    on: bool


def create_leds_router(leds: SimulatedLeds) -> APIRouter:
    routes = APIRouter(prefix="/leds-api", tags=["LEDs"])

    @routes.get("/leds")
    def get_leds():
        return leds.snapshot()

    @routes.post("/leds/reset")
    def reset_leds():
        leds.reset("reset by hand")
        return leds.snapshot()

    @routes.post("/leds/{color}")
    def set_led(color: str, body: LedState):
        if color not in COLORS:
            raise HTTPException(404, f"No LED '{color}'; there are {COLORS}")
        leds.set(color, body.on, "set by hand")
        return leds.snapshot()

    return routes


def create_app(leds: SimulatedLeds | None = None) -> FastAPI:
    leds = leds or SimulatedLeds()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        await leds.close()

    app = FastAPI(title="sim_leds plugin", lifespan=lifespan)
    app.include_router(create_plugin_router(leds))
    app.include_router(create_leds_router(leds))
    app.state.leds = leds
    return app
