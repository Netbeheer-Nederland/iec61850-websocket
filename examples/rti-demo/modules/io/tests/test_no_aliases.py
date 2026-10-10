# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The IO plugin keeps one way to do each thing: no aliases or old formats."""

import json
import sys
from pathlib import Path

import pytest

IO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(IO))

from rti_io.plugin.client import AsyncIOClient, DemoIOClient  # noqa: E402
from rti_io.plugin.mapping import IOMappingManager  # noqa: E402

pytestmark = pytest.mark.unit

ALIASES = ["turn_on", "turn_off", "add_led", "get_all_states", "create_led"]


@pytest.mark.parametrize("cls", [AsyncIOClient, DemoIOClient])
@pytest.mark.parametrize("name", ALIASES)
def test_the_clients_have_no_aliases(cls, name):
    assert not hasattr(cls, name)


def test_the_mapping_has_no_first_device_lookup():
    assert not hasattr(IOMappingManager, "get_device_by_objref")


def test_the_old_objref_indexed_mapping_file_is_not_read(tmp_path):
    path = tmp_path / "io_mapping.json"
    path.write_text(
        json.dumps({"mappings": {"LD0/GGIO1.Ind1": {"led_name": "led1"}}}),
        encoding="utf-8",
    )
    manager = IOMappingManager(mapping_file=str(path))
    manager.load()
    assert manager.get_all_mappings() == {}


def test_the_objref_route_lists_every_mapped_device(monkeypatch, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from rti_io.plugin import router as io_router

    path = tmp_path / "io_mapping.json"
    path.write_text(
        json.dumps(
            {
                "leds": {
                    "led1": {"objRef": "LD0/GGIO1.Ind1"},
                    "led2": {"objRef": ["LD0/GGIO1.Ind1", "other"]},
                }
            }
        ),
        encoding="utf-8",
    )
    manager = IOMappingManager(mapping_file=str(path))
    manager.load()
    monkeypatch.setattr(io_router, "get_mapping_manager", lambda: manager)
    app = FastAPI()
    app.include_router(io_router.create_io_router(prefix=""))
    body = TestClient(app).get("/mappings/by-objref/LD0/GGIO1.Ind1").json()
    assert [m["device_name"] for m in body["mappings"]] == ["led1", "led2"]
