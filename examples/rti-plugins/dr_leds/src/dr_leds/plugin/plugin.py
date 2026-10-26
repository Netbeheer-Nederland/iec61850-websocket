# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The plugin API of dr_leds, under /plugin (decision 0029).

What the FSP or SO calls (examples/rti-demo/modules/plugins/openapi.yaml, tag
Plugin API); it shows each event on the LEDs of the server:

- green: on while associated; blinks on a good Operate, write or report;
- red: on after a failed Operate, write or read, until a good one or a reset.

Settings (from /start): blink_seconds (default 0.3).
Claims: the objRefs in DR_LEDS_CLAIMS (comma-separated, default none); an
Operate on one is refused while red is on.
Routes: the server's /leds-api, under /api/plugins/dr_leds/ in the FSP or SO.
Attached (optional, decision 0025): its two LEDs, for the HMI to draw next to
the FSP or SO.
"""

from __future__ import annotations

import importlib.metadata
import os
from typing import Any

from fastapi import APIRouter, Response
from pydantic import BaseModel

from ..server.leds import SimulatedLeds

API_VERSION = 2
NAME = "dr_leds"


def _version() -> str:
    try:
        return importlib.metadata.version("dr-leds")
    except importlib.metadata.PackageNotFoundError:
        return ""


def claims() -> list[str]:
    return [c.strip() for c in os.getenv("DR_LEDS_CLAIMS", "").split(",") if c.strip()]


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


def create_plugin_router(leds: SimulatedLeds) -> APIRouter:
    """The plugin API under /plugin, showing the events on `leds`."""
    plugin = APIRouter(prefix="/plugin", tags=["Plugin API (decision 0029)"])

    @plugin.get("")
    def describe():
        return {
            "name": NAME,
            "version": _version(),
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
            # The FSP dropped its connection to the SO; its server runs on.
            leds.reset("disconnected")
        elif kind == "OperateResponse" and event.get("success"):
            leds.set("red", False, "operate succeeded")
            leds.blink("green", f"operate {obj_ref}".strip())
        elif kind == "OperateResponse":
            leds.set(
                "red", True, f"operate failed: {event.get('add_cause') or 'no cause'}"
            )
        elif kind == "ValueWritten" and event.get("ok", True):
            leds.set("red", False, "write succeeded")
            leds.blink("green", f"write {obj_ref}")
        elif kind in ("ValueWritten", "ValueRead") and not event.get("ok", True):
            leds.set("red", True, f"{kind} failed: {obj_ref}")
        elif kind == "ReportReceived":
            leds.blink("green", f"report {event.get('rpt_id')}")
        return {"ok": True}

    @plugin.get("/attached")
    def attached():
        """What this plugin attaches, for the HMI: answer what you know, fast."""
        return {
            "items": [
                {
                    "kind": "other",
                    "label": "Simulated LEDs",
                    "state": "ok",
                    "detail": "red: last Operate, write or read failed",
                    "live": [
                        {
                            "type": "indicators",
                            "items": [
                                {"name": color, "on": on, "color": color}
                                for color, on in leds.state.items()
                            ],
                        }
                    ],
                }
            ]
        }

    @plugin.post("/control")
    def control(request: ControlRequest):
        """Refuse an Operate on a claimed objRef while red is on; else leave it to the FSP."""
        if leds.state["red"]:
            return {"ok": False, "add_cause": "blockedByInterlocking"}
        return Response(status_code=204)

    return plugin
