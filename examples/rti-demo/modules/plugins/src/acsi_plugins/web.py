# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""Plugins in a FastAPI app: installing, reloading and removing them, and
their routes under /api/plugins/<name>/ (decision 0021).

    service = PluginService.from_env(PluginHost(role="fsp"))
    app = FastAPI(lifespan=...)   # the lifespan runs `service.lifespan(app)`
    attach(app, service)

FastAPI can't remove routes once added, so a plugin's routes aren't added to
the app. One fixed route passes each request on to the plugin's own small
app, which the host replaces on reload and drops on removal.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx2 as httpx
from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field

from . import loader
from .host import PluginConflictError, PluginHost
from .loader import PluginLoadError, SourceNotAllowedError

logger = logging.getLogger(__name__)

INSTALLED = "installed"
DEFAULT_STORAGE = "/app/plugins"


class PluginNotFoundError(Exception):
    pass


class PluginService:
    """Installs, reloads and removes the plugins of one FSP or SO."""

    def __init__(
        self,
        host: PluginHost,
        *,
        storage: Path,
        allowed_sources: list[str],
        configured: list[dict[str, Any]] | None = None,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
    ):
        self.host = host
        self.storage = Path(storage)
        self.allowed_sources = list(allowed_sources)
        self.configured = list(configured or [])
        self._client_factory = client_factory or (
            lambda: httpx.AsyncClient(timeout=10.0)
        )
        self._settings: dict[str, dict[str, Any]] = {}
        # Plugins that failed to load at startup: name -> why.
        self.failed: dict[str, str] = {}

    @classmethod
    def from_env(cls, host: PluginHost) -> PluginService:
        """Settings from the environment:

        - PLUGIN_STORAGE: where downloaded plugins are kept (default
          /app/plugins);
        - PLUGIN_ALLOWED_SOURCES: comma-separated URLs plugins may be
          downloaded from (default: none);
        - PLUGINS: a JSON list of plugins to load at startup,
          [{"name": ..., "source": ..., "settings": {...}}].
        """
        storage = os.getenv("PLUGIN_STORAGE") or DEFAULT_STORAGE
        allowed = [
            s.strip()
            for s in os.getenv("PLUGIN_ALLOWED_SOURCES", "").split(",")
            if s.strip()
        ]
        configured: list[dict[str, Any]] = []
        raw = os.getenv("PLUGINS", "").strip()
        if raw:
            try:
                parsed = json.loads(raw)
                if not isinstance(parsed, list) or not all(
                    isinstance(p, dict) and p.get("name") for p in parsed
                ):
                    raise ValueError("expected a list of objects with a name")
                configured = parsed
            except ValueError as e:
                logger.error(f"PLUGINS is ignored, it isn't valid: {e}")
        return cls(
            host, storage=Path(storage), allowed_sources=allowed, configured=configured
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
        """Load the downloaded plugins, the installed ones, then the configured ones.

        A plugin that fails is logged and listed in `failed`; startup goes on.
        """
        self.host.bind_loop(asyncio.get_running_loop())
        configured = {p["name"]: p for p in self.configured}

        for name in loader.stored(self.storage):
            source, settings = loader.read_install(self.storage / name)
            await self._try(name, self._load_stored(name, source, settings))
        for name in loader.installed():
            if name not in self.host.names():
                settings = configured.get(name, {}).get("settings") or {}
                await self._try(name, self.install(name, None, settings))
        for name, entry in configured.items():
            if name not in self.host.names() and name not in self.failed:
                await self._try(
                    name,
                    self.install(
                        name, entry.get("source"), entry.get("settings") or {}
                    ),
                )

    async def shutdown(self) -> None:
        for name in self.host.names():
            await self.host.remove(name)

    async def _try(self, name: str, step) -> None:
        try:
            await step
            self.failed.pop(name, None)
        except Exception as e:
            logger.error(f"Plugin '{name}' not loaded at startup: {e}")
            self.failed[name] = str(e)

    # ==================== Operations ====================

    async def install(
        self, name: str, source_url: str | None, settings: dict[str, Any] | None = None
    ) -> dict:
        """Download (or take the installed) plugin `name`, load and start it."""
        settings = dict(settings or {})
        if name in self.host.names():
            raise PluginConflictError(
                f"Plugin '{name}' is already loaded; reload or remove it first"
            )
        if source_url:
            await self._download(name, source_url, settings)
            try:
                await self._load_stored(name, source_url, settings)
            except Exception:
                # A failed install leaves nothing for the next start to retry.
                shutil.rmtree(self.storage / name, ignore_errors=True)
                raise
        else:
            await self._add_installed(name, settings)
        self.failed.pop(name, None)
        return self.host.status(name)

    async def reload(self, name: str) -> dict:
        """Load the plugin again, downloading it again if it came from a URL. Settings stay."""
        status = self.host.status(name)
        if status is None:
            raise PluginNotFoundError(name)
        source = status["source"]
        settings = self._settings.get(name, {})
        if source and source != INSTALLED:
            await self._download(name, source, settings)
            plugin, manifest = loader.load(name, self.storage / name)
            await self.host.remove(name)
            await self.host.add(
                name, plugin, settings=settings, version=manifest.version, source=source
            )
        else:
            await self.host.remove(name)
            await self._add_installed(name, settings)
        return self.host.status(name)

    async def uninstall(self, name: str) -> None:
        """Stop and remove the plugin, and delete its downloaded files."""
        if self.host.status(name) is None:
            raise PluginNotFoundError(name)
        await self.host.remove(name)
        loader.unload_modules(name)
        self._settings.pop(name, None)
        shutil.rmtree(self.storage / name, ignore_errors=True)

    async def _download(self, name: str, source: str, settings: dict[str, Any]) -> None:
        """Download the plugin, and record its source and settings next to it
        (the download replaces the folder), so the next start loads it the same."""
        async with self._client_factory() as client:
            await loader.download(
                name, source, self.storage, self.allowed_sources, client=client
            )
        loader.save_install(self.storage / name, source, settings)

    async def _load_stored(
        self, name: str, source: str | None, settings: dict[str, Any]
    ) -> None:
        plugin, manifest = loader.load(name, self.storage / name)
        try:
            await self.host.add(
                name, plugin, settings=settings, version=manifest.version, source=source
            )
        except Exception:
            loader.unload_modules(name)
            raise
        self._settings[name] = settings

    async def _add_installed(self, name: str, settings: dict[str, Any]) -> None:
        found = loader.installed().get(name)
        if found is None:
            raise PluginLoadError(
                f"No source given, and no plugin '{name}' is installed"
            )
        cls, version = found
        await self.host.add(
            name, cls(), settings=settings, version=version, source=INSTALLED
        )
        self._settings[name] = settings


# ==================== Routes ====================


class InstallRequest(BaseModel):
    name: str = Field(
        ..., description="The plugin's name, as in its plugin.json", examples=["io"]
    )
    source_url: str | None = Field(
        None,
        description="Where to download it from (<source_url>/plugin.json); "
        "leave out for a plugin installed with the image",
        examples=["http://localhost:8099"],
    )
    settings: dict[str, Any] = Field(
        default_factory=dict, description="The plugin's own settings"
    )


def _http_error(e: Exception) -> HTTPException:
    if isinstance(e, PluginNotFoundError):
        return HTTPException(404, f"No plugin '{e}' is loaded")
    if isinstance(e, SourceNotAllowedError):
        return HTTPException(403, str(e))
    if isinstance(e, PluginConflictError):
        return HTTPException(409, str(e))
    if isinstance(e, PluginLoadError):
        return HTTPException(422, str(e))
    return HTTPException(500, str(e))


_PROXY_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]
_HOP_HEADERS = {"content-length", "transfer-encoding", "connection"}


def create_plugins_router(service: PluginService) -> APIRouter:
    router = APIRouter(prefix="/api/plugins", tags=["Plugins"])

    @router.get("", summary="List plugins")
    def api_list_plugins():
        return {"plugins": service.host.status(), "failed": dict(service.failed)}

    @router.post("", summary="Install a plugin")
    async def api_install_plugin(request: InstallRequest):
        try:
            return {
                "ok": True,
                "plugin": await service.install(
                    request.name, request.source_url, request.settings
                ),
            }
        except Exception as e:
            raise _http_error(e) from e

    @router.get("/{name}", summary="A plugin's status")
    def api_plugin_status(name: str):
        status = service.host.status(name)
        if status is None:
            raise _http_error(PluginNotFoundError(name))
        return status

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
        app = service.host.app(name)
        if app is None:
            raise HTTPException(404, f"No plugin '{name}' with routes is loaded")
        headers = [
            (k, v)
            for k, v in request.headers.items()
            if k.lower() not in ("host", "content-length")
        ]
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://plugin"
        ) as client:
            answer = await client.request(
                request.method,
                "/" + path,
                params=list(request.query_params.multi_items()),
                headers=headers,
                content=await request.body(),
            )
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

    Plugins are loaded by `service.lifespan`, which the app's lifespan runs.
    """
    app.include_router(create_plugins_router(service))
