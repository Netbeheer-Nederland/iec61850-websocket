# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""Which header pins each device uses, so two devices can't take the same one.

Every device claims the pins it needs (`device_claims`); `io_config.json` can
also reserve pins for hardware this server doesn't drive (`reserved_pins`),
such as a display run by another program on the same Pi. A pin can be shared
only by the claims of one group: the SPI and I2C bus pins by every device on
that bus, a chip select or I2C address by the channels of one ADC chip.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .devices import (
    DeviceConfig,
    DigitalDeviceConfig,
    LCDConfig,
    LCDI2CConfig,
    PotentiometerConfig,
)

# BCM GPIO number -> physical pin on the 40-pin header (Pi 3, 4 and 5).
BCM_TO_PHYSICAL = {
    0: 27,
    1: 28,
    2: 3,
    3: 5,
    4: 7,
    5: 29,
    6: 31,
    7: 26,
    8: 24,
    9: 21,
    10: 19,
    11: 23,
    12: 32,
    13: 33,
    14: 8,
    15: 10,
    16: 36,
    17: 11,
    18: 12,
    19: 35,
    20: 38,
    21: 40,
    22: 15,
    23: 16,
    24: 18,
    25: 22,
    26: 37,
    27: 13,
}

# SPI bus -> (SCLK, MOSI, MISO, chip selects by device number)
SPI_PINS = {0: (11, 10, 9, {0: 8, 1: 7}), 1: (21, 20, 19, {0: 18, 1: 17, 2: 16})}
# I2C bus -> (SDA, SCL)
I2C_PINS = {1: (2, 3), 0: (0, 1)}


@dataclass(frozen=True)
class Claim:
    """One resource a device (or a reservation) uses.

    resource: "GPIO17", "SPI0.1" or "I2C1@0x27".
    group: claims of the same group may share the resource.
    """

    resource: str
    owner: str
    purpose: str
    group: str


def spi_claims(owner: str, bus: int, device: int, chip_group: str) -> list[Claim]:
    if bus not in SPI_PINS or device not in SPI_PINS[bus][3]:
        raise ValueError(f"{owner}: no SPI{bus}.{device} on the header")
    sclk, mosi, miso, ces = SPI_PINS[bus]
    bus_group = f"spi{bus}"
    return [
        Claim(f"GPIO{sclk}", owner, f"SPI{bus} SCLK", bus_group),
        Claim(f"GPIO{mosi}", owner, f"SPI{bus} MOSI", bus_group),
        Claim(f"GPIO{miso}", owner, f"SPI{bus} MISO", bus_group),
        Claim(f"GPIO{ces[device]}", owner, f"SPI{bus} CE{device}", chip_group),
        Claim(f"SPI{bus}.{device}", owner, f"/dev/spidev{bus}.{device}", chip_group),
    ]


def i2c_claims(owner: str, bus: int, address: int, chip_group: str) -> list[Claim]:
    claims = [
        Claim(
            f"I2C{bus}@0x{address:02X}",
            owner,
            f"I2C address 0x{address:02X}",
            chip_group,
        )
    ]
    if bus in I2C_PINS:  # other buses are overlays on pins we don't know
        sda, scl = I2C_PINS[bus]
        claims += [
            Claim(f"GPIO{sda}", owner, f"I2C{bus} SDA", f"i2c{bus}"),
            Claim(f"GPIO{scl}", owner, f"I2C{bus} SCL", f"i2c{bus}"),
        ]
    return claims


def gpio_claim(owner: str, pin: int, purpose: str) -> Claim:
    if pin not in BCM_TO_PHYSICAL:
        raise ValueError(f"{owner}: GPIO{pin} is not on the 40-pin header (GPIO0..27)")
    return Claim(f"GPIO{pin}", owner, purpose, owner)


def device_claims(config: DeviceConfig) -> list[Claim]:
    """The pins and bus addresses a configured device uses."""
    name = config.name
    if isinstance(config, PotentiometerConfig):
        adc = (config.adc_type or "").lower()
        if adc == "mcp3008":
            chip = f"mcp3008 SPI{config.spi_bus}.{config.spi_device}"
            return spi_claims(name, config.spi_bus, config.spi_device, chip)
        chip = f"{adc} I2C{config.i2c_bus}@0x{config.i2c_address:02X}"
        return i2c_claims(name, config.i2c_bus, config.i2c_address, chip)
    if isinstance(config, LCDI2CConfig):
        return i2c_claims(name, config.i2c_bus, config.i2c_address, name)
    if isinstance(config, LCDConfig):
        pins = {
            "RS": config.gpio_rs,
            "E": config.gpio_e,
            "RW": config.gpio_rw,
            "backlight": config.backlight_pin,
        }
        pins.update({f"D{4 + i}": pin for i, pin in enumerate(config.gpio_data)})
        return [
            gpio_claim(name, pin, f"LCD {role}")
            for role, pin in pins.items()
            if pin is not None
        ]
    if isinstance(config, DigitalDeviceConfig):
        return [gpio_claim(name, config.gpio_pin, config.device_type.value)]
    return []


def reserved_claims(reserved: list[dict[str, Any]]) -> list[Claim]:
    """Claims for io_config.json's "reserved_pins".

    Each entry has "by" (what uses it) and one of:
    {"gpio": 25}, {"spi": "0.1"} (bus.device: its CE and the bus pins, shared
    with this server's SPI devices) or {"i2c": "1@0x3C"}.
    """
    claims = []
    for entry in reserved or []:
        by = str(entry.get("by") or "reserved")
        owner = f"reserved: {by}"
        if "gpio" in entry:
            claims.append(gpio_claim(owner, int(entry["gpio"]), by))
        elif "spi" in entry:
            bus, _, device = str(entry["spi"]).partition(".")
            claims += spi_claims(owner, int(bus), int(device or 0), owner)
        elif "i2c" in entry:
            bus, _, address = str(entry["i2c"]).partition("@")
            claims += i2c_claims(owner, int(bus), int(address, 0), owner)
        else:
            raise ValueError(f"Reserved pin entry needs gpio, spi or i2c: {entry}")
    return claims


def find_conflicts(new: list[Claim], existing: list[Claim]) -> list[str]:
    """Why `new` can't be added next to `existing`; empty when it can."""
    taken = {}
    for claim in existing:
        taken.setdefault(claim.resource, []).append(claim)
    conflicts = []
    for claim in new:
        for other in taken.get(claim.resource, []):
            if other.group != claim.group and other.owner != claim.owner:
                conflicts.append(
                    f"{claim.resource} ({claim.purpose}) for {claim.owner} is used by "
                    f"{other.owner} ({other.purpose})"
                )
                break
    return conflicts


def pin_map(claims: list[Claim]) -> dict[str, Any]:
    """Every header pin with what uses it, for GET /api/io/pins."""
    users: dict[str, list[dict[str, str]]] = {}
    for claim in claims:
        users.setdefault(claim.resource, []).append(
            {"owner": claim.owner, "purpose": claim.purpose}
        )
    gpio = [
        {
            "gpio": bcm,
            "physical": BCM_TO_PHYSICAL[bcm],
            "used_by": users.get(f"GPIO{bcm}", []),
        }
        for bcm in sorted(BCM_TO_PHYSICAL)
    ]
    buses = {
        res: who for res, who in sorted(users.items()) if not res.startswith("GPIO")
    }
    return {
        "gpio": gpio,
        "buses": buses,
        "free": [row["gpio"] for row in gpio if not row["used_by"]],
    }
