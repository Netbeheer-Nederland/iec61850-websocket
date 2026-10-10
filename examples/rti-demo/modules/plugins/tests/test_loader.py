# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""Plugins are downloaded from allowed sources and loaded as acsi_<name>_plugin (decision 0021)."""

import json
import sys

import httpx2 as httpx
import pytest
from acsi_plugins import AcsiPlugin, loader
from acsi_plugins.loader import Manifest, PluginLoadError

pytestmark = pytest.mark.unit

MANIFEST = {
    "name": "demo",
    "version": "1.0.0",
    "api": 1,
    "entry": "plugin:DemoPlugin",
    "files": ["__init__.py", "plugin.py", "helper.py"],
}
FILES = {
    "__init__.py": "",
    "helper.py": "GREETING = 'hello'\n",
    "plugin.py": (
        "from acsi_plugins import AcsiPlugin\n"
        "from .helper import GREETING\n"
        "class DemoPlugin(AcsiPlugin):\n"
        "    greeting = GREETING\n"
    ),
}


def write_plugin(directory, manifest=MANIFEST, files=FILES):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    for name, text in files.items():
        (directory / name).write_text(text, encoding="utf-8")
    return directory


def modules_of(name):
    package = loader.package_name(name)
    return sorted(n for n in sys.modules if n == package or n.startswith(package + "."))


@pytest.fixture(autouse=True)
def _unload():
    yield
    loader.unload_modules("demo")


# ==================== Manifest ====================


def test_a_manifest_is_read():
    m = Manifest.parse(MANIFEST)
    assert (m.name, m.version, m.entry) == ("demo", "1.0.0", "plugin:DemoPlugin")
    assert m.files == ["__init__.py", "plugin.py", "helper.py"]


@pytest.mark.parametrize(
    "change",
    [
        {"name": "Demo-Plugin"},
        {"api": 2},
        {"entry": "plugin"},
        {"entry": "missing:DemoPlugin"},
        {"files": ["plugin.py", "helper.py"]},
        {"files": ["__init__.py", "plugin.py", "../server/io_config.json"]},
        {"files": ["__init__.py", "plugin.py", "sub/helper.py"]},
        {"files": ["__init__.py", "plugin.py", "plugin.json"]},
    ],
)
def test_a_bad_manifest_is_refused(change):
    with pytest.raises(PluginLoadError):
        Manifest.parse({**MANIFEST, **change})


def test_the_package_name_follows_acsi_name_plugin():
    assert loader.package_name("io") == "acsi_io_plugin"


# ==================== Allowed sources ====================


@pytest.mark.parametrize(
    ("url", "allowed"),
    [
        ("http://rti-io:9000/api/io-plugin/files", True),
        ("http://rti-io:9000", True),
        ("http://rti-io:9000/other", True),
        ("https://rti-io:9000/api/io-plugin/files", False),
        ("http://rti-io:9001/api/io-plugin/files", False),
        ("http://rti-io:9000.evil.test/api", False),
        ("http://evil.test/http://rti-io:9000", False),
    ],
)
def test_a_source_is_allowed_by_scheme_host_port_and_path(url, allowed):
    assert loader.is_allowed(url, ["http://rti-io:9000"]) is allowed


def test_an_allowed_path_is_matched_by_whole_segments():
    allowed = ["http://io.test/api/io-plugin"]
    assert loader.is_allowed("http://io.test/api/io-plugin/files", allowed)
    assert not loader.is_allowed("http://io.test/api/io-plugin-evil/files", allowed)


def test_nothing_is_allowed_by_default():
    assert not loader.is_allowed("http://rti-io:9000", [])


# ==================== Download ====================


def _server(files, calls=None):
    def handler(request):
        if calls is not None:
            calls.append(request.url.path)
        name = request.url.path.rsplit("/", 1)[-1]
        if name == "plugin.json":
            return httpx.Response(200, json=files["plugin.json"])
        if name in files:
            return httpx.Response(200, text=files[name])
        return httpx.Response(404, json={"detail": "File not found"})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_download_fetches_the_manifest_then_its_files(tmp_path):
    calls = []
    client = _server({"plugin.json": MANIFEST, **FILES}, calls)
    manifest = await loader.download(
        "demo", "http://io.test/files", tmp_path, ["http://io.test"], client=client
    )
    assert manifest.name == "demo"
    assert calls == [
        "/files/plugin.json",
        "/files/__init__.py",
        "/files/plugin.py",
        "/files/helper.py",
    ]
    assert sorted(p.name for p in (tmp_path / "demo").iterdir()) == [
        "__init__.py",
        "helper.py",
        "plugin.json",
        "plugin.py",
    ]


async def test_download_refuses_a_source_that_is_not_allowed(tmp_path):
    calls = []
    client = _server({"plugin.json": MANIFEST, **FILES}, calls)
    with pytest.raises(PluginLoadError, match="not allowed"):
        await loader.download(
            "demo",
            "http://evil.test/files",
            tmp_path,
            ["http://io.test"],
            client=client,
        )
    assert calls == []


async def test_download_refuses_a_manifest_for_another_name(tmp_path):
    client = _server({"plugin.json": {**MANIFEST, "name": "other"}, **FILES})
    with pytest.raises(PluginLoadError, match="other"):
        await loader.download(
            "demo", "http://io.test/files", tmp_path, ["http://io.test"], client=client
        )


async def test_a_failed_download_keeps_the_previous_files(tmp_path):
    write_plugin(tmp_path / "demo")
    files = {"plugin.json": MANIFEST, **FILES}
    del files["helper.py"]
    with pytest.raises(PluginLoadError, match="helper.py"):
        await loader.download(
            "demo",
            "http://io.test/files",
            tmp_path,
            ["http://io.test"],
            client=_server(files),
        )
    assert (tmp_path / "demo" / "helper.py").read_text(encoding="utf-8") == FILES[
        "helper.py"
    ]


# ==================== Load ====================


def test_load_imports_the_plugin_as_one_package(tmp_path):
    plugin, manifest = loader.load("demo", write_plugin(tmp_path / "demo"))
    assert isinstance(plugin, AcsiPlugin)
    assert plugin.greeting == "hello"
    assert manifest.version == "1.0.0"
    assert modules_of("demo") == [
        "acsi_demo_plugin",
        "acsi_demo_plugin.helper",
        "acsi_demo_plugin.plugin",
    ]


def test_load_again_picks_up_changed_files(tmp_path):
    directory = write_plugin(tmp_path / "demo")
    loader.load("demo", directory)
    (directory / "helper.py").write_text("GREETING = 'changed'\n", encoding="utf-8")
    plugin, _ = loader.load("demo", directory)
    assert plugin.greeting == "changed"


def test_a_failed_load_leaves_no_modules(tmp_path):
    directory = write_plugin(tmp_path / "demo")
    (directory / "helper.py").write_text(
        "raise RuntimeError('broken')\n", encoding="utf-8"
    )
    with pytest.raises(PluginLoadError, match="broken"):
        loader.load("demo", directory)
    assert modules_of("demo") == []


def test_an_entry_that_is_not_a_plugin_is_refused(tmp_path):
    files = {**FILES, "plugin.py": "class DemoPlugin:\n    pass\n"}
    with pytest.raises(PluginLoadError, match="AcsiPlugin"):
        loader.load("demo", write_plugin(tmp_path / "demo", files=files))
    assert modules_of("demo") == []


def test_unload_drops_the_modules(tmp_path):
    loader.load("demo", write_plugin(tmp_path / "demo"))
    loader.unload_modules("demo")
    assert modules_of("demo") == []


# ==================== Install records ====================


def test_the_install_record_keeps_source_and_settings(tmp_path):
    directory = write_plugin(tmp_path / "demo")
    loader.save_install(directory, "http://io.test/files", {"io_url": "http://io.test"})
    assert loader.read_install(directory) == (
        "http://io.test/files",
        {"io_url": "http://io.test"},
    )


def test_stored_lists_the_downloaded_plugins(tmp_path):
    write_plugin(tmp_path / "demo")
    (tmp_path / "empty").mkdir()
    assert loader.stored(tmp_path) == ["demo"]
    assert loader.stored(tmp_path / "missing") == []
