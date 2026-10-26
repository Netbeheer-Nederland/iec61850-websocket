# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The plugin API under /plugin, which the FSP and SO connect to (decision 0029)."""

from .plugin import create_plugin_router

__all__ = ["create_plugin_router"]
