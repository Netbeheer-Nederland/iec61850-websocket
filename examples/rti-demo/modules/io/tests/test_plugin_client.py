# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The IO plugin's client module."""

import sys
from pathlib import Path

IO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(IO))

from rti_io.plugin import client as plugin_client  # noqa: E402
from rti_io.plugin import router as plugin_router  # noqa: E402

PLUGIN = IO / "rti_io" / "plugin"


def test_one_async_client():
    assert not hasattr(plugin_client, "AsyncDemoIOClient")
    assert plugin_router.AsyncIOClient is plugin_client.AsyncIOClient


import asyncio  # noqa: E402

import pytest  # noqa: E402


def test_connection_failure_raises_io_connection_error():
    assert not hasattr(plugin_client, "ConnectionError")
    client = plugin_client.AsyncIOClient(base_url="http://127.0.0.1:9", max_retries=0)
    with pytest.raises(plugin_client.IOConnectionError):
        asyncio.run(client._request("GET", "/api/io/health"))


def test_the_router_imports_no_removed_package():
    assert "demo_IO" not in (PLUGIN / "router.py").read_text(encoding="utf-8")
