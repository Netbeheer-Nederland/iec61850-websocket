# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The IO server is the package rpi_io, flat, in src/ (decision 0023)."""

import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

IO = Path(__file__).resolve().parents[1]
PROJECT = tomllib.loads((IO / "pyproject.toml").read_text(encoding="utf-8"))


def test_the_distribution_is_named_after_the_package():
    assert PROJECT["project"]["name"] == "rpi-io"


def test_the_package_is_built_from_src():
    assert PROJECT["build-system"]["build-backend"] == "setuptools.build_meta"
    assert PROJECT["tool"]["setuptools"]["packages"]["find"]["where"] == ["src"]
    assert "io_config.json" in PROJECT["tool"]["setuptools"]["package-data"]["rpi_io"]


def test_the_code_is_flat_in_src_rpi_io():
    package = IO / "src" / "rpi_io"
    assert (package / "main.py").is_file()
    assert (package / "io_config.json").is_file()
    assert not (IO / "rti_io").exists()
    assert not (package / "server").exists()


def test_it_depends_only_on_what_it_imports():
    names = {
        dep.split(">")[0].split("=")[0].split("<")[0].strip().lower()
        for dep in PROJECT["project"]["dependencies"]
    }
    assert names == {
        "fastapi",
        "pydantic",
        "uvicorn",
        "httpx2",
        "gpiod",
        "gpiozero",
        "smbus2",
        "adafruit-ads1x15",
    }
