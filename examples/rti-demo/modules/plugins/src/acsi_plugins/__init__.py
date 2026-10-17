# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""Plugins for the FSP and SO: what the host tells a plugin, the host that
runs them, how a plugin is reached over HTTP, the plugin configuration, and
the routes (decisions 0021, 0029)."""

from .config import PluginEntry, PluginsConfig
from .contract import (
    API_VERSION,
    EVENT_TYPES,
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
    event_json,
)
from .host import PluginConflictError, PluginHost
from .remote import PluginError, RemotePlugin

__all__ = [
    "API_VERSION",
    "EVENT_TYPES",
    "AcsiPlugin",
    "Associated",
    "ControlResult",
    "Event",
    "OperateReceived",
    "OperateResponse",
    "PluginConflictError",
    "PluginContext",
    "PluginEntry",
    "PluginError",
    "PluginHost",
    "PluginsConfig",
    "RemotePlugin",
    "ReportReceived",
    "ServerStopped",
    "ValueRead",
    "ValueWritten",
    "event_json",
]
