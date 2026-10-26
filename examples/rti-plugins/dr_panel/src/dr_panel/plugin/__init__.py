# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The IO plugin: the plugin API (decision 0029) under /plugin, which the FSP
and SO connect to, and io_mapping.json, which says what the devices show."""

from .plugin import create_plugin_router

__all__ = ["create_plugin_router"]
