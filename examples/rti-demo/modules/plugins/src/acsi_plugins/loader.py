# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""How a plugin gets into the FSP or SO (decision 0021).

A plugin is a flat folder of files with a manifest, `plugin.json`:

    {"name": "io", "version": "2.0.0", "api": 1,
     "entry": "plugin:RtiIoPlugin",
     "files": ["__init__.py", "plugin.py", ...]}

It is downloaded from a source URL (`<source>/plugin.json`, then
`<source>/<file>` for each file, served as is), only when the source is
allowed, into
`<storage>/<name>/`, and imported as the package `acsi_<name>_plugin`.
Plugins installed with the image register a class under the entry point
group `acsi.plugins` instead.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import json
import logging
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx2 as httpx

from .contract import API_VERSION, AcsiPlugin

logger = logging.getLogger(__name__)

MANIFEST_FILE = "plugin.json"
# Written by the host next to a downloaded plugin; not part of the plugin.
INSTALL_FILE = "install.json"
ENTRY_POINT_GROUP = "acsi.plugins"

_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_FILE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")


class PluginLoadError(Exception):
    """A plugin can't be downloaded or loaded; the message says why."""


class SourceNotAllowedError(PluginLoadError):
    """The source URL isn't in PLUGIN_ALLOWED_SOURCES."""


@dataclass(frozen=True)
class Manifest:
    name: str
    version: str
    entry: str
    files: list[str]

    @classmethod
    def parse(cls, data: Any) -> Manifest:
        if not isinstance(data, dict):
            raise PluginLoadError("plugin.json is not a JSON object")
        name = data.get("name")
        if not isinstance(name, str) or not _NAME.match(name):
            raise PluginLoadError(
                f"Plugin name {name!r} isn't lowercase letters, digits and _"
            )
        if data.get("api") != API_VERSION:
            raise PluginLoadError(
                f"Plugin '{name}' is written for contract version {data.get('api')!r}; "
                f"this host supports {API_VERSION}"
            )
        files = data.get("files")
        if not isinstance(files, list) or not all(isinstance(f, str) for f in files):
            raise PluginLoadError(
                f"Plugin '{name}': 'files' must be a list of file names"
            )
        for f in files:
            # Flat folder: the plugin server serves only files directly in
            # the plugin folder (decision 0019), and so does this loader.
            if not _FILE.match(f) or f in (MANIFEST_FILE, INSTALL_FILE) or ".." in f:
                raise PluginLoadError(f"Plugin '{name}': {f!r} isn't a plain file name")
        if "__init__.py" not in files:
            raise PluginLoadError(f"Plugin '{name}' has no __init__.py")
        entry = data.get("entry")
        module, _, attr = str(entry).partition(":")
        if not module or not attr:
            raise PluginLoadError(
                f"Plugin '{name}': entry {entry!r} isn't 'module:Class'"
            )
        if f"{module}.py" not in files:
            raise PluginLoadError(
                f"Plugin '{name}': entry module {module}.py isn't in its files"
            )
        return cls(
            name=name,
            version=str(data.get("version", "")),
            entry=entry,
            files=list(files),
        )

    @classmethod
    def read(cls, directory: Path) -> Manifest:
        try:
            data = json.loads((directory / MANIFEST_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise PluginLoadError(f"Can't read {directory / MANIFEST_FILE}: {e}") from e
        return cls.parse(data)


def package_name(name: str) -> str:
    """The package a plugin is imported as."""
    return f"acsi_{name}_plugin"


# ==================== Sources ====================


def is_allowed(url: str, allowed: list[str]) -> bool:
    """Whether `url` is under one of the `allowed` URLs.

    Scheme, host and port must be equal, and the allowed path must be a
    whole-segment prefix of the URL's path. Plain string prefixes aren't
    enough: "http://rti-io:9000" would also match "http://rti-io:9000.evil.test".
    """
    target = urlsplit(url)
    for entry in allowed:
        base = urlsplit(entry.strip())
        if not base.scheme or (target.scheme, target.netloc) != (
            base.scheme,
            base.netloc,
        ):
            continue
        base_path = base.path.rstrip("/")
        if target.path == base_path or target.path.startswith(base_path + "/"):
            return True
    return False


async def download(
    name: str,
    source_url: str,
    storage: Path,
    allowed: list[str],
    *,
    client: httpx.AsyncClient | None = None,
) -> Manifest:
    """Download plugin `name` from `source_url` into `<storage>/<name>/`.

    The files are fetched into a temporary folder first, so a failed
    download leaves the previous files as they were.
    """
    if not is_allowed(source_url, allowed):
        raise SourceNotAllowedError(
            f"Source {source_url} is not allowed; add it to PLUGIN_ALLOWED_SOURCES"
        )
    base = source_url.rstrip("/")
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=10.0)
    try:
        manifest = Manifest.parse(
            await _get(client, f"{base}/{MANIFEST_FILE}", json_body=True)
        )
        if manifest.name != name:
            raise PluginLoadError(
                f"{source_url} serves plugin '{manifest.name}', not '{name}'"
            )
        storage.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{name}-", dir=storage))
        try:
            for f in manifest.files:
                (staging / f).write_bytes(await _get(client, f"{base}/{f}"))
            (staging / MANIFEST_FILE).write_text(
                json.dumps({**_manifest_dict(manifest), "api": API_VERSION}, indent=2),
                encoding="utf-8",
            )
            target = storage / name
            if target.exists():
                shutil.rmtree(target)
            staging.rename(target)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    finally:
        if own_client:
            await client.aclose()
    logger.info(f"Downloaded plugin '{name}' {manifest.version} from {source_url}")
    return manifest


def _manifest_dict(m: Manifest) -> dict[str, Any]:
    return {"name": m.name, "version": m.version, "entry": m.entry, "files": m.files}


async def _get(client: httpx.AsyncClient, url: str, json_body: bool = False) -> Any:
    try:
        response = await client.get(url)
    except httpx.HTTPError as e:
        raise PluginLoadError(f"Can't fetch {url}: {e}") from e
    if response.status_code != 200:
        try:
            detail = response.json().get("detail")
        except Exception:
            detail = None
        raise PluginLoadError(
            f"Can't fetch {url}: HTTP {response.status_code}"
            + (f": {detail}" if detail else "")
        )
    if json_body:
        try:
            return json.loads(response.content)
        except ValueError as e:
            raise PluginLoadError(f"{url} isn't JSON: {e}") from e
    return response.content


# ==================== Storage ====================


def stored(storage: Path) -> list[str]:
    """The plugins downloaded into `storage` (folders with a manifest)."""
    if not storage.is_dir():
        return []
    return sorted(
        d.name
        for d in storage.iterdir()
        if d.is_dir() and (d / MANIFEST_FILE).is_file()
    )


def save_install(directory: Path, source: str | None, settings: dict[str, Any]) -> None:
    """Remember where a plugin came from and its settings, for the next start."""
    (directory / INSTALL_FILE).write_text(
        json.dumps({"source": source, "settings": settings}, indent=2), encoding="utf-8"
    )


def read_install(directory: Path) -> tuple[str | None, dict[str, Any]]:
    try:
        data = json.loads((directory / INSTALL_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, {}
    return data.get("source"), dict(data.get("settings") or {})


# ==================== Import ====================


def unload_modules(name: str) -> None:
    """Remove the plugin's package and its modules from sys.modules."""
    package = package_name(name)
    for module in [
        n for n in sys.modules if n == package or n.startswith(package + ".")
    ]:
        del sys.modules[module]


def load(name: str, directory: Path) -> tuple[AcsiPlugin, Manifest]:
    """Import the plugin in `directory` as `acsi_<name>_plugin` and create it.

    Always imports the files on disk: any modules of an earlier load are
    dropped first. A failed load leaves no modules behind.
    """
    manifest = Manifest.read(directory)
    if manifest.name != name:
        raise PluginLoadError(
            f"{directory} holds plugin '{manifest.name}', not '{name}'"
        )
    missing = [f for f in manifest.files if not (directory / f).is_file()]
    if missing:
        raise PluginLoadError(f"Plugin '{name}' is missing {', '.join(missing)}")

    package = package_name(name)
    unload_modules(name)
    try:
        spec = importlib.util.spec_from_file_location(
            package,
            directory / "__init__.py",
            submodule_search_locations=[str(directory)],
        )
        if spec is None or spec.loader is None:
            raise PluginLoadError(f"Can't import plugin '{name}' from {directory}")
        module = importlib.util.module_from_spec(spec)
        # Registered before exec_module: relative imports, and Pydantic's
        # deferred schema builds, look the package up in sys.modules.
        sys.modules[package] = module
        spec.loader.exec_module(module)

        module_name, _, attr = manifest.entry.partition(":")
        cls = getattr(importlib.import_module(f"{package}.{module_name}"), attr, None)
        if not (isinstance(cls, type) and issubclass(cls, AcsiPlugin)):
            raise PluginLoadError(
                f"Plugin '{name}': {manifest.entry} isn't an AcsiPlugin class"
            )
        for loaded in [
            m for n, m in sys.modules.items() if n.startswith(package + ".")
        ]:
            _rebuild_pydantic_models(loaded)
        return cls(), manifest
    except PluginLoadError:
        unload_modules(name)
        raise
    except Exception as e:
        unload_modules(name)
        raise PluginLoadError(f"Plugin '{name}' failed to load: {e!r}") from e


def installed() -> dict[str, tuple[type[AcsiPlugin], str]]:
    """Plugins installed with the image: name -> (class, version)."""
    found: dict[str, tuple[type[AcsiPlugin], str]] = {}
    for ep in importlib.metadata.entry_points(group=ENTRY_POINT_GROUP):
        try:
            cls = ep.load()
        except Exception as e:
            logger.error(f"Installed plugin '{ep.name}' failed to load: {e!r}")
            continue
        if isinstance(cls, type) and issubclass(cls, AcsiPlugin):
            version = ep.dist.version if ep.dist is not None else ""
            found[ep.name] = (cls, version)
        else:
            logger.error(f"Installed plugin '{ep.name}' isn't an AcsiPlugin class")
    return found


def _rebuild_pydantic_models(module) -> None:
    """Build any deferred Pydantic schemas in `module` now.

    Pydantic can defer a model's schema until first use, and then resolves
    forward references through sys.modules. Building them here makes a
    broken model fail the load instead of the next /openapi.json request.
    """
    try:
        from pydantic import BaseModel
    except ImportError:
        return
    for attr, obj in vars(module).items():
        if (
            isinstance(obj, type)
            and issubclass(obj, BaseModel)
            and obj is not BaseModel
        ):
            try:
                obj.model_rebuild(force=True, _types_namespace=vars(module))
            except Exception as e:
                logger.warning(
                    f"Could not build Pydantic model '{attr}' in {module.__name__}: {e}"
                )
