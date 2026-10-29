# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""Plugins in a FastAPI app: connecting the configured plugins at startup,
adding, editing, reloading and removing them, and their routes under
/api/plugins/<name>/ (decisions 0021, 0029).

    service = PluginService.from_env(PluginHost(role="fsp"))
    app = FastAPI(lifespan=...)   # the lifespan runs `service.lifespan(app)`
    attach(app, service)

A plugin is an HTTP service (remote.RemotePlugin). One fixed route passes
each request under /api/plugins/<name>/ on to the plugin's own routes.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx2 as httpx
from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .config import ConfigError, PluginEntry, PluginsConfig
from .host import PluginConflictError, PluginHost
from .remote import (
    ANY_SOURCE,
    ClientFactory,
    PluginError,
    RemotePlugin,
    SourceNotAllowedError,
    default_client,
    is_allowed,
)

logger = logging.getLogger(__name__)

DEFAULT_RETRY_SECONDS = 10.0


class PluginNotFoundError(Exception):
    pass


class PluginService:
    """Connects, reloads and removes the plugins of one FSP or SO."""

    def __init__(
        self,
        host: PluginHost,
        *,
        configured: list[PluginEntry] | None = None,
        allowed_sources: list[str] | None = None,
        client_factory: ClientFactory = default_client,
        retry_seconds: float = DEFAULT_RETRY_SECONDS,
    ):
        self.host = host
        self.configured = list(configured or [])
        self.allowed_sources = list(allowed_sources or [])
        self.client_factory = client_factory
        self.retry_seconds = retry_seconds
        # The plugins added, loaded or not: name -> entry. A configured plugin
        # that isn't loaded is retried; one removed through the API isn't.
        self._entries: dict[str, PluginEntry] = {}
        # Plugins that aren't loaded: name -> why.
        self.failed: dict[str, str] = {}
        self._retry_task: asyncio.Task | None = None

    @classmethod
    def from_env(cls, host: PluginHost) -> PluginService:
        """Settings from the environment:

        - PLUGINS_FILE: the plugin configuration (config.py);
        - PLUGINS: the same JSON inline; its plugins and host_url win;
        - PLUGIN_HOST_URL: where plugins reach this FSP or SO; wins over the
          configuration's host_url;
        - PLUGIN_ALLOWED_SOURCES: comma-separated URLs that POST /api/plugins
          may add plugins from, with `*` for any host, host part or port;
          `*` alone allows any URL (remote.is_allowed). Default `*`; set but
          empty: none. The configuration is trusted;
        - PLUGIN_RETRY_SECONDS: how often a configured plugin that isn't
          reachable is tried again (default 10; 0: never).
        """
        config = PluginsConfig()
        sources = [
            ("PLUGINS_FILE", lambda v: PluginsConfig.read(Path(v))),
            ("PLUGINS", lambda v: PluginsConfig.parse(_loads(v))),
        ]
        for var, parse in sources:
            value = os.getenv(var, "").strip()
            if value:
                try:
                    config = config.merged(parse(value))
                except ConfigError as e:
                    logger.error(f"{var} is ignored, it isn't valid: {e}")
        host.host_url = os.getenv("PLUGIN_HOST_URL") or config.host_url or host.host_url
        allowed = [
            s.strip()
            for s in os.getenv("PLUGIN_ALLOWED_SOURCES", ANY_SOURCE).split(",")
            if s.strip()
        ]
        if ANY_SOURCE in allowed:
            logger.warning(
                "PLUGIN_ALLOWED_SOURCES is *: plugins can be added from any URL"
            )
        try:
            retry = float(os.getenv("PLUGIN_RETRY_SECONDS", DEFAULT_RETRY_SECONDS))
        except ValueError:
            retry = DEFAULT_RETRY_SECONDS
        return cls(
            host,
            configured=config.plugins,
            allowed_sources=allowed,
            retry_seconds=retry,
        )

    # ==================== Lifecycle ====================

    @asynccontextmanager
    async def lifespan(self, _app: FastAPI | None = None):
        await self.startup()
        try:
            yield
        finally:
            await self.shutdown()

    async def startup(self) -> None:
        """Connect the configured plugins. One that can't be reached is
        listed in `failed` and tried again in the background; startup goes on."""
        self.host.bind_loop(asyncio.get_running_loop())
        for entry in self.configured:
            self._entries[entry.name] = entry
        await asyncio.gather(*(self._try(e) for e in self.configured))
        if self.failed and self.retry_seconds > 0:
            self._retry_task = asyncio.create_task(self._retry())

    async def shutdown(self) -> None:
        if self._retry_task is not None:
            self._retry_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._retry_task
            self._retry_task = None
        for name in self.host.names():
            await self.host.remove(name)

    async def _try(self, entry: PluginEntry) -> bool:
        try:
            await self._connect(entry)
        except Exception as e:
            if self.failed.get(entry.name) != str(e):
                logger.warning(f"Plugin '{entry.name}' not connected: {e}")
            self.failed[entry.name] = str(e)
            return False
        if entry.name in self.failed:
            logger.info(f"Plugin '{entry.name}' connected after all")
        self.failed.pop(entry.name, None)
        return True

    async def _retry(self) -> None:
        while self.failed:
            await asyncio.sleep(self.retry_seconds)
            for name in list(self.failed):
                entry = self._entries.get(name)
                if entry is not None and name not in self.host.names():
                    await self._try(entry)

    def _ensure_retrying(self) -> None:
        if self.retry_seconds > 0 and (
            self._retry_task is None or self._retry_task.done()
        ):
            self._retry_task = asyncio.create_task(self._retry())

    # ==================== Operations ====================

    async def install(
        self, name: str, url: str, settings: dict[str, Any] | None = None
    ) -> dict:
        """Add the plugin at `url`, from POST /api/plugins: only from an allowed source."""
        if name in self.host.names():
            raise PluginConflictError(
                f"Plugin '{name}' is already loaded; reload or remove it first"
            )
        if not is_allowed(url, self.allowed_sources):
            raise SourceNotAllowedError(
                f"{url} is not allowed; add it to PLUGIN_ALLOWED_SOURCES"
            )
        entry = PluginEntry(name, url, dict(settings or {}))
        await self._connect(entry)
        self._entries[name] = entry
        self.failed.pop(name, None)
        return self.host.status(name)

    async def reload(self, name: str) -> dict:
        """Ask the plugin again what it is and start it again; the settings stay."""
        entry = self._entries.get(name)
        if entry is None or (name not in self.host.names() and name not in self.failed):
            raise PluginNotFoundError(name)
        await self.host.remove(name)
        try:
            await self._connect(entry)
        except Exception as e:
            self.failed[name] = str(e)
            self._ensure_retrying()
            raise
        self.failed.pop(name, None)
        return self.host.status(name)

    async def edit(
        self,
        name: str,
        url: str | None = None,
        settings: dict[str, Any] | None = None,
    ) -> dict:
        """Change the plugin's URL or settings, from PUT /api/plugins/{name}: stop
        it and connect it from the new definition; what isn't given stays. A new
        URL must be from an allowed source. When the new definition doesn't
        connect, the old one is connected again and the error raised: nothing
        changes. Until the FSP or SO restarts, as an added plugin."""
        old = self._entries.get(name)
        if old is None or (name not in self.host.names() and name not in self.failed):
            raise PluginNotFoundError(name)
        new = PluginEntry(
            name,
            old.url if url is None else url,
            dict(old.settings if settings is None else settings),
        )
        if new.url != old.url and not is_allowed(new.url, self.allowed_sources):
            raise SourceNotAllowedError(
                f"{new.url} is not allowed; add it to PLUGIN_ALLOWED_SOURCES"
            )
        was_loaded = name in self.host.names()
        await self.host.remove(name)
        try:
            await self._connect(new)
        except Exception:
            if was_loaded and not await self._try(old):
                self._ensure_retrying()
            raise
        self._entries[name] = new
        self.failed.pop(name, None)
        logger.info(f"Plugin '{name}' edited: {new.url}")
        return self.host.status(name)

    def definitions(self) -> dict[str, dict[str, Any]]:
        """The definition (url, settings) of every plugin, connected or not:
        what PUT /api/plugins/{name} changes."""
        listed = set(self.host.names()) | set(self.failed)
        return {
            name: {"url": entry.url, "settings": dict(entry.settings)}
            for name, entry in self._entries.items()
            if name in listed
        }

    async def uninstall(self, name: str) -> None:
        """Stop and remove the plugin; a configured one isn't tried again until the next start."""
        if name not in self._entries:
            raise PluginNotFoundError(name)
        await self.host.remove(name)
        self._entries.pop(name, None)
        self.failed.pop(name, None)

    async def _connect(self, entry: PluginEntry) -> None:
        plugin = RemotePlugin(
            entry.url,
            client_factory=self.client_factory,
            control_timeout=self.host.control_timeout,
        )
        description = await plugin.describe()
        if description.name != entry.name:
            raise PluginError(
                f"{entry.url} is plugin '{description.name}', not '{entry.name}'"
            )
        await self.host.add(
            entry.name,
            plugin,
            settings=entry.settings,
            version=description.version,
            url=entry.url,
        )


def _loads(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError as e:
        raise ConfigError(str(e)) from e


# ==================== Routes ====================


class InstallRequest(BaseModel):
    name: str = Field(
        ...,
        description="The plugin's name, as it describes itself",
        examples=["dr_panel"],
    )
    url: str = Field(
        ...,
        description="The plugin's base URL (GET <url> describes it)",
        examples=["http://dr-panel:9000/plugin"],
    )
    settings: dict[str, Any] = Field(
        default_factory=dict, description="The plugin's own settings"
    )


class EditRequest(BaseModel):
    url: str | None = Field(
        None,
        description="The plugin's new base URL; left out: it stays",
        examples=["http://dr-panel:9000/plugin"],
    )
    settings: dict[str, Any] | None = Field(
        None, description="The plugin's new settings, all of them; left out: they stay"
    )


def _http_error(e: Exception) -> HTTPException:
    if isinstance(e, PluginNotFoundError):
        return HTTPException(404, f"No plugin '{e}' is configured")
    if isinstance(e, SourceNotAllowedError):
        return HTTPException(403, str(e))
    if isinstance(e, PluginConflictError):
        return HTTPException(409, str(e))
    if isinstance(e, (PluginError, ConfigError)):
        return HTTPException(422, str(e))
    return HTTPException(500, str(e))


_PROXY_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]
_HOP_HEADERS = {"content-length", "transfer-encoding", "connection", "content-encoding"}


def create_plugins_router(service: PluginService) -> APIRouter:
    router = APIRouter(prefix="/api/plugins", tags=["Plugins"])

    @router.get("", summary="List plugins")
    async def api_list_plugins():
        await service.host.refresh_attached()
        return {
            "plugins": service.host.status(),
            "failed": dict(service.failed),
            "definitions": service.definitions(),
        }

    @router.post("", summary="Add a plugin")
    async def api_install_plugin(request: InstallRequest):
        try:
            return {
                "ok": True,
                "plugin": await service.install(
                    request.name, request.url, request.settings
                ),
            }
        except Exception as e:
            raise _http_error(e) from e

    @router.get("/{name}", summary="A plugin's status")
    def api_plugin_status(name: str):
        status = service.host.status(name)
        if status is None:
            raise HTTPException(404, f"No plugin '{name}' is loaded")
        return status

    @router.put("/{name}", summary="Edit a plugin")
    async def api_edit_plugin(name: str, request: EditRequest):
        try:
            return {
                "ok": True,
                "plugin": await service.edit(name, request.url, request.settings),
            }
        except Exception as e:
            raise _http_error(e) from e

    @router.post("/{name}/reload", summary="Reload a plugin")
    async def api_reload_plugin(name: str):
        try:
            return {"ok": True, "plugin": await service.reload(name)}
        except Exception as e:
            raise _http_error(e) from e

    @router.delete("/{name}", summary="Remove a plugin")
    async def api_remove_plugin(name: str):
        try:
            await service.uninstall(name)
        except Exception as e:
            raise _http_error(e) from e
        return {"ok": True}

    @router.api_route(
        "/{name}/{path:path}", methods=_PROXY_METHODS, include_in_schema=False
    )
    async def api_plugin_route(name: str, path: str, request: Request):
        base = service.host.routes_url(name)
        if base is None:
            raise HTTPException(404, f"No plugin '{name}' with routes is loaded")
        headers = [
            (k, v)
            for k, v in request.headers.items()
            if k.lower() not in ("host", "content-length")
        ]
        try:
            async with service.client_factory() as client:
                answer = await client.request(
                    request.method,
                    f"{base.rstrip('/')}/{path}",
                    params=list(request.query_params.multi_items()),
                    headers=headers,
                    content=await request.body(),
                )
        except httpx.HTTPError as e:
            raise HTTPException(502, f"Plugin '{name}' can't be reached: {e!r}") from e
        return Response(
            content=answer.content,
            status_code=answer.status_code,
            headers={
                k: v for k, v in answer.headers.items() if k.lower() not in _HOP_HEADERS
            },
        )

    return router


def attach(app: FastAPI, service: PluginService) -> None:
    """Add /api/plugins to `app`.

    Plugins are connected by `service.lifespan`, which the app's lifespan runs.
    """
    app.include_router(create_plugins_router(service))
