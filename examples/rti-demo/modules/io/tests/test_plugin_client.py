# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The IO plugin's client module."""

import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / "io_client"
sys.path.insert(0, str(PLUGIN))

import async_client_io  # noqa: E402
import io_router  # noqa: E402


def test_one_async_client():
    assert not hasattr(async_client_io, "AsyncDemoIOClient")
    assert io_router.AsyncIOClient is async_client_io.AsyncIOClient


import asyncio  # noqa: E402

import pytest  # noqa: E402


def test_connection_failure_raises_io_connection_error():
    assert not hasattr(async_client_io, "ConnectionError")
    client = async_client_io.AsyncIOClient(base_url="http://127.0.0.1:9", max_retries=0)
    with pytest.raises(async_client_io.IOConnectionError):
        asyncio.run(client._request("GET", "/api/io/health"))


def test_the_router_imports_no_removed_package():
    assert "demo_IO" not in (PLUGIN / "io_router.py").read_text(encoding="utf-8")
