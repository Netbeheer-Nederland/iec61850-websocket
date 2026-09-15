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

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_WS61850_SRC = _REPO_ROOT / "src"

if _WS61850_SRC.is_dir() and str(_WS61850_SRC) not in sys.path:
    sys.path.insert(0, str(_WS61850_SRC))
