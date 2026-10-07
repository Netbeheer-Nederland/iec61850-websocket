# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""Where the IO server keeps its device configuration (IO_CONFIG_FILE)."""

import json
import sys
from pathlib import Path

import pytest

IO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(IO))

from rti_io.server.main import resolve_config_path  # noqa: E402

SHIPPED = IO / "rti_io" / "server" / "io_config.json"

pytestmark = pytest.mark.unit


def test_without_io_config_file_it_is_the_shipped_file(monkeypatch):
    monkeypatch.delenv("IO_CONFIG_FILE", raising=False)
    assert resolve_config_path() == SHIPPED


def test_io_config_file_is_seeded_from_the_shipped_file(monkeypatch, tmp_path):
    target = tmp_path / "local" / "io_config.json"
    monkeypatch.setenv("IO_CONFIG_FILE", str(target))
    assert resolve_config_path() == target
    assert json.loads(target.read_text(encoding="utf-8")) == json.loads(
        SHIPPED.read_text(encoding="utf-8")
    )


def test_an_existing_io_config_file_is_kept(monkeypatch, tmp_path):
    target = tmp_path / "io_config.json"
    target.write_text('{"devices": []}', encoding="utf-8")
    monkeypatch.setenv("IO_CONFIG_FILE", str(target))
    assert resolve_config_path() == target
    assert target.read_text(encoding="utf-8") == '{"devices": []}'
