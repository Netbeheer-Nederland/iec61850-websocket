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


def test_io_image_installs_the_package():
    # The code is the package rpi_io in src/, installed by uv (decision 0023).
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert re.search(r"^COPY src/ /app/src/$", text, re.MULTILINE)
    assert re.search(r"uv sync --frozen --no-dev$", text, re.MULTILINE)
    assert 'CMD ["python", "-u", "-m", "rpi_io.main"]' in text
    assert "rti_io" not in text
