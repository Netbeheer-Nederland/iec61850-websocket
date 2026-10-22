# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""RemotePlugin speaks the plugin API to a plugin service (decision 0029)."""

import asyncio
import logging

import pytest
from acsi_plugins import (
    Associated,
    ControlResult,
    PluginContext,
    PluginError,
    RemotePlugin,
    ValueWritten,
    event_json,
)
from acsi_plugins.remote import is_allowed

from .fake_plugin import URL, FakePlugin

pytestmark = pytest.mark.unit

CTX = PluginContext(
    name="demo",
    role="fsp",
    settings={"a": 1},
    host_url="http://fsp.test:5001",
    logger=logging.getLogger("test"),
)
HOST = {"name": "demo", "role": "fsp", "host_url": "http://fsp.test:5001"}


async def test_describe_reads_name_version_claims_and_routes():
    fake = FakePlugin(claims=["LD0/CSWI1.Pos"])
    plugin = RemotePlugin(URL, client_factory=fake.client)
    d = await plugin.describe()
    assert (d.name, d.version, d.claims) == ("demo", "1.0.0", ["LD0/CSWI1.Pos"])
    assert d.routes == "http://plugin.test/plugin/routes"
    assert list(plugin.claims()) == ["LD0/CSWI1.Pos"]
    assert plugin.routes_url == "http://plugin.test/plugin/routes"


@pytest.mark.parametrize(
    "change",
    [{"api": 1}, {"name": "Bad-Name"}, {"claims": "LD0/CSWI1.Pos"}, {"routes": 3}],
)
async def test_a_bad_description_is_refused(change):
    fake = FakePlugin()
    fake.description.update(change)
    with pytest.raises(PluginError):
        await RemotePlugin(URL, client_factory=fake.client).describe()


async def test_an_unreachable_plugin_is_an_error():
    fake = FakePlugin()
    fake.up = False
    with pytest.raises(PluginError, match="Can't reach"):
        await RemotePlugin(URL, client_factory=fake.client).describe()


async def test_start_events_and_stop_carry_the_host():
    fake = FakePlugin()
    plugin = RemotePlugin(URL, client_factory=fake.client)
    await plugin.describe()
    await plugin.start(CTX)
    await plugin.on_event(ValueWritten("LD0/GGIO1.SPCSO1", True))
    await plugin.stop()
    assert fake.calls == [
        ("start", {**HOST, "settings": {"a": 1}}),
        (
            "events",
            {
                "host": HOST,
                "event": {
                    "type": "ValueWritten",
                    "obj_ref": "LD0/GGIO1.SPCSO1",
                    "value": True,
                    "ok": True,
                },
            },
        ),
        ("stop", HOST),
    ]


def test_an_event_is_its_type_and_fields():
    assert event_json(Associated("cp1")) == {
        "type": "Associated",
        "associate_id": "cp1",
    }


async def test_a_value_that_is_not_json_is_sent_as_text():
    fake = FakePlugin()
    plugin = RemotePlugin(URL, client_factory=fake.client)
    await plugin.start(CTX)
    await plugin.on_event(ValueWritten("LD0/X", b"\x01"))
    assert fake.events()[0]["value"] == "b'\\x01'"
    await plugin.stop()


@pytest.mark.parametrize(
    ("answer", "result"),
    [
        (None, None),
        ({"ok": True}, ControlResult(True)),
        (
            {"ok": False, "add_cause": "blockedByInterlocking"},
            ControlResult(False, "blockedByInterlocking"),
        ),
    ],
)
async def test_control_is_the_plugin_s_answer(answer, result):
    fake = FakePlugin(answer=answer)
    plugin = RemotePlugin(URL, client_factory=fake.client)
    await plugin.start(CTX)
    # The host calls it from a worker thread, with no loop running there.
    got = await asyncio.to_thread(plugin.handle_control, "LD0/CSWI1.Pos", {"v": 1})
    assert got == result
    assert fake.calls[-1] == (
        "control",
        {"host": HOST, "obj_ref": "LD0/CSWI1.Pos", "ctl_val": {"v": 1}},
    )
    await plugin.stop()


async def test_a_control_answer_that_is_not_a_result_is_an_error():
    fake = FakePlugin(answer={"accepted": "yes"})
    plugin = RemotePlugin(URL, client_factory=fake.client)
    with pytest.raises(PluginError, match="not a ControlResult"):
        await asyncio.to_thread(plugin.handle_control, "LD0/CSWI1.Pos", {})


@pytest.mark.parametrize(
    ("url", "allowed"),
    [
        ("http://rpi-io:9000/plugin", True),
        ("http://rpi-io:9000", True),
        ("https://rpi-io:9000/plugin", False),
        ("http://rpi-io:9001/plugin", False),
        ("http://rpi-io:9000.evil.test/plugin", False),
    ],
)
def test_a_url_is_allowed_by_scheme_host_port_and_path(url, allowed):
    assert is_allowed(url, ["http://rpi-io:9000"]) is allowed


def test_an_allowed_path_is_matched_by_whole_segments():
    allowed = ["http://io.test/plugins"]
    assert is_allowed("http://io.test/plugins/io", allowed)
    assert not is_allowed("http://io.test/pluginsx/io", allowed)


def test_nothing_is_allowed_by_default():
    assert not is_allowed("http://rpi-io:9000/plugin", [])
