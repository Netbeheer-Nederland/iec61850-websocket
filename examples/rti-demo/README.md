# RTI Demo

Unified entry point for launching RTI (Real-Time Infrastructure) demo services.

## Quick Start

```bash
# Launch all services (default: all services with foreground & verbose mode)
python launch.py

# Launch individual services
python launch.py bff
python launch.py fsp
python launch.py so
python launch.py frontend
```

## Services

| Service                  | Port        | Description                                                           |
|--------------------------|-------------|-----------------------------------------------------------------------|
| `bff`                    | 5000        | Backend for Frontend - REST API gateway                               |
| `fsp`                    | 5001        | RTI-FSP - IEC 61850 server                                            |
| `so`                     | 5002        | RTI-SO - IEC 61850 client                                             |
| `frontend`               | 8080        | Web-based HMI                                                         |
| `keycloak` (Docker only) | 8080 / 8443 | IDP-Server for OAuth - see [Keycloak](#keycloak-idp-server-for-oauth) |

## Access URLs

- BFF: http://localhost:5000/api/health
- FSP: http://localhost:5001/api/status
- SO: http://localhost:5002/api/status
- Frontend: http://localhost:8080

## Common Commands

```bash
# Show help
python launch.py --help

# List available services
python launch.py list

# Launch with custom port
python launch.py bff --port 5005

# Disable foreground mode (run in background)
python launch.py --background

# Disable verbose logging
python launch.py --no-verbose

# Check running services
python launch.py --status

# Stop all services
python launch.py --stop

# Docker mode
python launch.py --docker
```

## Verbose Mode & Logs

By default, verbose logging is enabled and the console is kept alive (foreground mode). All service logs are prefixed
with the service name:

```
[BFF Server] INFO: Starting RTI Demo BFF Server (FastAPI)...
[BFF Server] INFO: 127.0.0.1:35682 - "GET /docs HTTP/1.1" 200 OK
[FSP ACSI-Server_WebsocketActive] Starting server on port 5001
[SO ACSI-Client_WebsocketPassive] Connected to endpoint
[Frontend] Serving HTTP on 0.0.0.0 port 8080
```

To disable verbose logging: `python launch.py --no-verbose`
To run in background: `python launch.py --background`

## Troubleshooting

### Port already in use

```bash
# Find and kill process on port 8080
sudo kill -9 $(sudo lsof -t -i :8080) 2>/dev/null
```

### Module not found

```bash
# Install dependencies
pip install -e .
pip install uvicorn fastapi requests
```

### connections.json error

```bash
# Remove directory and create file
rmdir /S /Q connections.json 2>/dev/null
echo [] > connections.json
```

## Docker

```shell
docker network create rti-network 2>/dev/null || true
```

```shell
# Build images (each module's Dockerfile builds from the repo root, since
# fsp/so need the ws61850 core library at src/)
cd ../..   # repo root
docker build -f examples/rti-demo/modules/bff/docker/Dockerfile -t rti-demo-bff .
docker build -f examples/rti-demo/modules/fsp/docker/Dockerfile -t rti-demo-fsp .
docker build -f examples/rti-demo/modules/so/docker/Dockerfile -t rti-demo-so .
```

# Launch with Docker (all services by default)

```shell
python launch.py --docker
```

# Docker Compose

```shell
cd examples/rti-demo
docker compose up -d
```

### Keycloak (IDP-Server) for OAuth

From the directory scripts/keycloak `docker compose up -d` with `iec61850-test` realm (client `ws-client`) imported from
`scripts/keycloak/data`, on `rti-network`.

- Admin console: http://localhost:8080 (admin / admin)
- From the other containers: `http://keycloak:8080`

Token issuer is always `http://localhost:8080/realms/iec61850-test`,
whichever address a token was requested on (`KC_HOSTNAME`), so the SO's
issuer check sees a single value. Settings to enter in the HMI (Setup):

| Where                  | Field                | Value                                                                     |
|------------------------|----------------------|---------------------------------------------------------------------------|
| IDP-Server connection  | Endpoint             | `http://keycloak:8080`                                                    |
| RTI-FSP / RTI-SO OAuth | Token endpoint       | `http://keycloak:8080/realms/iec61850-test/protocol/openid-connect/token` |
|                        | Certificate endpoint | `http://keycloak:8080/realms/iec61850-test/protocol/openid-connect/certs` |
|                        | Token issuer         | `http://localhost:8080/realms/iec61850-test`                              |
|                        | Client ID / secret   | `ws-client` / see `scripts/keycloak/README.md`                            |

HTTPS (8443) uses `testing/certs/server.pem`, whose certificate only covers
`rti-so`/`localhost` - so from the containers use plain HTTP on 8080, or
reissue the certificate with a `keycloak` SAN.

### BFF connection persistence in Docker

The `rti-bff` container persists `connections.json` in a dedicated `/config`
directory backed by the `bff-config` named volume (not in `/app` or the `./bff`
code mount). On first start it is seeded from `bff/connections.json`; after that
the volume is authoritative. To reset it:

```bash
docker-compose down
docker volume rm rti-demo_bff-config   # prefix matches your compose project name
docker-compose up -d rti-bff
```

The `BFF_CONNECTIONS_FILE` env var overrides the path if you need a different
location (e.g. a host bind mount).

## IO API Server

The IO API Server provides REST API endpoints for controlling physical IO devices (LEDs, buttons, LCDs, etc.) on a
Raspberry Pi.

### Raspberry Pi Setup

#### Enable I2C Interface (Required for LCD I2C)

For LCD displays using I2C interface (SDA/SCL), you must enable I2C on the Raspberry Pi:

```bash
sudo raspi-config
```

- Navigate to: **Interface Options → I2C → Enable**
- Exit and reboot:

```bash
sudo reboot
```

#### Install I2C Dependencies

```bash
# Install I2C tools and Python dependencies
sudo apt update
sudo apt install -y i2c-tools python3-smbus
pip install smbus2
```

#### Verify I2C is Working

```bash
# Check if I2C kernel modules are loaded
lsmod | grep i2c

# List I2C devices
ls /dev/i2c*

# Scan for I2C devices (replace 1 with your bus number if different)
sudo i2cdetect -y 1
```

Most I2C LCD backpacks (PCF8574) use address **0x27** or **0x3F**. Update `io_config.json` with the correct address:

```json
{
  "name": "lcd_i2c",
  "device_type": "lcd_i2c",
  "i2c_address": 40,
  // 0x27 in decimal
  "i2c_bus": 1
}
```

#### Troubleshooting I2C LCD

| Issue                             | Solution                                                        |
|-----------------------------------|-----------------------------------------------------------------|
| `i2cdetect` shows no devices      | Check wiring, verify I2C is enabled                             |
| Address shows `UU`                | Device conflict, try power cycling                              |
| Wrong address (0x27 vs 0x3F)      | Try both addresses in config                                    |
| Permission denied on `/dev/i2c-1` | Add user to i2c group: `sudo usermod -aG i2c $USER` then reboot |

#### Wiring Reference (PCF8574 I2C LCD Backpack)

| LCD Backpack | Raspberry Pi                 |
|--------------|------------------------------|
| GND          | Pin 6 (GND)                  |
| VCC          | Pin 2 (5V) or Pin 1 (3.3V) * |
| SDA          | Pin 3 (GPIO 2, SDA)          |
| SCL          | Pin 5 (GPIO 3, SCL)          |

*Check your LCD backpack documentation for voltage requirements (3.3V vs 5V)*

### IO API Server Usage

#### Start the IO API Server

```bash
# Direct Python
cd demo_IO/io_api_server
python main.py

# With custom port
PORT=8080 python main.py

# With Docker Compose
cd demo_IO
docker-compose up rti-io
```

#### API Endpoints

- **Health**: `GET /api/io/health`
- **List devices**: `GET /api/io/devices`
- **Device state**: `GET /api/io/{device_name}`
- **Write to device**: `POST /api/io/{device_name}`
- **LCD write**: `POST /api/io/lcd/{device_name}/write` - Body: `{"text": ["line1", "line2"]}`
- **LCD write line**: `POST /api/io/lcd/{device_name}/write-line` - Body: `{"line": 0, "text": "text"}`
- **LCD clear**: `POST /api/io/lcd/{device_name}/clear`

#### Device Configuration

Edit `demo_IO/io_api_server/io_config.json` to configure your devices. Example:

```json
{
  "devices": [
    {
      "name": "led1",
      "device_type": "led",
      "type": "led",
      "gpio_pin": 17,
      "direction": "output"
    },
    {
      "name": "lcd_i2c",
      "device_type": "lcd_i2c",
      "type": "lcd_i2c",
      "i2c_address": 40,
      "i2c_bus": 1,
      "columns": 16,
      "rows": 2,
      "direction": "output"
    }
  ]
}
```

See `demo_IO/io_api_server/devices.py` for all supported device types and configurations.

## Project Structure

```
rti-demo/
├── launch.py                  # Main entry point
├── README.md                  # This file
├── docker-compose.yml
├── config/
│   ├── launch_config.json.example
│   └── models/                # IED model files (model_1.py, model_2.py)
├── scripts/
│   ├── set_docker_user.sh     # Detect/export host UID+GID for the demo_io build
│   └── setup_raspberry_docker.sh  # Install Docker on a fresh Raspberry Pi
└── modules/
    ├── bff/       { pyproject.toml, docker/Dockerfile, src/bff/, tests/ }
    ├── fsp/       { pyproject.toml, docker/Dockerfile, src/fsp/, tests/ }
    ├── so/        { pyproject.toml, docker/Dockerfile, src/so/, tests/ }
    ├── io/        { pyproject.toml, docker/Dockerfile, io_api_server/, io_client/ }
    └── hmi/       { package.json, docker/Dockerfile, src/ }  # Web HMI (React)
```

`bff`, `fsp` and `so` are members of a single uv workspace rooted at the
repository root (alongside the `ws61850` core library at `src/`) - see
`TESTING.md` for how to install/run them. `demo_io` and `hmi` build and
run independently (Pi hardware deps / npm toolchain respectively).

## UV

UV is already implemented to manage the dependencies inside the dockers. To add a dependency to the project, you can use
the following command:

```bash
uv add <package_name>
```

This should be followed by rebuilding the dockers to make sure the new dependency is included in the images.

```bash

After adding the dependency, you can run the following command to make sure the lock file is updated with the new dependency:

```bash
uv lock
```

To run the python codes without the dockers, you can use the following command to install the dependencies in your local
environment:

```bash
uv sync
```

and the python codes can be run using the following command:

```bash
uv run python <script_name.py>
```
