# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""Sample plugin: shows what the FSP or SO does on two simulated LEDs.

- green: on while associated; blinks on a good Operate, write or report;
- red: on after a failed Operate, write or read, until a good one or a reset.

Settings: blink_seconds (default 0.3).
Routes, under /api/plugins/sim_leds/:
- GET  /leds              the LEDs and what changed them;
- POST /leds/{color}      {"on": true|false}, set one by hand;
- POST /leds/reset        both off.
"""

from __future__ import annotations

from acsi_plugins import (
    AcsiPlugin,
    Associated,
    Event,
    OperateResponse,
    PluginContext,
    ReportReceived,
    ServerStopped,
    ValueRead,
    ValueWritten,
)
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .leds import COLORS, SimulatedLeds


class LedState(BaseModel):
    on: bool


class SimLedsPlugin(AcsiPlugin):
    def __init__(self):
        self.leds = SimulatedLeds()
        self.ctx: PluginContext | None = None

    async def start(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        self.leds.blink_seconds = float(ctx.settings.get("blink_seconds", 0.3))
        ctx.logger.info(f"Simulating LEDs {', '.join(COLORS)} in the {ctx.role}")

    async def stop(self) -> None:
        await self.leds.close()

    async def on_event(self, event: Event) -> None:
        match event:
            case Associated(associate_id=associate_id):
                self.leds.set("green", True, f"associated {associate_id}")
            case ServerStopped():
                self.leds.reset("server stopped")
            case OperateResponse(success=True, obj_ref=obj_ref):
                self.leds.set("red", False, "operate succeeded")
                self.leds.blink("green", f"operate {obj_ref or ''}".strip())
            case OperateResponse(add_cause=cause):
                self.leds.set("red", True, f"operate failed: {cause or 'no cause'}")
            case ValueWritten(obj_ref=obj_ref, ok=True):
                self.leds.set("red", False, "write succeeded")
                self.leds.blink("green", f"write {obj_ref}")
            case ValueWritten(obj_ref=obj_ref) | ValueRead(obj_ref=obj_ref, ok=False):
                self.leds.set("red", True, f"{type(event).__name__} failed: {obj_ref}")
            case ReportReceived(rpt_id=rpt_id):
                self.leds.blink("green", f"report {rpt_id}")

    def router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/leds")
        def get_leds():
            return self.leds.snapshot()

        @router.post("/leds/reset")
        def reset_leds():
            self.leds.reset("reset by hand")
            return self.leds.snapshot()

        @router.post("/leds/{color}")
        def set_led(color: str, body: LedState):
            if color not in COLORS:
                raise HTTPException(404, f"No LED '{color}'; there are {COLORS}")
            self.leds.set(color, body.on, "set by hand")
            return self.leds.snapshot()

        return router
