# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The IO server is a plugin of the FSP and SO (decision 0029).

It implements the plugin API (examples/rti-demo/modules/plugins/openapi.yaml)
under /plugin, so an FSP or SO configures

    {"name": "io", "url": "http://rpi-io:9000/plugin"}

and nothing of IO is installed in it. The FSP or SO tells it what happens
(an association, an Operate, a write, a report); it shows that on its LEDs
and displays, and passes writes on to the output devices mapped to the
objRef. Which devices react to what is in io_mapping.json (IO_MAPPING_FILE);
the names it uses there for events ("connected", "oper_rcv", ...) are its own.

When an FSP or SO starts it, its input devices (buttons, potentiometers)
write their changes back to that host's host_url (the most recent one,
unless its settings say "write_inputs": false). Its routes, under
/api/plugins/io/ in the FSP or SO, are this server's /api/io.

What it attaches (GET /plugin/attached, decision 0025): this server, with its
LEDs, buttons and potentiometers, and each display, with the text the plugin
last wrote to it. Read from its own devices when asked.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import logging
import os
from typing import Any

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from ..server import io_controller as controller_module
from ..server.devices import DeviceType
from ..server.io_controller import ACSIConfig, IOController, configure_acsi
from .mapping import IOMappingManager, resolve_mapping_path

logger = logging.getLogger(__name__)

API_VERSION = 2
NAME = "io"


class Host(BaseModel):
    name: str
    role: str = Field(pattern="^(fsp|so)$")
    host_url: str | None = None


class StartRequest(Host):
    settings: dict[str, Any] = Field(default_factory=dict)


class EventRequest(BaseModel):
    host: Host
    event: dict[str, Any]


def _version() -> str:
    try:
        return importlib.metadata.version("rpi-io")
    except importlib.metadata.PackageNotFoundError:
        return ""


class IoPlugin:
    """What the IO server does for the FSPs and SOs that use it."""

    def __init__(self, io_controller: IOController, mapping: IOMappingManager):
        self.io = io_controller
        self.mapping = mapping
        # The hosts started, by host_url (or role:name without one).
        self.hosts: dict[str, Host] = {}
        # The host whose host_url the input devices write to.
        self.input_target: str | None = None
        self._tasks: set[asyncio.Task] = set()
        self.sleep = asyncio.sleep  # between blinks; tests make it instant
        # What the plugin last wrote to each display, as lines.
        self.display_text: dict[str, list[str]] = {}

    # ==================== Lifecycle ====================

    def start(self, request: StartRequest) -> None:
        key = _key(request)
        self.hosts[key] = Host(**request.model_dump(exclude={"settings"}))
        if not self.io._initialized:
            self.io.initialize()
        if request.host_url and request.settings.get("write_inputs", True):
            self.input_target = key
            self._write_inputs_to(request.host_url)
        logger.info(f"Started for {request.role} '{request.name}' ({request.host_url})")

    def stop(self, host: Host) -> None:
        key = _key(host)
        self.hosts.pop(key, None)
        if self.input_target == key:
            self.input_target = None
            configure_acsi(ACSIConfig(url=host.host_url or "", enabled=False))
        logger.info(f"Stopped for {host.role} '{host.name}'")

    def _write_inputs_to(self, url: str) -> None:
        """Have the input devices write their changes to `url`, as their
        mapping says (objRef, fc, service, dataType)."""
        inputs = {
            name: {
                "objRef": m["objRef"],
                "fc": m.get("fc", "ST"),
                "service": m.get("service", "writeValue"),
                "dataType": m.get("dataType", ""),
            }
            for name, m in self.mapping.get_all_mappings().items()
            if m.get("direction") == "input" and isinstance(m.get("objRef"), str)
        }
        # Changed in place: the input callbacks read this dict.
        controller_module._device_mappings.clear()
        controller_module._device_mappings.update(inputs)
        configure_acsi(ACSIConfig(url=url, enabled=True))

    # ==================== Events ====================

    def handle(self, request: EventRequest) -> None:
        """Do what the event asks, after answering: a blink takes longer
        than the host waits for an event."""
        steps = (
            self._fsp_steps(request.event)
            if request.host.role == "fsp"
            else self._so_steps(request.event)
        )
        if steps:
            task = asyncio.create_task(self._run(steps))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    @staticmethod
    async def _run(steps) -> None:
        results = await asyncio.gather(*steps, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"Plugin step failed: {result!r}")

    def _fsp_steps(self, event: dict) -> list:
        kind = event.get("type")
        if kind == "Associated":
            return [
                self.sync("connected", True),
                self.show("connected", f"FSP Connected: {event.get('associate_id')}"),
            ]
        if kind == "OperateReceived":
            return [self.blink("oper_rcv")]
        if kind == "OperateResponse":
            if event.get("success"):
                return [self.show("oper_send", "Operation: SUCCESS")]
            cause = event.get("add_cause")
            text = f"Operation: FAILED - {cause}" if cause else "Operation: FAILED"
            return [self.show("oper_send", text)]
        if kind == "ServerStopped":
            # The FSP dropped its connection to the SO; its server runs on.
            return [self.sync("stopped", False), self.show("stopped", "Disconnected")]
        if kind == "ValueWritten":
            obj_ref, value = event.get("obj_ref"), event.get("value")
            return [
                self.sync(obj_ref, value),
                self.show("writeValue", f"{obj_ref} : {value}"),
            ]
        return []

    def _so_steps(self, event: dict) -> list:
        kind = event.get("type")
        obj_ref, value = event.get("obj_ref"), event.get("value")
        if kind == "Associated":
            return [
                self.blink("connected", interval=0.5, count=2),
                self.show("connected", f"Connected: {event.get('associate_id')}"),
            ]
        if kind == "ReportReceived":
            text = f"rptID={event.get('rpt_id')} dataSet={event.get('data_set')}"
            return [self.blink("rc_rcv"), self.show("rc_rcv", text)]
        if kind == "ValueRead":
            if event.get("ok", True):
                return [self.blink("read"), self.show("read", f"{obj_ref} : {value}")]
            return [
                self.blink("read"),
                self.show("read", f"Readvalue failed - {obj_ref} fail"),
            ]
        if kind == "ValueWritten":
            if event.get("ok", True):
                return [
                    self.sync(obj_ref, value),
                    self.blink("setpoint"),
                    self.show("setpoint", f"Write - {obj_ref} Value: {value}"),
                ]
            return [
                self.blink("setpoint"),
                self.show("setpoint", f"Write - {obj_ref} fail"),
            ]
        if kind == "OperateResponse":
            return [
                self.blink("operate"),
                self.show("operate", f"Oper {obj_ref}={value}"),
            ]
        return []

    # ==================== Devices ====================

    def _mapped(self, name: str, *, displays: bool) -> list[str]:
        """The devices mapped to `name` (an objRef or an event name) that are
        displays, or LEDs."""
        found = []
        for config in self.mapping.get_devices_by_objref(name):
            device = self.io.get_device(config["device_name"])
            if device is None:
                continue
            is_display = hasattr(device, "write_line")
            kind = str(config.get("type", config.get("device_type", ""))).lower()
            if (displays and is_display) or (not displays and kind == "led"):
                found.append(config["device_name"])
        return found

    async def show(self, name: str, text: str) -> None:
        for device in self._mapped(name, displays=True):
            await asyncio.to_thread(self.io.get_device(device).write, text)
            self.display_text[device] = str(text).split("\n")

    async def blink(self, name: str, interval: float = 0.2, count: int = 1) -> None:
        leds = self._mapped(name, displays=False)
        for _ in range(count if leds else 0):
            for state in (True, False):
                for led in leds:
                    await asyncio.to_thread(self.io.write, led, state)
                await self.sleep(interval)

    async def sync(self, obj_ref: str | None, value: Any) -> None:
        """Set the output devices mapped to `obj_ref` to `value`."""
        if obj_ref:
            await asyncio.to_thread(
                self.mapping.sync_device_from_iec61850, obj_ref, value, self
            )

    def set_device(self, name: str, state: Any) -> None:
        """For IOMappingManager.sync_device_from_iec61850."""
        self.io.write(name, state)

    # ==================== Attached ====================

    def attached(self, address: str | None) -> dict:
        """This server and its displays, for the HMI (decision 0025). The
        IO server doesn't know an LED's colour; LEDs are reported green."""
        configs = getattr(self.io, "configs", {})
        up = [name for name in configs if self.io.get_device(name) is not None]
        indicators, values, displays = [], [], []
        for name, config in configs.items():
            kind = config.device_type
            device = self.io.get_device(name)
            if kind in (DeviceType.LCD, DeviceType.LCD_I2C):
                displays.append(
                    {
                        "kind": "display",
                        "label": name,
                        "address": f"{address} ({kind.value})" if address else None,
                        "state": "ok" if device is not None else "down",
                        "detail": config.description or None,
                        "live": [
                            {"type": "text", "lines": self.display_text.get(name, [])}
                        ],
                    }
                )
                continue
            value = _read(device)
            if kind == DeviceType.LED:
                indicators.append({"name": name, "on": bool(value), "color": "green"})
            elif kind == DeviceType.BUTTON:
                text = None if value is None else ("pressed" if value else "released")
                values.append({"label": name, "value": text})
            else:
                if isinstance(value, float):
                    value = round(value, 1)
                values.append({"label": name, "value": value})
        if not self.io._initialized:
            state, detail = "down", "not initialised"
        elif len(up) < len(configs):
            state, detail = "degraded", f"{len(up)} of {len(configs)} devices up"
        else:
            state, detail = "ok", f"{len(configs)} devices"
        live = []
        if indicators:
            live.append({"type": "indicators", "items": indicators})
        if values:
            live.append({"type": "values", "items": values})
        server = {
            "kind": "io",
            "label": "IO server",
            "address": address,
            "state": state,
            "detail": detail,
            "live": live,
        }
        return {"items": [server, *displays]}


def _read(device) -> Any:
    if device is None:
        return None
    try:
        return device.read()
    except Exception:
        return None


def _key(host: Host) -> str:
    return host.host_url or f"{host.role}:{host.name}"


def create_plugin_router(
    io_controller: IOController, mapping: IOMappingManager | None = None
) -> APIRouter:
    """The plugin API under /plugin."""
    if mapping is None:
        mapping = IOMappingManager(
            mapping_file=str(resolve_mapping_path(os.getenv("IO_MAPPING_FILE")))
        )
    plugin = IoPlugin(io_controller, mapping)
    router = APIRouter(prefix="/plugin", tags=["Plugin API (decision 0029)"])

    @router.get("", summary="Describe the plugin")
    def describe():
        return {
            "name": NAME,
            "version": _version(),
            "api": API_VERSION,
            "claims": [],
            "routes": "/api/io",
        }

    @router.post("/start", summary="Start serving an FSP or SO")
    def start(request: StartRequest):
        plugin.start(request)
        return {"ok": True}

    @router.post("/stop", summary="Stop serving an FSP or SO")
    def stop(host: Host):
        plugin.stop(host)
        return {"ok": True}

    @router.post(
        "/events", status_code=202, summary="Something happened in the FSP or SO"
    )
    async def events(request: EventRequest):
        plugin.handle(request)
        return {"ok": True}

    @router.post("/control", status_code=204, summary="Answer an Operate (claims none)")
    def control():
        return Response(status_code=204)

    @router.get("/attached", summary="What the plugin attaches (decision 0025)")
    async def attached(request: Request):
        address = str(request.base_url).rstrip("/")
        return await asyncio.to_thread(plugin.attached, address)

    @router.get("/mappings", summary="The IO mapping the plugin uses")
    def mappings():
        return {
            "file": str(mapping.mapping_path),
            "mappings": mapping.get_all_mappings(),
            "hosts": [h.model_dump() for h in plugin.hosts.values()],
            "input_target": plugin.input_target,
        }

    router.plugin = plugin  # for tests
    return router
