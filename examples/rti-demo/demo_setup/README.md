# RTI Demo Setup - Docker Compose Files

This folder contains Docker Compose configuration files for deploying the RTI demo system across multiple devices.

## Setup Overview

| Device | Docker Compose File | Services | Ports |
|--------|---------------------|----------|-------|
| **PC** | `docker-compose.HMI.yml` | BFF + Frontend (HMI) | 5000, 8080 |
| **Raspberry Pi 1** | `docker-compose.FSP.yml` | FSP + IO Server | 5001, 8000 |
| **Raspberry Pi 2** | `docker-compose.SO.yml` | SO + IO Server | 5002, 8765, 8000 |

## Prerequisites

1. **Docker** installed on all devices (PC, Raspberry Pi 1, Raspberry Pi 2)
2. **Dockerfiles** exist in the parent directory:
   - `Dockerfile.bff`
   - `Dockerfile.frontend`
   - `Dockerfile.IO`
   - `examples/rti-demo/Dockerfile.rti-fsp`
   - `examples/rti-demo/Dockerfile.rti-so`
3. All devices on the **same LAN network**
4. **Firewall rules** allow traffic between devices on required ports

## Configuration

### 1. Update IP Addresses

Before deploying, edit each compose file to replace IP placeholders:

- **`docker-compose.HMI.yml`**: Set `REACT_APP_BFF_URL=http://<BFF_IP>:5000` to the PC's IP
- **`docker-compose.FSP.yml`**: Ensure `DEMO_IO_URL=http://demo_io:8000` (Docker internal DNS)
- **`docker-compose.SO.yml`**: Ensure `DEMO_IO_URL=http://demo_io:8000` (Docker internal DNS)

### 2. BFF Configuration (Optional)

The BFF needs to know where to find FSP and SO services. Add these environment variables to `docker-compose.HMI.yml`:

```yaml
bff-server:
  environment:
    - FSP_URL=http://<RPI1_IP>:5001
    - SO_URL=http://<RPI2_IP>:5002
```

## Deployment

### On PC (HMI + BFF):
```bash
cd examples/rti-demo/demo_setup
docker-compose -f docker-compose.HMI.yml up -d --build
```

### On Raspberry Pi 1 (FSP + IO):
```bash
cd examples/rti-demo/demo_setup
docker-compose -f docker-compose.FSP.yml up -d --build
```

### On Raspberry Pi 2 (SO + IO):
```bash
cd examples/rti-demo/demo_setup
docker-compose -f docker-compose.SO.yml up -d --build
```

## Service URLs

| Service | URL |
|---------|-----|
| HMI/Frontend | `http://<PC_IP>:8080` |
| BFF | `http://<PC_IP>:5000` |
| FSP | `http://<RPI1_IP>:5001` |
| FSP WebSocket | `ws://<RPI1_IP>:8765` |
| SO | `http://<RPI2_IP>:5002` |
| SO WebSocket | `ws://<RPI2_IP>:8765` |
| IO Server (RPi1) | `http://<RPI1_IP>:8000` |
| IO Server (RPi2) | `http://<RPI2_IP>:8000` |

## Stopping Services

To stop all services on a device:

```bash
cd examples/rti-demo/demo_setup
docker-compose -f docker-compose.<FILE>.yml down
```

## Viewing Logs

```bash
# View all logs
docker-compose -f docker-compose.<FILE>.yml logs -f

# View specific service logs
docker-compose -f docker-compose.<FILE>.yml logs -f <service_name>
```

## Network Connectivity

The `rti-network` bridge network allows containers on the same device to communicate using service names:
- `bff-server` -> `http://bff-server:5000`
- `rti-fsp` -> `http://rti-fsp:5001`
- `rti-so` -> `http://rti-so:5002`
- `demo_io` -> `http://demo_io:8000`

For cross-device communication, use the device's actual IP address.

## Troubleshooting

1. **Port conflicts**: Ensure ports are not already in use
2. **Docker daemon**: Make sure Docker is running on all devices
3. **Network**: Verify all devices can ping each other
4. **GPU devices**: Raspberry Pi requires `--privileged` and device access for GPIO
5. **Build context**: If build fails, verify the context paths are correct

## Notes

- The IO server on Raspberry Pi requires access to GPIO devices (`/dev/gpiochip*`)
- Containers use `privileged: true` and `cap_add: SYS_RAWIO` for GPIO access
- The `//var/run/docker.sock` volume mount is Windows-specific for Docker socket access
- For Linux, use `/var/run/docker.sock:/var/run/docker.sock`
