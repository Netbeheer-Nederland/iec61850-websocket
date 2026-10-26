# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The plugin configuration of an FSP or SO (decision 0029)."""

import json

import pytest
from acsi_plugins import PluginEntry, PluginsConfig
from acsi_plugins.config import ConfigError

pytestmark = pytest.mark.unit

CONFIG = {
    "host_url": "http://rti-fsp01:5001",
    "plugins": [
        {"name": "io", "url": "http://dr-panel:9000/plugin", "settings": {"a": 1}},
        {"name": "sim_leds", "url": "http://localhost:8099/plugin"},
    ],
}


def test_a_configuration_is_read(tmp_path):
    path = tmp_path / "plugins.json"
    path.write_text(json.dumps(CONFIG), encoding="utf-8")
    config = PluginsConfig.read(path)
    assert config.host_url == "http://rti-fsp01:5001"
    assert config.plugins == [
        PluginEntry("io", "http://dr-panel:9000/plugin", {"a": 1}),
        PluginEntry("sim_leds", "http://localhost:8099/plugin", {}),
    ]


def test_a_list_is_the_plugins():
    config = PluginsConfig.parse(CONFIG["plugins"])
    assert config.host_url is None
    assert [p.name for p in config.plugins] == ["io", "sim_leds"]


@pytest.mark.parametrize(
    "plugins",
    [
        [{"name": "Bad", "url": "http://x"}],
        [{"name": "io", "url": "ftp://x"}],
        [{"name": "io"}],
        [{"name": "io", "url": "http://x", "settings": []}],
        [{"name": "io", "url": "http://x"}, {"name": "io", "url": "http://y"}],
        "io",
    ],
)
def test_a_bad_configuration_is_refused(plugins):
    with pytest.raises(ConfigError):
        PluginsConfig.parse({"plugins": plugins})


def test_an_unreadable_file_is_refused(tmp_path):
    with pytest.raises(ConfigError, match="Can't read"):
        PluginsConfig.read(tmp_path / "missing.json")


def test_merged_lets_the_other_win():
    base = PluginsConfig.parse(CONFIG)
    other = PluginsConfig.parse(
        {"host_url": "http://h:1", "plugins": [{"name": "io", "url": "http://io2"}]}
    )
    merged = base.merged(other)
    assert merged.host_url == "http://h:1"
    assert {p.name: p.url for p in merged.plugins} == {
        "io": "http://io2",
        "sim_leds": "http://localhost:8099/plugin",
    }
