# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The plugin host: holds the plugins of one FSP or SO and passes ACSI
events and operations to them (decisions 0021, 0029).

Plugin coroutines (start, stop, on_event) all run on one event loop, the web
app's (`bind_loop`), whichever thread an event comes from. The ACSI runtime
loop isn't used: the FSP replaces it on every start, and it doesn't exist
while the server is stopped.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from . import attached as attached_items
from .contract import AcsiPlugin, ControlResult, Event, PluginContext

logger = logging.getLogger(__name__)


def setting_claims(settings: dict[str, Any] | None) -> list[str]:
    """The objRefs in `settings["claims"]`: claimed for the plugin by its
    configuration, as well as those it describes (decision 0042)."""
    claims = (settings or {}).get("claims", [])
    if not isinstance(claims, list) or not all(isinstance(c, str) for c in claims):
        raise ValueError("settings.claims must be a list of objRefs")
    return claims


class PluginConflictError(Exception):
    """A plugin can't be added: its name is taken, or it claims an objRef another plugin owns."""


@dataclass
class _Entry:
    plugin: AcsiPlugin
    version: str | None
    url: str | None
    claims: list[str]
    healthy: bool = True
    last_error: str | None = None
    # What it attaches (decision 0025), as last asked; its own error, which
    # doesn't change `healthy`.
    attached: list[dict] = field(default_factory=list)
    attached_error: str | None = None
    attached_at: float | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, error: str | None) -> None:
        with self.lock:
            self.healthy = error is None
            if error is not None:
                self.last_error = error


class PluginHost:
    """The plugins loaded into one FSP or SO."""

    def __init__(
        self,
        role: str,
        *,
        host_url: str | None = None,
        event_timeout: float = 5.0,
        control_timeout: float = 2.0,
        attached_timeout: float = 1.0,
        attached_max_age: float = 1.0,
    ):
        self.role = role
        # Where plugins reach this FSP or SO (PluginContext.host_url).
        self.host_url = host_url
        self.event_timeout = event_timeout
        self.control_timeout = control_timeout
        self.attached_timeout = attached_timeout
        # Asked again at most this often, however often the list is asked for.
        self.attached_max_age = attached_max_age
        self.clock = time.monotonic
        self._loop: asyncio.AbstractEventLoop | None = None
        self._entries: dict[str, _Entry] = {}
        self._owners: dict[str, str] = {}
        self._lock = threading.Lock()
        # handle_control runs a plugin's handler here, so a handler that
        # hangs costs a worker thread, not the ACSI runtime loop.
        self._control_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="plugin-control"
        )

    # ==================== Loop ====================

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Run plugin coroutines on `loop` from now on."""
        self._loop = loop

    def _bind_running_loop(self) -> None:
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.get_running_loop()

    # ==================== Plugins ====================

    def names(self) -> list[str]:
        with self._lock:
            return list(self._entries)

    def plugin(self, name: str) -> AcsiPlugin | None:
        with self._lock:
            entry = self._entries.get(name)
        return entry.plugin if entry else None

    def routes_url(self, name: str) -> str | None:
        """Where the plugin's own routes are, if it has any."""
        with self._lock:
            entry = self._entries.get(name)
        return entry.plugin.routes_url if entry else None

    async def add(
        self,
        name: str,
        plugin: AcsiPlugin,
        *,
        settings: dict[str, Any] | None = None,
        version: str | None = None,
        url: str | None = None,
    ) -> None:
        """Start `plugin` and add it under `name`.

        It owns the objRefs it claims and those in `settings["claims"]`.
        Raises PluginConflictError, without starting the plugin, when the
        name is taken or an objRef it claims already has an owner.
        """
        self._bind_running_loop()
        claims = list(dict.fromkeys([*plugin.claims(), *setting_claims(settings)]))
        with self._lock:
            if name in self._entries:
                raise PluginConflictError(f"A plugin named '{name}' is already loaded")
            taken = {ref: self._owners[ref] for ref in claims if ref in self._owners}
        if taken:
            listed = ", ".join(
                f"{ref} (owned by '{owner}')" for ref, owner in taken.items()
            )
            raise PluginConflictError(
                f"Plugin '{name}' claims objRefs another plugin owns: {listed}"
            )

        await plugin.start(
            PluginContext(
                name=name,
                role=self.role,
                settings=dict(settings or {}),
                host_url=self.host_url,
                logger=logging.getLogger(f"acsi_plugins.{name}"),
            )
        )

        with self._lock:
            # Checked again: another add may have run while this plugin started.
            clash = name in self._entries or any(ref in self._owners for ref in claims)
            if not clash:
                self._entries[name] = _Entry(plugin, version, url, claims)
                for ref in claims:
                    self._owners[ref] = name
        if clash:
            await self._stop(name, plugin)
            raise PluginConflictError(
                f"Plugin '{name}' conflicts with a plugin added meanwhile"
            )
        logger.info(f"Plugin '{name}' loaded ({len(claims)} objRefs claimed)")

    async def remove(self, name: str) -> None:
        """Stop the plugin and remove it. Its objRefs are free again."""
        with self._lock:
            entry = self._entries.pop(name, None)
            if entry is None:
                return
            for ref in entry.claims:
                self._owners.pop(ref, None)
        await self._stop(name, entry.plugin)
        logger.info(f"Plugin '{name}' unloaded")

    async def _stop(self, name: str, plugin: AcsiPlugin) -> None:
        try:
            await asyncio.wait_for(plugin.stop(), self.event_timeout)
        except Exception as e:
            logger.warning(f"Plugin '{name}' failed to stop cleanly: {e!r}")

    def status(self, name: str | None = None) -> Any:
        """Every plugin's status, or one plugin's (None when it isn't loaded)."""
        with self._lock:
            entries = dict(self._entries)
        listed = [
            {
                "name": n,
                "version": e.version,
                "url": e.url,
                "claims": list(e.claims),
                "routes": e.plugin.routes_url is not None,
                "healthy": e.healthy,
                "last_error": e.last_error,
                "attached": list(e.attached),
                "attached_error": e.attached_error,
            }
            for n, e in entries.items()
        ]
        if name is None:
            return listed
        return next((s for s in listed if s["name"] == name), None)

    # ==================== Attached ====================

    async def refresh_attached(self) -> None:
        """Ask every plugin what it attaches, all at once; one asked less than
        attached_max_age ago keeps its answer. A plugin that fails or is too
        slow keeps its last items and gets attached_error."""
        now = self.clock()
        with self._lock:
            due = [
                (name, entry)
                for name, entry in self._entries.items()
                if entry.attached_at is None
                or now - entry.attached_at >= self.attached_max_age
            ]
        await asyncio.gather(*(self._ask_attached(n, e, now) for n, e in due))

    async def _ask_attached(self, name: str, entry: _Entry, now: float) -> None:
        try:
            answer = await asyncio.wait_for(
                entry.plugin.attached(), self.attached_timeout
            )
            items = attached_items.check(answer)
        except TimeoutError:
            error = f"attached timed out after {self.attached_timeout}s"
        except Exception as e:
            error = f"attached failed: {e}"
        else:
            with entry.lock:
                entry.attached, entry.attached_error = items, None
                entry.attached_at = now
            return
        if entry.attached_error != error:
            logger.warning(f"Plugin '{name}': {error}")
        with entry.lock:
            entry.attached_error = error
            entry.attached_at = now

    # ==================== Events ====================

    def emit(self, event: Event) -> list[concurrent.futures.Future]:
        """Pass `event` to every plugin. Safe from any thread; doesn't wait.

        Returns one future per plugin, for a caller that has to wait (from a
        thread other than the plugin loop). Without a loop, nothing is sent.
        """
        loop = self._loop
        if loop is None or loop.is_closed():
            logger.debug(f"No plugin loop; {type(event).__name__} not delivered")
            return []
        with self._lock:
            entries = list(self._entries.items())
        return [
            asyncio.run_coroutine_threadsafe(self._deliver(name, entry, event), loop)
            for name, entry in entries
        ]

    async def _deliver(self, name: str, entry: _Entry, event: Event) -> None:
        kind = type(event).__name__
        try:
            await asyncio.wait_for(entry.plugin.on_event(event), self.event_timeout)
        except TimeoutError:
            error = f"{kind} timed out after {self.event_timeout}s"
        except Exception as e:
            error = f"{kind} failed: {e!r}"
        else:
            entry.record(None)
            return
        logger.warning(f"Plugin '{name}': {error}")
        entry.record(error)

    # ==================== Operations ====================

    def handle_control(self, obj_ref: str, ctl_val: dict) -> ControlResult | None:
        """The owner's answer to an Operate on `obj_ref`; None leaves it to the model
        (no plugin owns it, or the owner answered None).

        An owner that raises, hangs past the timeout, or answers something
        that isn't a ControlResult fails the Operate.
        """
        with self._lock:
            name = self._owners.get(obj_ref)
            entry = self._entries.get(name) if name else None
        if entry is None:
            return None
        future = self._control_pool.submit(
            entry.plugin.handle_control, obj_ref, ctl_val
        )
        try:
            result = future.result(timeout=self.control_timeout)
        except concurrent.futures.TimeoutError:
            error = f"Operate {obj_ref} timed out after {self.control_timeout}s"
        except Exception as e:
            error = f"Operate {obj_ref} failed: {e!r}"
        else:
            if result is None or isinstance(result, ControlResult):
                entry.record(None)
                return result
            error = f"Operate {obj_ref} answered {result!r}, not a ControlResult"
        logger.warning(f"Plugin '{name}': {error}")
        entry.record(error)
        return ControlResult(False)
