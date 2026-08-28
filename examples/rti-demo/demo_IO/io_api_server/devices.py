"""
IO Devices Module - Base classes and implementations for various IO devices.

This module provides a hierarchy of IO device classes that support:
- LEDs (digital output)
- Potentiometers (analog input)
- Buttons (digital input)
- PWM outputs (analog output)
- DACs (digital-to-analog)

All devices implement a common interface for read/write operations,
allowing the IOController to manage them uniformly.

Usage:
    from devices import IODevice, LEDDevice, PotentiometerDevice, DeviceConfig
    
    # Create a device config
    led_config = LEDConfig(name="led1", gpio_pin=17, initial_state=False)
    
    # Create the device
    led = LEDDevice(led_config)
    led.write(True)  # Turn on
    state = led.read()  # Get state
"""

from __future__ import annotations

import logging
import time
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

# Import gpiod at module level for new API
try:
    import gpiod
    GPOD_AVAILABLE = True
except ImportError:
    GPOD_AVAILABLE = False

# Import smbus2 at module level for I2C LCD
try:
    import smbus2
    SMBUS2_AVAILABLE = True
except ImportError:
    SMBUS2_AVAILABLE = False

logger = logging.getLogger(__name__)


# ==================== ENUMS ====================

class DeviceType(Enum):
    """Supported IO device types."""
    LED = "led"              # Digital output (on/off)
    POTENTIOMETER = "potentiometer"  # Analog input (variable resistance)
    BUTTON = "button"        # Digital input (pressed/released)
    PWM = "pwm"              # Pulse-width modulation output
    DAC = "dac"              # Digital-to-analog converter
    RELAY = "relay"          # Relay switch
    BUZZER = "buzzer"        # Buzzer/speaker
    SENSOR = "sensor"        # Generic sensor
    LCD = "lcd"              # LCD display (HD44780 controller)
    LCD_I2C = "lcd_i2c"      # LCD display (HD44780 with I2C backpack)


class DeviceDirection(Enum):
    """Device data flow direction."""
    INPUT = "input"
    OUTPUT = "output"
    BIDIRECTIONAL = "bidirectional"


# ==================== CONFIGURATION CLASSES ====================

@dataclass
class DeviceConfig:
    """Base configuration for any IO device."""
    name: str
    device_type: DeviceType
    identifier: Union[int, str] = 0
    description: str = ""
    direction: DeviceDirection = DeviceDirection.OUTPUT
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary for serialization."""
        return {
            "name": self.name,
            "device_type": self.device_type.value,
            "identifier": self.identifier,
            "description": self.description,
            "direction": self.direction.value,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeviceConfig":
        """Create config from dictionary."""
        return cls(
            name=data.get("name", ""),
            device_type=DeviceType(data.get("device_type", "led")),
            identifier=data.get("identifier", 0),
            description=data.get("description", ""),
            direction=DeviceDirection(data.get("direction", "output")),
        )


@dataclass
class DigitalDeviceConfig(DeviceConfig):
    """Configuration for digital IO devices (LEDs, buttons, relays)."""
    gpio_pin: int = field(default=0)
    initial_state: bool = False
    is_active_high: bool = True
    
    def __post_init__(self):
        if self.identifier == 0 and self.gpio_pin != 0:
            self.identifier = self.gpio_pin
    
    def to_dict(self) -> Dict[str, Any]:
        result = super().to_dict()
        result.update({
            "gpio_pin": self.gpio_pin,
            "initial_state": self.initial_state,
            "is_active_high": self.is_active_high,
        })
        return result


@dataclass
class LEDConfig(DigitalDeviceConfig):
    """Configuration for LED devices."""
    device_type: DeviceType = field(default=DeviceType.LED, init=False)
    direction: DeviceDirection = field(default=DeviceDirection.OUTPUT, init=False)
    brightness: float = 1.0


@dataclass
class PotentiometerConfig(DeviceConfig):
    """Configuration for potentiometer (analog input) devices."""
    device_type: DeviceType = field(default=DeviceType.POTENTIOMETER, init=False)
    adc_channel: int = 0
    adc_reference_voltage: float = 3.3
    min_value: float = 0.0
    max_value: float = 100.0
    is_inverted: bool = False
    
    def __post_init__(self):
        if self.identifier == 0 and self.adc_channel != 0:
            self.identifier = self.adc_channel
        self.direction = DeviceDirection.INPUT
    
    def to_dict(self) -> Dict[str, Any]:
        result = super().to_dict()
        result.update({
            "adc_channel": self.adc_channel,
            "adc_reference_voltage": self.adc_reference_voltage,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "is_inverted": self.is_inverted,
        })
        return result


@dataclass
class LCDConfig(DeviceConfig):
    """Configuration for LCD display devices with HD44780 controller."""
    device_type: DeviceType = field(default=DeviceType.LCD, init=False)
    direction: DeviceDirection = field(default=DeviceDirection.OUTPUT, init=False)
    # GPIO pins for HD44780 in 4-bit mode
    gpio_rs: int = 26
    gpio_e: int = 19
    gpio_data: List[int] = field(default_factory=lambda: [13, 12, 16, 20])  # D4, D5, D6, D7
    gpio_rw: Optional[int] = None  # RW pin (optional, tie to GND if not used)
    columns: int = 16
    rows: int = 2
    backlight: bool = True
    backlight_pin: Optional[int] = None  # Optional backlight control pin
    
    def __post_init__(self):
        self.direction = DeviceDirection.OUTPUT
        
    def to_dict(self) -> Dict[str, Any]:
        result = super().to_dict()
        result.update({
            "gpio_rs": self.gpio_rs,
            "gpio_e": self.gpio_e,
            "gpio_data": self.gpio_data,
            "gpio_rw": self.gpio_rw,
            "columns": self.columns,
            "rows": self.rows,
            "backlight": self.backlight,
            "backlight_pin": self.backlight_pin,
        })
        return result


@dataclass
class LCDI2CConfig(DeviceConfig):
    """Configuration for LCD display devices with I2C backpack (PCF8574, etc.)."""
    device_type: DeviceType = field(default=DeviceType.LCD_I2C, init=False)
    direction: DeviceDirection = field(default=DeviceDirection.OUTPUT, init=False)
    # I2C configuration
    i2c_address: int = 0x27  # Common addresses: 0x27, 0x3F for PCF8574 backpacks
    i2c_bus: int = 1        # Raspberry Pi I2C bus (usually 1)
    columns: int = 16
    rows: int = 2
    backlight: bool = True
    # PCF8574 pin mapping (bit positions in the I2C byte)
    # Typically: P0=RS, P1=RW, P2=E, P3=BL, P4=D4, P5=D5, P6=D6, P7=D7
    # These can be customized if backpack uses different mapping
    rs_bit: int = 0
    rw_bit: int = 1
    e_bit: int = 2
    backlight_bit: int = 3
    d4_bit: int = 4
    d5_bit: int = 5
    d6_bit: int = 6
    d7_bit: int = 7
    
    def __post_init__(self):
        self.direction = DeviceDirection.OUTPUT
        
    def to_dict(self) -> Dict[str, Any]:
        result = super().to_dict()
        result.update({
            "i2c_address": self.i2c_address,
            "i2c_bus": self.i2c_bus,
            "columns": self.columns,
            "rows": self.rows,
            "backlight": self.backlight,
            "rs_bit": self.rs_bit,
            "rw_bit": self.rw_bit,
            "e_bit": self.e_bit,
            "backlight_bit": self.backlight_bit,
            "d4_bit": self.d4_bit,
            "d5_bit": self.d5_bit,
            "d6_bit": self.d6_bit,
            "d7_bit": self.d7_bit,
        })
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LCDI2CConfig":
        """Create config from dictionary, handling device_type properly."""
        return cls(
            name=data.get("name", ""),
            identifier=data.get("identifier", 0),
            description=data.get("description", ""),
            i2c_address=data.get("i2c_address", 0x27),
            i2c_bus=data.get("i2c_bus", 1),
            columns=data.get("columns", 16),
            rows=data.get("rows", 2),
            backlight=data.get("backlight", True),
            rs_bit=data.get("rs_bit", 0),
            rw_bit=data.get("rw_bit", 1),
            e_bit=data.get("e_bit", 2),
            backlight_bit=data.get("backlight_bit", 3),
            d4_bit=data.get("d4_bit", 4),
            d5_bit=data.get("d5_bit", 5),
            d6_bit=data.get("d6_bit", 6),
            d7_bit=data.get("d7_bit", 7),
        )


@dataclass
class ButtonConfig(DigitalDeviceConfig):
    """Configuration for button (digital input) devices."""
    device_type: DeviceType = field(default=DeviceType.BUTTON, init=False)
    direction: DeviceDirection = field(default=DeviceDirection.INPUT, init=False)
    debounce_time: float = 0.05
    pull_up: bool = True
    latching: bool = False


@dataclass
class PWMConfig(DigitalDeviceConfig):
    """Configuration for PWM (pulse-width modulation) output devices."""
    device_type: DeviceType = field(default=DeviceType.PWM, init=False)
    frequency: int = 1000
    duty_cycle: float = 0.0


# ==================== BASE DEVICE CLASS ====================

class IODevice(ABC):
    """
    Abstract base class for all IO devices.
    
    All IO devices must implement:
    - read() - Read the current value from the device
    - write(value) - Write a value to the device
    - close() - Clean up resources
    """
    
    config: DeviceConfig
    
    @abstractmethod
    def read(self) -> Optional[Union[bool, float]]:
        pass
    
    @abstractmethod
    def write(self, value: Union[bool, float]) -> bool:
        pass
    
    @abstractmethod
    def close(self) -> None:
        pass
    
    @property
    @abstractmethod
    def is_connected(self) -> bool:
        pass
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.config.name}, type={self.config.device_type.value})"


# ==================== GPIOD 2.x WRAPPER FOR LED ====================

class _GpioZeroLED:
    """Internal wrapper for LED using gpiod 2.x API."""

    def __init__(self, gpio_pin: int, active_high: bool = True, initial_value: bool = False):
        self._lines = None
        self._chip = None
        self._gpio_pin = gpio_pin
        self._active_high = active_high

        if not GPOD_AVAILABLE:
            raise RuntimeError(f"gpiod library not available. LED requires GPIO hardware.")

        try:
            self._chip = gpiod.Chip('/dev/gpiochip0')
            direction = gpiod.line_settings.Direction.OUTPUT
            active_low = not active_high
            initial_val = gpiod.line.Value.ACTIVE if initial_value else gpiod.line.Value.INACTIVE
            settings = gpiod.line_settings.LineSettings(
                direction=direction,
                active_low=active_low,
                output_value=initial_val
            )
            self._lines = self._chip.request_lines({gpio_pin: settings})
            logger.info(f"Initialized gpiod LED on GPIO {gpio_pin}")
        except Exception as e:
            raise RuntimeError(f"GPIO {gpio_pin} unavailable: {e}. LED requires GPIO hardware.")

    @property
    def value(self) -> bool:
        try:
            values = self._lines.get_values([self._gpio_pin])
            raw = values[0]
            return raw == gpiod.line.Value.ACTIVE
        except Exception as e:
            raise RuntimeError(f"Failed to read LED {self._gpio_pin}: {e}")

    @value.setter
    def value(self, val: bool) -> None:
        try:
            target = gpiod.line.Value.ACTIVE if val else gpiod.line.Value.INACTIVE
            self._lines.set_values({self._gpio_pin: target})
        except Exception as e:
            raise RuntimeError(f"Failed to write LED {self._gpio_pin}: {e}")

    def on(self) -> None:
        self.value = True

    def off(self) -> None:
        self.value = False

    def toggle(self) -> None:
        self.value = not self.value

    def close(self) -> None:
        if self._lines:
            try:
                self._lines.release()
            except Exception:
                pass
            self._lines = None
        if self._chip:
            try:
                self._chip.close()
            except Exception:
                pass
            self._chip = None


# ==================== GPIOD 2.x WRAPPER FOR BUTTON ====================

class _GpioZeroButton:
    """Internal wrapper for Button using gpiod 2.x API."""

    def __init__(self, gpio_pin: int, pull_up: bool = True, bounce_time: float = 0.05, active_high: bool = True):
        self._lines = None
        self._chip = None
        self._gpio_pin = gpio_pin
        self._active_high = active_high
        self._bounce_time = bounce_time
        self._pull_up = pull_up
        self._last_read_time = 0
        self._last_read_value = False

        if not GPOD_AVAILABLE:
            raise RuntimeError(f"gpiod library not available. Button requires GPIO hardware.")

        try:
            self._chip = gpiod.Chip('/dev/gpiochip0')
            direction = gpiod.line_settings.Direction.INPUT
            active_low = not active_high
            bias = gpiod.line_settings.Bias.PULL_UP if pull_up else gpiod.line_settings.Bias.PULL_DOWN
            settings = gpiod.line_settings.LineSettings(
                direction=direction,
                active_low=active_low,
                bias=bias,
                edge_detection=gpiod.line_settings.Edge.BOTH
            )
            self._lines = self._chip.request_lines({gpio_pin: settings})
            logger.info(f"Initialized gpiod Button on GPIO {gpio_pin}")
        except Exception as e:
            raise RuntimeError(f"GPIO {gpio_pin} unavailable: {e}. Button requires GPIO hardware.")

    @property
    def is_pressed(self) -> bool:
        try:
            import time
            current_time = time.time()
            # Simple debounce
            if current_time - self._last_read_time < self._bounce_time:
                return self._last_read_value
            values = self._lines.get_values([self._gpio_pin])
            raw = values[0]
            state = raw == gpiod.line.Value.ACTIVE
            self._last_read_time = current_time
            self._last_read_value = state
            return state
        except Exception as e:
            raise RuntimeError(f"Failed to read Button {self._gpio_pin}: {e}")

    def close(self) -> None:
        if self._lines:
            try:
                self._lines.release()
            except Exception:
                pass
            self._lines = None
        if self._chip:
            try:
                self._chip.close()
            except Exception:
                pass
            self._chip = None


# ==================== INPUT DEVICE BASE CLASS WITH EDGE DETECTION ====================

class InputDevice(IODevice):
    """
    Base class for input devices with edge/change detection support.
    
    Provides:
    - Callback-based edge detection for hardware that supports it (gpiozero)
    - Polling-based edge detection for devices that don't support interrupts
    - Unified interface for all input device types
    """
    
    def __init__(self, config: DeviceConfig):
        self.config = config
        self._hardware_available = False
        self._value_history: List[Optional[Union[bool, float]]] = []
        self._change_callbacks: List[Callable[[Any, Any], None]] = []
        self._monitoring_thread = None
        self._stop_monitoring = False
        self._last_reported_value = None
        self._poll_threshold = None
    
    def register_change_callback(self, callback: callable) -> None:
        """Register a callback to be called when the input value changes."""
        self._change_callbacks.append(callback)
    
    def clear_change_callbacks(self) -> None:
        """Clear all registered change callbacks."""
        self._change_callbacks = []
        logger.debug(f"Cleared all change callbacks for {self.config.name}")
    
    def _notify_change(self, old_value: Any, new_value: Any) -> None:
        """Notify all registered callbacks of a value change."""
        # Sync to ACSI server if mapping exists
        from io_controller import sync_device_to_acsi
        sync_device_to_acsi(self.config.name, new_value)
        
        # Notify registered callbacks
        for callback in self._change_callbacks:
            try:
                callback(old_value, new_value)
            except Exception as e:
                logger.warning(f"Error in change callback: {e}")
    
    def _start_polling_monitor(self, poll_interval: float = 0.1, threshold: Optional[float] = None) -> None:
        """Start a background thread to monitor for value changes (for devices without hardware interrupts).
        
        Args:
            poll_interval: Time between polls in seconds
            threshold: Minimum change required to trigger notification (for analog values)
        """
        if self._monitoring_thread is not None:
            return
        
        self._stop_monitoring = False
        self._poll_threshold = threshold
        import threading
        
        def monitor_loop():
            import time
            while not self._stop_monitoring:
                current_value = self.read()
                if current_value is not None:
                    # For analog values, check if change exceeds threshold
                    if self._poll_threshold is not None and isinstance(current_value, (int, float)):
                        if self._last_reported_value is not None and isinstance(self._last_reported_value, (int, float)):
                            if abs(current_value - self._last_reported_value) >= self._poll_threshold:
                                old_value = self._last_reported_value
                                self._last_reported_value = current_value
                                self._notify_change(old_value, current_value)
                        elif self._last_reported_value is None:
                            # First read
                            self._last_reported_value = current_value
                    # For digital/boolean values or no threshold, check for any change
                    elif current_value != self._last_reported_value:
                        old_value = self._last_reported_value
                        self._last_reported_value = current_value
                        self._notify_change(old_value, current_value)
                time.sleep(poll_interval)
        
        self._monitoring_thread = threading.Thread(target=monitor_loop, daemon=True)
        self._monitoring_thread.start()
    
    def _stop_polling_monitor(self) -> None:
        """Stop the background monitoring thread."""
        self._stop_monitoring = True
        if self._monitoring_thread is not None:
            self._monitoring_thread.join(timeout=1.0)
            self._monitoring_thread = None
    
    @property
    def is_connected(self) -> bool:
        """Check if the device is connected and operational."""
        return self._hardware_available
    
    def close(self) -> None:
        """Clean up resources including monitoring thread."""
        self._stop_polling_monitor()


# ==================== HARDWARE DEVICE IMPLEMENTATIONS ====================

class LEDDevice(IODevice):
    """
    LED device implementation using gpiod 2.x for hardware control.
    Requires GPIO hardware.
    """
    
    def __init__(self, config: LEDConfig):
        self.config = config
        self._gpiozero_led = _GpioZeroLED(
            gpio_pin=config.gpio_pin,
            active_high=config.is_active_high,
            initial_value=config.initial_state
        )
        logger.info(f"Initialized LED device '{config.name}' on GPIO {config.gpio_pin}")
    
    def read(self) -> Optional[bool]:
        """Read the current LED state."""
        return self._gpiozero_led.value
    
    def write(self, value: Union[bool, float]) -> bool:
        """Set the LED state (True=ON, False=OFF)."""
        state = bool(value)
        self._gpiozero_led.value = state
        return True
    
    def close(self) -> None:
        """Clean up GPIO resources."""
        self._gpiozero_led.close()
    
    @property
    def is_connected(self) -> bool:
        return True
    
    def toggle(self) -> Optional[bool]:
        """Toggle the LED state and return new state."""
        self._gpiozero_led.toggle()
        return self.read()


class PotentiometerDevice(InputDevice):
    """
    Potentiometer (analog input) device implementation.
    
    Reads analog values from an ADC (Analog-to-Digital Converter).
    Requires ADC hardware.
    
    Supports change detection via polling for value changes.
    """
    
    ADC_MCP3008 = "mcp3008"
    ADC_ADS1115 = "ads1115"
    
    def __init__(self, config: PotentiometerConfig):
        super().__init__(config)
        self._adc = None
        self._spi = None
        self._adc_type = None
        self._channel = 0
        self._value_change_threshold = 0.01  # 1% change to trigger callback
        self._mock_value = 0.5  # Default midpoint value for mock mode
        self._init_hardware()
        if not self._hardware_available:
            logger.warning(f"ADC not available for potentiometer '{config.name}'. Using mock mode.")
            self._hardware_available = True  # Allow operation in mock mode
        # Start polling-based change detection for analog inputs
        # Uses threshold to avoid noise-triggered false changes
        self._start_polling_monitor(poll_interval=0.2, threshold=self._value_change_threshold)
    
    def _init_hardware(self) -> None:
        try:
            try:
                import spidev
                import RPi.GPIO as GPIO
                self._spi = spidev.SpiDev()
                self._spi.open(0, 0)
                self._spi.max_speed_hz = 1000000
                self._adc_type = self.ADC_MCP3008
                self._channel = self.config.adc_channel
                self._hardware_available = True
                logger.info(f"Initialized potentiometer '{self.config.name}' on ADC channel {self.config.adc_channel}")
                return
            except (ImportError, AttributeError, OSError):
                try:
                    import Adafruit_ADS1x15
                    self._adc = Adafruit_ADS1x15.ADS1115()
                    self._adc_type = self.ADC_ADS1115
                    self._channel = self.config.adc_channel
                    self._hardware_available = True
                    logger.info(f"Initialized potentiometer '{self.config.name}' on ADS1115 channel {self.config.adc_channel}")
                    return
                except (ImportError, AttributeError, OSError):
                    pass
        except Exception as e:
            logger.debug(f"ADC initialization failed: {e}")
        self._hardware_available = False
    
    def _read_mcp3008(self, channel: int) -> int:
        if not self._spi:
            return 0
        cmd = 0b11 << 6
        cmd |= (channel & 0x07) << 3
        adc = self._spi.xfer2([cmd, 0, 0])
        data = ((adc[1] & 0x03) << 8) | adc[2]
        return data
    
    def _read_ads1115(self, channel: int) -> int:
        if not self._adc:
            return 0
        return self._adc.read_adc(channel, gain=1)
    
    def read(self) -> Optional[float]:
        if not self.is_connected:
            return None
        try:
            if self._adc_type == self.ADC_MCP3008:
                raw = self._read_mcp3008(self._channel)
                max_value = 1023
            elif self._adc_type == self.ADC_ADS1115:
                raw = self._read_ads1115(self._channel)
                max_value = 32767
            elif self._adc_type is None:
                # Mock mode - return stored mock value
                return self._mock_value
            else:
                return None
            normalized = max(0, min(1, raw / max_value))
            if self.config.is_inverted:
                normalized = 1.0 - normalized
            return normalized
        except Exception as e:
            logger.warning(f"Failed to read potentiometer '{self.config.name}': {e}")
            return self._mock_value
    
    def read_scaled(self) -> Optional[float]:
        normalized = self.read()
        if normalized is None:
            return None
        return self.config.min_value + normalized * (self.config.max_value - self.config.min_value)
    
    def write(self, value: Union[bool, float]) -> bool:
        # In mock mode, allow setting the value for testing
        if self._adc_type is None:
            self._mock_value = float(value)
            return True
        logger.warning(f"Cannot write to read-only potentiometer '{self.config.name}'")
        return False
    
    def close(self) -> None:
        # Stop monitoring thread
        super().close()
        # Clean up hardware
        if self._spi:
            try:
                self._spi.close()
            except Exception:
                pass
        self._spi = None
        self._adc = None


class ButtonDevice(InputDevice):
    """
    Button (digital input) device implementation.
    Requires GPIO hardware.
    
    When latching=True, the button toggles its state on each press (rising edge)
    and maintains that state even after release. This is useful for momentary
    buttons that should act like toggle switches.
    
    Supports:
    - Polling-based edge detection (via gpiod 2.x)
    - Change detection callbacks
    """
    
    def __init__(self, config: ButtonConfig):
        super().__init__(config)
        self._last_read_time = 0
        self._last_read_value = False
        self._latched_state = False
        self._previous_physical_state = False
        self._gpiozero_button = None
        self._active_high = config.is_active_high
        
        try:
            self._gpiozero_button = _GpioZeroButton(
                gpio_pin=config.gpio_pin,
                pull_up=config.pull_up,
                bounce_time=config.debounce_time,
                active_high=config.is_active_high
            )
            self._hardware_available = True
            
            # === Edge Detection Callbacks ===
            # With gpiod 2.x, we use polling-based edge detection since it doesn't support interrupts
            # For latching buttons, use custom polling that reads physical state
            if config.latching:
                self._start_latching_polling(poll_interval=0.05)
            else:
                # For non-latching buttons, use base class polling
                self._start_polling_monitor(poll_interval=0.05)
            
            # Initialize previous state to current physical state
            if self._hardware_available:
                try:
                    import time
                    time.sleep(0.1)
                    raw_value = self._gpiozero_button.is_pressed
                    if self.config.is_active_high:
                        self._previous_physical_state = raw_value
                        self._last_reported_value = raw_value if config.latching else None
                    else:
                        self._previous_physical_state = not raw_value
                        self._last_reported_value = not raw_value if config.latching else None
                except Exception:
                    self._previous_physical_state = False
                    self._last_reported_value = None
            
            logger.info(f"Initialized button '{config.name}' on GPIO {config.gpio_pin}" + 
                       (" (latching)" if config.latching else ""))
        except Exception as e:
            raise RuntimeError(f"Hardware not available for button '{config.name}': {e}. Button requires GPIO hardware.")
    
    def _read_physical_raw(self) -> Optional[bool]:
        """Read the raw physical state directly from hardware without debounce caching.
        
        This is used for latching mode edge detection where we need to see
        actual state transitions, not debounced values.
        """
        if not self.is_connected:
            return None
        try:
            return self._gpiozero_button.is_pressed
        except Exception as e:
            logger.warning(f"Failed to read button '{self.config.name}': {e}")
            return None
    
    def _get_physical_state(self) -> Optional[bool]:
        """Read the actual physical state of the button (pressed/released) with debounce."""
        if not self.is_connected:
            return None
        try:
            import time
            current_time = time.time()
            if current_time - self._last_read_time < self.config.debounce_time:
                return self._last_read_value
            state = self._gpiozero_button.is_pressed
            self._last_read_time = current_time
            self._last_read_value = state
            return state
        except Exception as e:
            logger.warning(f"Failed to read button '{self.config.name}': {e}")
            return None
    
    def _start_latching_polling(self, poll_interval: float = 0.05) -> None:
        """Start polling for latching button edge detection."""
        self._stop_monitoring = False
        import threading

        def monitor():
            last_physical = self._read_physical_raw()
            while not self._stop_monitoring:
                current_physical = self._read_physical_raw()
                if current_physical is not None and last_physical is not None:
                    if current_physical and not last_physical:
                        # Rising edge: toggle latched state
                        old = self._latched_state
                        self._latched_state = not self._latched_state
                        self._notify_change(old, self._latched_state)
                last_physical = current_physical
                time.sleep(poll_interval)

        self._monitoring_thread = threading.Thread(target=monitor, daemon=True)
        self._monitoring_thread.start()
    
    def read(self) -> Optional[bool]:
        """Read button state.
        
        If latching=True: returns the latched state (toggles on press via callback)
        If latching=False: returns the current physical state (True=pressed, False=released)
        """
        if self.config.latching:
            # For gpiozero with callbacks, latched state is updated automatically
            # For gpiod, we detect edges via polling in _start_polling_monitor
            return self._latched_state
        else:
            # Normal mode: use debounced reading
            return self._get_physical_state()
    
    def reset_latch(self) -> None:
        """Reset latched state to False (for latching buttons)."""
        self._latched_state = False
        logger.info(f"Reset latched state for button '{self.config.name}'")
    
    def write(self, value: Union[bool, float]) -> bool:
        logger.warning(f"Cannot write to read-only button '{self.config.name}'")
        return False
    
    def close(self) -> None:
        # Stop monitoring thread
        super().close()
        # Clean up button
        if self._gpiozero_button:
            try:
                self._gpiozero_button.close()
            except Exception as e:
                logger.warning(f"Failed to release button '{self.config.name}': {e}")


class LCDDevice(IODevice):
    """
    LCD display device implementation for HD44780 controller (16x2, 20x4, etc.).
    
    Uses GPIO in 4-bit mode for communication with the HD44780 controller.
    Supports writing text to the display, clearing, and cursor positioning.
    Requires GPIO hardware (RPi.GPIO or gpiod).
    """
    
    LCD_CLEARDISPLAY = 0x01
    LCD_RETURNHOME = 0x02
    LCD_ENTRYMODESET = 0x04
    LCD_DISPLAYCONTROL = 0x08
    LCD_CURSORSHIFT = 0x10
    LCD_FUNCTIONSET = 0x20
    LCD_SETCGRAMADDR = 0x40
    LCD_SETDDRAMADDR = 0x80
    
    LCD_ENTRYRIGHT = 0x00
    LCD_ENTRYLEFT = 0x02
    LCD_ENTRYSHIFTINCREMENT = 0x01
    LCD_ENTRYSHIFTDECREMENT = 0x00
    
    LCD_DISPLAYON = 0x04
    LCD_DISPLAYOFF = 0x00
    LCD_CURSORON = 0x02
    LCD_CURSOROFF = 0x00
    LCD_BLINKON = 0x01
    LCD_BLINKOFF = 0x00
    
    LCD_DISPLAYMOVE = 0x08
    LCD_CURSORMOVE = 0x00
    LCD_MOVERIGHT = 0x04
    LCD_MOVELEFT = 0x00
    
    LCD_8BITMODE = 0x10
    LCD_4BITMODE = 0x00
    LCD_2LINE = 0x08
    LCD_1LINE = 0x00
    LCD_5x10DOTS = 0x04
    LCD_5x8DOTS = 0x00
    
    def __init__(self, config: LCDConfig):
        self.config = config
        self._gpio_rs = config.gpio_rs
        self._gpio_e = config.gpio_e
        self._gpio_data = config.gpio_data
        self._gpio_rw = config.gpio_rw
        self._columns = config.columns
        self._rows = config.rows
        self._backlight = config.backlight
        self._backlight_pin = config.backlight_pin
        
        self._hardware_available = False
        self._gpio_chip = None
        self._gpio_lines = {}
        self._display_function = 0
        self._display_control = 0
        self._display_mode = 0
        
        self._init_hardware()
        if self._hardware_available:
            self._initialize_display()
            logger.info(f"Initialized LCD device '{config.name}' ({config.columns}x{config.rows}) on GPIO RS={config.gpio_rs}, E={config.gpio_e}, D4-D7={config.gpio_data}")
        else:
            logger.warning(f"GPIO hardware not available for LCD '{config.name}'. Using mock mode.")
    
    def _init_hardware(self) -> None:
        """Initialize GPIO hardware for LCD."""
        try:
            if not GPOD_AVAILABLE:
                raise RuntimeError("gpiod library not available")
            
            self._gpio_chip = gpiod.Chip('/dev/gpiochip0')
            
            output_pins = [self._gpio_rs, self._gpio_e] + self._gpio_data
            if self._gpio_rw is not None:
                output_pins.append(self._gpio_rw)
            if self._backlight_pin is not None:
                output_pins.append(self._backlight_pin)
            
            settings = gpiod.line_settings.LineSettings(
                direction=gpiod.line_settings.Direction.OUTPUT,
                active_low=False,
                output_value=gpiod.line.Value.INACTIVE
            )
            
            all_pins = set(output_pins)
            self._gpio_lines = self._gpio_chip.request_lines({pin: settings for pin in all_pins})
            
            if self._backlight_pin is not None:
                self._set_backlight(self._backlight)
            
            self._hardware_available = True
            
        except Exception as e:
            logger.debug(f"LCD hardware initialization failed: {e}")
            self._hardware_available = False
    
    def _set_backlight(self, state: bool) -> None:
        """Set the backlight on/off."""
        if self._backlight_pin is not None and self._hardware_available:
            try:
                value = gpiod.line.Value.ACTIVE if state else gpiod.line.Value.INACTIVE
                self._gpio_lines.set_values({self._backlight_pin: value})
            except Exception as e:
                logger.warning(f"Failed to set backlight: {e}")
    
    def _pulse_enable(self) -> None:
        """Pulse the enable pin to latch data. HD44780 requires >450ns pulse."""
        if not self._hardware_available:
            return
        try:
            self._gpio_lines.set_values({self._gpio_e: gpiod.line.Value.ACTIVE})
            time.sleep(0.000005)   # 5 microseconds (was 1us - too short)
            self._gpio_lines.set_values({self._gpio_e: gpiod.line.Value.INACTIVE})
            time.sleep(0.000050)   # 50 microseconds (was 45us)
        except Exception as e:
            logger.warning(f"Failed to pulse enable: {e}")
    
    def _write4bits(self, value: int) -> None:
        """Write 4 bits to the data lines.
        
        GPIO data pins are mapped as:
        - Pin 0 (GPIO 13) = D4 (LSB)
        - Pin 1 (GPIO 12) = D5
        - Pin 2 (GPIO 16) = D6
        - Pin 3 (GPIO 20) = D7 (MSB)
        
        So bit i of the nibble goes to pin i, which is D(i+4).
        """
        if not self._hardware_available:
            return
        try:
            pin_values = {}
            for i, pin in enumerate(self._gpio_data):
                bit = (value >> i) & 0x01
                pin_values[pin] = gpiod.line.Value.ACTIVE if bit else gpiod.line.Value.INACTIVE
            self._gpio_lines.set_values(pin_values)
        except Exception as e:
            logger.warning(f"Failed to write 4 bits: {e}")
    
    def _send_byte(self, value: int, mode: int) -> None:
        """Send a byte to the LCD in 4-bit mode."""
        if not self._hardware_available:
            return
        
        try:
            mode_str = "DATA" if mode else "COMMAND"
            logger.info(f"[LCD SEND] {mode_str} 0x{value:02X} ({value})")
            rs_value = gpiod.line.Value.ACTIVE if mode else gpiod.line.Value.INACTIVE
            self._gpio_lines.set_values({self._gpio_rs: rs_value})
            
            high = value >> 4
            self._write4bits(high)
            logger.info(f"[LCD SEND] High nibble: 0x{high:01X}")
            self._pulse_enable()
            
            low = value & 0x0F
            self._write4bits(low)
            logger.info(f"[LCD SEND] Low nibble: 0x{low:01X}")
            self._pulse_enable()
            
            self._gpio_lines.set_values({self._gpio_rs: gpiod.line.Value.INACTIVE})
            logger.info(f"[LCD SEND] RS reset to LOW")
        except Exception as e:
            logger.warning(f"Failed to send byte: {e}")
    
    def _initialize_display(self) -> None:
        """Initialize the LCD with proper HD44780 timing."""
        if not self._hardware_available:
            return
        
        try:
            time.sleep(0.05)  # Wait 50ms for power-on

            # Set all control pins low initially
            self._gpio_lines.set_values({
                self._gpio_rs: gpiod.line.Value.INACTIVE,
                self._gpio_e: gpiod.line.Value.INACTIVE
            })

            # D4-D7 must be 0 for init
            self._write4bits(0b0000)

            # Initialization sequence for 4-bit mode
            # First: Try 8-bit mode 3 times
            self._write4bits(0b0011)  # 0x30 - Function set (8-bit)
            self._pulse_enable()
            time.sleep(0.005)  # 5ms

            self._pulse_enable()
            time.sleep(0.001)  # 1ms

            self._pulse_enable()
            time.sleep(0.001)

            # Switch to 4-bit mode
            self._write4bits(0b0010)  # 0x20 - 4-bit mode
            self._pulse_enable()
            time.sleep(0.001)

            # Function Set: 4-bit, 2 lines, 5x8 dots
            self._display_function = self.LCD_FUNCTIONSET | self.LCD_4BITMODE | self.LCD_2LINE | self.LCD_5x8DOTS
            self._send_byte(self._display_function, 0)
            time.sleep(0.0016)  # >1.52ms for Function Set command

            # Display ON
            self._display_control = self.LCD_DISPLAYCONTROL | self.LCD_DISPLAYON | self.LCD_CURSOROFF | self.LCD_BLINKOFF
            self._send_byte(self._display_control, 0)
            time.sleep(0.0016)  # >1.52ms for Display Control command

            # Clear display
            self._send_byte(self.LCD_CLEARDISPLAY, 0)
            time.sleep(0.0021)  # >2ms for clear display

            # Return Home
            self._send_byte(self.LCD_RETURNHOME, 0)
            time.sleep(0.0021)  # >2ms for return home

            # Entry mode: increment, no shift
            self._display_mode = self.LCD_ENTRYMODESET | self.LCD_ENTRYLEFT | self.LCD_ENTRYSHIFTDECREMENT
            self._send_byte(self._display_mode, 0)
            time.sleep(0.0016)  # >1.52ms for Entry Mode Set command
            
            # Write startup message
            self.write(["RTI", "DEMO"])
            
        except Exception as e:
            logger.warning(f"Failed to initialize LCD display: {e}")
        finally:
            logger.info(f"[LCD DEBUG] Hardware available: {self._hardware_available}")
    
    def read(self) -> Optional[str]:
        """Read from LCD - not supported for output-only display."""
        logger.warning(f"Read not supported for LCD '{self.config.name}'")
        return None
    
    def write(self, value: Union[bool, float, str, List[str]]) -> bool:
        """
        Write to the LCD display.
        
        Args:
            value: Can be:
                - str: Text to display on first line
                - List[str]: Multiple lines of text
        """
        if not self._hardware_available:
            logger.warning(f"Cannot write to LCD '{self.config.name}': hardware not available")
            return False
        
        try:
            logger.info(f"[LCD DEBUG] Writing: {value}")
            self.clear()
            time.sleep(0.0021)  # >2ms delay after clear display
            
            if isinstance(value, str):
                lines = [value]
            elif isinstance(value, list):
                lines = value
            else:
                lines = [str(value)]
            
            for i, line in enumerate(lines[:self._rows]):
                row_offsets = [0x00, 0x40, 0x14, 0x54]
                self._send_byte(self.LCD_SETDDRAMADDR | row_offsets[i], 0)
                
                for char in line[:self._columns]:
                    self._send_byte(ord(char), 1)
            
            logger.info(f"[LCD DEBUG] Write complete")
            return True
        except Exception as e:
            logger.warning(f"Failed to write to LCD '{self.config.name}': {e}")
            return False
    
    def write_line(self, line_number: int, text: str) -> bool:
        """Write text to a specific line (0-indexed)."""
        if line_number < 0 or line_number >= self._rows:
            logger.warning(f"Invalid line number {line_number} for LCD with {self._rows} rows")
            return False
        
        if not self._hardware_available:
            return False
        
        try:
            row_offsets = [0x00, 0x40, 0x14, 0x54]
            self._send_byte(self.LCD_SETDDRAMADDR | row_offsets[line_number], 0)
            
            for char in text[:self._columns]:
                self._send_byte(ord(char), 1)
            
            return True
        except Exception as e:
            logger.warning(f"Failed to write to line {line_number}: {e}")
            return False
    
    def clear(self) -> bool:
        """Clear the LCD display."""
        if not self._hardware_available:
            return False
        
        try:
            self._send_byte(self.LCD_CLEARDISPLAY, 0)
            time.sleep(0.002)
            return True
        except Exception as e:
            logger.warning(f"Failed to clear LCD '{self.config.name}': {e}")
            return False
    
    def set_cursor(self, row: int, col: int) -> bool:
        """Set cursor position (0-indexed row and column)."""
        if row < 0 or row >= self._rows or col < 0 or col >= self._columns:
            logger.warning(f"Invalid cursor position ({row}, {col}) for {self._columns}x{self._rows} LCD")
            return False
        
        if not self._hardware_available:
            return False
        
        try:
            row_offsets = [0x00, 0x40, 0x14, 0x54]
            address = row_offsets[row] + col
            self._send_byte(self.LCD_SETDDRAMADDR | address, 0)
            return True
        except Exception as e:
            logger.warning(f"Failed to set cursor: {e}")
            return False
    
    def display_on(self, state: bool = True) -> bool:
        """Turn display on or off."""
        if not self._hardware_available:
            return False
        
        try:
            if state:
                self._display_control |= self.LCD_DISPLAYON
            else:
                self._display_control &= ~self.LCD_DISPLAYON
            self._send_byte(self._display_control, 0)
            return True
        except Exception as e:
            logger.warning(f"Failed to set display state: {e}")
            return False
    
    def backlight_on(self, state: bool = True) -> bool:
        """Turn backlight on or off."""
        self._backlight = state
        self._set_backlight(state)
        return True
    
    def close(self) -> None:
        """Clean up GPIO resources."""
        try:
            self.clear()
            self.display_on(False)
            self.backlight_on(False)
        except Exception:
            pass
        
        if self._gpio_lines:
            try:
                self._gpio_lines.release()
            except Exception:
                pass
            self._gpio_lines = {}
        
        if self._gpio_chip:
            try:
                self._gpio_chip.close()
            except Exception:
                pass
            self._gpio_chip = None
        
        self._hardware_available = False
    
    @property
    def is_connected(self) -> bool:
        return self._hardware_available


class LCDI2CDevice(IODevice):
    """
    LCD display device with I2C backpack (PCF8574) for HD44780 controller.
    Communicates via I2C instead of GPIO.
    
    Most I2C LCD backpacks use PCF8574 I/O expander with this pin mapping:
    - P0 (bit 0): RS (Register Select)
    - P1 (bit 1): RW (Read/Write) - usually tied LOW for write-only
    - P2 (bit 2): E (Enable)
    - P3 (bit 3): BL (Backlight control)
    - P4 (bit 4): D4 (Data bit 4)
    - P5 (bit 5): D5 (Data bit 5)
    - P6 (bit 6): D6 (Data bit 6)
    - P7 (bit 7): D7 (Data bit 7)
    """
    
    # LCD command constants (same as LCDDevice)
    LCD_CLEARDISPLAY = 0x01
    LCD_RETURNHOME = 0x02
    LCD_ENTRYMODESET = 0x04
    LCD_DISPLAYCONTROL = 0x08
    LCD_CURSORSHIFT = 0x10
    LCD_FUNCTIONSET = 0x20
    LCD_SETCGRAMADDR = 0x40
    LCD_SETDDRAMADDR = 0x80
    
    LCD_ENTRYRIGHT = 0x00
    LCD_ENTRYLEFT = 0x02
    LCD_ENTRYSHIFTINCREMENT = 0x01
    LCD_ENTRYSHIFTDECREMENT = 0x00
    
    LCD_DISPLAYON = 0x04
    LCD_DISPLAYOFF = 0x00
    LCD_CURSORON = 0x02
    LCD_CURSOROFF = 0x00
    LCD_BLINKON = 0x01
    LCD_BLINKOFF = 0x00
    
    LCD_DISPLAYMOVE = 0x08
    LCD_CURSORMOVE = 0x00
    LCD_MOVERIGHT = 0x04
    LCD_MOVELEFT = 0x00
    
    LCD_8BITMODE = 0x10
    LCD_4BITMODE = 0x00
    LCD_2LINE = 0x08
    LCD_1LINE = 0x00
    LCD_5x10DOTS = 0x04
    LCD_5x8DOTS = 0x00
    
    def __init__(self, config: LCDI2CConfig):
        self.config = config
        self._i2c_address = config.i2c_address
        self._i2c_bus = config.i2c_bus
        self._columns = config.columns
        self._rows = config.rows
        self._backlight = config.backlight
        
        # Bit positions for PCF8574 backpack
        self._rs_bit = config.rs_bit
        self._rw_bit = config.rw_bit
        self._e_bit = config.e_bit
        self._backlight_bit = config.backlight_bit
        self._d4_bit = config.d4_bit
        self._d5_bit = config.d5_bit
        self._d6_bit = config.d6_bit
        self._d7_bit = config.d7_bit
        
        self._hardware_available = False
        self._bus = None
        self._display_function = 0
        self._display_control = 0
        self._display_mode = 0
        
        self._init_hardware()
        if self._hardware_available:
            self._initialize_display()
            logger.info(f"Initialized I2C LCD device '{config.name}' ({config.columns}x{config.rows}) at 0x{config.i2c_address:02X} on bus {config.i2c_bus}")
        else:
            logger.warning(f"I2C hardware not available for LCD '{config.name}'. Using mock mode.")
    
    def _init_hardware(self) -> None:
        """Initialize I2C bus using smbus2."""
        if not SMBUS2_AVAILABLE:
            logger.warning("smbus2 library not available. I2C LCD requires smbus2. Install with: pip install smbus2")
            self._hardware_available = False
            return
        
        try:
            self._bus = smbus2.SMBus(self._i2c_bus)
            # Test communication with the device
            self._bus.read_byte(self._i2c_address)
            self._hardware_available = True
        except Exception as e:
            logger.warning(f"I2C initialization failed for LCD '{self.config.name}': {e}")
            self._hardware_available = False
    
    def _write_byte_to_bus(self, byte_value: int) -> None:
        """Write a single byte to the I2C device."""
        if not self._hardware_available or self._bus is None:
            return
        try:
            self._bus.write_byte(self._i2c_address, byte_value)
        except Exception as e:
            logger.warning(f"Failed to write to I2C bus: {e}")
    
    def _pulse_enable(self, data_byte: int) -> None:
        """Pulse the enable pin to latch data."""
        if not self._hardware_available:
            return
        try:
            # Send with E low
            self._write_byte_to_bus(data_byte & ~(1 << self._e_bit))
            time.sleep(0.000005)  # 5 microseconds
            # Send with E high
            self._write_byte_to_bus(data_byte | (1 << self._e_bit))
            time.sleep(0.000005)  # 5 microseconds pulse width
            # Send with E low
            self._write_byte_to_bus(data_byte & ~(1 << self._e_bit))
            time.sleep(0.000050)  # 50 microseconds delay
        except Exception as e:
            logger.warning(f"Failed to pulse enable: {e}")
    
    def _write_nibble(self, nibble: int, mode: int) -> None:
        """
        Write 4 bits to the LCD via I2C.
        mode: 0=command, 1=data (controls RS bit)
        """
        if not self._hardware_available:
            return
        
        try:
            # Build the byte for PCF8574
            # Start with all bits low
            byte_out = 0
            
            # Set RS bit based on mode
            if mode:
                byte_out |= (1 << self._rs_bit)
            
            # RW is always low for writing
            byte_out &= ~(1 << self._rw_bit)
            
            # Set backlight bit
            if self._backlight:
                byte_out |= (1 << self._backlight_bit)
            
            # Set data bits D4-D7 from the nibble
            if (nibble >> 0) & 0x01:
                byte_out |= (1 << self._d4_bit)
            if (nibble >> 1) & 0x01:
                byte_out |= (1 << self._d5_bit)
            if (nibble >> 2) & 0x01:
                byte_out |= (1 << self._d6_bit)
            if (nibble >> 3) & 0x01:
                byte_out |= (1 << self._d7_bit)
            
            # Pulse enable with this byte
            self._pulse_enable(byte_out)
            
        except Exception as e:
            logger.warning(f"Failed to write nibble via I2C: {e}")
    
    def _send_byte(self, value: int, mode: int) -> None:
        """
        Send a byte to the LCD in 4-bit mode via I2C.
        mode: 0=command, 1=data
        """
        if not self._hardware_available:
            return
        
        try:
            mode_str = "DATA" if mode else "COMMAND"
            logger.info(f"[I2C LCD SEND] {mode_str} 0x{value:02X} ({value})")
            
            # Send high nibble
            high = value >> 4
            self._write_nibble(high, mode)
            
            # Send low nibble
            low = value & 0x0F
            self._write_nibble(low, mode)
            
        except Exception as e:
            logger.warning(f"Failed to send byte via I2C: {e}")
    
    def _initialize_display(self) -> None:
        """Initialize the LCD with proper HD44780 timing via I2C."""
        if not self._hardware_available:
            return
        
        try:
            time.sleep(0.05)  # Wait 50ms for power-on
            
            # Initialization sequence for 4-bit mode
            # First: Try 8-bit mode 3 times (as per HD44780 datasheet)
            self._write_nibble(0b0011, 0)  # 0x3 - Function set (8-bit)
            time.sleep(0.005)  # 5ms
            
            self._write_nibble(0b0011, 0)
            time.sleep(0.001)  # 1ms
            
            self._write_nibble(0b0011, 0)
            time.sleep(0.001)
            
            # Switch to 4-bit mode
            self._write_nibble(0b0010, 0)  # 0x2 - 4-bit mode
            time.sleep(0.001)
            
            # Function Set: 4-bit, 2 lines, 5x8 dots
            self._display_function = self.LCD_FUNCTIONSET | self.LCD_4BITMODE | self.LCD_2LINE | self.LCD_5x8DOTS
            self._send_byte(self._display_function, 0)
            time.sleep(0.0016)  # >1.52ms for Function Set command
            
            # Display ON
            self._display_control = self.LCD_DISPLAYCONTROL | self.LCD_DISPLAYON | self.LCD_CURSOROFF | self.LCD_BLINKOFF
            self._send_byte(self._display_control, 0)
            time.sleep(0.0016)  # >1.52ms for Display Control command
            
            # Clear display
            self._send_byte(self.LCD_CLEARDISPLAY, 0)
            time.sleep(0.0021)  # >2ms for clear display
            
            # Return Home
            self._send_byte(self.LCD_RETURNHOME, 0)
            time.sleep(0.0021)  # >2ms for return home
            
            # Entry mode: increment, no shift
            self._display_mode = self.LCD_ENTRYMODESET | self.LCD_ENTRYLEFT | self.LCD_ENTRYSHIFTDECREMENT
            self._send_byte(self._display_mode, 0)
            time.sleep(0.0016)  # >1.52ms for Entry Mode Set command
            
            # Write startup message
            self.write(["RTI", "DEMO"])
            
        except Exception as e:
            logger.warning(f"Failed to initialize I2C LCD display: {e}")
    
    def read(self) -> Optional[str]:
        """Read from LCD - not supported for output-only display."""
        logger.warning(f"Read not supported for I2C LCD '{self.config.name}'")
        return None
    
    def write(self, value: Union[bool, float, str, List[str]]) -> bool:
        """
        Write to the I2C LCD display.
        
        Args:
            value: Can be:
                - str: Text to display on first line
                - List[str]: Multiple lines of text
        """
        if not self._hardware_available:
            logger.debug(f"I2C LCD '{self.config.name}' in mock mode - write simulated")
            # In mock mode, still return True to allow API testing
            return True
        
        try:
            logger.info(f"[I2C LCD DEBUG] Writing: {value}")
            self.clear()
            time.sleep(0.0021)  # >2ms delay after clear display
            
            if isinstance(value, str):
                lines = [value]
            elif isinstance(value, list):
                lines = value
            else:
                lines = [str(value)]
            
            for i, line in enumerate(lines[:self._rows]):
                row_offsets = [0x00, 0x40, 0x14, 0x54]
                self._send_byte(self.LCD_SETDDRAMADDR | row_offsets[i], 0)
                
                for char in line[:self._columns]:
                    self._send_byte(ord(char), 1)
            
            logger.info(f"[I2C LCD DEBUG] Write complete")
            return True
        except Exception as e:
            logger.warning(f"Failed to write to I2C LCD '{self.config.name}': {e}")
            return False
    
    def write_line(self, line_number: int, text: str) -> bool:
        """Write text to a specific line (0-indexed)."""
        if line_number < 0 or line_number >= self._rows:
            logger.warning(f"Invalid line number {line_number} for I2C LCD with {self._rows} rows")
            return False
        
        if not self._hardware_available:
            logger.debug(f"I2C LCD '{self.config.name}' in mock mode - write_line simulated")
            return True
        
        try:
            row_offsets = [0x00, 0x40, 0x14, 0x54]
            self._send_byte(self.LCD_SETDDRAMADDR | row_offsets[line_number], 0)
            
            for char in text[:self._columns]:
                self._send_byte(ord(char), 1)
            
            return True
        except Exception as e:
            logger.warning(f"Failed to write to I2C LCD line {line_number}: {e}")
            return False
    
    def clear(self) -> bool:
        """Clear the I2C LCD display."""
        if not self._hardware_available:
            logger.debug(f"I2C LCD '{self.config.name}' in mock mode - clear simulated")
            return True
        
        try:
            self._send_byte(self.LCD_CLEARDISPLAY, 0)
            time.sleep(0.002)
            return True
        except Exception as e:
            logger.warning(f"Failed to clear I2C LCD '{self.config.name}': {e}")
            return False
    
    def set_cursor(self, row: int, col: int) -> bool:
        """Set cursor position (0-indexed row and column)."""
        if row < 0 or row >= self._rows or col < 0 or col >= self._columns:
            logger.warning(f"Invalid cursor position ({row}, {col}) for {self._columns}x{self._rows} I2C LCD")
            return False
        
        if not self._hardware_available:
            logger.debug(f"I2C LCD '{self.config.name}' in mock mode - set_cursor simulated")
            return True
        
        try:
            row_offsets = [0x00, 0x40, 0x14, 0x54]
            address = row_offsets[row] + col
            self._send_byte(self.LCD_SETDDRAMADDR | address, 0)
            return True
        except Exception as e:
            logger.warning(f"Failed to set I2C LCD cursor: {e}")
            return False
    
    def display_on(self, state: bool = True) -> bool:
        """Turn display on or off."""
        if not self._hardware_available:
            logger.debug(f"I2C LCD '{self.config.name}' in mock mode - display_on simulated")
            return True
        
        try:
            if state:
                self._display_control |= self.LCD_DISPLAYON
            else:
                self._display_control &= ~self.LCD_DISPLAYON
            self._send_byte(self._display_control, 0)
            return True
        except Exception as e:
            logger.warning(f"Failed to set I2C LCD display state: {e}")
            return False
    
    def backlight_on(self, state: bool = True) -> bool:
        """Turn backlight on or off."""
        self._backlight = state
        if self._hardware_available:
            # Update backlight by sending any command (this will trigger backlight update)
            self._send_byte(self._display_control, 0)
        return True
    
    def close(self) -> None:
        """Clean up I2C resources."""
        try:
            self.clear()
            self.display_on(False)
            self.backlight_on(False)
        except Exception:
            pass
        
        if self._bus is not None:
            try:
                self._bus.close()
            except Exception:
                pass
            self._bus = None
        
        self._hardware_available = False
    
    @property
    def is_connected(self) -> bool:
        return self._hardware_available



# ==================== MOCK DEVICES ====================

# ==================== DEVICE FACTORY ====================

class DeviceFactory:
    """
    Factory for creating IO devices from configurations.
    """
    
    @staticmethod
    def create_device(config: DeviceConfig) -> IODevice:
        device_classes = {
            DeviceType.LED: LEDDevice,
            DeviceType.POTENTIOMETER: PotentiometerDevice,
            DeviceType.BUTTON: ButtonDevice,
            DeviceType.LCD: LCDDevice,
            DeviceType.LCD_I2C: LCDI2CDevice,
            DeviceType.PWM: LEDDevice,
            DeviceType.DAC: LEDDevice,
            DeviceType.RELAY: LEDDevice,
            DeviceType.BUZZER: LEDDevice,
            DeviceType.SENSOR: PotentiometerDevice,
        }
        device_class = device_classes.get(config.device_type)
        if device_class is None:
            raise ValueError(f"Unsupported device type: {config.device_type}")
        return device_class(config)
    
# ==================== VALIDATION ====================

RASPBERRY_PI_VALID_GPIO = set(range(0, 28))
MCP3008_VALID_CHANNELS = set(range(0, 8))
ADS1115_VALID_CHANNELS = set(range(0, 4))


def validate_device_config(config: DeviceConfig) -> bool:
    if not config.name:
        raise ValueError("Device name cannot be empty")
    if config.device_type == DeviceType.LED:
        if not isinstance(config, DigitalDeviceConfig):
            raise ValueError("LED config must be DigitalDeviceConfig")
        if config.gpio_pin not in RASPBERRY_PI_VALID_GPIO:
            raise ValueError(f"Invalid GPIO pin {config.gpio_pin}. Valid: {sorted(RASPBERRY_PI_VALID_GPIO)}")
    elif config.device_type == DeviceType.POTENTIOMETER:
        if not isinstance(config, PotentiometerConfig):
            raise ValueError("Potentiometer config must be PotentiometerConfig")
        if config.adc_channel not in MCP3008_VALID_CHANNELS:
            raise ValueError(f"Invalid ADC channel {config.adc_channel}. Valid: {sorted(MCP3008_VALID_CHANNELS)}")
    elif config.device_type == DeviceType.BUTTON:
        if not isinstance(config, ButtonConfig):
            raise ValueError("Button config must be ButtonConfig")
        if config.gpio_pin not in RASPBERRY_PI_VALID_GPIO:
            raise ValueError(f"Invalid GPIO pin {config.gpio_pin}. Valid: {sorted(RASPBERRY_PI_VALID_GPIO)}")
    elif config.device_type == DeviceType.LCD:
        if not isinstance(config, LCDConfig):
            raise ValueError("LCD config must be LCDConfig")
        # Validate all GPIO pins
        all_pins = [config.gpio_rs, config.gpio_e] + config.gpio_data
        if config.gpio_rw is not None:
            all_pins.append(config.gpio_rw)
        if config.backlight_pin is not None:
            all_pins.append(config.backlight_pin)
        for pin in all_pins:
            if pin not in RASPBERRY_PI_VALID_GPIO:
                raise ValueError(f"Invalid GPIO pin {pin} for LCD. Valid: {sorted(RASPBERRY_PI_VALID_GPIO)}")
        if config.columns not in [8, 16, 20, 24, 40]:
            raise ValueError(f"Invalid LCD columns {config.columns}. Valid: [8, 16, 20, 24, 40]")
        if config.rows not in [1, 2, 4]:
            raise ValueError(f"Invalid LCD rows {config.rows}. Valid: [1, 2, 4]")
    elif config.device_type == DeviceType.LCD_I2C:
        if not isinstance(config, LCDI2CConfig):
            raise ValueError("I2C LCD config must be LCDI2CConfig")
        # Validate I2C address (7-bit addresses: 0x08 to 0x77)
        if config.i2c_address < 0x08 or config.i2c_address > 0x77:
            raise ValueError(f"Invalid I2C address 0x{config.i2c_address:02X}. Valid range: 0x08-0x77")
        # Validate I2C bus (typically 0 or 1 on Raspberry Pi)
        if config.i2c_bus not in [0, 1]:
            raise ValueError(f"Invalid I2C bus {config.i2c_bus}. Valid: [0, 1]")
        # Validate bit positions (0-7 for PCF8574)
        all_bits = [config.rs_bit, config.rw_bit, config.e_bit, config.backlight_bit,
                    config.d4_bit, config.d5_bit, config.d6_bit, config.d7_bit]
        for bit in all_bits:
            if bit < 0 or bit > 7:
                raise ValueError(f"Invalid bit position {bit}. Valid range: 0-7")
        # Validate display dimensions
        if config.columns not in [8, 16, 20, 24, 40]:
            raise ValueError(f"Invalid I2C LCD columns {config.columns}. Valid: [8, 16, 20, 24, 40]")
        if config.rows not in [1, 2, 4]:
            raise ValueError(f"Invalid I2C LCD rows {config.rows}. Valid: [1, 2, 4]")
    return True
