# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The plugin host passes ACSI events and operations to its plugins (decisions 0021, 0029)."""

import asyncio
import threading
import time

import pytest
from acsi_plugins import (
    AcsiPlugin,
    Associated,
    ControlResult,
    PluginConflictError,
    PluginHost,
)

pytestmark = pytest.mark.unit


class Recorder(AcsiPlugin):
    """Records what the host gives it."""

    def __init__(self, owns=(), answer=None):
        self.owns = owns
        self.answer = answer
        self.events = []
        self.ctx = None
        self.stopped = False

    def claims(self):
        return self.owns

    async def start(self, ctx):
        self.ctx = ctx

    async def stop(self):
        self.stopped = True

    async def on_event(self, event):
        self.events.append(event)

    def handle_control(self, obj_ref, ctl_val):
        return self.answer


async def _settle(futures):
    for f in futures:
        await asyncio.wrap_future(f)


@pytest.fixture
async def host():
    host = PluginHost(
        role="fsp",
        host_url="http://fsp.test:5001",
        event_timeout=0.5,
        control_timeout=0.5,
    )
    host.bind_loop(asyncio.get_running_loop())
    yield host
    for name in list(host.names()):
        await host.remove(name)


async def test_start_gives_the_plugin_its_context(host):
    plugin = Recorder()
    await host.add("rec", plugin, settings={"a": 1}, url="http://plugin.test/rec")
    assert plugin.ctx.name == "rec"
    assert plugin.ctx.role == "fsp"
    assert plugin.ctx.settings == {"a": 1}
    assert plugin.ctx.host_url == "http://fsp.test:5001"
    assert plugin.ctx.logger.name == "acsi_plugins.rec"


async def test_an_event_goes_to_every_plugin(host):
    first, second = Recorder(), Recorder()
    await host.add("one", first)
    await host.add("two", second)
    await _settle(host.emit(Associated(associate_id="cp1")))
    assert first.events == [Associated(associate_id="cp1")]
    assert second.events == [Associated(associate_id="cp1")]


async def test_an_event_can_come_from_another_thread(host):
    plugin = Recorder()
    await host.add("rec", plugin)
    futures = []
    t = threading.Thread(target=lambda: futures.extend(host.emit(Associated("cp1"))))
    t.start()
    t.join()
    await _settle(futures)
    assert plugin.events == [Associated("cp1")]


async def test_a_failing_plugin_does_not_stop_the_others(host):
    class Failing(Recorder):
        async def on_event(self, event):
            raise RuntimeError("boom")

    good = Recorder()
    await host.add("bad", Failing())
    await host.add("good", good)
    await _settle(host.emit(Associated("cp1")))
    assert good.events == [Associated("cp1")]
    bad = host.status("bad")
    assert bad["healthy"] is False
    assert "boom" in bad["last_error"]
    assert host.names() == ["bad", "good"]


async def test_a_slow_plugin_is_cut_off_at_the_timeout(host):
    class Slow(Recorder):
        async def on_event(self, event):
            await asyncio.sleep(10)

    await host.add("slow", Slow())
    started = time.monotonic()
    await _settle(host.emit(Associated("cp1")))
    assert time.monotonic() - started < 2
    assert host.status("slow")["healthy"] is False
    assert "timed out" in host.status("slow")["last_error"]


async def test_a_later_success_makes_a_plugin_healthy_again(host):
    class Once(Recorder):
        failed = False

        async def on_event(self, event):
            if not self.failed:
                self.failed = True
                raise RuntimeError("first")

    await host.add("once", Once())
    await _settle(host.emit(Associated("cp1")))
    await _settle(host.emit(Associated("cp1")))
    assert host.status("once")["healthy"] is True


async def test_emit_without_a_loop_delivers_nothing():
    host = PluginHost(role="so")
    assert host.emit(Associated("cp1")) == []


async def test_a_name_is_loaded_once(host):
    await host.add("rec", Recorder())
    with pytest.raises(PluginConflictError):
        await host.add("rec", Recorder())


async def test_two_plugins_cannot_claim_one_objref(host):
    await host.add("one", Recorder(owns=["LD0/CSWI1.Pos"]))
    with pytest.raises(PluginConflictError, match="one.*two|two.*one"):
        await host.add("two", Recorder(owns=["LD0/CSWI1.Pos"]))
    assert host.names() == ["one"]


async def test_a_refused_plugin_is_stopped(host):
    await host.add("one", Recorder(owns=["LD0/CSWI1.Pos"]))
    refused = Recorder(owns=["LD0/CSWI1.Pos"])
    with pytest.raises(PluginConflictError):
        await host.add("two", refused)
    assert refused.ctx is None or refused.stopped


async def test_the_owner_answers_an_operate(host):
    await host.add(
        "owner",
        Recorder(
            owns=["LD0/CSWI1.Pos"],
            answer=ControlResult(False, "blocked-by-interlocking"),
        ),
    )
    result = host.handle_control("LD0/CSWI1.Pos", {"type": "boolean", "value": True})
    assert result == ControlResult(False, "blocked-by-interlocking")


async def test_an_objref_nobody_owns_is_left_to_the_model(host):
    await host.add(
        "owner", Recorder(owns=["LD0/CSWI1.Pos"], answer=ControlResult(True))
    )
    assert (
        host.handle_control("LD0/XCBR1.Pos", {"type": "boolean", "value": True}) is None
    )


async def test_an_owner_can_leave_an_operate_to_the_model(host):
    await host.add("owner", Recorder(owns=["LD0/CSWI1.Pos"], answer=None))
    assert (
        host.handle_control("LD0/CSWI1.Pos", {"type": "boolean", "value": True}) is None
    )


async def test_an_owner_that_hangs_fails_the_operate(host):
    class Hangs(Recorder):
        def handle_control(self, obj_ref, ctl_val):
            time.sleep(5)

    await host.add("owner", Hangs(owns=["LD0/CSWI1.Pos"]))
    started = time.monotonic()
    result = host.handle_control("LD0/CSWI1.Pos", {"type": "boolean", "value": True})
    assert time.monotonic() - started < 2
    assert result.ok is False
    assert host.status("owner")["healthy"] is False


async def test_an_owner_that_raises_fails_the_operate(host):
    class Raises(Recorder):
        def handle_control(self, obj_ref, ctl_val):
            raise RuntimeError("broken")

    await host.add("owner", Raises(owns=["LD0/CSWI1.Pos"]))
    assert host.handle_control("LD0/CSWI1.Pos", {}).ok is False


async def test_remove_stops_the_plugin_and_frees_its_objrefs(host):
    plugin = Recorder(owns=["LD0/CSWI1.Pos"], answer=ControlResult(True))
    await host.add("owner", plugin)
    await host.remove("owner")
    assert plugin.stopped
    assert host.names() == []
    assert host.handle_control("LD0/CSWI1.Pos", {}) is None
    await host.add("other", Recorder(owns=["LD0/CSWI1.Pos"]))


async def test_status_lists_the_plugins(host):
    await host.add(
        "owner",
        Recorder(owns=["LD0/CSWI1.Pos"]),
        version="1.2.0",
        url="http://plugin.test/owner",
    )
    [entry] = host.status()
    assert entry == {
        "name": "owner",
        "version": "1.2.0",
        "url": "http://plugin.test/owner",
        "claims": ["LD0/CSWI1.Pos"],
        "routes": False,
        "healthy": True,
        "last_error": None,
    }
