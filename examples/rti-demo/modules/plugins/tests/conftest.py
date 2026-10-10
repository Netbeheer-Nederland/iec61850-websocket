# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The host's tests don't see the plugins the workspace installs (the IO
plugin, decision 0022): each test brings the plugins it needs."""

import pytest
from acsi_plugins import loader


@pytest.fixture(autouse=True)
def no_installed_plugins(monkeypatch):
    monkeypatch.setattr(loader, "installed", dict)
