# Raspberry Pi GPIO Pin Mapping for RTI DEMO

## Device Configuration Summary

| Device Name | Device Type | GPIO | Physical Pin | Direction | Description | Tag Name |
|-------------|-------------|------|--------------|-----------|-------------|----------|
| led1 | LED | 17 | 11 | OUTPUT | LED 1 | RTI_LED_1 |
| led2 | LED | 18 | 12 | OUTPUT | LED 2 | RTI_LED_2 |
| led3 | LED | 22 | 15 | OUTPUT | LED 3 | RTI_LED_3 |
| button1 | Button | 10 | 19 | INPUT | Button (latching, pull-up) | RTI_BTN_1 |
| pot1 | Potentiometer | - | - | INPUT | ADC Channel 0 (SPI) | RTI_POT_1 |
| lcd1 | LCD 16x2 | Multiple | Multiple | OUTPUT | HD44780 4-bit mode | RTI_LCD |

## LCD Pin Mapping (HD44780 4-bit mode)

| LCD Pin | Pin Name | Raspberry Pi GPIO | Physical Pin | Function |
|---------|----------|-------------------|--------------|----------|
| 1 | VSS | - | - | Ground (0V) |
| 2 | VDD | - | - | +5V Power |
| 3 | V0 | - | - | Contrast (via potentiometer) |
| 4 | RS | 26 | 37 | Register Select (0=Command, 1=Data) |
| 5 | RW | GND | - | Read/Write (GND = Write mode) |
| 6 | E | 19 | 35 | Enable (clock signal) |
| 7 | D0 | - | - | Not used (4-bit mode) |
| 8 | D1 | - | - | Not used (4-bit mode) |
| 9 | D2 | - | - | Not used (4-bit mode) |
| 10 | D3 | - | - | Not used (4-bit mode) |
| 11 | D4 | 13 | 33 | Data Bit 4 (MSB) |
| 12 | D5 | 12 | 32 | Data Bit 5 |
| 13 | D6 | 16 | 36 | Data Bit 6 |
| 14 | D7 | 20 | 38 | Data Bit 7 (LSB) |
| 15 | A | +5V | - | Backlight Anode |
| 16 | K | GND | - | Backlight Cathode |

## Raspberry Pi Physical Pinout (40-pin header)

```
3V3     (1) [o] [o] (2)  5V
GPIO2   (3) [o] [o] (4)  5V
GPIO3   (5) [o] [o] (6)  GND
GPIO4   (7) [o] [o] (8)  GPIO14 (TXD)
GND     (9) [o] [o] (10) GPIO15 (RXD)
GPIO17 (11) [o] [o] (12) GPIO18  <-- LED2
GPIO27 (13) [o] [o] (14) GND
GPIO22 (15) [o] [o] (16) GPIO23  <-- LED3
3V3     (17) [o] [o] (18) GPIO24
GPIO10 (19) [o] [o] (20) GND     <-- BUTTON1
GPIO9  (21) [o] [o] (22) GPIO25
GPIO11 (23) [o] [o] (24) GPIO8 (CE0)
GND    (25) [o] [o] (26) GPIO7 (CE1)

GPIO0  (27) [o] [o] (28) GPIO1
GPIO5  (29) [o] [o] (30) GND
GPIO6  (31) [o] [o] (32) GPIO12  <-- LCD D5
GPIO13 (33) [o] [o] (34) GND      <-- LCD D4
GPIO19 (35) [o] [o] (36) GPIO16  <-- LCD E
GPIO26 (37) [o] [o] (38) GPIO20  <-- LCD D6
GND    (39) [o] [o] (40) GPIO21
```

## Wiring Connections

### LEDs (Active High)
- **LED1**: GPIO 17 (Pin 11) -> LED anode -> Resistor (220-470R) -> GND
- **LED2**: GPIO 18 (Pin 12) -> LED anode -> Resistor (220-470R) -> GND
- **LED3**: GPIO 22 (Pin 15) -> LED anode -> Resistor (220-470R) -> GND

### Button
- **BUTTON1**: GPIO 10 (Pin 19) -> Button -> GND (pull-up enabled in software)

### Potentiometer (Contrast Control)
- **POT1**: Connect to LCD V0 pin (Pin 3)
  - Potentiometer center wiper -> LCD V0
  - Potentiometer ends -> +5V and GND

### LCD 16x2 (HD44780 Controller)

#### Control Lines:
- **RS (Register Select)**: GPIO 26 (Pin 37) -> LCD Pin 4
- **RW (Read/Write)**: GND -> LCD Pin 5 (hardwired to write mode)
- **E (Enable)**: GPIO 19 (Pin 35) -> LCD Pin 6

#### Data Lines (4-bit mode):
- **D4**: GPIO 13 (Pin 33) -> LCD Pin 11
- **D5**: GPIO 12 (Pin 32) -> LCD Pin 12
- **D6**: GPIO 16 (Pin 36) -> LCD Pin 13
- **D7**: GPIO 20 (Pin 38) -> LCD Pin 14

#### Power:
- **VDD (5V)**: +5V -> LCD Pin 2
- **VSS (GND)**: GND -> LCD Pin 1
- **V0 (Contrast)**: Potentiometer center -> LCD Pin 3

#### Backlight:
- **A (Anode)**: +5V -> LCD Pin 15
- **K (Cathode)**: GND -> LCD Pin 16

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/io/health` | GET | Health check |
| `/api/io/status` | GET | Get all device states |
| `/api/io/{device_name}` | GET | Get device state |
| `/api/io/{device_name}` | POST | Set device state |
| `/api/io/led/{name}/on` | POST | Turn LED on |
| `/api/io/led/{name}/off` | POST | Turn LED off |
| `/api/io/led/{name}/toggle` | POST | Toggle LED |
| `/api/io/led/all/on` | POST | Turn all LEDs on |
| `/api/io/led/all/off` | POST | Turn all LEDs off |
| `/api/io/lcd/{name}/write` | POST | Write text to LCD (accepts `{"text": ["line1", "line2"]}`) |
| `/api/io/lcd/{name}/clear` | POST | Clear LCD |
| `/api/io/button/{name}/reset` | POST | Reset latching button |

## Tag Naming Convention

For industrial control systems, use the following tag names:

- **LEDs**: `RTI_LED_1`, `RTI_LED_2`, `RTI_LED_3`
- **Button**: `RTI_BTN_1`
- **Potentiometer**: `RTI_POT_1` (for contrast control)
- **LCD**: `RTI_LCD` (for display content)

## Startup Behavior

On system startup:
1. All LEDs blink 3 times (0.3s on, 0.3s off) for visual confirmation
2. LCD displays "RTI" on line 1 and "DEMO" on line 2
3. IO controller initializes all configured devices
4. API server starts on port 8000

## GPIO Chip Information

The system uses `/dev/gpiochip0` for GPIO access via gpiod library.

Available GPIO chips in Docker:
- `/dev/gpiochip0` - Main GPIO chip (pins 0-53)
- `/dev/gpiochip4` - Additional chip
- `/dev/gpiochip10-13` - Additional chips

## Troubleshooting

### LCD Not Displaying
1. **Check contrast**: Adjust potentiometer connected to V0 pin
2. **Check backlight**: Verify +5V and GND on pins 15 and 16
3. **Check wiring**: Ensure all data and control lines are connected correctly
4. **Check initialization**: Look for "LCD DEBUG" messages in logs
5. **Verify commands**: Commands should include: 0x28, 0x0C, 0x01, 0x02, 0x06

### LEDs Not Working
1. **Check polarity**: LEDs are active high (GPIO HIGH = LED ON)
2. **Check resistors**: 220-470 ohm current limiting resistors required
3. **Check GND**: LEDs must have common ground

### Button Not Working
1. **Check pull-up**: Button uses internal pull-up (GPIO 10)
2. **Check wiring**: Button connects between GPIO 10 and GND
3. **Check debounce**: 50ms debounce time configured
