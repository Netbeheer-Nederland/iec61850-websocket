# Raspberry Pi GPIO LED Control API

A FastAPI-based web service for controlling LEDs connected to a Raspberry Pi via GPIO pins. This project provides a REST API that allows you to remotely control LED states from any device on your network.

## Features

- **REST API** for LED control via FastAPI
- **GPIO Abstraction** - Clean separation between hardware and API
- **Multiple LEDs** - Control individual or all LEDs at once
- **Mock Mode** - Works on any system (not just Raspberry Pi) for development
- **Swagger UI** - Interactive API documentation
- **CORS Support** - Accessible from web browsers and mobile apps

## Quick Start

### On Raspberry Pi

```bash
# 1. Clone or navigate to this directory
cd rti_2_0_demo/iec61850-websocket/examples/rti-demo/demo_IO

# 2. Install dependencies
pip install fastapi uvicorn gpiozero

# 3. Run the API server
python main.py

# 4. Open the API docs in your browser
# http://<raspberry-pi-ip>:8080/api/io/docs
```

### On Windows/macOS (Development/Testing)

```powershell
cd rti_2_0_demo/iec61850-websocket/examples/rti-demo/demo_IO

# Install only web dependencies (gpiozero not required)
pip install fastapi uvicorn

# Run the server (uses mock LEDs)
python main.py

# Access at: http://localhost:8080/api/io/docs
```

---

## Hardware Setup

### What You Need

| Component | Quantity | Notes |
|-----------|----------|-------|
| Raspberry Pi | 1 | Any model with GPIO header (Pi 2, 3, 4, Zero, etc.) |
| LEDs | 1-3 | 5mm standard LEDs |
| Resistors | 1-3 | 220Ω - 470Ω (recommended: 220Ω) |
| Breadboard | 1 | Optional but recommended |
| Jumper Wires | 6-10 | Male-to-Female for Pi to breadboard |
| Power Supply | 1 | For Raspberry Pi |

### Raspberry Pi GPIO Pin Reference

The application uses **BCM (Broadcom) GPIO numbering** by default.

| LED Name | GPIO Pin | Physical Pin | Location |
|----------|----------|---------------|----------|
| led1 | GPIO 17 | Pin 11 | Row 1, Column 4 |
| led2 | GPIO 18 | Pin 12 | Row 1, Column 5 |
| led3 | GPIO 22 | Pin 15 | Row 1, Column 8 |

![Raspberry Pi GPIO Pinout](https://pinout.xyz/resources/raspberry-pi-pinout-diagram.png)

> **Tip**: Use `pinout` command on Raspberry Pi to see the pin layout:
> ```bash
> pinout
> ```

### Circuit Diagram

```
Raspberry Pi GPIO Pin --- Resistor (220Ω) --- LED (+) --- GND (-)
```

For each LED:
1. Connect the **long leg (anode, +)** of the LED to one end of the resistor
2. Connect the other end of the resistor to the **GPIO pin** (e.g., GPIO 17)
3. Connect the **short leg (cathode, -)** of the LED to any **GND** pin

**Example for 3 LEDs:**
```
GPIO 17 (Pin 11) --- 220Ω --- LED1 (+) --- GND (Pin 6)
GPIO 18 (Pin 12) --- 220Ω --- LED2 (+) --- GND (Pin 9)
GPIO 22 (Pin 15) --- 220Ω --- LED3 (+) --- GND (Pin 14)
```

> **⚠️ CRITICAL**: Always use a resistor! Connecting an LED directly to GPIO without a resistor will burn it out.

### Breadboard Layout

```
Breadboard Columns:
+---------------------+---------------------+
| GND Rail            | + Rail              |
+---------------------+---------------------+
|                     |                     |
|  R1 (220Ω)          |  LED1 (+)           |
|  + to GPIO 17       |  - to GND           |
|                     |                     |
|  R2 (220Ω)          |  LED2 (+)           |
|  + to GPIO 18       |  - to GND           |
|                     |                     |
|  R3 (220Ω)          |  LED3 (+)           |
|  + to GPIO 22       |  - to GND           |
+---------------------+---------------------+
```

---

## Software Setup

### Raspberry Pi Preparation

#### 1. Update System

```bash
sudo apt update && sudo apt upgrade -y
```

#### 2. Enable GPIO (if not already enabled)

```bash
sudo raspi-config
```
- Navigate to: **Interface Options** → **I2C/SPI/Serial**
- Enable **I2C** and **SPI** (optional but recommended)
- Exit and reboot if prompted

#### 3. Install Dependencies

```bash
# Install Python 3 (usually pre-installed)
sudo apt install python3 python3-pip -y

# Install required packages
pip3 install fastapi uvicorn gpiozero
```

#### 4. Verify gpiozero Installation

```bash
python3 -c "from gpiozero import LED; print('gpiozero OK')"
```

### Windows/macOS Setup (Development Only)

For development and testing without a Raspberry Pi:

```powershell
# Create virtual environment (recommended)
python -m venv venv
.\venv\Scripts\activate

# Install dependencies
pip install fastapi uvicorn
```

> **Note**: On Windows/macOS, the application runs in **mock mode** - it simulates LEDs without actual hardware.

---

## Running the Application

### On Raspberry Pi

#### Method 1: Direct Run

```bash
cd rti_2_0_demo/iec61850-websocket/examples/rti-demo/demo_IO
python3 main.py
```

#### Method 2: Custom Port

```bash
PORT=8000 python3 main.py
```

#### Method 3: Run in Background (Production)

```bash
# Install as a systemd service
sudo cp demo_io.service /etc/systemd/system/
sudo systemctl enable demo_io
sudo systemctl start demo_io

# Check status
sudo systemctl status demo_io

# View logs
journalctl -u demo_io -f
```

See `demo_io.service` template below for service file.

### On Windows/macOS

```powershell
cd rti_2_0_demo/iec61850-websocket/examples/rti-demo/demo_IO
python main.py
```

> **Output**: The server starts on `http://localhost:8080` with mock LEDs

---

## API Endpoints

All endpoints are under the `/api/io/` prefix.

### Base URL

- On Raspberry Pi: `http://<raspberry-pi-ip>:8080/api/io/`
- On local PC: `http://localhost:8080/api/io/`

### Get Information

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | API information and available endpoints |
| GET | `/health` | Health check endpoint |
| GET | `/status` | GPIO controller status with all LED states |
| GET | `/leds` | Get state of all LEDs |
| GET | `/leds/{name}` | Get state of specific LED |

### Configure LEDs

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/leds/config` | Configure a new LED (add to controller) |

**Request body:**
```json
{
  "name": "my_led",
  "gpio_pin": 23,
  "description": "Custom LED",
  "initial_state": false
}
```

### Control LEDs

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/leds/{name}/set` | Set LED to ON or OFF |
| POST | `/leds/{name}/toggle` | Toggle LED state |
| POST | `/leds/all/set` | Set all LEDs to same state |
| POST | `/leds/all/on` | Turn all LEDs ON |
| POST | `/leds/all/off` | Turn all LEDs OFF |

**Set LED state:**
```bash
curl -X POST http://localhost:8080/api/io/leds/led1/set \
  -H "Content-Type: application/json" \
  -d '{"state": true}'
```

**Toggle LED:**
```bash
curl -X POST http://localhost:8080/api/io/leds/led2/toggle
```

**Turn all ON:**
```bash
curl -X POST http://localhost:8080/api/io/leds/all/on
```

**Turn all OFF:**
```bash
curl -X POST http://localhost:8080/api/io/leds/all/off
```

### System Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/initialize` | Initialize GPIO controller |
| POST | `/cleanup` | Clean up GPIO resources |

---

## Using Swagger UI

The easiest way to explore and test the API:

1. Open your browser
2. Navigate to: `http://<raspberry-pi-ip>:8080/api/io/docs`
3. Click on any endpoint to expand it
4. Click **"Try it out"**
5. Fill in parameters (if any)
6. Click **"Execute"**

![Swagger UI Example](https://fastapi.tiangolo.com/img/tutorial/first-steps/image01.png)

---

## Project Structure

```
demo_IO/
├── __init__.py              # Package initialization
├── gpio_controller.py       # GPIO hardware abstraction
├── api_endpoint.py          # FastAPI endpoints
├── main.py                  # Application entry point
├── README.md                # This file
└── requirements.txt         # Python dependencies
```

### Key Components

#### gpio_controller.py
- `GPIOController` - Main class for managing GPIO/LEDs
- `LEDConfig` - Configuration for individual LEDs
- Mock LED support for non-Pi systems

#### api_endpoint.py
- FastAPI application factory
- All REST endpoints
- Pydantic models for request validation
- CORS middleware

#### main.py
- Creates GPIOController with default LEDs
- Initializes hardware
- Starts FastAPI server
- Platform-specific configuration (Windows vs Unix)

---

## Customization

### Adding More LEDs

Edit `main.py` to add more LEDs:

```python
gpio_controller.add_led(
    name="led4",
    gpio_pin=23,
    description="Additional LED on GPIO 23",
    initial_state=False
)
```

Or via API:
```bash
curl -X POST http://localhost:8080/api/io/leds/config \
  -H "Content-Type: application/json" \
  -d '{"name": "led4", "gpio_pin": 23, "description": "New LED", "initial_state": false}'
```

### Changing GPIO Pins

Modify the default LEDs in `main.py`:

```python
gpio_controller.add_led("led1", gpio_pin=4, description="LED on GPIO 4")
gpio_controller.add_led("led2", gpio_pin=27, description="LED on GPIO 27")
```

---

## Systemd Service File (Optional)

Create `/etc/systemd/system/demo_io.service`:

```ini
[Unit]
Description=RPi GPIO LED Control API
After=network.target

[Service]
User=pi
WorkingDirectory=/home/pi/rti_2_0_demo/iec61850-websocket/examples/rti-demo/demo_IO
ExecStart=/usr/bin/python3 /home/pi/rti_2_0_demo/iec61850-websocket/examples/rti-demo/demo_IO/main.py
Restart=always
RestartSec=5
Environment=PORT=8080

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable demo_io
sudo systemctl start demo_io
```

---

## Troubleshooting

### Port Already in Use

**Error:** `[Errno 13] error while attempting to bind on address ('0.0.0.0', 8080)`

**Solution:** Use a different port:
```bash
PORT=8081 python main.py
```

Or find and kill the process using the port:
```bash
# Linux/macOS
lsof -i :8080
kill -9 <PID>

# Windows
netstat -ano | findstr 8080
taskkill /PID <PID> /F
```

### gpiozero Import Error

**Error:** `ModuleNotFoundError: No module named 'gpiozero'`

**Solution:**
```bash
pip install gpiozero
```

> **Note:** This error is expected on Windows/macOS. The application automatically falls back to mock mode.

### Permission Denied (Linux)

**Error:** Permission denied when accessing GPIO

**Solution:**
```bash
# Option 1: Run with sudo
sudo python main.py

# Option 2: Add user to gpio group
sudo usermod -aG gpio $USER
sudo reboot

# Option 3: Use localhost instead of 0.0.0.0
# Edit main.py: host="localhost"
```

### LEDs Not Responding

**Checklist:**

1. ✅ Are the LEDs connected correctly? (long leg to GPIO via resistor)
2. ✅ Is the resistor the correct value? (220Ω-470Ω)
3. ✅ Are you using BCM GPIO numbering? (not physical pin numbers)
4. ✅ Are the GND connections secure?
5. ✅ Is the Raspberry Pi powered on?
6. ✅ Did you enable GPIO in raspi-config?

**Test GPIO manually:**
```python
from gpiozero import LED
from time import sleep

led = LED(17)
led.on()
sleep(2)
led.off()
```

If this works, your wiring is correct.

### API Returns 404 for LED

**Error:** `LED 'led4' not found`

**Solution:** Configure the LED first:
```bash
curl -X POST http://localhost:8080/api/io/leds/config \
  -H "Content-Type: application/json" \
  -d '{"name": "led4", "gpio_pin": 23}'
```

Or add it to `main.py` before running.

---

## Development

### Running Tests

```bash
python test_imports.py
```

### Code Structure

The code follows these principles:
- **Separation of Concerns**: GPIO logic is separate from API logic
- **Dependency Injection**: GPIOController can be injected into the API
- **Mock Support**: Works without hardware for testing
- **Type Hints**: Full PEP 484 type annotations
- **Error Handling**: Proper HTTP status codes and error messages

### Adding New Features

To add a new endpoint:

1. Add a Pydantic model if needed (in `api_endpoint.py`)
2. Add a method to `GPIOController` if needed (in `gpio_controller.py`)
3. Add the route handler (in `api_endpoint.py`)
4. Add it to the router with proper documentation

---

## Maxson Development

### Raspberry Pi SSH Access

| Detail | Value |
|--------|-------|
| IP Address | `192.168.1.129` |
| Username | `raspberry` |
| Password | rti |

**SSH Connection:**
```bash
ssh raspberry@192.168.1.129
```

### Copy Project to Raspberry Pi (PowerShell)
To copy the `iec61850-websocket` directory from Windows to the Raspberry Pi (replacing any existing version):
```powershell
ssh raspberry@192.168.1.129 "rm -rf ~/iec61850-websocket"; scp -r .\iec61850-websocket raspberry@192.168.1.129:~/iec61850-websocket
```

**Alternative (Git Bash):**
```bash
ssh raspberry@192.168.1.129 "rm -rf ~/iec61850-websocket"
scp -r iec61850-websocket raspberry@192.168.1.129:~/iec61850-websocket
```

### Copy demo_IO Directory Only (PowerShell)
To copy just the `demo_IO` subdirectory (run from `rti_2_0_demo` directory):
```powershell
ssh raspberry@192.168.1.129 "rm -rf ~/iec61850-websocket/examples/rti-demo/demo_IO"; scp -r .\iec61850-websocket\examples\rti-demo\demo_IO raspberry@192.168.1.129:~/iec61850-websocket/examples/rti-demo/demo_IO
```

**Alternative (Git Bash):**
```bash
ssh raspberry@192.168.1.129 "rm -rf ~/iec61850-websocket/examples/rti-demo/demo_IO"
scp -r iec61850-websocket/examples/rti-demo/demo_IO raspberry@192.168.1.129:~/iec61850-websocket/examples/rti-demo/demo_IO
```

---

## License

This project is part of the RTI_DEMO project. See the main project for licensing information.

---

## Support

For issues or questions:

1. Check the **Troubleshooting** section above
2. Review the **API Endpoints** documentation
3. Test with Swagger UI first
4. Verify your hardware connections
5. Check system logs for errors

---

## Version History

- **v1.0.0** - Initial release
  - FastAPI REST API for GPIO control
  - Support for multiple LEDs
  - Mock mode for non-Pi systems
  - Swagger UI documentation
