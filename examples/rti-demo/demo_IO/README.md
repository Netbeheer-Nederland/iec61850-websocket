# demo_IO: Raspberry Pi IO Device Control - WebSocket and ACSI Services Integration

This directory contains a complete **IO Device Control System** for Raspberry Pi, consisting of two main components:

1. **`io_api_server/`** - A FastAPI-based REST API service for direct hardware control
2. **`io_client/`** - Connection and use of IO server services and synchronization between IO server and RTI component (ACSI client/server with WebSocket passive/active)

## Overview

The demo_IO system enables remote control and monitoring of physical IO devices (LEDs, potentiometers, buttons, LCD displays) through:

- **Direct REST API** via the `io_api_server` service
- **ACSI Integration** via the `io_client` library that proxies requests to the IO server
- **IEC 61850 Object Mapping** to connect IO devices to power system data model objects

### Architecture

```
+------------------+     +---------------------+     +------------------+
|                  |     |                     |     |                  |
|   RTI component  +---->+   io_client/router   +---->+   io_api_server   |
|                  |     |   (IO Router)       |     |                  |
|                  |     |                     |     |                  |
+------------------+     +---------------------+     +--------+---------+
                                            |                    |
                                            v                    v
                                    +--------------------------------------+
                                    |     Physical IO & Hardware Devices    |
                                    |       (all connected to io_api_server)|
                                    +--------------------------------------+
```

## Directory Structure

```
demo_IO/
├── io_api_server/                      # IO Device REST API Service
│   ├── main.py                         # Entry point - creates IOController + FastAPI app
│   ├── io_controller.py                # Core IO device management (LEDs, pots, buttons, LCDs)
│   ├── devices.py                      # Device configuration classes and types
│   ├── api_endpoint.py                 # FastAPI endpoints for device control
│   ├── io_config.py                    # Configuration loading/saving
│   └── io_config.json                  # Default device configurations
│
├── io_client/                          # Connection and synchronization between IO server and RTI
│   ├── async_client_io.py              # Async client for demo_IO API
│   ├── io_router.py                    # FastAPI router for ACSI BFF
│   ├── io_utils.py                     # Utility functions
│   ├── mapping_manager.py              # IEC 61850 to IO device mapping
│   └── io_mapping.json                 # Default IEC 61850 object mappings
│
└── __init__.py                         # Package initialization
```

---

## Component 1: io_api_server - IO Device Control API

A **FastAPI-based web service** that provides REST API endpoints for controlling physical IO devices connected to a Raspberry Pi or simulated devices for development.

### Key Features

| Feature | Description |
|---------|-------------|
| **Multi-Device Support** | LEDs (digital output), Potentiometers (analog input), Buttons (digital input), LCDs (16x2, I2C) |
| **Hardware Abstraction** | Clean separation between hardware drivers and API logic |
| **Mock Mode** | Works without Raspberry Pi hardware (Windows/macOS development) |
| **REST API** | Complete CRUD operations for all device types |
| **Swagger UI** | Interactive API documentation at `/api/io/docs` |
| **Thread-Safe** | Safe concurrent access to IO devices |
| **Plug-in Architecture** | Easy to add new device types |

### Supported Devices

| Device Type | Description | Direction | Configuration |
|-------------|-------------|-----------|---------------|
| **LED** | Digital output - on/off control | OUTPUT | GPIO pin, initial state |
| **Potentiometer** | Analog input via ADS1115 ADC | INPUT | ADC channel, min/max values |
| **Button** | Digital input with debounce | INPUT | GPIO pin, debounce time, pull-up |
| **LCD (HD44780)** | 16x2 character display | OUTPUT | GPIO pins (RS, E, D4-D7) |
| **LCD I2C** | LCD with I2C backpack (PCF8574) | OUTPUT | I2C address, pin mappings |

### API Endpoints

All endpoints are under the `/api/io/` prefix and provide device management, LED control, and system status functionality.

### Configuration via Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | 8080 | Server port |
| `IO_CONFIG_FILE` | `io_config.json` | Path to configuration file |

### Hardware Requirements

For **physical hardware operation** (not mock mode):

- **Raspberry Pi** (any model with GPIO header)
- **LEDs**: 5mm standard, 220Ω-470Ω resistors
- **ADS1115 ADC**: For analog inputs (potentiometers)
- **Potentiometer**: 10kΩ recommended
- **LCD**: HD44780-compatible 16x2 display
- **I2C LCD Backpack**: PCF8574-based (address 0x27 or 0x39)

---

## Component 2: io_client - Connection and Synchronization Layer

The `io_client` directory provides connection and synchronization between the IO server services and the RTI component, which is a combination of ACSI client/server with WebSocket passive/active.

### Key Features

| Feature | Description |
|---------|-------------|
| **AsyncDemoIOClient** | Python client for demo_IO REST API |
| **IO Router** | FastAPI router that proxies requests to demo_IO |
| **IEC 61850 Mapping** | Map IO devices to IEC 61850 data objects |
| **Automatic Integration** | IO router auto-included in ACSI BFF |
| **Connection Management** | Connect/disconnect from demo_IO via API |
| **Bulk Operations** | Control multiple devices at once |

### Architecture

The `io_client` provides **two integration paths**:

1. **Direct Client Usage**: Import and use `AsyncDemoIOClient` directly in your code
2. **Router Proxy**: ACSI exposes IO endpoints that proxy to demo_IO via the IO router

### IO Router Endpoints

All endpoints are proxied to the demo_IO server and provide connection management, device control, and IEC 61850 object mapping functionality.

### Direct Client Usage

```python
from demo_IO.io_client.async_client_io import AsyncDemoIOClient

# Create async client
client = AsyncDemoIOClient(base_url="http://localhost:8080")

# Configure an LED
client.config_led(name="led1", gpio_pin=17, description="Status LED")

# Control device
client.turn_on("led1")
client.toggle_led("led2")
state = client.get_led_state("led1")

# Bulk operations
client.all_leds_on()
client.all_leds_off()

# Check health
if client.is_healthy():
    print("demo_IO is healthy")
```

### IEC 61850 Object Mapping

The system supports **mapping IO devices to IEC 61850 data objects** using the `io_mapping.json` configuration:

```json
{
  "leds": {
    "led1": {
      "device_name": "led1",
      "objRef": "connected",
      "direction": "output",
      "device_type": "led"
    }
  },
  "buttons": {
    "button1": {
      "device_name": "button1",
      "objRef": "LD0/LPHD.PwrUp.stVal",
      "direction": "input",
      "device_type": "button"
    }
  }
}
```

This mapping allows:
- **Automatic IEC 61850 integration** when devices change state
- **BFF endpoints** to expose IO device states as IEC 61850 objects
- **Client applications** to subscribe to IEC 61850 objects that control IO devices

---

## Configuration Files

### io_api_server/io_config.json

Defines all IO devices and their configurations:
- Device name, type, and identifier
- GPIO pins for digital devices
- ADC channels for analog devices
- I2C addresses for I2C devices
- Initial states and descriptions
- ACSI server integration settings
- IEC 61850 object mappings

### io_client/io_mapping.json

Defines mappings between IEC 61850 objects and IO devices:
- Which IO device corresponds to which IEC 61850 data object
- Object reference (objRef) for each device
- Direction (input/output)
- Device type for validation

---

## IEC 61850 Integration

The demo_IO system integrates with IEC 61850 power system protocols through:

1. **Object Mapping**: Map IO devices to IEC 61850 data objects (LD, LN, DO, DA)
2. **BFF Endpoints**: Expose IO device states through ACSI's BFF
3. **ACSI Integration**: Connect IO devices to ACSI server for protocol-level control

## GPIO Pin Mapping

### Raspberry Pi 5 Pinout Diagram

```
       3V3  (1) [o] [o] (2)  5V
  GPIO2/SDA (3) [o] [o] (4)  5V
  GPIO3/SCL (5) [o] [o] (6)  GND
   GPIO4    (7) [o] [o] (8)  GPIO14 (TXD)
       GND  (9) [o] [o] (10) GPIO15 (RXD)
  GPIO17   (11) [o] [o] (12) GPIO18
  GPIO27   (13) [o] [o] (14) GND
  GPIO22   (15) [o] [o] (16) GPIO23
      3V3  (17) [o] [o] (18) GPIO24
  GPIO10   (19) [o] [o] (20) GND
   GPIO9   (21) [o] [o] (22) GPIO25
  GPIO11   (23) [o] [o] (24) GPIO8 (CE0)
       GND  (25) [o] [o] (26) GPIO7 (CE1)
 GPIO0/ID_SD(27) [o] [o] (28) GPIO1/ID_SC
   GPIO5   (29) [o] [o] (30) GND
   GPIO6   (31) [o] [o] (32) GPIO12
  GPIO13   (33) [o] [o] (34) GND
  GPIO19   (35) [o] [o] (36) GPIO16
  GPIO26   (37) [o] [o] (38) GPIO20
       GND  (39) [o] [o] (40) GPIO21
```

The default devices defined in `io_config.json` use the following GPIO configuration:

| Device Name | Device Type | GPIO | Physical Pin | Direction | Description |
|-------------|-------------|------|--------------|-----------|-------------|
| led1 | LED | 17 | 11 | OUTPUT | LED 1 |
| led2 | LED | 18 | 12 | OUTPUT | LED 2 |
| led3 | LED | 22 | 15 | OUTPUT | LED 3 |
| button1 | Button | 10 | 19 | INPUT | Button (latching, pull-up) |
| pot1 | Potentiometer | - | - | INPUT | ADC Channel 0 |
| lcd1 | LCD 16x2 | Multiple | Multiple | OUTPUT | HD44780 4-bit mode |

### LCD Pin Mapping (HD44780 4-bit mode)

| LCD Pin | Pin Name | Raspberry Pi GPIO | Physical Pin | Function |
|---------|----------|-------------------|--------------|----------|
| 4 | RS | 26 | 37 | Register Select (0=Command, 1=Data) |
| 5 | RW | GND | - | Read/Write (GND = Write mode) |
| 6 | E | 19 | 35 | Enable (clock signal) |
| 11 | D4 | 13 | 33 | Data Bit 4 (MSB) |
| 12 | D5 | 12 | 32 | Data Bit 5 |
| 13 | D6 | 16 | 36 | Data Bit 6 |
| 14 | D7 | 20 | 38 | Data Bit 7 (LSB) |

### Wiring Connections

**LEDs (Active High)**:
- LED1: GPIO 17 (Pin 11) -> LED anode -> Resistor (220-470Ω) -> GND
- LED2: GPIO 18 (Pin 12) -> LED anode -> Resistor (220-470Ω) -> GND
- LED3: GPIO 22 (Pin 15) -> LED anode -> Resistor (220-470Ω) -> GND

**Button**:
- BUTTON1: GPIO 10 (Pin 19) -> Button -> GND (pull-up enabled in software)

**LCD 16x2 (HD44780 Controller)**:
- RS (Register Select): GPIO 26 (Pin 37) -> LCD Pin 4
- RW (Read/Write): GND -> LCD Pin 5 (hardwired to write mode)
- E (Enable): GPIO 19 (Pin 35) -> LCD Pin 6
- D4: GPIO 13 (Pin 33) -> LCD Pin 11
- D5: GPIO 12 (Pin 32) -> LCD Pin 12
- D6: GPIO 16 (Pin 36) -> LCD Pin 13
- D7: GPIO 20 (Pin 38) -> LCD Pin 14
- VDD (+5V): +5V -> LCD Pin 2
- VSS (GND): GND -> LCD Pin 1
- V0 (Contrast): Adjustable via potentiometer -> LCD Pin 3
- Backlight: +5V -> LCD Pin 15, GND -> LCD Pin 16

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| **Port already in use** | Use different port: `PORT=8081 python main.py` |
| **gpiozero import error (Windows)** | Normal - uses mock mode. Install gpiozero for Pi. |
| **GPIO permission denied (Linux)** | Run with sudo or add user to gpio group |
| **ADS1115 not detected** | Check I2C wiring, enable I2C in raspi-config |
| **LEDs not responding** | Verify wiring (resistor +, GND -), check GPIO numbering |
| **ACSI connection failed** | Verify DEMO_IO_URL, check demo_IO is running |

### Debug Commands

```bash
# Check if demo_IO is running
curl http://localhost:8080/api/io/health

# Check if ACSI IO router is connected
curl http://localhost:5001/api/io/connection

# List all devices
curl http://localhost:8080/api/io/devices

# Get device state
curl http://localhost:8080/api/io/devices/led1

# Check I2C devices
sudo i2cdetect -y 1

# Check GPIO access
ls /dev/gpio*
```

### Enable I2C on Raspberry Pi

```bash
sudo raspi-config
# Navigate to: Interface Options -> I2C -> Enable
sudo reboot
```

### Enable SPI on Raspberry Pi

```bash
sudo raspi-config
# Navigate to: Interface Options -> SPI -> Enable
sudo reboot
```

---

## License

This project is part of the **RTI_DEMO** project. See the main project for licensing information.

---

## Support

For issues or questions:

1. Check the **Troubleshooting** section above
2. Review the **API Endpoints** documentation
3. Test with Swagger UI: `http://localhost:8080/api/io/docs`
4. Verify hardware connections
5. Check system logs for errors

---

