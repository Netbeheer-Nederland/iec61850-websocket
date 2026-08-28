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

## Demo IO Setup

### Services to Demonstrate
- Reports
- Operation Control
- Setpoints

### I/O Demo

#### SO → ACSI Client
- **WebSocket (WS)**: Passive
- **Indicators**:
  - LED 1 → Connection status
  - LED 2 → Report received
  - LED 3 → stVal (Boolean)
    - Mapping of the report value change of the data attribute stVal received in the RCB
- **Inputs**:
  - **Potentiometer 1**:
    - Input for Oper Float
    - Monitor displays the value
  - **Potentiometer 2**:
    - Input for Oper Int
    - Monitor displays the value

#### FSP → ACSI Server
- **WebSocket (WS)**: Active
- **Indicators**:
  - LED 1 → Connection status
  - LED 2 → Operation control received
- **Monitoring**:
  - Monitor displays Operation Float value
- **Input**:
  - **Button**:
    - Input to stVal (Boolean)
    - Triggers the RCB

### Demo Flow
1. Establish communication between FSP (ACSI Server) and SO (ACSI Client).
2. Verify LED 1 on both sides indicates connection status.
3. Change Potentiometer 1 and observe the Oper Float value on the monitor.
4. Change Potentiometer 2 and observe the Oper Int value on the monitor.
5. Verify report reception:
   - LED 2 on SO indicates report received.
   - LED 2 on FSP indicates operation control received.
6. Press the button to change stVal.
7. Verify LED 3 reflects the report value change corresponding to the stVal data attribute received in the RCB.
8. Confirm the RCB is triggered and the report is transmitted successfully.

### Signal Mapping
```
BUTTON (FSP)
    │
    ▼
stVal (Boolean)
    │
    ▼
RCB Triggered
    │
    ▼
Report Sent
    │
    ▼
SO receives report
    │
    ▼
LED3 indicates change of stVal
```

### Operation Control Demo
```
SO Potentiometer 1 (Oper Float)
           │
           ▼
      Operation Control
           │
           ▼
         FSP
           │
           ▼
      Monitor Value
```

### Physical Devices

**P1 (SO)**
```
├─ LED1 Connection
├─ LED2 Report Received
├─ LED3 stVal Mapping
├─ Pot 1 Oper Float
└─ Pot 2 Oper Int
```

**P2 (FSP)**
```
├─ LED1 Connection
├─ LED2 Operation Received
├─ Button → stVal
└─ Monitor → Oper Float
```

**P3**
```
└─ Status/Display Module (optional)
```

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
