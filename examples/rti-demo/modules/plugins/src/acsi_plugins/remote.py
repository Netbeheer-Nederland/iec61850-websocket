# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""A plugin is an HTTP service; RemotePlugin is how the host talks to one
(decision 0029). The API it speaks is openapi.yaml, tag "Plugin API":

    GET  <url>           what the plugin is: name, version, api, claims, routes
    POST <url>/start     {name, role, host_url, settings}
    POST <url>/stop      {name, role, host_url}
    POST <url>/events    {host: {...}, event: {"type": ..., <fields>}}
    POST <url>/control   {host: {...}, obj_ref, ctl_val} -> ControlResult, or 204
    GET  <url>/attached  {items: [...]}, what it attaches (optional, decision 0025)

`url` is the plugin's base URL, from the plugin configuration.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx2 as httpx

from .contract import (
    API_VERSION,
    AcsiPlugin,
    ControlResult,
    Event,
    PluginContext,
    event_json,
)

NAME = re.compile(r"^[a-z][a-z0-9_]*$")
# A plugin that doesn't answer this fast at startup is tried again later.
DESCRIBE_TIMEOUT = 5.0
# GET <url>/attached is asked while GET /api/plugins waits for it.
ATTACHED_TIMEOUT = 1.0


class PluginError(Exception):
    """A plugin can't be reached, or doesn't answer as the plugin API says; the message says why."""


class SourceNotAllowedError(PluginError):
    """The plugin's URL isn't in PLUGIN_ALLOWED_SOURCES."""


@dataclass(frozen=True)
class Description:
    """What a plugin says it is (GET <url>)."""

    name: str
    version: str
    claims: list[str]
    routes: str | None

    @classmethod
    def parse(cls, data: Any, url: str) -> Description:
        if not isinstance(data, dict):
            raise PluginError(f"{url} doesn't describe a plugin: not a JSON object")
        name = data.get("name")
        if not isinstance(name, str) or not NAME.match(name):
            raise PluginError(
                f"{url}: plugin name {name!r} isn't lowercase letters, digits and _"
            )
        if data.get("api") != API_VERSION:
            raise PluginError(
                f"Plugin '{name}' at {url} speaks plugin API {data.get('api')!r}; "
                f"this host speaks {API_VERSION}"
            )
        claims = data.get("claims", [])
        if not isinstance(claims, list) or not all(isinstance(c, str) for c in claims):
            raise PluginError(f"Plugin '{name}': 'claims' must be a list of objRefs")
        routes = data.get("routes")
        if routes is not None and not isinstance(routes, str):
            raise PluginError(f"Plugin '{name}': 'routes' must be a URL or a path")
        return cls(
            name=name,
            version=str(data.get("version", "")),
            claims=list(claims),
            routes=urljoin(url.rstrip("/") + "/", routes) if routes else None,
        )


ANY_SOURCE = "*"
WILDCARD = "*"


def is_allowed(url: str, allowed: list[str]) -> bool:
    """Whether `url` is under one of the `allowed` URLs (decision 0037).

    Scheme, host and port must be equal, and the allowed path must be a
    whole-segment prefix of the URL's path. Plain string prefixes aren't
    enough: "http://dr-panel:9000" would also match "http://dr-panel:9000.evil.test".

    In an allowed URL, `*` as the whole host stands for any host, `*` as one
    part of it for any one part ("http://192.168.0.*:8000", "http://*.lab.test"),
    and `*` as the port for any port. An entry that is just `*` allows any
    http or https URL.
    """
    target = urlsplit(url)
    try:
        target_port = target.port
    except ValueError:
        return False
    if target.scheme not in ("http", "https") or not target.hostname:
        return False
    for entry in allowed:
        entry = entry.strip()
        if entry == ANY_SOURCE:
            return True
        base = urlsplit(entry)
        if not base.scheme or base.scheme != target.scheme:
            continue
        host, port = _host_and_port(base.netloc)
        if not _host_matches(host, target.hostname):
            continue
        if port != WILDCARD and port != (
            str(target_port) if target_port is not None else None
        ):
            continue
        base_path = base.path.rstrip("/")
        if target.path == base_path or target.path.startswith(base_path + "/"):
            return True
    return False


def _host_and_port(netloc: str) -> tuple[str, str | None]:
    """An allowed URL's host and port, as written: urlsplit can't take `*` as a port."""
    netloc = netloc.rpartition("@")[2]
    if netloc.startswith("["):
        host, _, rest = netloc[1:].partition("]")
        return host.lower(), rest[1:] if rest.startswith(":") else None
    host, colon, port = netloc.partition(":")
    return host.lower(), port if colon else None


def _host_matches(pattern: str, host: str) -> bool:
    if pattern == WILDCARD:
        return True
    parts, wanted = host.lower().split("."), pattern.split(".")
    return len(parts) == len(wanted) and all(
        w == WILDCARD or w == p for w, p in zip(wanted, parts)
    )


def _json(data: Any) -> bytes:
    # Event values come from the ACSI model and needn't be JSON types.
    return json.dumps(data, default=str).encode()


ClientFactory = Callable[[], httpx.AsyncClient]


def default_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=10.0)


class RemotePlugin(AcsiPlugin):
    """The plugin at `url`, once described (`describe`)."""

    def __init__(
        self,
        url: str,
        *,
        client_factory: ClientFactory = default_client,
        control_timeout: float = 2.0,
    ):
        self.url = url.rstrip("/")
        self.description: Description | None = None
        self._client_factory = client_factory
        self._control_timeout = control_timeout
        self._client: httpx.AsyncClient | None = None
        self._host: dict[str, Any] = {}

    @property
    def routes_url(self) -> str | None:
        return self.description.routes if self.description else None

    async def describe(self) -> Description:
        """Ask the plugin what it is (GET <url>)."""
        async with self._client_factory() as client:
            response = await self._send(
                client, "GET", self.url, timeout=DESCRIBE_TIMEOUT
            )
        self.description = Description.parse(self._body(response), self.url)
        return self.description

    def claims(self):
        return self.description.claims if self.description else ()

    async def start(self, ctx: PluginContext) -> None:
        self._host = {"name": ctx.name, "role": ctx.role, "host_url": ctx.host_url}
        self._client = self._client_factory()
        await self._call(
            self._client,
            "POST",
            f"{self.url}/start",
            {**self._host, "settings": ctx.settings},
        )

    async def stop(self) -> None:
        client, self._client = self._client, None
        if client is None:
            return
        try:
            await self._call(client, "POST", f"{self.url}/stop", self._host)
        finally:
            await client.aclose()

    async def on_event(self, event: Event) -> None:
        if self._client is None:
            raise PluginError("not started")
        await self._call(
            self._client,
            "POST",
            f"{self.url}/events",
            {"host": self._host, "event": event_json(event)},
        )

    def handle_control(self, obj_ref: str, ctl_val: dict) -> ControlResult | None:
        """Ask the plugin (POST <url>/control). Runs in one of the host's
        worker threads, so it has a loop of its own."""
        return asyncio.run(self._control(obj_ref, ctl_val))

    async def _control(self, obj_ref: str, ctl_val: dict) -> ControlResult | None:
        async with self._client_factory() as client:
            response = await self._send(
                client,
                "POST",
                f"{self.url}/control",
                {"host": self._host, "obj_ref": obj_ref, "ctl_val": ctl_val},
                timeout=self._control_timeout,
            )
        if response.status_code == 204:
            return None
        data = self._body(response)
        if not isinstance(data, dict) or not isinstance(data.get("ok"), bool):
            raise PluginError(
                f"{self.url}/control answered {data!r}, not a ControlResult"
            )
        cause = data.get("add_cause")
        return ControlResult(data["ok"], cause if isinstance(cause, str) else None)

    async def attached(self) -> Any:
        """What the plugin attaches (GET <url>/attached); a plugin without
        the route (404) attaches nothing."""
        async with self._client_factory() as client:
            try:
                response = await client.get(
                    f"{self.url}/attached", timeout=ATTACHED_TIMEOUT
                )
            except httpx.HTTPError as e:
                raise PluginError(f"Can't reach {self.url}/attached: {e!r}") from e
        if response.status_code in (404, 405):
            return {"items": []}
        if response.status_code >= 300:
            raise PluginError(f"GET {self.url}/attached: HTTP {response.status_code}")
        return self._body(response)

    async def _call(
        self, client: httpx.AsyncClient, method: str, url: str, body: Any = None
    ) -> Any:
        response = await self._send(client, method, url, body)
        return None if response.status_code == 204 else self._body(response)

    @staticmethod
    async def _send(
        client: httpx.AsyncClient,
        method: str,
        url: str,
        body: Any = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        kwargs: dict[str, Any] = {}
        if body is not None:
            kwargs["content"] = _json(body)
            kwargs["headers"] = {"content-type": "application/json"}
        if timeout is not None:
            kwargs["timeout"] = timeout
        try:
            response = await client.request(method, url, **kwargs)
        except httpx.HTTPError as e:
            raise PluginError(f"Can't reach {url}: {e!r}") from e
        if response.status_code >= 300:
            try:
                detail = response.json().get("detail")
            except Exception:
                detail = None
            raise PluginError(
                f"{method} {url}: HTTP {response.status_code}"
                + (f": {detail}" if detail else "")
            )
        return response

    @staticmethod
    def _body(response: httpx.Response) -> Any:
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as e:
            raise PluginError(f"{response.request.url} isn't JSON: {e}") from e
