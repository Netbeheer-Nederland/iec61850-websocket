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

| Service | Port | Description |
|---------|------|-------------|
| `bff` | 5000 | Backend for Frontend - REST API gateway |
| `fsp` | 5001 | RTI-FSP - IEC 61850 server |
| `so` | 5002 | RTI-SO - IEC 61850 client |
| `frontend` | 8080 | Web-based HMI |

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

By default, verbose logging is enabled and the console is kept alive (foreground mode). All service logs are prefixed with the service name:

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

```bash
# Build images
docker build -t rti-demo-bff -f rti-demo/bff/Dockerfile .
docker build -t rti-demo-fsp -f rti-demo/fsp/Dockerfile .
docker build -t rti-demo-so -f rti-demo/so/Dockerfile .

# Launch with Docker (all services by default)
python launch.py --docker

# Docker Compose
docker-compose -f rti-demo/docker-compose.yml up -d
```

## Project Structure

```
rti-demo/
├── launch.py              # Main entry point
├── README.md              # This file
├── bff/
│   └── bff_server.py      # BFF Server
├── fsp/
│   └── bff_endpoint.py    # FSP ACSI-Server
├── so/
│   └── bff_endpoint.py    # SO ACSI-Client
└── front-end/
    └── index.html         # Web HMI
```

## UV 
UV is already implemented to manage the dependencies inside the dockers. To add a dependency to the project, you can use the following command:

```bash
uv add <package_name>
```
This should be followed by rebuilding the dockers to make sure the new dependency is included in the images.

```bash

After adding the dependency, you can run the following command to make sure the lock file is updated with the new dependency:

```bash
uv lock
```

To run the python codes without the dockers, you can use the following command to install the dependencies in your local environment:

```bash
uv sync
```
and the python codes can be run using the following command:

```bash
uv run python <script_name.py>
```
