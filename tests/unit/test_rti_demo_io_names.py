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


@pytest.mark.parametrize("old", ["rti_io", "rpi_io", "rpi-io", "rti-io"])
def test_the_io_server_code_is_dr_panel(old):
    # Decision 0023 renamed rti_io to rpi_io, and 0038 rpi_io to dr_panel
    # (image rti-io to dr-panel); only the decision records keep the old
    # names, as the paths they were written with, and the tests that check
    # they are gone.
    allowed = {
        "examples/rti-plugins/dr_panel/tests/test_project.py",
        "tests/unit/test_rti_demo_io_image.py",
        "tests/unit/test_rti_demo_io_names.py",
    }
    found = subprocess.run(
        ["git", "grep", "-l", "-w", "-F", old],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout.split()
    assert [
        f
        for f in found
        if not f.startswith("docs/rti-demo/decisions/") and f not in allowed
    ] == []


@pytest.mark.parametrize(
    "pattern",
    [r"/api/plugins/io\b", r"""["']name["']\s*:\s*["']io["']""", r"name: 'io'"],
)
def test_the_io_plugin_name_is_dr_panel(pattern):
    # Decision 0040 renamed the plugin io to dr_panel, and its routes
    # /api/plugins/io to /api/plugins/dr_panel; the role keeps io.
    found = subprocess.run(
        ["git", "grep", "-l", "-P", pattern],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout.split()
    assert [
        f
        for f in found
        if not f.startswith("docs/rti-demo/decisions/")
        and f != "tests/unit/test_rti_demo_io_names.py"
    ] == []


# Links to decision 0034 keep the file name it was written with.
DECISION_0034 = "0034-demo-stack-plugins-sim-leds-io-opt-in.md"


@pytest.mark.parametrize("old", ["sim_leds", "sim-leds", "SIM_LEDS"])
def test_the_sample_plugin_is_dr_leds(old):
    # Decision 0039 renamed sim_leds to dr_leds (sim-leds to dr-leds); only the
    # decision records keep the old names, and this test.
    found = subprocess.run(
        ["git", "grep", "-l", "-F", old],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout.split()
    assert [
        f
        for f in found
        if not f.startswith("docs/rti-demo/decisions/")
        and f != "tests/unit/test_rti_demo_io_names.py"
        and old in (ROOT / f).read_text().replace(DECISION_0034, "")
    ] == []
