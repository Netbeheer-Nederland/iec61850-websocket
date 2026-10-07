# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""No doc or source names the IO module's old files and folders (decision 0018)."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
OLD_NAMES = [
    "io_api_server",
    "io_client_file_server",
    "async_client_io",
    "mapping_manager.py",
    "README_IO",
    "AsyncDemoIOClient",
    "IO-Device-Control",
    "GPIO-LED-Control",
]
# Where an old name is the point: the decision record, and the server's list
# of file names it answers with 410.
ALLOWED = {
    "docs/rti-demo/decisions/0018-io-module-names.md",
    "examples/rti-demo/modules/io/rti_io/server/plugin_files.py",
    "examples/rti-demo/modules/io/tests/test_plugin_files.py",
    "examples/rti-demo/modules/io/tests/test_plugin_client.py",
    "examples/rti-demo/modules/fsp/tests/test_io_plugin_loading.py",
    "examples/rti-demo/modules/so/tests/test_io_plugin_loading.py",
    "tests/unit/test_rti_demo_io_names.py",
}


@pytest.mark.parametrize("name", OLD_NAMES)
def test_old_name_is_gone(name):
    found = subprocess.run(
        ["git", "grep", "-l", "-F", name], cwd=ROOT, capture_output=True, text=True
    ).stdout.split()
    assert sorted(set(found) - ALLOWED) == []
