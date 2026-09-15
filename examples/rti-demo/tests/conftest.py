"""Shared pytest configuration for the rti-demo test suite.

The fsp/so unit tests import `ws61850` (the core IEC 61850 library that
lives at the repo root, e.g. `from ws61850.endpoint import ActiveEndpoint`
in fsp/acsi_server.py). rti-demo is its own standalone uv project with its
own pyproject.toml/uv.lock, and doesn't declare ws61850 as a dependency, so
without this it's simply not importable here.

Rather than pulling ws61850 in as a managed dependency (which would mean
reconciling rti-demo's dependency pins against the root project's - e.g.
aiohttp, requests, flask and websockets are pinned to different, mutually
incompatible versions on each side), this adds the root project's `src/`
directory to sys.path, the same way individual test modules already add
rti-demo's own fsp/, so/ and bff/ directories (which aren't packages
either) - see e.g. tests/unit/fsp/test_bff_endpoint.py.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_WS61850_SRC = _REPO_ROOT / "src"

if _WS61850_SRC.is_dir() and str(_WS61850_SRC) not in sys.path:
    sys.path.insert(0, str(_WS61850_SRC))


def import_module_from_path(module_name: str, file_path: Path):
    """Load a standalone (non-package) .py file as a uniquely-named module.

    fsp/bff_endpoint.py and so/bff_endpoint.py are both literally named
    "bff_endpoint.py" in their own directories. A plain `import bff_endpoint`
    after adding each directory to sys.path works when only one of those
    test files ever runs, but caches under the single key
    sys.modules["bff_endpoint"] - so whichever file's test module imports
    first "wins", and the other file silently gets handed the wrong module
    (wrong routes, wrong signatures) when the full suite runs together.

    Give each one a distinct sys.modules key (e.g. "fsp_bff_endpoint" /
    "so_bff_endpoint") instead. The module's own internal same-directory
    imports (e.g. `from acsi_server import ACSIServer`) still resolve
    normally via sys.path, which is unaffected by what name this module
    itself is registered under.
    """
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
