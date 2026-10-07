# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The rti-io image contains what the IO server serves."""

import re
from pathlib import Path

DOCKERFILE = (
    Path(__file__).resolve().parents[2]
    / "examples"
    / "rti-demo"
    / "modules"
    / "io"
    / "docker"
    / "Dockerfile"
)


def test_io_image_ships_the_plugin_files():
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert re.search(r"^COPY io_client/ /app/io/io_client/$", text, re.MULTILINE)
