# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""Pins are configuration: each device claims its pins, io_config.json can
reserve pins for other hardware, and two users can't take the same pin."""

import json
from pathlib import Path

import pytest
from dr_panel.server.api_endpoint import create_io_router
from dr_panel.server.devices import (
    ButtonConfig,
    LCDI2CConfig,
    LEDConfig,
    PotentiometerConfig,
)
from dr_panel.server.io_config import (
    _config_to_dict,
    _dict_to_config,
    load_reserved_pins,
    save_full_config,
)
from dr_panel.server.io_controller import IOController
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

SHIPPED = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "dr_panel"
    / "server"
    / "io_config.json"
)

# The ST7789V display of dr-st7789v, on a Pi shared with the IO server
DISPLAY = [
    {"gpio": 25, "by": "ST7789V display DC"},
    {"gpio": 27, "by": "ST7789V display RST"},
    {"spi": "0.1", "by": "ST7789V display"},
]


def shipped_controller():
    controller = IOController()
    assert controller.load_config(str(SHIPPED))
    return controller


def users(pin_map, gpio):
    return [user["owner"] for user in pin_map["gpio"][gpio]["used_by"]]


def test_the_shipped_config_has_no_conflicts():
    controller = shipped_controller()
    shipped = json.loads(SHIPPED.read_text(encoding="utf-8"))
    assert set(controller.configs) == {device["name"] for device in shipped["devices"]}
    pins = controller.pin_map()
    assert users(pins, 24) == ["button3"]
    assert set(users(pins, 8)) == {"pot1", "pot2", "pot3", "pot4"}  # one MCP3008 on CE0
    assert {7, 25, 27} <= set(pins["free"])


def test_the_display_pins_can_be_reserved_next_to_the_shipped_devices():
    controller = shipped_controller()
    controller.set_reserved_pins(DISPLAY)
    pins = controller.pin_map()
    assert users(pins, 7) == ["reserved: ST7789V display"]
    assert set(users(pins, 11)) >= {
        "pot1",
        "reserved: ST7789V display",
    }  # SPI0 bus is shared
    assert 25 not in pins["free"]


def test_a_reservation_on_a_used_pin_is_refused():
    controller = shipped_controller()
    with pytest.raises(ValueError, match="GPIO24 .* is used by button3"):
        controller.set_reserved_pins([{"gpio": 24, "by": "ST7789V display RST"}])


def test_a_device_on_a_reserved_or_used_pin_is_refused():
    controller = shipped_controller()
    controller.set_reserved_pins(DISPLAY)
    with pytest.raises(ValueError, match="GPIO25"):
        controller.add_device(LEDConfig(name="led4", gpio_pin=25))
    with pytest.raises(ValueError, match="GPIO17"):
        controller.add_device(ButtonConfig(name="button4", gpio_pin=17))
    with pytest.raises(ValueError, match="SPI0 MOSI"):
        controller.add_device(LEDConfig(name="led5", gpio_pin=10))
    with pytest.raises(ValueError, match="SPI0.1"):
        controller.add_device(
            PotentiometerConfig(name="pot5", adc_type="mcp3008", spi_device=1)
        )
    controller.add_device(LEDConfig(name="led6", gpio_pin=5))


def test_channels_of_one_adc_share_it_but_two_chips_cannot_share_an_address():
    controller = IOController()
    controller.add_device(
        PotentiometerConfig(name="a0", adc_type="ads1115", adc_channel=0)
    )
    controller.add_device(
        PotentiometerConfig(name="a1", adc_type="ads1115", adc_channel=1)
    )
    controller.add_device(LCDI2CConfig(name="lcd", i2c_address=0x27))
    with pytest.raises(ValueError, match="I2C1@0x27"):
        controller.add_device(LCDI2CConfig(name="lcd2", i2c_address=0x27))


def test_loading_skips_a_conflicting_device_and_keeps_the_rest(tmp_path):
    config = json.loads(SHIPPED.read_text(encoding="utf-8"))
    config["reserved_pins"] = [
        {"gpio": 18, "by": "fan"}
    ]  # led2's pin: the wired fan wins
    config["devices"].append(
        {"name": "led9", "device_type": "led", "gpio_pin": 17}
    )  # led1's
    path = tmp_path / "io_config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    controller = IOController()
    assert controller.load_config(str(path))
    assert "led1" in controller.configs and "button1" in controller.configs
    assert "led9" not in controller.configs and "led2" not in controller.configs
    assert controller.reserved_pins == [{"gpio": 18, "by": "fan"}]


def test_potentiometer_settings_survive_a_save():
    pot = PotentiometerConfig(
        name="pot1",
        adc_type="mcp3008",
        adc_channel=2,
        spi_bus=0,
        spi_device=1,
        spi_speed_hz=500_000,
        is_inverted=True,
        change_threshold=0.1,
        adc_reference_voltage=5.0,
    )
    again = _dict_to_config(_config_to_dict(pot))
    assert (
        again.spi_device,
        again.spi_speed_hz,
        again.is_inverted,
        again.change_threshold,
        again.adc_reference_voltage,
        again.adc_channel,
    ) == (1, 500_000, True, 0.1, 5.0, 2)


def test_saving_keeps_the_reserved_pins(tmp_path):
    path = tmp_path / "io_config.json"
    save_full_config(
        {"led1": LEDConfig(name="led1", gpio_pin=17)},
        path=str(path),
        reserved_pins=DISPLAY,
    )
    save_full_config({"led1": LEDConfig(name="led1", gpio_pin=17)}, path=str(path))
    assert load_reserved_pins(str(path)) == DISPLAY


def test_pins_route_and_conflict_answers_400():
    controller = shipped_controller()
    controller.set_reserved_pins(DISPLAY)
    app = FastAPI()
    app.include_router(create_io_router(app, controller))
    client = TestClient(app)
    body = client.get("/api/io/pins").json()
    assert body["ok"] and body["reserved_pins"] == DISPLAY
    assert body["gpio"][27]["physical"] == 13
    assert "SPI0.1" in body["buses"]
    response = client.post(
        "/api/io/devices/config",
        json={"name": "led4", "device_type": "led", "identifier": 25},
    )
    assert response.status_code == 400, response.text
    assert "GPIO25" in response.json()["detail"]
