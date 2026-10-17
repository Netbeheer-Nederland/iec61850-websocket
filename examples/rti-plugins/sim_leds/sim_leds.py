# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""Sample plugin: shows what the FSP or SO does on two simulated LEDs.

A plugin is an HTTP service that implements the plugin API
(examples/rti-demo/modules/plugins/openapi.yaml, decision 0029). This one
needs only FastAPI; it doesn't import anything of the FSP or SO.

- green: on while associated; blinks on a good Operate, write or report;
- red: on after a failed Operate, write or read, until a good one or a reset.

Run it:

    uv run --no-project --with fastapi --with uvicorn \\
      uvicorn sim_leds:app --app-dir examples/rti-plugins/sim_leds --port 8099

and configure {"name": "sim_leds", "url": "http://localhost:8099/plugin"} in
the FSP or SO.

Settings (from /start): blink_seconds (default 0.3).
Claims: the objRefs in SIM_LEDS_CLAIMS (comma-separated, default none); an
Operate on one is refused while red is on.
Routes, under /api/plugins/sim_leds/ in the FSP or SO:
- GET  /leds              the LEDs and what changed them;
- POST /leds/{color}      {"on": true|false}, set one by hand;
- POST /leds/reset        both off.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Response
from leds import COLORS, SimulatedLeds
from pydantic import BaseModel

API_VERSION = 2

leds = SimulatedLeds()


def claims() -> list[str]:
    return [c.strip() for c in os.getenv("SIM_LEDS_CLAIMS", "").split(",") if c.strip()]


# ==================== The plugin API ====================


class Host(BaseModel):
    name: str
    role: str
    host_url: str | None = None


class StartRequest(Host):
    settings: dict[str, Any] = {}


class EventRequest(BaseModel):
    host: Host
    event: dict[str, Any]


class ControlRequest(BaseModel):
    host: Host
    obj_ref: str
    ctl_val: dict[str, Any] = {}


plugin = APIRouter(prefix="/plugin")


@plugin.get("")
def describe():
    return {
        "name": "sim_leds",
        "version": "2.0.0",
        "api": API_VERSION,
        "claims": claims(),
        "routes": "/leds-api",
    }


@plugin.post("/start")
def start(request: StartRequest):
    leds.blink_seconds = float(request.settings.get("blink_seconds", 0.3))
    return {"ok": True}


@plugin.post("/stop")
async def stop(host: Host):
    await leds.close()
    return {"ok": True}


@plugin.post("/events")
async def on_event(request: EventRequest):
    """Match on the event's type; ignore the types this plugin doesn't know."""
    event = request.event
    kind = event.get("type")
    obj_ref = event.get("obj_ref") or ""
    if kind == "Associated":
        leds.set("green", True, f"associated {event.get('associate_id')}")
    elif kind == "ServerStopped":
        leds.reset("server stopped")
    elif kind == "OperateResponse" and event.get("success"):
        leds.set("red", False, "operate succeeded")
        leds.blink("green", f"operate {obj_ref}".strip())
    elif kind == "OperateResponse":
        leds.set("red", True, f"operate failed: {event.get('add_cause') or 'no cause'}")
    elif kind == "ValueWritten" and event.get("ok", True):
        leds.set("red", False, "write succeeded")
        leds.blink("green", f"write {obj_ref}")
    elif kind in ("ValueWritten", "ValueRead") and not event.get("ok", True):
        leds.set("red", True, f"{kind} failed: {obj_ref}")
    elif kind == "ReportReceived":
        leds.blink("green", f"report {event.get('rpt_id')}")
    return {"ok": True}


@plugin.post("/control")
def control(request: ControlRequest):
    """Refuse an Operate on a claimed objRef while red is on; else leave it to the FSP."""
    if leds.state["red"]:
        return {"ok": False, "add_cause": "blockedByInterlocking"}
    return Response(status_code=204)


# ==================== Its own routes ====================


class LedState(BaseModel):
    on: bool


routes = APIRouter(prefix="/leds-api")


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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await leds.close()


app = FastAPI(title="sim_leds plugin", lifespan=lifespan)
app.include_router(plugin)
app.include_router(routes)
