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
