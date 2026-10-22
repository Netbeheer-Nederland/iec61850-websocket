# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""What the FSP and SO tell a plugin, and how the host sees one (decisions
0021, 0029).

A plugin is an HTTP service that implements the plugin API in openapi.yaml;
`remote.RemotePlugin` speaks it. The events below are what the host sends,
as JSON (`event_json`). `AcsiPlugin` is the host's view of a plugin:
RemotePlugin is the one implementation, and tests use small in-memory ones.
Events go to every plugin; an Operate on an objRef goes to the one plugin
that claims it.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

# The contract version a plugin's description names in "api". The host
# refuses a plugin written for another version. Version 1 was the in-process
# Python contract (decision 0021); 2 is the HTTP one (decision 0029).
API_VERSION = 2


# ==================== Events ====================


@dataclass(frozen=True)
class Event:
    """Something that happened in the FSP or SO. Plugins only watch events."""


@dataclass(frozen=True)
class Associated(Event):
    """An association was set up: the FSP answered it, or the SO got the answer."""

    associate_id: str


@dataclass(frozen=True)
class OperateReceived(Event):
    """The FSP received an Operate request (`data`: the request as received)."""

    data: dict = field(default_factory=dict)


@dataclass(frozen=True)
class OperateResponse(Event):
    """An Operate was answered: the FSP sent the answer, or the SO received it."""

    success: bool
    add_cause: str | None = None
    obj_ref: str | None = None
    value: Any = None
    data: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ValueWritten(Event):
    """A value was written: in the FSP's own model, or by the SO to a server."""

    obj_ref: str
    value: Any
    ok: bool = True


@dataclass(frozen=True)
class ValueRead(Event):
    """The SO read a value from a server."""

    obj_ref: str
    value: Any
    ok: bool = True


@dataclass(frozen=True)
class ReportReceived(Event):
    """The SO received a report."""

    rpt_id: str
    data_set: str
    data: list = field(default_factory=list)


@dataclass(frozen=True)
class ServerStopped(Event):
    """The FSP is about to drop its connection to the SO (Disconnect).

    Its ACSI server keeps running, ready (decision 0033).
    """


EVENT_TYPES: dict[str, type[Event]] = {
    cls.__name__: cls
    for cls in (
        Associated,
        OperateReceived,
        OperateResponse,
        ValueWritten,
        ValueRead,
        ReportReceived,
        ServerStopped,
    )
}


def event_json(event: Event) -> dict[str, Any]:
    """The event as the plugin API sends it: {"type": <class name>, <fields>}."""
    return {"type": type(event).__name__, **dataclasses.asdict(event)}


# ==================== Operations ====================


@dataclass(frozen=True)
class ControlResult:
    """A plugin's answer to an Operate on an objRef it owns.

    `add_cause` is an IEC 61850 AddCause name (for example
    "blockedByInterlocking"), sent to the client when `ok` is False.
    """

    ok: bool
    add_cause: str | None = None


@dataclass(frozen=True)
class PluginContext:
    """What the host tells a plugin when it starts it."""

    name: str
    role: str  # "fsp" or "so"
    settings: dict[str, Any]
    # Where the plugin reaches this FSP or SO (its REST API), for example to
    # write input changes back; None when the host doesn't know.
    host_url: str | None
    logger: logging.Logger


class AcsiPlugin:
    """The host's view of a plugin. Every method has a do-nothing default."""

    # Where the plugin's own routes are, for /api/plugins/<name>/: a base URL
    # the host passes requests on to, or None.
    routes_url: str | None = None

    def claims(self) -> Iterable[str]:
        """The objRefs whose Operate this plugin answers. At most one plugin per objRef."""
        return ()

    async def start(self, ctx: PluginContext) -> None:
        """Called once, when the plugin is added."""

    async def stop(self) -> None:
        """Called once, when the plugin is removed or reloaded."""

    async def on_event(self, event: Event) -> None:
        """Called for every event. Runs with a timeout; errors are logged, not raised."""

    def handle_control(self, obj_ref: str, ctl_val: dict) -> ControlResult | None:
        """Answer an Operate on a claimed objRef; None leaves it to the model.

        Synchronous: the ACSI server asks for the answer while it builds its
        response. Runs with a timeout; keep it short.
        """
        return None

    async def attached(self) -> Any:
        """What the plugin attaches, as {"items": [...]} (decision 0025;
        attached.py checks it). Runs with a timeout; answer what is known."""
        return {"items": []}
