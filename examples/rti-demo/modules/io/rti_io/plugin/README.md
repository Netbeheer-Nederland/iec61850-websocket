<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# IO plugin

> The IO plugin is what the FSP and SO download from the IO server (`GET /api/io-plugin/files`) and load as the package
> `rti_io_plugin` (decision 0018). In this document "ACSI" is the RTI-FSP/RTI-SO REST service (`fsp.bff_endpoint` /
> `so.bff_endpoint`) and the "IO server" is `rti_io.server`. For running the whole stack, see
> `examples/rti-demo/README.md`.

This directory provides the ability for ACSI to connect to and control the IO server's IO device functionality.

## Overview

The IO server provides a REST API for controlling IO devices (LEDs, potentiometers, buttons) on a Raspberry Pi (or simulated devices for development). This integration allows ACSI to:

- Connect to a running IO server
- Configure and manage IO devices (primarily LEDs)
- Control individual or all devices (turn on/off, toggle)
- Monitor device states and IO controller status
- Expose these capabilities through ACSI's BFF endpoints

**Note:** The LED-specific methods in the client are convenience wrappers that use the underlying device API internally.

## Components

### 1. `client.py` - DemoIOClient & AsyncIOClient

A Python client library for communicating with the IO server's REST API.

**Features:**
- Full device control API (configure, read, write, toggle)
- LED-specific convenience methods (configure LED, set LED, toggle LED, etc.)
- Bulk operations (control all output devices at once)
- IO controller management (initialize, cleanup)
- Health checks and status monitoring
- Device abstraction supporting multiple device types
- Convenience methods for common operations
- Both synchronous (`DemoIOClient`) and asynchronous (`AsyncIOClient`) interfaces

**Usage (Synchronous):**

```python
import sys
sys.path.insert(0, "examples/rti-demo/modules/io")
from rti_io.plugin.client import DemoIOClient

# Create client
client = DemoIOClient(base_url="http://localhost:9000")

# Configure an LED
client.config_led(name="led1", gpio_pin=17, description="Status LED")

# Control device
client.turn_on("led1")
client.turn_off("led1")
client.toggle_led("led1")
client.set_device("led1", state=True)

# Get LED state
state = client.get_led_state("led1")
print(f"LED state: {state}")

# Bulk operations
client.all_leds_on()
client.all_leds_off()

# Get status
status = client.get_status()
print(f"GPIO status: {status}")

# Check health
if client.is_healthy():
    print("IO server is healthy")
```

### 2. `router.py` - FastAPI IO Router

A FastAPI router that provides IO/LED control endpoints for FSP's BFF, proxying requests to the IO server.

**Features:**
- Automatic connection via `IO_URL` environment variable
- Programmatic connection management via API endpoints
- Full LED control through REST endpoints (proxied to the IO server device API)
- Connection status monitoring
- Health checks
- IEC 61850 object mapping to IO devices

**Endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/io/connect` | Connect to the IO server |
| GET | `/api/io/health` | Check the IO server health |
| GET | `/api/io/status` | Get IO controller status |
| POST | `/api/io/leds/config` | Configure an LED (proxied to device API) |
| GET | `/api/io/leds` | List all LEDs and states (proxied to device API) |
| GET | `/api/io/leds/{name}` | Get specific LED state (proxied to device API) |
| POST | `/api/io/leds/{name}/set` | Set LED state (proxied to device API) |
| POST | `/api/io/leds/{name}/toggle` | Toggle LED state (proxied to device API) |
| POST | `/api/io/leds/{name}/on` | Turn LED on (proxied to device API) |
| POST | `/api/io/leds/{name}/off` | Turn LED off (proxied to device API) |
| POST | `/api/io/leds/all/set` | Set all LEDs state (proxied to device API) |
| POST | `/api/io/leds/all/on` | Turn all LEDs on (proxied to device API) |
| POST | `/api/io/leds/all/off` | Turn all LEDs off (proxied to device API) |
| POST | `/api/io/initialize` | Initialize IO controller |
| POST | `/api/io/cleanup` | Clean up IO resources |
| POST | `/api/io/mappings/add` | Add IEC 61850 to device mapping |

### 3. Integration with ACSI BFF

FSP and SO don't ship these files. They download them from the IO server and load them at runtime (see below).

## Quick Start

### Connect FSP or SO to the IO server

```bash
curl -X POST http://localhost:5001/api/io-plugin/connect \
  -H "Content-Type: application/json" \
  -d '{"server_url": "http://localhost:9000", "acsi_url": "http://localhost:5001"}'
```

This downloads the IO plugin files from the IO server (`GET /api/io-plugin/files`), loads them, and adds the
`/api/io/*` routes to the running service. Use port 5000 for the SO, and `http://rti-io:9000` as `server_url` in Docker. `server_url` defaults to the
`IO_SERVER_URL` environment variable. If `IO_URL` is set, the loaded router configures its client from it; otherwise
call `POST /api/io/connect` with `{"base_url": ...}`.

Then use the IO routes:

```bash
# Connection status
curl http://localhost:5001/api/io-plugin/connection-status

# Control an LED
curl -X POST http://localhost:5001/api/io/leds/led1/set \
  -H "Content-Type: application/json" \
  -d '{"state": true}'

# Get LED state, or all LEDs
curl http://localhost:5001/api/io/leds/led1
curl http://localhost:5001/api/io/leds
```

### Use the client directly

```python
import sys
sys.path.insert(0, "examples/rti-demo/modules/io")
from rti_io.plugin.client import DemoIOClient

client = DemoIOClient(base_url="http://localhost:9000")
client.turn_on("led1")
client.toggle_led("led2")
state = client.get_led_state("led1")
```

The client needs `httpx2`, which the `fsp` and `so` environments have: run it with `uv run --package fsp python ...`.

## Configuration

### IO server

The IO server is configured in `examples/rti-demo/modules/io/`.

**Default Configuration:**
- Port: 9000, however it's started (`rti-io:9000` on
  `rti-network`)
- Default LEDs: led1 (GPIO 17), led2 (GPIO 18), led3 (GPIO 22)
- Health endpoint: `/api/io/health`

**Starting the IO server:**

```bash
# With default port (from examples/rti-demo/modules/io)
python -m rti_io.server.main

# With custom port
PORT=9100 python -m rti_io.server.main

# With Docker (from examples/rti-demo)
docker compose up -d rti-io
```

### ACSI Service (FSP / SO)

FSP runs on port 5001 and SO on 5000. From the repository root:

```bash
uv run --package fsp python -m fsp.bff_endpoint
uv run --package so python -m so.bff_endpoint
```

or from `examples/rti-demo`: `uv run python launch.py fsp so`, or `docker compose up -d rti-fsp01 rti-so`.

## Usage Examples

### Example 1: Adding a New LED

```bash
# Configure a new LED
curl -X POST http://localhost:5001/api/io/leds/config \
  -H "Content-Type: application/json" \
  -d '{
    "name": "new_led",
    "gpio_pin": 23,
    "description": "New LED from FSP",
    "initial_state": false
  }'

# Turn it on
curl -X POST http://localhost:5001/api/io/leds/new_led/on

# Turn it off
curl -X POST http://localhost:5001/api/io/leds/new_led/off

# Toggle it
curl -X POST http://localhost:5001/api/io/leds/new_led/toggle

# Get its state
curl http://localhost:5001/api/io/leds/new_led
```

### Example 2: Controlling All LEDs

```bash
# Turn all LEDs on
curl -X POST http://localhost:5001/api/io/leds/all/on

# Turn all LEDs off
curl -X POST http://localhost:5001/api/io/leds/all/off

# Set all LEDs to a specific state
curl -X POST http://localhost:5001/api/io/leds/all/set \
  -H "Content-Type: application/json" \
  -d '{"state": true}'
```

### Example 3: Monitoring Status

```bash
# Get GPIO controller status
curl http://localhost:5001/api/io/status

# Check the IO server health
curl http://localhost:5001/api/io/health

# Check connection status
curl http://localhost:5001/api/io-plugin/connection-status
```

## Docker Deployment

### Docker Compose Example

`examples/rti-demo/docker-compose.yml` already wires this up: `rti-fsp01` and `rti-fsp02` get
`IO_URL=http://rti-io:9000`, and all services share the external `rti-network`:

```bash
docker network create rti-network 2>/dev/null || true
cd examples/rti-demo
docker compose up -d rti-io rti-fsp01
```

## Development

### Testing

The IO plugin's own tests, and the IO server's file serving, run with the fsp environment (it has FastAPI):
`uv run --package fsp pytest examples/rti-demo/modules/io/tests -q`. The FSP and SO tests cover how it is loaded
(`uv run --package fsp pytest examples/rti-demo/modules/fsp/tests -q`, and the same for `so`). On a Raspberry Pi, a
script checks the I2C LCD:

```bash
cd examples/rti-demo/modules/io
python -m rti_io.server.lcd_i2c_check
```

### Adding New IO Functionality

1. **Extend DemoIOClient**: Add new methods to `client.py` for additional IO server API calls
2. **Add New Endpoints**: Add new routes to `router.py` to expose new functionality
3. **Reload**: FSP and SO pick up changed files with `POST /api/io-plugin/reload` (or a new `/api/io-plugin/connect`)

## Troubleshooting

### Connection Issues

**Error:** the IO server doesn't respond

- Check that the IO server is running
- Verify the URL is correct (`http://localhost:9000`, or `http://rti-io:9000` from another container)
- Check that the port is accessible (firewall, Docker networking)
- Test with: `curl http://localhost:9000/api/io/health`

**Error:** `Client not configured`

- Load the IO plugin first with `POST /api/io-plugin/connect`, then
- set the `IO_URL` environment variable, or call `POST /api/io/connect` with `{"base_url": ...}`

### Port Conflicts

- The IO server uses port 9000
- ACSI uses port 5001 by default
- Change ports using `PORT` environment variable

### GPIO Issues (on Raspberry Pi)

- Ensure gpiozero or gpiod is installed
- Run as root or with appropriate permissions
- Check GPIO pin availability

## API Reference

### DemoIOClient Methods

#### Connection & Health
- `health_check()` - Get health status
- `is_healthy()` - Check if service is healthy
- `get_status()` - Get GPIO controller status

#### LED Configuration
- `config_led(name, gpio_pin, description="", initial_state=False)` - Configure an LED
- `list_leds()` - List all LEDs and their states
- `get_led_config(name)` - Get LED configuration

#### LED Control
- `get_led_state(name)` - Get LED state
- `set_led(name, state)` - Set LED state (True=ON, False=OFF)
- `toggle_led(name)` - Toggle LED state

#### Bulk Operations
- `set_all_leds(state)` - Set all LEDs to state
- `all_leds_on()` - Turn all LEDs on
- `all_leds_off()` - Turn all LEDs off

#### GPIO Management
- `initialize()` - Initialize GPIO controller
- `cleanup()` - Clean up GPIO resources

#### Convenience Methods
- `turn_on(name)` - Turn LED on
- `turn_off(name)` - Turn LED off
- `add_led(name, gpio_pin, **kwargs)` - Alias for config_led
- `get_all_states()` - Alias for list_leds
- `create_led(name, gpio_pin, **kwargs)` - Alias for config_led

## Files

- `client.py` - DemoIOClient & AsyncIOClient HTTP clients
- `router.py` - FastAPI IO router that FSP and SO load at runtime
- `mapping.py` - IEC 61850 object to IO device mapping (`io_mapping.json`)
- `utils.py` - helpers (LED blink, LCD write) used by FSP and SO
- `io_mapping.json` - default mapping
- `README.md` - This file

## Compatibility

- Python 3.13+
- FastAPI 0.100+
- httpx2
- The IO server (from examples/rti-demo/modules/io/)

## License

This code is part of the RTI_DEMO project and follows the same license terms.
