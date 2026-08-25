# ACSI IO Client - Device Control via demo_IO

This directory provides the ability for ACSI to connect to and control the demo_IO service's IO device functionality.

## Overview

The demo_IO service provides a REST API for controlling IO devices (LEDs, potentiometers, buttons) on a Raspberry Pi (or simulated devices for development). This integration allows ACSI to:

- Connect to a running demo_IO instance
- Configure and manage IO devices (primarily LEDs)
- Control individual or all devices (turn on/off, toggle)
- Monitor device states and IO controller status
- Expose these capabilities through ACSI's BFF endpoints

**Note:** The LED-specific methods in the client are convenience wrappers that use the underlying device API internally.

## Components

### 1. `client_io.py` - DemoIOClient

A Python client library for communicating with the demo_IO service's REST API.

**Features:**
- Full device control API (configure, read, write, toggle)
- LED-specific convenience methods (configure LED, set LED, toggle LED, etc.)
- Bulk operations (control all output devices at once)
- IO controller management (initialize, cleanup)
- Health checks and status monitoring
- Device abstraction supporting multiple device types
- Convenience methods for common operations

**Usage:**

```python
from demo_IO.io_client.client_io import DemoIOClient

# Create client
client = DemoIOClient(base_url="http://localhost:8080")

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
    print("demo_IO is healthy")
```

### 2. `io_router.py` - FastAPI IO Router

A FastAPI router that provides IO/LED control endpoints for FSP's BFF, proxying requests to demo_IO.

**Features:**
- Automatic connection via `DEMO_IO_URL` environment variable
- Programmatic connection management via API endpoints
- Full LED control through REST endpoints (proxied to demo_IO device API)
- Connection status monitoring
- Health checks
- IEC 61850 object mapping to IO devices

**Endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/io/connect` | Connect to demo_IO service |
| GET | `/api/io/connection` | Get connection status |
| POST | `/api/io/disconnect` | Disconnect from demo_IO |
| GET | `/api/io/health` | Check demo_IO health |
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

The IO router is automatically included in ACSI's BFF when the `bff_endpoint.py` is imported (if the dependencies are available).

## Quick Start

### Option 1: Using Environment Variable (Recommended)

Set the `DEMO_IO_URL` and `ACSI_BASE_URL` environment variables before starting ACSI:

```bash
# Linux/macOS
export DEMO_IO_URL=http://demo-io:8080
export ACSI_BASE_URL=http://localhost:5001
python acsi/bff_endpoint.py

# Windows
set DEMO_IO_URL=http://demo-io:8080
set ACSI_BASE_URL=http://localhost:5001
python acsi/bff_endpoint.py
```

Now ACSI will automatically connect to demo_IO on startup.

### Option 2: Using API Endpoints

1. Start ACSI normally
2. Connect to demo_IO via API:

```bash
# Connect to demo_IO
curl -X POST http://localhost:5001/api/io/connect \
  -H "Content-Type: application/json" \
  -d '{"base_url": "http://demo-io:8080"}'

# Check connection status
curl http://localhost:5001/api/io/connection

# Control an LED
curl -X POST http://localhost:5001/api/io/leds/led1/set \
  -H "Content-Type: application/json" \
  -d '{"state": true}'

# Get LED state
curl http://localhost:5001/api/io/leds/led1

# Get all LEDs
curl http://localhost:5001/api/io/leds
```

### Option 3: Direct Client Usage in ACSI Code

```python
from acsi.client_io import DemoIOClient

# In your ACSI code, create a client and use it directly
client = DemoIOClient(base_url="http://demo-io:8080")

# Use the client methods
client.turn_on("led1")
client.toggle_led("led2")
state = client.get_led_state("led1")
```

## Configuration

### demo_IO Service

The demo_IO service is configured in `examples/rti-demo/demo_IO/`.

**Default Configuration:**
- Port: 8080
- Default LEDs: led1 (GPIO 17), led2 (GPIO 18), led3 (GPIO 22)
- Health endpoint: `/api/io/health`

**Starting demo_IO:**

```bash
# With default port
python examples/rti-demo/demo_IO/main.py

# With custom port
PORT=8000 python examples/rti-demo/demo_IO/main.py

# With Docker
# See Dockerfile.IO in examples/rti-demo/
```

### ACSI Service

ACSI runs on port 5001 by default.

**Starting ACSI:**

```bash
# With IO router enabled (default in this integration)
python examples/rti-demo/acsi/bff_endpoint.py

# With custom port
PORT=5005 python examples/rti-demo/acsi/bff_endpoint.py

# With Docker
# See Dockerfile.rti-acsi in examples/rti-demo/
```

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

# Check demo_IO health
curl http://localhost:5001/api/io/health

# Check connection status
curl http://localhost:5001/api/io/connection
```

## Docker Deployment

### Docker Compose Example

```yaml
version: '3.8'

services:
  rti-acsi:
    build:
      context: examples/rti-demo
      dockerfile: Dockerfile.rti-acsi
    ports:
      - "5001:5001"
    environment:
      - DEMO_IO_URL=http://demo-io:8080
      - ACSI_BASE_URL=http://localhost:5001
    depends_on:
      - demo-io

  demo-io:
    build:
      context: examples/rti-demo
      dockerfile: Dockerfile.IO
    ports:
      - "8080:8080"
```

### Docker Network Configuration

Make sure both services are on the same Docker network:

```bash
# Create a network
docker network create rti-network

# Run services on the network
docker run --network rti-network --name demo-io -p 8080:8080 rti-demo-io
docker run --network rti-network --name rti-acsi -p 5001:5001 -e DEMO_IO_URL=http://demo-io:8080 -e ACSI_BASE_URL=http://localhost:5001 rti-demo-acsi
```

## Development

### Testing

Run the test scripts:

```bash
# Test client_io and io_router
python examples/rti-demo/acsi/test_client_io.py

# Run standalone io_router tests
python examples/rti-demo/acsi/test_io_router_standalone.py

# Run usage examples
python examples/rti-demo/acsi/example_usage.py
```

### Adding New IO Functionality

1. **Extend DemoIOClient**: Add new methods to `client_io.py` for additional demo_IO API calls
2. **Add New Endpoints**: Add new routes to `io_router.py` to expose new functionality
3. **Update BFF**: The IO router is automatically included in ACSI's BFF via `bff_endpoint.py`

## Troubleshooting

### Connection Issues

**Error:** `demo_IO service is not responding`

- Check that demo_IO service is running
- Verify the URL is correct (default: http://localhost:8080)
- Check that the port is accessible (firewall, Docker networking)
- Test with: `curl http://demo-io:8080/api/io/health`

**Error:** `Client not configured`

- Set `DEMO_IO_URL` environment variable, or
- Use POST `/api/io/connect` endpoint to configure connection

### Port Conflicts

- demo_IO uses port 8080 by default
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

- `client_io.py` - DemoIOClient HTTP client
- `io_router.py` - FastAPI IO router for ACSI BFF
- `test_client_io.py` - Test script for client and router
- `test_io_router_standalone.py` - Standalone router tests
- `example_usage.py` - Usage examples
- `README_IO.md` - This file

## Compatibility

- Python 3.10+
- FastAPI 0.100+
- requests library
- demo_IO service (from examples/rti-demo/demo_IO/)

## License

This code is part of the RTI_DEMO project and follows the same license terms.
