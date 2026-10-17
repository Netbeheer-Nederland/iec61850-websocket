# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The IO plugin's docker-compose.yaml runs anywhere; docker-compose.pi.yaml
adds the Raspberry Pi's devices (decision 0030, the layout of every plugin).

Docker refuses to start a container whose device paths don't exist on the
host, so everything in rti-io that needs the host's GPIO/I2C/SPI devices is
in the Pi overlay, and `docker compose up` works on any machine.
"""

from pathlib import Path

import pytest
import yaml

IO = Path(__file__).resolve().parents[2] / "examples" / "rti-plugins" / "rpi_io"

# rti-io settings that only work, or only make sense, with the Pi's devices.
HARDWARE_KEYS = ["devices", "group_add", "user", "ipc", "security_opt", "cap_add"]


def _service(file: str) -> dict:
    return yaml.safe_load((IO / file).read_text(encoding="utf-8"))["services"]["rti-io"]


@pytest.mark.parametrize("key", HARDWARE_KEYS)
def test_the_base_has_no_hardware_setting(key):
    assert key not in _service("docker-compose.yaml")


@pytest.mark.parametrize("key", HARDWARE_KEYS)
def test_the_pi_overlay_adds_it(key):
    assert key in _service("docker-compose.pi.yaml")


def test_the_pi_overlay_adds_only_hardware_settings():
    assert set(_service("docker-compose.pi.yaml")) == set(HARDWARE_KEYS)


def test_the_old_names_are_gone():
    assert not (IO / "docker-compose.yml").exists()
    assert not (IO / "docker-compose.no-devices.yml").exists()
