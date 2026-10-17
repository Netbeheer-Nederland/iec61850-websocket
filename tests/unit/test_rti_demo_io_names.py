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
# Where an old name is the point: the decision record, and the tests that
# check the old names are gone. The architecture diagram is drawn by hand and
# still labels the IO server io_api_server.
ALLOWED = {
    "docs/rti-demo/decisions/0018-io-module-names.md",
    "docs/rti-demo/design/RTI-demo-system-architecture.drawio",
    "examples/rti-plugins/io/plugin/tests/test_plugin_client.py",
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


def test_the_io_server_code_is_rpi_io():
    # Decision 0023 renamed rti_io to rpi_io; only the decision records keep
    # the old name, as the paths they were written with, and the tests that
    # check it is gone.
    allowed = {
        "examples/rti-plugins/io/plugin/tests/test_installed.py",
        "examples/rti-plugins/io/server/tests/test_project.py",
        "tests/unit/test_rti_demo_io_image.py",
        "tests/unit/test_rti_demo_io_names.py",
    }
    found = subprocess.run(
        ["git", "grep", "-l", "-F", "rti_io"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout.split()
    assert [
        f
        for f in found
        if not f.startswith("docs/rti-demo/decisions/") and f not in allowed
    ] == []
