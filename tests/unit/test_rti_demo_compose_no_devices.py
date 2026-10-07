# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""docker-compose.no-devices.yml runs the rti-demo without Raspberry Pi hardware.

Layered over docker-compose.yml, it must drop everything in rti-io that needs
the host's GPIO/I2C/SPI devices, so `docker compose up` works on any machine.
"""

from pathlib import Path

import pytest
import yaml

DEMO = Path(__file__).resolve().parents[2] / "examples" / "rti-demo"

# rti-io settings that only work, or only make sense, with the Pi's devices.
HARDWARE_KEYS = ["devices", "group_add", "user", "ipc", "security_opt", "cap_add"]


class _ComposeLoader(yaml.SafeLoader):
    """SafeLoader that keeps Compose's !reset / !override tags visible."""


def _tagged(loader, tag_suffix, node):
    return {"tag": f"!{tag_suffix}"}


_ComposeLoader.add_multi_constructor("!", _tagged)


def _service(name: str, file: str) -> dict:
    text = (DEMO / file).read_text(encoding="utf-8")
    return yaml.load(text, Loader=_ComposeLoader)["services"][name]  # noqa: S506


@pytest.fixture(scope="module")
def override():
    return _service("rti-io", "docker-compose.no-devices.yml")


def test_base_io_service_has_the_hardware_settings():
    base = _service("rti-io", "docker-compose.yml")
    assert set(HARDWARE_KEYS) <= set(base)


@pytest.mark.parametrize("key", HARDWARE_KEYS)
def test_override_resets_hardware_setting(override, key):
    assert override.get(key) == {"tag": "!reset"}, f"{key} is not reset"


def test_override_resets_every_hardware_setting_the_base_has(override):
    base = _service("rti-io", "docker-compose.yml")
    left = [k for k in base if k in HARDWARE_KEYS and k not in override]
    assert not left, f"rti-io keeps {left} without the devices"
