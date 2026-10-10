# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""What a plugin is, and what the FSP and SO tell it (decision 0021).

A plugin subclasses `AcsiPlugin` and overrides what it needs. Events go to
every plugin; an Operate on an objRef goes to the one plugin that claims it.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import APIRouter

# The contract version a plugin's manifest names in "api". The host refuses
# a plugin written for another version.
API_VERSION = 1


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
    """The FSP is about to stop its ACSI server."""


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
    """What a plugin gets from the host when it starts."""

    name: str
    role: str  # "fsp" or "so"
    settings: dict[str, Any]
    source: str | None
    logger: logging.Logger


class AcsiPlugin:
    """Base class for a plugin. Every method has a do-nothing default."""

    def claims(self) -> Iterable[str]:
        """The objRefs whose Operate this plugin answers. At most one plugin per objRef."""
        return ()

    async def start(self, ctx: PluginContext) -> None:
        """Called once, when the plugin is loaded."""

    async def stop(self) -> None:
        """Called once, when the plugin is unloaded or reloaded."""

    async def on_event(self, event: Event) -> None:
        """Called for every event. Runs with a timeout; errors are logged, not raised."""

    def handle_control(self, obj_ref: str, ctl_val: dict) -> ControlResult | None:
        """Answer an Operate on a claimed objRef; None leaves it to the model.

        Synchronous: the ACSI server asks for the answer while it builds its
        response. Runs with a timeout; keep it short.
        """
        return None

    def router(self) -> APIRouter | None:
        """Routes served under /api/plugins/<name>/, or None."""
        return None
