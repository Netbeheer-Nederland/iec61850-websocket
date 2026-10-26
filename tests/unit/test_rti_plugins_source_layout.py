# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""Every plugin in examples/rti-plugins has the source layout of decision 0031:
server/ is the service, plugin/ the plugin API, and only the server's app
factory imports the plugin. The source is read, not imported: the IO plugin's
hardware packages aren't installed here."""

import ast
import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

PLUGINS = Path(__file__).resolve().parents[2] / "examples" / "rti-plugins"
PROJECTS = sorted(p.parent for p in PLUGINS.glob("*/pyproject.toml"))
# The FSP's and SO's code: a plugin knows them only through openapi.yaml.
HOST_PACKAGES = {"acsi_plugins", "fsp", "so", "bff", "ws61850"}


def _package(project: Path) -> Path:
    [package] = [
        p for p in (project / "src").iterdir() if (p / "__init__.py").is_file()
    ]
    return package


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _imports(path: Path) -> list[ast.ImportFrom | ast.Import]:
    return [
        n for n in ast.walk(_tree(path)) if isinstance(n, ast.Import | ast.ImportFrom)
    ]


def _imports_plugin(path: Path) -> bool:
    """A relative import of the sibling subpackage plugin, from server/."""
    return any(
        isinstance(n, ast.ImportFrom)
        and n.level == 2
        and (n.module or "").split(".")[0] == "plugin"
        for n in _imports(path)
    )


def test_the_plugins_are_found():
    assert [p.name for p in PROJECTS] == ["dr_leds", "dr_panel"]


@pytest.fixture(params=PROJECTS, ids=lambda p: p.name)
def project(request):
    return request.param


def test_the_package_has_only_server_and_plugin(project):
    package = _package(project)
    assert sorted(p.name for p in package.glob("*.py")) == ["__init__.py"]
    for sub in ("server", "plugin"):
        assert (package / sub / "__init__.py").is_file(), sub


def test_the_script_is_server_main(project):
    package = _package(project)
    pyproject = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))
    assert list(pyproject["project"]["scripts"].values()) == [
        f"{package.name}.server.main:main"
    ]
    functions = {
        n.name
        for n in _tree(package / "server" / "main.py").body
        if isinstance(n, ast.FunctionDef)
    }
    assert "main" in functions


def test_the_plugin_module_has_the_plugin_api(project):
    path = _package(project) / "plugin" / "plugin.py"
    tree = _tree(path)
    assigned = {
        t.id: n.value
        for n in tree.body
        if isinstance(n, ast.Assign)
        for t in n.targets
        if isinstance(t, ast.Name)
    }
    assert isinstance(assigned["NAME"], ast.Constant)
    assert ast.literal_eval(assigned["API_VERSION"]) == 2
    defined = {
        n.name for n in tree.body if isinstance(n, ast.ClassDef | ast.FunctionDef)
    }
    assert {"Host", "StartRequest", "EventRequest", "create_plugin_router"} <= defined
    text = path.read_text(encoding="utf-8")
    assert 'prefix="/plugin"' in text
    assert 'tags=["Plugin API (decision 0029)"]' in text


def test_the_version_is_the_project_s(project):
    pyproject = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))
    text = (_package(project) / "plugin" / "plugin.py").read_text(encoding="utf-8")
    assert f'importlib.metadata.version("{pyproject["project"]["name"]}")' in text


def test_the_plugin_subpackage_exports_its_router(project):
    [export] = [
        n
        for n in _imports(_package(project) / "plugin" / "__init__.py")
        if isinstance(n, ast.ImportFrom)
    ]
    assert (export.level, export.module) == (1, "plugin")
    assert [a.name for a in export.names] == ["create_plugin_router"]


def test_only_the_app_factory_imports_the_plugin(project):
    server = _package(project) / "server"
    importing = [p.name for p in sorted(server.glob("*.py")) if _imports_plugin(p)]
    assert len(importing) == 1, importing
    assert "create_plugin_router" in (server / importing[0]).read_text(encoding="utf-8")


def test_no_code_of_the_fsp_or_so(project):
    for path in _package(project).rglob("*.py"):
        for node in _imports(path):
            if isinstance(node, ast.ImportFrom):
                names = [node.module or ""] if node.level == 0 else []
            else:
                names = [a.name for a in node.names]
            for name in names:
                assert name.split(".")[0] not in HOST_PACKAGES, f"{path}: {name}"
