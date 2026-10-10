# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The IO plugin on the plugin contract (decision 0021).

The FSP and SO tell it what happens (an association, an Operate, a write,
a report); it shows that on the IO server's LEDs and LCDs, and passes writes
on to the devices mapped to the objRef. Which devices react to what is in
io_mapping.json; the names it uses there for events ("connected",
"oper_rcv", ...) are the plugin's own.

Settings (`POST /api/plugins` "settings", or PLUGINS):
- io_url: the IO server (default: IO_URL, else the server the plugin came from);
- acsi_url: where the IO server writes input device changes to, this FSP
  or SO (default: ACSI_BASE_URL, else the router works it out).
"""

from __future__ import annotations

import asyncio
import os
from urllib.parse import urlsplit

import httpx2 as httpx
from acsi_plugins import (
    AcsiPlugin,
    Associated,
    Event,
    OperateReceived,
    OperateResponse,
    PluginContext,
    ReportReceived,
    ServerStopped,
    ValueRead,
    ValueWritten,
)
from fastapi import APIRouter, FastAPI

from . import router as io_router
from .utils import blink_led_task, sync_to_io_device, write_to_lcd


def _origin(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}"


class RtiIoPlugin(AcsiPlugin):
    def __init__(self):
        self._router: APIRouter | None = None
        self.ctx: PluginContext | None = None

    def router(self) -> APIRouter:
        if self._router is None:
            self._router = io_router.create_io_router(prefix="")
        return self._router

    async def start(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        io_url = (
            ctx.settings.get("io_url") or os.getenv("IO_URL") or _origin(ctx.source)
        )
        if not io_url:
            ctx.logger.info(
                "No IO server configured; connect with POST /api/plugins/io/connect"
            )
            return
        acsi_url = ctx.settings.get("acsi_url") or os.getenv("ACSI_BASE_URL")
        # Connect the way a client of the plugin's routes would: /connect
        # sets up the client and the input callbacks, and
        # /acsi/enable-server-sync tells the IO server where to write input
        # changes. A failure is logged, not raised: the plugin stays loaded
        # and can be connected later.
        app = FastAPI()
        app.include_router(self.router())
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://io-plugin",
            timeout=15.0,
        ) as client:
            for path, body in (
                ("/connect", {"base_url": io_url, "acsi_url": acsi_url}),
                ("/acsi/enable-server-sync", None),
            ):
                response = await client.post(path, json=body)
                if response.status_code >= 400:
                    ctx.logger.warning(
                        f"IO plugin {path} failed (HTTP {response.status_code}): {response.text}"
                    )
                    return
        ctx.logger.info(f"IO plugin connected to {io_url}")

    async def stop(self) -> None:
        client = io_router.get_io_client()
        if client is not None and hasattr(client, "aclose"):
            await client.aclose()

    async def on_event(self, event: Event) -> None:
        client = io_router.get_io_client()
        if client is None or self.ctx is None:
            return
        mapping = io_router.get_mapping_manager()

        def blink(name, interval=0.2, count=1):
            return blink_led_task(
                client, name, interval=interval, count=count, mapping_manager=mapping
            )

        def show(name, text):
            return write_to_lcd(client, name, text, mapping_manager=mapping)

        steps = (
            self._fsp_steps(event, client, blink, show)
            if self.ctx.role == "fsp"
            else self._so_steps(event, client, blink, show)
        )
        if steps:
            await asyncio.gather(*steps)

    @staticmethod
    def _fsp_steps(event, client, blink, show):
        match event:
            case Associated(associate_id=associate_id):
                return [
                    sync_to_io_device(client, "connected", True),
                    show("connected", f"FSP Connected: {associate_id}"),
                ]
            case OperateReceived():
                return [blink("oper_rcv")]
            case OperateResponse(success=True):
                return [show("oper_send", "Operation: SUCCESS")]
            case OperateResponse(add_cause=cause) if cause:
                return [show("oper_send", f"Operation: FAILED - {cause}")]
            case OperateResponse():
                return [show("oper_send", "Operation: FAILED")]
            case ServerStopped():
                return [
                    sync_to_io_device(client, "stopped", False),
                    show("stopped", "Stopped"),
                ]
            case ValueWritten(obj_ref=obj_ref, value=value):
                return [
                    sync_to_io_device(client, obj_ref, value),
                    show("writeValue", f"{obj_ref} : {value}"),
                ]
        return []

    @staticmethod
    def _so_steps(event, client, blink, show):
        match event:
            case Associated(associate_id=associate_id):
                return [
                    blink("connected", interval=0.5, count=2),
                    show("connected", f"Connected: {associate_id}"),
                ]
            case ReportReceived(rpt_id=rpt_id, data_set=data_set):
                return [
                    blink("rc_rcv"),
                    show("rc_rcv", f"rptID={rpt_id} dataSet={data_set}"),
                ]
            case ValueRead(obj_ref=obj_ref, value=value, ok=True):
                return [blink("read"), show("read", f"{obj_ref} : {value}")]
            case ValueRead(obj_ref=obj_ref):
                return [
                    blink("read"),
                    show("read", f"Readvalue failed - {obj_ref} fail"),
                ]
            case ValueWritten(obj_ref=obj_ref, value=value, ok=True):
                return [
                    sync_to_io_device(client, obj_ref, value),
                    blink("setpoint"),
                    show("setpoint", f"Write - {obj_ref} Value: {value}"),
                ]
            case ValueWritten(obj_ref=obj_ref):
                return [blink("setpoint"), show("setpoint", f"Write - {obj_ref} fail")]
            case OperateResponse(obj_ref=obj_ref, value=value):
                return [blink("operate"), show("operate", f"Oper {obj_ref}={value}")]
        return []
