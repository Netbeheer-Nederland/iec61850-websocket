# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The plugin configuration of an FSP or SO (decision 0029).

A JSON file (PLUGINS_FILE), or the same JSON inline (PLUGINS):

    {
      "host_url": "http://rti-fsp01:5001",
      "plugins": [
        {"name": "io", "url": "http://dr-panel:9000/plugin", "settings": {}}
      ]
    }

`host_url` is where the plugins reach this FSP or SO; `url` is each
plugin's base URL (openapi.yaml, tag "Plugin API"). A bare list stands for
{"plugins": [...]}.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .remote import NAME


class ConfigError(ValueError):
    """The plugin configuration isn't valid; the message says why."""


@dataclass(frozen=True)
class PluginEntry:
    name: str
    url: str
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PluginsConfig:
    host_url: str | None = None
    plugins: list[PluginEntry] = field(default_factory=list)

    @classmethod
    def parse(cls, data: Any) -> PluginsConfig:
        if isinstance(data, list):
            data = {"plugins": data}
        if not isinstance(data, dict):
            raise ConfigError("expected an object with 'plugins', or a list")
        host_url = data.get("host_url")
        if host_url is not None and not isinstance(host_url, str):
            raise ConfigError("'host_url' must be a URL")
        raw = data.get("plugins", [])
        if not isinstance(raw, list):
            raise ConfigError("'plugins' must be a list")
        plugins: list[PluginEntry] = []
        for i, entry in enumerate(raw):
            if not isinstance(entry, dict):
                raise ConfigError(f"plugins[{i}] isn't an object")
            name, url = entry.get("name"), entry.get("url")
            if not isinstance(name, str) or not NAME.match(name):
                raise ConfigError(
                    f"plugins[{i}]: name {name!r} isn't lowercase letters, digits and _"
                )
            if not isinstance(url, str) or not url.startswith(("http://", "https://")):
                raise ConfigError(f"plugin '{name}': url {url!r} isn't an http(s) URL")
            settings = entry.get("settings")
            if settings is None:
                settings = {}
            if not isinstance(settings, dict):
                raise ConfigError(f"plugin '{name}': settings must be an object")
            if any(p.name == name for p in plugins):
                raise ConfigError(f"plugin '{name}' is configured twice")
            plugins.append(PluginEntry(name, url, dict(settings)))
        return cls(host_url=host_url, plugins=plugins)

    @classmethod
    def read(cls, path: Path) -> PluginsConfig:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise ConfigError(f"Can't read {path}: {e}") from e
        return cls.parse(data)

    def merged(self, other: PluginsConfig) -> PluginsConfig:
        """This configuration, with `other`'s host_url and plugins winning."""
        by_name = {p.name: p for p in self.plugins}
        by_name.update({p.name: p for p in other.plugins})
        return PluginsConfig(
            host_url=other.host_url or self.host_url, plugins=list(by_name.values())
        )
