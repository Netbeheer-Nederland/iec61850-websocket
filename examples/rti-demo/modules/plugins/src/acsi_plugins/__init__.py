# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""Plugins for the FSP and SO: the contract, the host that runs them, how
they are loaded, and their routes (decision 0021)."""

from .contract import (
    API_VERSION,
    AcsiPlugin,
    Associated,
    ControlResult,
    Event,
    OperateReceived,
    OperateResponse,
    PluginContext,
    ReportReceived,
    ServerStopped,
    ValueRead,
    ValueWritten,
)
from .host import PluginConflictError, PluginHost

__all__ = [
    "API_VERSION",
    "AcsiPlugin",
    "Associated",
    "ControlResult",
    "Event",
    "OperateReceived",
    "OperateResponse",
    "PluginConflictError",
    "PluginContext",
    "PluginHost",
    "ReportReceived",
    "ServerStopped",
    "ValueRead",
    "ValueWritten",
]
