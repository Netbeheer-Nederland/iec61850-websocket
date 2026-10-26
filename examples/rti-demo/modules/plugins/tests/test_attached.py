# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""What a plugin attaches (GET <url>/attached, decision 0025): checked and
trimmed by the host, asked at most once a second, and listed with the plugin."""

import asyncio

import pytest
from acsi_plugins import AcsiPlugin, PluginEntry, PluginHost, RemotePlugin
from acsi_plugins.attached import (
    MAX_ITEMS,
    MAX_LINE_CHARS,
    MAX_LINES,
    AttachedError,
    check,
)
from fastapi.testclient import TestClient

from .fake_plugin import URL, FakePlugin
from .test_web import make_app

pytestmark = pytest.mark.unit

IO = {
    "kind": "io",
    "label": "IO server",
    "address": "http://dr-panel:9000",
    "state": "ok",
    "detail": "6 devices",
    "live": [
        {
            "type": "indicators",
            "items": [{"name": "led1", "on": True, "color": "green"}],
        },
        {"type": "values", "items": [{"label": "pot1", "value": 42.0, "unit": "%"}]},
    ],
}


# -------------------- check --------------------


def test_a_valid_item_is_kept_as_it_is():
    assert check({"items": [IO]}) == [IO]


def test_optional_fields_are_filled_in():
    assert check({"items": [{"kind": "other", "label": "x"}]}) == [
        {
            "kind": "other",
            "label": "x",
            "address": None,
            "state": "unknown",
            "detail": None,
            "live": [],
        }
    ]


@pytest.mark.parametrize(
    "item",
    [
        {"kind": "io"},  # no label
        {"kind": "robot", "label": "x"},
        {"kind": "io", "label": "x", "state": "on fire"},
        "not an item",
    ],
)
def test_an_item_that_does_not_fit_is_dropped(item):
    assert (
        check({"items": [item, {"kind": "io", "label": "kept"}]})[0]["label"] == "kept"
    )


def test_too_much_is_cut():
    many = [{"kind": "io", "label": f"io{i}"} for i in range(MAX_ITEMS + 3)]
    assert len(check({"items": many})) == MAX_ITEMS

    [item] = check(
        {
            "items": [
                {
                    "kind": "display",
                    "label": "oled",
                    "live": [
                        {"type": "text", "lines": ["x" * 100] * (MAX_LINES + 5)},
                        {"type": "chart", "points": [1, 2, 3]},
                    ]
                    + [{"type": "text", "lines": []}] * 10,
                }
            ]
        }
    )
    assert len(item["live"]) == 4
    text = item["live"][0]
    assert len(text["lines"]) == MAX_LINES
    assert text["lines"][0] == "x" * MAX_LINE_CHARS
    # The unknown "chart" block is dropped, not cut into.
    assert all(b["type"] == "text" for b in item["live"])


def test_live_content_stays_plain_values():
    [item] = check(
        {
            "items": [
                {
                    "kind": "io",
                    "label": "<b>io</b>",
                    "live": [
                        {
                            "type": "indicators",
                            "items": [
                                {"name": "led1", "on": 1, "color": "purple"},
                                {"on": True},
                            ],
                        },
                        {
                            "type": "values",
                            "items": [
                                {"label": "a", "value": True},
                                {"label": "b", "value": {"x": 1}},
                                {"label": "c", "value": 3},
                            ],
                        },
                    ],
                }
            ]
        }
    )
    # Text is kept as text: the HMI never renders it as HTML.
    assert item["label"] == "<b>io</b>"
    indicators, values = item["live"]
    assert indicators["items"] == [{"name": "led1", "on": True, "color": "white"}]
    assert [v["value"] for v in values["items"]] == ["True", None, 3]


@pytest.mark.parametrize("answer", [None, [], {"items": "x"}, "items"])
def test_an_answer_that_is_not_items_is_an_error(answer):
    with pytest.raises(AttachedError):
        check(answer)


# -------------------- the host --------------------


class Attaching(AcsiPlugin):
    def __init__(self, answer=None, delay=0.0, error=None):
        self.answer = {"items": [IO]} if answer is None else answer
        self.delay = delay
        self.error = error
        self.asked = 0

    async def attached(self):
        self.asked += 1
        await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return self.answer


@pytest.fixture
def host():
    host = PluginHost(role="fsp", attached_timeout=0.2)
    host.now = 100.0
    host.clock = lambda: host.now
    return host


async def test_status_lists_what_the_plugin_attaches(host):
    await host.add("io", Attaching())
    assert host.status("io")["attached"] == []

    await host.refresh_attached()

    status = host.status("io")
    assert status["attached"] == [IO]
    assert status["attached_error"] is None


async def test_it_is_asked_at_most_once_a_second(host):
    plugin = Attaching()
    await host.add("io", plugin)

    await host.refresh_attached()
    host.now += 0.5
    await host.refresh_attached()
    assert plugin.asked == 1

    host.now += 0.5
    await host.refresh_attached()
    assert plugin.asked == 2


async def test_a_plugin_that_fails_keeps_its_items_and_stays_healthy(host):
    plugin = Attaching()
    await host.add("io", plugin)
    await host.refresh_attached()

    plugin.error = RuntimeError("devices gone")
    host.now += 1
    await host.refresh_attached()

    status = host.status("io")
    assert status["attached"] == [IO]
    assert status["attached_error"] == "attached failed: devices gone"
    assert status["healthy"] is True

    plugin.error = None
    host.now += 1
    await host.refresh_attached()
    assert host.status("io")["attached_error"] is None


async def test_a_slow_plugin_does_not_hold_up_the_others(host):
    await host.add("slow", Attaching(delay=5))
    await host.add("io", Attaching())

    await asyncio.wait_for(host.refresh_attached(), 1)

    assert host.status("slow")["attached_error"] == "attached timed out after 0.2s"
    assert host.status("io")["attached"] == [IO]


async def test_a_bad_answer_is_an_error(host):
    await host.add("io", Attaching(answer=[IO]))
    await host.refresh_attached()
    assert host.status("io")["attached"] == []
    assert host.status("io")["attached_error"].startswith("attached failed: answered")


# -------------------- over HTTP --------------------


async def test_a_plugin_without_the_route_attaches_nothing():
    plugin = RemotePlugin(URL, client_factory=FakePlugin().client)
    assert await plugin.attached() == {"items": []}


async def test_a_remote_plugin_answers_its_items():
    fake = FakePlugin(attached={"items": [IO]})
    plugin = RemotePlugin(URL, client_factory=fake.client)
    assert await plugin.attached() == {"items": [IO]}


def test_get_api_plugins_lists_what_each_plugin_attaches():
    fake = FakePlugin(attached={"items": [IO]})
    app, _ = make_app(fake, [PluginEntry("demo", URL)])
    with TestClient(app) as client:
        [status] = client.get("/api/plugins").json()["plugins"]
    assert status["attached"] == [IO]
    assert status["attached_error"] is None
