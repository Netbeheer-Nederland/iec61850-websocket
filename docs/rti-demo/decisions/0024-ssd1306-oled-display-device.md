<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# 24. The SSD1306 OLED is a display device of the IO server, on any Pi, shown by the IO plugin

- Status: proposed
- Date: 2026-10-11

## Context

The demo should show what happens in the RTI-FSP on a small SSD1306 OLED, 0.96", 128×64 pixels, on I2C (address
`0x3C`). The IO side is split in two ([0022](0022-io-plugin-own-package.md), [0023](0023-io-server-package-rpi-io.md)):
the IO server `rpi_io` owns the Raspberry Pi's hardware, and the IO plugin in the FSP and SO decides which event
shows on which device, through `io_mapping.json`. How things stand (2026-10-11):

- **Displays are text, HD44780 only.** `rpi_io` has `DeviceType.LCD` (GPIO) and `DeviceType.LCD_I2C` (PCF8574
  backpack, driven over `smbus2` by its own code), with `POST /api/io/lcd/{name}/write` taking `text`, a string or a
  list of lines. Nothing draws pixels.
- **The plugin already tells the FSP's story in text.** `_fsp_steps` calls `show(key, text)` on association
  (`connected`), an Operate's answer (`oper_send`), a stop (`stopped`) and a write (`writeValue`); `_so_steps` does the
  same for its own events. `show` is `write_to_lcd`, which looks up the devices mapped to the key and writes the text.
- **But nothing reaches a display.** `write_to_lcd` only picks devices whose type is `lcd`, so an `lcd_i2c` is never
  written; and `io_mapping.json` knows only `leds`, `buttons` and `potentiometers`, so no display is mapped at all.
- **Only the IO server has the devices.** The `rti-io` container gets `/dev/i2c-*` and the GPIO chips; the FSP and SO
  containers get none (0017).
- **The OLED can be on another Pi** than the LEDs and buttons (2026-10-11). The plugin reaches one IO server: one
  `IO_URL`, one client in `_router_state`. The FSP uses that server's LEDs too (`connected`, `stopped`, `oper_rcv`),
  so pointing its `IO_URL` at the OLED's Pi would lose them.

Four options were considered:

1. **A new device type in `rpi_io`** (chosen).
2. **A second IO server, on its own Pi, for the OLED.** Not an alternative but where option 1 may run: another
   `rpi_io` with its own `io_config.json`. It needs the plugin to reach more than one IO server (point 6).
3. **A plugin in the FSP that drives the OLED itself.** The FSP has no I2C device, and it would put hardware code
   back in the FSP, which 0022 took out.
4. **A module of its own (`modules/oled`).** A second server, image, config and health check for one device.

## Decision

1. **A display device type in the IO server.** `rpi_io` gets `DeviceType.OLED_SSD1306` (`"oled_ssd1306"`), with an
   `OLEDConfig` (`i2c_bus`, default 1; `i2c_address`, default `0x3C`; `width` 128 and `height` 64; `rotate`;
   `contrast`) and an `OLEDDevice`, configured in `io_config.json` like any other device.
2. **Driven with `luma.oled`.** It handles the SSD1306's start-up and frame buffer, and draws with Pillow, which gives
   fonts and shapes. On the Pi (aarch64, Python 3.13) it adds `luma-oled`, `luma-core`, `pillow` and `cbor2`;
   `smbus2` is there already (checked 2026-10-11). Writing the SSD1306 protocol over `smbus2` ourselves, as the PCF8574
   code does, was set aside: it saves three small packages but needs our own font and drawing code at 128×64.
3. **The server draws, the plugin sends text.** The OLED takes the same request as an LCD:
   `POST /api/io/oled/{name}/write` with `text`, a string or lines. The server lays them out: up to 8 lines of 21
   characters in the default 6×8 font; a longer line is cut, extra lines are dropped. Also `POST .../clear`,
   `POST .../contrast`, and `GET /api/io/oled/{name}` for what the display shows now. Graphics (a bar for a
   measurement, icons) can come later behind the same device, without changing the plugin.
4. **Without hardware it keeps the text.** As the I2C LCD does, an OLED whose bus or display isn't there runs in mock
   mode: writes succeed, and `GET` returns the last text, so tests and machines without a Pi work (0017).
5. **One display path in the plugin.** `write_to_lcd` becomes `write_to_display`: it writes to every mapped device of
   type `lcd`, `lcd_i2c` or `oled_ssd1306`, through one `write_display` call on the client that picks the route by
   type. `io_mapping.json` gets a `displays` section, as `leds` and `buttons` are sections, mapping a display to the
   keys `show` uses. The shipped mapping maps `oled1` to the FSP's keys (`connected`, `oper_send`, `stopped`,
   `writeValue`), so the FSP's story appears on it with no change to the FSP or to `_fsp_steps`.
6. **Where the OLED is connected is configuration.** On the Pi with the LEDs and buttons, it is one more entry in
   that server's `io_config.json`. On a Pi of its own, that Pi runs the same `rpi_io` image (`docker compose up
   rti-io`, or `launch.py io`) with an `io_config.json` holding only the OLED. The code is the same either way.
7. **The plugin reaches named IO servers.** `IO_URL` stays the default server. More are named in the setting
   `io_servers` (`{"oled": "http://rti-pi2:9000"}`), else `IO_SERVERS` (`oled=http://rti-pi2:9000`, comma-separated).
   A mapped device may say which server it is on (`"io_server": "oled"`); without it, the default. The plugin keeps a
   client per server, connects each at start (`/connect`, `/acsi/enable-server-sync`), and sends each write to the
   device's server. A server that doesn't answer is logged and leaves the others working, as one without `IO_URL` is
   now (0022, point 3). The plugin's routes (`/api/plugins/io/...`) keep acting on the default server.

## Consequences

- The FSP's events show on a display without changing the FSP, the plugin host or the plugin's event steps: only the
  IO server, the plugin's display path, its connection to the IO servers and the mapping change.
- The LCD path is fixed with it: an `lcd_i2c` mapped to a key is written, which it isn't now.
- The IO image grows by Pillow (a wheel for aarch64 and amd64, no build step) and the three small packages; the
  `rpi-io` lock file gets them. The FSP and SO images don't change: the plugin sends text only.
- The FSP can use devices on more than one Pi: the OLED on one, the LEDs and buttons on another, both mapped in its
  own `io_mapping.json`. With one Pi, nothing is set and nothing changes.
- The FSP must reach the second Pi over the network, by a name or address that Docker on the FSP's host can resolve
  (`rti-pi2` above is an example). The IO server has no authentication (0019): on the second Pi, as on the first,
  port 9000 is open to the network it is on.
- `docker-compose.yml` passes the first Pi's devices (`/dev/gpiochip4`, `/dev/i2c-13`, ...); Docker won't start
  `rti-io` on a Pi that lacks one (0017). The second Pi needs a device list of its own: an overlay with only
  `/dev/i2c-1`.
- A second display type is now cheap: a device class and a route; the plugin and mapping already handle displays.
- 21×8 characters is less than a line of the FSP's messages can be (`f"{obj_ref} : {value}"`); long objRefs are cut.
  The server cutting them keeps the plugin simple; shorter texts for small displays are a later choice for the
  plugin, per display, if the cut ones turn out unreadable.
- `luma.oled` is a new dependency to follow; it is small and widely used for this display. If it goes unmaintained,
  the device class is the one place to replace it.
- Review one month after it runs on the Pi: whether the text is readable at 6×8, whether the FSP needs a status
  screen (graphics) instead of lines, and whether named IO servers are used for more than the OLED.

## In the code

- `examples/rti-demo/modules/io/src/rpi_io/devices.py` (`DeviceType.OLED_SSD1306`, `OLEDConfig`, `OLEDDevice`),
  `io_config.py`, `io_controller.py`, `api_endpoint.py` (`/api/io/oled/...`), `io_config.json` (`oled1`)
- `examples/rti-demo/modules/io/src/rpi_io/oled_i2c_check.py`, a hardware check like `lcd_i2c_check.py`
- `examples/rti-demo/modules/io/pyproject.toml` (`luma.oled`), `uv.lock`
- `examples/rti-demo/modules/io-plugin/src/acsi_io_plugin/utils.py` (`write_to_display`), `client.py`
  (`write_display`), `mapping.py` (the `displays` section, `io_server`), `router.py` (a client per server),
  `plugin.py` (`show`; `io_servers` / `IO_SERVERS` at start), `io_mapping.json`
- `examples/rti-demo/docker-compose.oled-pi.yml`, an overlay for the OLED's Pi (only `/dev/i2c-1`)
- Tests: `examples/rti-demo/modules/io/tests/` (config, mock device, routes), `examples/rti-demo/modules/io-plugin/tests/`
  (display path, mapping, named servers: a write goes to its device's server, one server down leaves the other)
- Docs: the READMEs of `io` (wiring: VCC, GND, SDA on GPIO 2, SCL on GPIO 3; `i2cdetect -y 1` shows `3c`) and
  `io-plugin`
