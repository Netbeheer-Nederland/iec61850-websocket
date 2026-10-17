# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0

import pytest


@pytest.fixture(autouse=True)
def no_autostart(monkeypatch):
    """An app started in a test doesn't dial out to an SO (decision 0033)."""
    monkeypatch.setenv("FSP_AUTOSTART", "false")
