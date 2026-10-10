<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# IO plugin

> The IO plugin is the package `acsi_io_plugin` (distribution `acsi-io-plugin`), one of the plugins the FSP and SO
> host (decision 0021; package `acsi_plugins`). It is installed with them, not downloaded (decision 0022). In this
> document "ACSI" is the RTI-FSP/RTI-SO REST service (`fsp.bff_endpoint` / `so.bff_endpoint`) and the "IO server" is
> `rti_io.server` (`modules/io`). For running the whole stack, see `examples/rti-demo/README.md`.

This package lets ACSI connect to and control the IO server's devices. It has no hardware dependencies: it talks to
the IO server over HTTP.

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
from acsi_io_plugin.client import DemoIOClient

# Create client
client = DemoIOClient(base_url="http://localhost:9000")

# Configure an LED
client.config_led(name="led1", gpio_pin=17, description="Status LED")

# Control device
client.set_device("led1", state=True)
client.set_device("led1", state=False)
client.toggle_led("led1")

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

### 2. `plugin.py` - RtiIoPlugin

The plugin itself, registered under the entry point group `acsi.plugins` as `io` (`pyproject.toml`). The FSP and SO
start it when they start. It connects to the IO server in its settings (`io_url`), else `IO_URL`; without one it does
nothing until `POST /api/plugins/io/connect`. It tells the IO server where to write input changes (`acsi_url`, else
`ACSI_BASE_URL`). Then it shows what the FSP or SO tells it:

| Event | FSP | SO |
|---|---|---|
| Association | `led1` on, LCD "FSP Connected: <id>" | blink `led1` twice, LCD "Connected: <id>" |
| Operate request received | blink `led2` | - |
| Operate answered | LCD "Operation: SUCCESS" / "FAILED - <cause>" | blink `led3`, LCD "Oper <objRef>=<value>" |
| Write | the value to the mapped devices, LCD "<objRef> : <value>" | the same (if it succeeded), blink `led3`, LCD "Write - ..." |
| Read | - | blink `led3`, LCD "<objRef> : <value>" |
| Report | - | blink `led2`, LCD "rptID=... dataSet=..." |
| Server stop | `led1` off, LCD "Stopped" | - |

Which devices react is in `io_mapping.json`: the names `connected`, `oper_rcv`, `oper_send`, `rc_rcv`, `read`,
`operate`, `setpoint`, `writeValue` and `stopped` are the plugin's own names for these events.

### 3. `router.py` - FastAPI IO Router

A FastAPI router that provides IO/LED control endpoints, proxying requests to the IO server. The FSP and SO serve it
under `/api/plugins/io/`.

**Features:**
- Connected when the plugin is loaded, or with `POST /api/plugins/io/connect`
- Programmatic connection management via API endpoints
- Full LED control through REST endpoints (proxied to the IO server device API)
- Connection status monitoring
- Health checks
- IEC 61850 object mapping to IO devices

**Endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/plugins/io/connect` | Connect to the IO server |
| GET | `/api/plugins/io/health` | Check the IO server health |
| GET | `/api/plugins/io/status` | Get IO controller status |
| POST | `/api/plugins/io/leds/config` | Configure an LED (proxied to device API) |
| GET | `/api/plugins/io/leds` | List all LEDs and states (proxied to device API) |
| GET | `/api/plugins/io/leds/{name}` | Get specific LED state (proxied to device API) |
| POST | `/api/plugins/io/leds/{name}/set` | Set LED state (proxied to device API) |
| POST | `/api/plugins/io/leds/{name}/toggle` | Toggle LED state (proxied to device API) |
| POST | `/api/plugins/io/leds/{name}/on` | Turn LED on (proxied to device API) |
| POST | `/api/plugins/io/leds/{name}/off` | Turn LED off (proxied to device API) |
| POST | `/api/plugins/io/leds/all/set` | Set all LEDs state (proxied to device API) |
| POST | `/api/plugins/io/leds/all/on` | Turn all LEDs on (proxied to device API) |
| POST | `/api/plugins/io/leds/all/off` | Turn all LEDs off (proxied to device API) |
| POST | `/api/plugins/io/initialize` | Initialize IO controller |
| POST | `/api/plugins/io/cleanup` | Clean up IO resources |
| POST | `/api/plugins/io/mappings/add` | Add IEC 61850 to device mapping |

### 4. `mapping.py` and `io_mapping.json`

Which IO devices go with which IEC 61850 objects and events. The plugin reads and saves the file in its setting
`mapping_file`, else `IO_MAPPING_FILE`; a file that doesn't exist yet is first copied from the shipped
`io_mapping.json`, so a save never changes the shipped file. Without either, it uses the shipped file. `launch.py`
gives each service its own, `config/plugins/<service>/io_mapping.json`.

## Quick Start

### Settings

The FSP and SO depend on `acsi-io-plugin`, so the plugin is in their environment (`uv sync --all-packages`) and their
images. It starts with them; set where it connects with environment variables, or with `PLUGINS`:

| Setting | Environment variable | |
|---|---|---|
| `io_url` | `IO_URL` | The IO server, e.g. `http://localhost:9000` (`http://rti-io:9000` in Docker) |
| `acsi_url` | `ACSI_BASE_URL` | This FSP or SO, where the IO server writes input changes |
| `mapping_file` | `IO_MAPPING_FILE` | The `io_mapping.json` to read and save |

```bash
PLUGINS='[{"name": "io", "settings": {"io_url": "http://localhost:9000", "acsi_url": "http://localhost:5001"}}]' \
  uv run --package fsp python -m fsp.bff_endpoint
```

`launch.py` and `docker-compose.yml` set `IO_URL` and `ACSI_BASE_URL` for every FSP and the SO.

Then use the IO routes:

```bash
# The plugin's status ("source": "installed") and health
curl http://localhost:5001/api/plugins/io
curl http://localhost:5001/api/plugins/io/health

# Control an LED
curl -X POST http://localhost:5001/api/plugins/io/leds/led1/set \
  -H "Content-Type: application/json" \
  -d '{"state": true}'

# Get LED state, or all LEDs
curl http://localhost:5001/api/plugins/io/leds/led1
curl http://localhost:5001/api/plugins/io/leds
```

### Use the client directly

```python
from acsi_io_plugin.client import DemoIOClient

client = DemoIOClient(base_url="http://localhost:9000")
client.set_device("led1", state=True)
client.toggle_led("led2")
state = client.get_led_state("led1")
```

Run it in the workspace: `uv run --package acsi-io-plugin python ...`.

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
curl -X POST http://localhost:5001/api/plugins/io/leds/config \
  -H "Content-Type: application/json" \
  -d '{
    "name": "new_led",
    "gpio_pin": 23,
    "description": "New LED from FSP",
    "initial_state": false
  }'

# Turn it on
curl -X POST http://localhost:5001/api/plugins/io/leds/new_led/on

# Turn it off
curl -X POST http://localhost:5001/api/plugins/io/leds/new_led/off

# Toggle it
curl -X POST http://localhost:5001/api/plugins/io/leds/new_led/toggle

# Get its state
curl http://localhost:5001/api/plugins/io/leds/new_led
```

### Example 2: Controlling All LEDs

```bash
# Turn all LEDs on
curl -X POST http://localhost:5001/api/plugins/io/leds/all/on

# Turn all LEDs off
curl -X POST http://localhost:5001/api/plugins/io/leds/all/off

# Set all LEDs to a specific state
curl -X POST http://localhost:5001/api/plugins/io/leds/all/set \
  -H "Content-Type: application/json" \
  -d '{"state": true}'
```

### Example 3: Monitoring Status

```bash
# Get GPIO controller status
curl http://localhost:5001/api/plugins/io/status

# Check the IO server health
curl http://localhost:5001/api/plugins/io/health

# Check connection status
curl http://localhost:5001/api/plugins
```

## Docker Deployment

### Docker Compose Example

`examples/rti-demo/docker-compose.yml` already wires this up: `rti-fsp01`, `rti-fsp02` and `rti-so` have the plugin
in their image and get `IO_URL=http://rti-io:9000` and their own `ACSI_BASE_URL`, and all services share the external
`rti-network`:

```bash
docker network create rti-network 2>/dev/null || true
cd examples/rti-demo
docker compose up -d rti-io rti-fsp01
```

## Development

### Testing

`uv run --package acsi-io-plugin pytest examples/rti-demo/modules/io-plugin/tests -q`: that it's installed
(`test_installed.py`), its mapping file (`test_mapping_file.py`), its routes and every event
(`test_plugin_contract.py`), and the client. How plugins are loaded is tested in `acsi_plugins`
(`uv run --package acsi-plugins pytest examples/rti-demo/modules/plugins/tests -q`). On a Raspberry Pi, a
script in the IO server checks the I2C LCD:

```bash
cd examples/rti-demo/modules/io
python -m rti_io.server.lcd_i2c_check
```

### Adding New IO Functionality

1. **Extend DemoIOClient**: Add new methods to `client.py` for additional IO server API calls
2. **Add New Endpoints**: Add new routes to `router.py` to expose new functionality
3. **New files**: put them in `src/acsi_io_plugin/`; a data file also goes in `[tool.setuptools.package-data]`
4. **Reload**: restart the FSP or SO (from source it runs the files in place; an image needs a rebuild)

## Troubleshooting

### Connection Issues

**Error:** the IO server doesn't respond

- Check that the IO server is running
- Verify the URL is correct (`http://localhost:9000`, or `http://rti-io:9000` from another container)
- Check that the port is accessible (firewall, Docker networking)
- Test with: `curl http://localhost:9000/api/io/health`

**Error:** `Client not configured`

- The plugin couldn't reach the IO server when it started (see the FSP's or SO's log), or has no IO server (`IO_URL`)
- connect it with `POST /api/plugins/io/connect` and `{"base_url": ...}`, or `POST /api/plugins/io/reload` once the
  IO server runs

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

## Files

- `pyproject.toml` - the package, its dependencies and its entry point (`acsi.plugins`: `io`)
- `src/acsi_io_plugin/`:
- `plugin.py` - RtiIoPlugin, what the plugin does with each event
- `client.py` - DemoIOClient & AsyncIOClient HTTP clients
- `router.py` - FastAPI IO router, served under `/api/plugins/io/`
- `mapping.py` - IEC 61850 object to IO device mapping (`io_mapping.json`)
- `utils.py` - helpers (LED blink, LCD write) used by `plugin.py`
- `io_mapping.json` - the shipped mapping
- `tests/` - the plugin's tests

## Compatibility

- Python 3.13+
- FastAPI 0.100+
- httpx2
- The IO server of the same commit (examples/rti-demo/modules/io/): the plugin's version follows the FSP and SO

## License

This code is part of the RTI_DEMO project and follows the same license terms.
