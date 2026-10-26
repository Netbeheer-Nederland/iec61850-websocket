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
        ("http://dr-panel:9000/plugin", True),
        ("http://dr-panel:9000", True),
        ("https://dr-panel:9000/plugin", False),
        ("http://dr-panel:9001/plugin", False),
        ("http://dr-panel:9000.evil.test/plugin", False),
    ],
)
def test_a_url_is_allowed_by_scheme_host_port_and_path(url, allowed):
    assert is_allowed(url, ["http://dr-panel:9000"]) is allowed


def test_an_allowed_path_is_matched_by_whole_segments():
    allowed = ["http://io.test/plugins"]
    assert is_allowed("http://io.test/plugins/io", allowed)
    assert not is_allowed("http://io.test/pluginsx/io", allowed)


def test_nothing_is_allowed_by_default():
    assert not is_allowed("http://dr-panel:9000/plugin", [])


@pytest.mark.parametrize(
    ("url", "allowed"),
    [
        ("http://192.168.0.226:8000/plugin", True),
        ("http://192.168.0.7:8000", True),
        ("http://192.168.1.226:8000/plugin", False),
        ("http://192.168.0.226:8001/plugin", False),
        ("https://192.168.0.226:8000/plugin", False),
        ("http://192.168.0.226.evil.test:8000/plugin", False),
        ("http://192.168.0.226:8000.evil.test/plugin", False),
    ],
)
def test_a_wildcard_stands_for_one_part_of_the_host(url, allowed):
    assert is_allowed(url, ["http://192.168.0.*:8000"]) is allowed


def test_a_wildcard_label_in_a_host_name_matches_one_label():
    allowed = ["http://*.lab.test:9000"]
    assert is_allowed("http://pi1.lab.test:9000/plugin", allowed)
    assert is_allowed("http://PI1.Lab.Test:9000/plugin", allowed)
    assert not is_allowed("http://lab.test:9000/plugin", allowed)
    assert not is_allowed("http://a.pi1.lab.test:9000/plugin", allowed)


def test_a_wildcard_host_matches_any_host_on_that_port():
    allowed = ["http://*:9000"]
    assert is_allowed("http://dr-panel:9000/plugin", allowed)
    assert is_allowed("http://10.0.0.5:9000/plugin", allowed)
    assert is_allowed("http://[::1]:9000/plugin", allowed)
    assert not is_allowed("http://dr-panel:9001/plugin", allowed)
    assert not is_allowed("http://dr-panel/plugin", allowed)


def test_a_wildcard_port_matches_any_port_and_none():
    allowed = ["http://dr-panel:*"]
    assert is_allowed("http://dr-panel:9000/plugin", allowed)
    assert is_allowed("http://dr-panel/plugin", allowed)
    assert not is_allowed("http://other:9000/plugin", allowed)


def test_a_wildcard_keeps_the_path_check():
    allowed = ["http://*:8000/plugins"]
    assert is_allowed("http://pi:8000/plugins/io", allowed)
    assert not is_allowed("http://pi:8000/other", allowed)


def test_a_star_alone_allows_any_http_url():
    assert is_allowed("http://anything.test:1234/plugin", ["*"])
    assert is_allowed("https://10.0.0.5/plugin", [" * "])
    assert not is_allowed("file:///etc/passwd", ["*"])
    assert not is_allowed("http:///plugin", ["*"])


def test_an_ipv6_host_is_matched_exactly():
    allowed = ["http://[::1]:9000"]
    assert is_allowed("http://[::1]:9000/plugin", allowed)
    assert not is_allowed("http://[::2]:9000/plugin", allowed)
