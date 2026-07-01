# RTI Demo - Unified Entry Point

## Overview

This directory contains the **RTI (Real-Time Infrastructure) Demo** applications for IEC 61850 WebSocket-based communication. The demo provides a complete ecosystem for testing and demonstrating IEC 61850 protocol implementations with various service types.

### 🎯 Key Improvement: Unified Entry Point

**Previously**: Each demo component had its own fragmented startup path, documentation, and inconsistent ways to launch services.

**Now**: All demos are launched through a single, consistent entry point: **`python launch.py`**

## Quick Start

### Launch All Services

```bash
# From the rti-demo directory
python launch.py all
```

This starts all demo services:
- **BFF Server** (port 5000) - Backend for Frontend gateway
- **FSP ACSI-Server_WebsocketActive** (port 5001) - RTI-FSP  
- **SO ACSI-Client_WebsocketPassive** (port 5002) - RTI-SO
- **Frontend** (port 8080) - Web-based HMI

### Launch Individual Services

```bash
# Launch only the BFF server
python launch.py bff

# Launch FSP and SO together
python launch.py fsp so

# Launch with custom port
python launch.py bff --port 8080
```

### Docker Mode

```bash
# Launch all services in Docker containers
python launch.py all --docker

# Launch specific service in Docker
python launch.py bff --docker
```

## 📋 Available Services

| Service | Type | Default Port | Description | Entry Point |
|---------|------|--------------|-------------|-------------|
| `bff` | Backend for Frontend | 5000 | REST API gateway for frontend applications | `bff/bff_server.py` |
| `fsp` | RTI-FSP | 5001 | IEC 61850 server with WebSocket support | `fsp/bff_endpoint.py` |
| `so` | RTI Standalone Object | 5002 | IEC 61850 client for data access | `so/bff_endpoint.py` |
| `frontend` | Web HMI | 8080 | HTML/JavaScript frontend interface | `front-end/` |

## 🚀 Command Reference

### Basic Commands

```bash
# Show help for all commands
python launch.py --help

# List available services
python launch.py list

# Launch specific services
python launch.py bff
python launch.py fsp so
python launch.py all

# Launch with custom port
python launch.py bff --port 5005

# Run in Docker containers
python launch.py bff --docker

# Run in background
python launch.py bff --background

# Show status of running services
python launch.py --status

# Stop all running services
python launch.py --stop
```

### Advanced Usage

```bash
# Launch all services with verbose logging
python launch.py all -v

# Launch multiple services with port override
python launch.py fsp so --port 6000

# Launch services in background and check status
python launch.py bff fsp --background
python launch.py --status

# Use custom configuration file
python launch.py all --config my_config.json
```

## 📁 Directory Structure

```
rti-demo/
├── launch.py                    # ✅ Unified entry point (NEW)
├── README.md                   # ✅ This file - unified documentation (NEW)
├── docker-compose.yml          # Docker Compose configuration
├── Dockerfile                  # Top-level Dockerfile
├── requirements.txt            # Python dependencies
│
├── bff/                        # Backend for Frontend
│   ├── bff_server.py          # FastAPI server
│   ├── bffClient.py           # BFF client library
│   └── Dockerfile             # BFF Docker configuration
│
├── fsp/                        # RTI-FSP
│   ├── bff_endpoint.py        # FastAPI endpoint
│   ├── acsi_server.py         # IEC 61850 server
│   └── Dockerfile             # FSP Docker configuration
│
├── so/                         # RTI Standalone Object
│   ├── bff_endpoint.py        # FastAPI endpoint
│   ├── acsi_client.py         # IEC 61850 client
│   └── Dockerfile             # SO Docker configuration
│
└── front-end/                 # Web Interface
    ├── index.html             # Main HTML page
    ├── app.js                 # JavaScript application
    └── styles.css            # CSS styles
```

## 🔧 Configuration

### Environment Variables

Each service can be configured using environment variables:

```bash
# Set port for BFF server
PORT=5005 python launch.py bff

# Enable Docker auto-discovery for BFF
RTI_DOCKER_ENABLED=true python launch.py bff

# Multiple environment variables
export PORT=5005
export RTI_DOCKER_ENABLED=true
python launch.py bff
```

### Custom Configuration File

Create a `launch_config.json` file:

```json
{
  "services": {
    "bff": {
      "port": 5005,
      "docker": false,
      "env": {
        "RTI_DOCKER_ENABLED": "true",
        "CUSTOM_VAR": "custom_value"
      }
    },
    "fsp": {
      "port": 5010,
      "docker": false
    }
  }
}
```

Then use it:
```bash
python launch.py all --config launch_config.json
```

## 🐳 Docker Deployment

### Build All Images

```bash
# From the repository root
docker build -t rti-demo-bff -f rti-demo/bff/Dockerfile .
docker build -t rti-demo-fsp -f rti-demo/fsp/Dockerfile .
docker build -t rti-demo-so -f rti-demo/so/Dockerfile .
```

### Use Docker Compose

```bash
# Create and start all services
docker-compose -f rti-demo/docker-compose.yml up -d

# View running services
docker-compose -f rti-demo/docker-compose.yml ps

# Stop all services
docker-compose -f rti-demo/docker-compose.yml down
```

### Using the Launcher with Docker

```bash
# Launch all services in Docker
python launch.py all --docker

# Launch specific service in Docker with custom port
python launch.py bff --docker --port 5005
```

## 🏥 Service Management

### Check Service Status

```bash
# Check which services are running
python launch.py --status

# Example output:
# Service Status:
# ---------------------------------------
#   bff             (port 5000) - RUNNING
#   fsp             (port 5001) - RUNNING
#   so              (port 5002) - RUNNING
```

### Health Checks

```bash
# Check service health (automatically done with --status)
python launch.py --status
```

### Stop Services

```bash
# Stop all running services
python launch.py --stop

# Stop specific service
# (Use Ctrl+C in the terminal where the service is running)
```

## 🧪 Testing & Validation

### Test Endpoints

```bash
# Test BFF health
curl http://localhost:5000/api/health

# Test FSP status
curl http://localhost:5001/api/iec61850server/status

# Test SO status
curl http://localhost:5002/api/iec61850client/status
```

### Frontend Access

Open your browser and navigate to:
```
http://localhost:8080
```

## 📊 Service Discovery

The BFF server includes automatic service discovery when running in Docker:

```bash
# Enable Docker auto-discovery
RTI_DOCKER_ENABLED=true python launch.py bff
```

This allows the BFF to automatically detect and register:
- Other RTI demo services running in Docker
- Their endpoints and health status
- Service types and metadata

## 🎨 Frontend Interface

The frontend provides a web-based HMI for:
- Viewing IEC 61850 server hierarchy
- Reading/writing data values
- Monitoring service status
- Performing ACSI operations

Access at: `http://localhost:8080`

## 🔒 Port Configuration

| Service | Default Port | Alternative Port | Notes |
|---------|--------------|-----------------|-------|
| BFF | 5000 | Any | Gateway for frontend |
| FSP | 5001 | Any | Server platform |
| SO | 5002 | Any | Standalone client |
| Frontend | 8080 | Any | Web interface |

**Note**: Port conflicts will occur if you try to run multiple instances on the same port.

## 🛠️ Development Setup

### Prerequisites

- Python 3.11+
- pip (Python package manager)
- Docker (optional, for containerized deployment)
- Node.js (optional, for advanced frontend development)

### Install Dependencies

```bash
# From the repository root
pip install -e .
pip install fastapi uvicorn requests docker
```

### Development Workflow

```bash
# Launch BFF in development mode with auto-reload
python launch.py bff --verbose

# Launch FSP with custom port for testing
python launch.py fsp --port 5010 --verbose

# Test changes and restart services as needed
```

## 📚 API Documentation

Each service provides REST API endpoints. See the individual README files for details:

- [BFF API Documentation](bff/BFF_EXPLANATION.md)
- [FSP API Documentation](fsp/BFF_API.md)
- [SO API Documentation](so/BFF_API.md)

## 🔄 Migration Guide

### From Fragmented Startup to Unified Entry Point

**Before (Fragmented):**
```bash
# Different commands for each service
python bff/bff_server.py
python fsp/bff_endpoint.py
python so/bff_endpoint.py
```

**After (Unified):**
```bash
# Single command for all services
python launch.py all

# Or individual services
python launch.py bff
python launch.py fsp
```

### Benefits of the Unified Approach

1. **Consistency**: Same command pattern for all services
2. **Simplicity**: One entry point to remember
3. **Flexibility**: Easy to launch individual or multiple services
4. **Management**: Built-in service status and health checks
5. **Configuration**: Centralized configuration options
6. **Documentation**: Single source of truth for usage

## 🐛 Troubleshooting

### Common Issues

**Port already in use:**
```
Error: [Errno 98] Address already in use
```

**Solution**: Stop the existing service or use a different port:
```bash
python launch.py --stop
python launch.py bff --port 5005
```

**Docker not found:**
```
Error: docker: command not found
```

**Solution**: Install Docker Desktop or run without Docker:
```bash
python launch.py bff  # Without --docker flag
```

**Module not found:**
```
ModuleNotFoundError: No module named 'ws61850'
```

**Solution**: Install the package from repository root:
```bash
pip install -e .
```

### Debug Mode

```bash
# Enable verbose logging for troubleshooting
python launch.py bff -v

# Check service logs
python launch.py bff  # Run in foreground to see logs
```

## 🎯 Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         RTI Demo Architecture                     │
├─────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐       │
│  │  Frontend   │    │    BFF      │    │    Docker    │       │
│  │   (8080)    │◄───►│   (5000)    │◄───►│  Discovery   │       │
│  └─────────────┘    └─────────────┘    └─────────────┘       │
│         ▲                  ▲ ▲ ▲                               │
│         │                  │ │ │                               │
│         │                  │ │ └──────────────────────────────┘
│         │                  │ │
│         │                  │ └───── WebSocket / REST API
│         │                  │
│         │                  └───────► ┌─────────────┐         │
│         │                             │   FSP      │         │
│         │                             │  (5001)    │         │
│         │                             └─────────────┘         │
│         │                                  ▲                     │
│         │                                  │                     │
│         │                          ┌───────┴───────┐              │
│         │                          │                 │              │
│         └──────────────────────────┤    ACSI Client    │              │
│                                        │    (5002)      │              │
│                                        │                 │              │
│                                        └─────────────────┘              │
│                                              ▲                           │
│                                              │                           │
│                                        ┌─────┴─────┐                      │
│                                        │           │                      │
│                                 ┌──────►  ACSI     │                      │
│                                 │        Server   │                      │
│                                 │        (5004)   │                      │
│                                 │        or       │                      │
│                                 │     ACSI Client │                      │
│                                 │     (5003)     │                      │
│                                 └────────────────┘                      │
│                                                                     │
└─────────────────────────────────────────────────────────────┘
```

## 📖 Service Details

### BFF Server (Backend for Frontend)

- **Purpose**: Central API gateway for frontend applications
- **Port**: 5000 (default)
- **Features**: 
  - Service discovery (Docker and network-based)
  - Connection management to remote endpoints
  - Data read/write operations
  - Dynamic API execution against registered targets
  - Health checks and status monitoring
  - Report generation and export

### FSP ACSI-Server_WebsocketActive (RTI-FSP)

- **Purpose**: IEC 61850 server implementation
- **Port**: 5001 (default)
- **Features**:
  - WebSocket endpoint lifecycle management
  - IEC 61850 server instantiation and control
  - Model loading and caching
  - Async event loop management

### SO ACSI-Client_WebsocketPassive (RTI Standalone Object)

- **Purpose**: IEC 61850 client for data access
- **Port**: 5002 (default)
- **Features**:
  - WebSocket endpoint lifecycle management
  - IEC 61850 client instantiation and control
  - Connection management
  - Async event loop management

## 🚀 Deployment Scenarios

### Local Development

```bash
# Start all services for local development
python launch.py all --verbose
```

### Docker Production Deployment

```bash
# Build all images
docker-compose -f rti-demo/docker-compose.yml build

# Start all services in detached mode
docker-compose -f rti-demo/docker-compose.yml up -d

# View logs
docker-compose -f rti-demo/docker-compose.yml logs -f
```

### Mixed Mode (Some Docker, Some Local)

```bash
# Start BFF and frontend locally, others in Docker
python launch.py bff frontend
docker-compose -f rti-demo/docker-compose.yml up -d fsp so
```

## 🔗 Integration

### With Existing Systems

The RTI demo services can integrate with:
- External IEC 61850 servers
- SCADA systems
- Other RTI-compliant applications

### Configuration for External Services

```bash
# Configure BFF to discover external services
RTI_DOCKER_ENABLED=false python launch.py bff

# Then manually add connections via API:
curl -X POST http://localhost:5000/api/connections \
  -H "Content-Type: application/json" \
  -d '{"name": "External Server", "host": "192.168.1.100", "port": 5001, "type": "RTI-FSP"}'
```

## 📈 Monitoring

### Built-in Monitoring

```bash
# Check service status
python launch.py --status

# Check health endpoints
curl http://localhost:5000/api/health
curl http://localhost:5001/api/iec61850server/status
```

### Docker Monitoring

```bash
# View Docker container status
docker ps

# View logs
docker logs <container_name>

# View resource usage
docker stats
```

## 📝 Changelog

### Version 2.0 - Unified Entry Point

- ✅ Added `launch.py` as unified entry point
- ✅ Removed fragmented startup paths
- ✅ Standardized service configuration
- ✅ Added comprehensive documentation
- ✅ Implemented service status and health checking
- ✅ Added Docker and non-Docker launch support
- ✅ Improved error handling and logging

### Previous Versions

- Fragmented startup scripts
- Individual Dockerfiles
- Separate documentation per component
- No centralized management

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

This project is part of the RTI demo suite. Check the main repository for license information.

## 🆘 Support

For issues or questions:
- Check the troubleshooting section above
- Review the API documentation for each service
- Enable verbose logging (`-v` flag) for detailed information

## 📞 Contact

For more information about the RTI demo or IEC 61850 implementation, refer to the main project documentation or contact the development team.

---

**RTI Demo v2.0** | Unified Entry Point | Consistent Service Management