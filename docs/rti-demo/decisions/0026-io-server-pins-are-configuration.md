<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 26. The IO server's pins are configuration, claimed per device and checked for conflicts

- Status: proposed
- Date: 2026-10-15

## Context

The IO server `rpi_io` (0023) drives the LEDs, buttons, potentiometers and LCDs of a Raspberry Pi from
`io_config.json`. Other devices should be able to join it: more of the same, new device types (0024's OLED), or
hardware on the same Pi that another program drives, such as an ST7789V SPI display for an FSP. How things stood
(2026-10-15):

- **Most pins are already in `io_config.json`**: `gpio_pin` for LEDs and buttons, the LCD's `gpio_*`, the I2C
  `i2c_bus` and `i2c_address`.
- **The MCP3008's SPI bus wasn't.** The shipped config sets `spi_bus` and `spi_device`, but `PotentiometerConfig`
  had no such fields and the device always opened `/dev/spidev0.0`. Loading and saving also dropped
  `adc_reference_voltage`, `is_inverted` and `change_threshold`.
- **Nothing checked for conflicts.** Two devices could take the same GPIO, or a GPIO that is an SPI or I2C bus pin.
  The built-in defaults even put a button on GPIO10, SPI0 MOSI.
- **There was no way to keep pins free** for hardware the server doesn't drive. The ST7789V display needs DC, reset
  and a chip select. With the shipped devices, reset can't be GPIO24 (`button3`), and the display can't use CE0,
  where the MCP3008 is.

## Decision

1. **Every pin is configuration.** `PotentiometerConfig` gets `spi_bus`, `spi_device` (default 0, 0) and
   `spi_speed_hz` (default 1 MHz), and the MCP3008 opens `/dev/spidev<spi_bus>.<spi_device>`. Loading and saving
   keep every potentiometer field.
2. **Each device claims its pins** (`rpi_io/pins.py`, `device_claims`). A GPIO device claims its pins. An SPI device
   claims SCLK, MOSI, MISO, its chip select and `SPI<bus>.<device>`. An I2C device claims SDA, SCL and
   `I2C<bus>@<address>`. A claim has a group, and only claims of one group share a resource. The bus pins are shared
   by every device on the bus, and a chip select or I2C address by the channels of one ADC chip.
3. **Conflicts are refused when a device is added** (`IOController.add_device`). The API answers `400` with the
   conflict. At startup, a device whose pins are taken is logged and left out, and the others still load. Before
   this, one failing device stopped the whole file from loading.
4. **`reserved_pins` in `io_config.json`** keeps pins for hardware the server doesn't drive. An entry is
   `{"gpio": n}`, `{"spi": "bus.device"}` or `{"i2c": "bus@address"}`, with `by` saying what uses it. Reservations are
   loaded before the devices and win over them, because they describe hardware that is wired. A reservation on a pin
   a device already uses is refused. Saving the configuration keeps the reservations, and `/config/update` takes a
   new list.
5. **`GET /api/io/pins`** shows every header pin with what uses it, the bus addresses in use, and the free pins, so
   someone adding a device can see where it fits.

## Consequences

- A new device or device type needs no change to how pins are handled. Its config names its pins, and
  `device_claims` learns what a new config type uses.
- The ST7789V display fits next to the shipped devices on one Pi. It goes on DC GPIO25, reset GPIO27 and CE1, and is
  reserved in `io_config.json`. The MCP3008 keeps CE0.
- A config that used to load with clashing pins now loads without the clashing device. The log says which pin and
  which other user.
- The check covers the 40-pin header's GPIO0..27 and the buses that use them. I2C buses other than 0 and 1 are
  overlays on pins it doesn't know. Their addresses are still checked, their pins are not.

## In the code

- `examples/rti-demo/modules/io/src/rpi_io/pins.py` (new): claims, reservations, conflicts, pin map
- `examples/rti-demo/modules/io/src/rpi_io/devices.py` (`PotentiometerConfig` SPI fields, the MCP3008 open)
- `examples/rti-demo/modules/io/src/rpi_io/io_config.py` (potentiometer fields, `load_reserved_pins`,
  `reserved_pins` kept on save)
- `examples/rti-demo/modules/io/src/rpi_io/io_controller.py` (`add_device` check, `set_reserved_pins`, `pin_map`,
  loading)
- `examples/rti-demo/modules/io/src/rpi_io/api_endpoint.py` (`GET /pins`, `reserved_pins` in `/config/update`, `400`)
- Tests: `examples/rti-demo/modules/io/tests/test_pins.py`
- Docs: `examples/rti-demo/modules/io/README.md` (*Pins are configuration*)
