# RTI Demo Setup - Docker Compose Files

This folder contains Docker Compose configuration files for deploying the RTI demo system across multiple physical devices.

> **Windows users**: Start Docker Desktop before running any docker-compose commands. The error `failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine` means Docker Desktop is not running.

## Device Setup

| Device | Docker Compose File | Services | Exposed Ports |
|--------|---------------------|----------|---------------|
| **PC** | `docker-compose.HMI.yml` | BFF + Frontend (HMI) | 5000, 8080 |
| **Raspberry Pi 1** | `docker-compose.FSP.yml` | FSP + IO Server | 5001, 8000 |
| **Raspberry Pi 2** | `docker-compose.SO.yml` | SO + IO Server | 5002, 8000, 8765 |

---

## Quick Start Commands

### On PC (HMI + BFF)
```bash
cd examples/rti-demo/demo_setup

# Build images without cache (fresh build)
docker-compose -f docker-compose.HMI.yml build --no-cache

# Start containers
docker-compose -f docker-compose.HMI.yml up -d

# Stop containers
docker-compose -f docker-compose.HMI.yml down

# Build + Start in one command
docker-compose -f docker-compose.HMI.yml build --no-cache && docker-compose -f docker-compose.HMI.yml up -d
```

### On Raspberry Pi 1 (FSP + IO Server)
```bash
cd examples/rti-demo/demo_setup

# Build images without cache
docker-compose -f docker-compose.FSP.yml build --no-cache

# Start containers
docker-compose -f docker-compose.FSP.yml up -d

# Stop containers
docker-compose -f docker-compose.FSP.yml down

# Build + Start in one command
docker-compose -f docker-compose.FSP.yml build --no-cache && docker-compose -f docker-compose.FSP.yml up -d
```

### On Raspberry Pi 2 (SO + IO Server)
```bash
cd examples/rti-demo/demo_setup

# Build images without cache
docker-compose -f docker-compose.SO.yml build --no-cache

# Start containers
docker-compose -f docker-compose.SO.yml up -d

# Stop containers
docker-compose -f docker-compose.SO.yml down

# Build + Start in one command
docker-compose -f docker-compose.SO.yml build --no-cache && docker-compose -f docker-compose.SO.yml up -d
```

---

## Complete Command Reference

### Build Commands (No Cache)
```bash
# Build only (no cache)
docker-compose -f docker-compose.HMI.yml build --no-cache
docker-compose -f docker-compose.FSP.yml build --no-cache
docker-compose -f docker-compose.SO.yml build --no-cache

# Force pull latest base images and rebuild
docker-compose -f docker-compose.HMI.yml build --no-cache --pull
```

### Start Commands
```bash
# Start with existing images
docker-compose -f docker-compose.HMI.yml up -d

# Start and rebuild if needed (uses cache)
docker-compose -f docker-compose.HMI.yml up -d --build

# Start with fresh build (no cache)
docker-compose -f docker-compose.HMI.yml build --no-cache && docker-compose -f docker-compose.HMI.yml up -d
```

### Stop Commands
```bash
# Stop containers (keeps images and volumes)
docker-compose -f docker-compose.HMI.yml down

# Stop and remove volumes
docker-compose -f docker-compose.HMI.yml down -v

# Stop and remove everything (containers, networks, images, volumes)
docker-compose -f docker-compose.HMI.yml down --rmi all -v
```

### Status and Logs
```bash
# View service status
docker-compose -f docker-compose.HMI.yml ps

# View all logs
docker-compose -f docker-compose.HMI.yml logs -f

# View specific service logs
docker-compose -f docker-compose.HMI.yml logs -f bff-server

# Check health
docker-compose -f docker-compose.HMI.yml exec bff-server curl http://localhost:5000/api/health
```

---

## Configuration Before Deployment

### 1. Update IP Addresses in HMI

Edit `docker-compose.HMI.yml` and replace the placeholder:
```yaml
frontend:
  environment:
    - REACT_APP_BFF_URL=http://<BFF_IP>:5000
```
Replace `<BFF_IP>` with your PC's actual LAN IP address (e.g., `192.168.1.100`).

### 2. (Optional) Configure BFF to Find FSP and SO

Add to `docker-compose.HMI.yml` under `bff-server` environment:
```yaml
bff-server:
  environment:
    - FSP_URL=http://<RPI1_IP>:5001
    - SO_URL=http://<RPI2_IP>:5002
```

---

## Service URLs After Deployment

| Service | URL | Device |
|---------|-----|--------|
| HMI (React) | `http://<PC_IP>:8080` | PC |
| BFF REST API | `http://<PC_IP>:5000` | PC |
| FSP REST API | `http://<RPI1_IP>:5001` | Raspberry Pi 1 |
| FSP WebSocket | `ws://<RPI1_IP>:8765` | Raspberry Pi 1 |
| SO REST API | `http://<RPI2_IP>:5002` | Raspberry Pi 2 |
| SO WebSocket | `ws://<RPI2_IP>:8765` | Raspberry Pi 2 |
| IO Server (RPi1) | `http://<RPI1_IP>:8000` | Raspberry Pi 1 |
| IO Server (RPi2) | `http://<RPI2_IP>:8000` | Raspberry Pi 2 |

---

## Docker Network Notes

- Each device has its own `rti-network` bridge network
- Containers on the same device can communicate using service names:
  - `bff-server:5000`
  - `frontend:8080`
  - `rti-fsp:5001`
  - `rti-so:5002`
  - `demo_io:8000`
- Cross-device communication requires using actual IP addresses

---

## Prerequisites

1. **Docker Desktop** (Windows) or **Docker Engine** (Linux/RPi) installed and running on all devices
2. **Dockerfiles** exist in the correct locations:
   - `Dockerfile.bff` (in rti-demo/)
   - `hmi/Dockerfile` (in rti-demo/hmi/) - for React HMI (multi-stage: node + nginx)
   - `Dockerfile.IO` (in rti-demo/)
   - `examples/rti-demo/Dockerfile.rti-fsp` (relative to repo root)
   - `examples/rti-demo/Dockerfile.rti-so` (relative to repo root)
3. All devices on the **same LAN network**
4. **Firewall** allows traffic on ports: 5000, 5001, 5002, 8000, 8080, 8765

---

## Troubleshooting

### Common Issues

1. **Port already in use**
   ```bash
   lsof -i :5000
   kill -9 <PID>
   ```

2. **Build fails - missing Dockerfile**
   ```bash
   ls -la Dockerfile.bff
   ```

3. **GPIO access denied on Raspberry Pi**
   ```bash
   sudo usermod -aG docker $USER
   sudo usermod -aG gpio $USER
   ```

4. **Images not found**
   ```bash
   docker images
   docker pull rti-demo-bff
   ```

5. **Docker socket permission (Windows vs Linux)**
   - Windows: `//var/run/docker.sock:/var/run/docker.sock`
   - Linux: `/var/run/docker.sock:/var/run/docker.sock`

---

## Useful Docker Commands

```bash
# List all running containers
docker ps

# List all images
docker images

# Remove unused containers, networks, images
docker system prune

# View container resource usage
docker stats

# Enter a running container
docker exec -it bff-server bash
```
