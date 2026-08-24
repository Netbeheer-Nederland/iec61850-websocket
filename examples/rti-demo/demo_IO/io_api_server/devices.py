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
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Union

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
    identifier: Union[int, str] = 0  # GPIO pin, ADC channel, I2C address, etc. (0 = unset, will be set by subclass)
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
    is_active_high: bool = True  # True = active high, False = active low
    
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
    brightness: float = 1.0  # 0.0-1.0, for PWM-capable LEDs


@dataclass
class PotentiometerConfig(DeviceConfig):
    """Configuration for potentiometer (analog input) devices."""
    device_type: DeviceType = field(default=DeviceType.POTENTIOMETER, init=False)
    adc_channel: int = 0
    adc_reference_voltage: float = 3.3  # Reference voltage in volts
    min_value: float = 0.0  # User-defined minimum value
    max_value: float = 100.0  # User-defined maximum value
    is_inverted: bool = False  # Whether to invert the reading
    
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
class ButtonConfig(DigitalDeviceConfig):
    """Configuration for button (digital input) devices."""
    device_type: DeviceType = field(default=DeviceType.BUTTON, init=False)
    direction: DeviceDirection = field(default=DeviceDirection.INPUT, init=False)
    debounce_time: float = 0.05  # Debounce time in seconds
    pull_up: bool = True  # Use internal pull-up resistor


@dataclass
class PWMConfig(DigitalDeviceConfig):
    """Configuration for PWM (pulse-width modulation) output devices."""
    device_type: DeviceType = field(default=DeviceType.PWM, init=False)
    frequency: int = 1000  # PWM frequency in Hz
    duty_cycle: float = 0.0  # Initial duty cycle 0.0-1.0


# ==================== BASE DEVICE CLASS ====================

class IODevice(ABC):
    """
    Abstract base class for all IO devices.
    
    All IO devices must implement:
    - read() - Read the current value from the device
    - write(value) - Write a value to the device
    - close() - Clean up resources
    
    Devices can be:
    - INPUT: read() returns meaningful data, write() may fail
    - OUTPUT: write() accepts data, read() returns last written value
    - BIDIRECTIONAL: both read() and write() work
    """
    
    config: DeviceConfig
    
    @abstractmethod
    def read(self) -> Optional[Union[bool, float]]:
        """
        Read the current value from the device.
        
        Returns:
            The current value (bool for digital, float for analog), or None on error
        """
        pass
    
    @abstractmethod
    def write(self, value: Union[bool, float]) -> bool:
        """
        Write a value to the device.
        
        Args:
            value: Value to write (bool for digital, float for analog)
            
        Returns:
            True if successful, False on error
        """
        pass
    
    @abstractmethod
    def close(self) -> None:
        """Clean up device resources."""
        pass
    
    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if device is properly initialized and connected."""
        pass
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.config.name}, type={self.config.device_type.value})"


# ==================== HARDWARE DEVICE IMPLEMENTATIONS ====================

class LEDDevice(IODevice):
    """
    LED device implementation using gpiod for hardware control.
    
    Falls back to mock mode if gpiod is not available.
    """
    
    def __init__(self, config: LEDConfig):
        self.config = config
        self._gpiod_available = False
        self._mock_state = config.initial_state
        self._device = None
        
        try:
            import gpiod
            from gpiod.line import Direction, Value
            
            self._request = gpiod.request_lines(
                "/dev/gpiochip0",
                consumer="demo_io",
                config={
                    config.gpio_pin: gpiod.LineSettings(
                        direction=Direction.OUTPUT,
                        active_state=Value.ACTIVE if config.is_active_high else Value.INACTIVE
                    )
                }
            )
            self._gpiod_available = True
            self._pin = config.gpio_pin
            self._active_high = config.is_active_high
            
            # Set initial state
            if config.initial_state:
                self.write(True)
            else:
                self.write(False)
            
            logger.info(f"Initialized LED device '{config.name}' on GPIO {config.gpio_pin}")
            
        except (ImportError, OSError, ValueError, AttributeError) as e:
            logger.warning(f"gpiod not available for LED '{config.name}': {e}. Using mock mode.")
            self._gpiod_available = False
            self._mock_state = config.initial_state
    
    def read(self) -> Optional[bool]:
        """Read the current LED state."""
        if not self.is_connected:
            return None
        
        if self._gpiod_available:
            try:
                import gpiod
                from gpiod.line import Value
                raw_value = self._request.get_value(self._pin)
                # Handle active high/low
                if self._active_high:
                    return raw_value == Value.ACTIVE
                else:
                    return raw_value == Value.INACTIVE
            except Exception as e:
                logger.warning(f"Failed to read LED '{self.config.name}': {e}")
                return None
        else:
            return self._mock_state
    
    def write(self, value: Union[bool, float]) -> bool:
        """Set the LED state (True=ON, False=OFF)."""
        if not self.is_connected:
            return False
        
        # Convert float to bool
        state = bool(value)
        
        if self._gpiod_available:
            try:
                import gpiod
                from gpiod.line import Value
                
                target_value = Value.ACTIVE if state else Value.INACTIVE
                if not self._active_high:
                    target_value = Value.INACTIVE if state else Value.ACTIVE
                
                self._request.set_value(self._pin, target_value)
                self._mock_state = state
                return True
            except Exception as e:
                logger.warning(f"Failed to write to LED '{self.config.name}': {e}")
                return False
        else:
            self._mock_state = state
            return True
    
    def close(self) -> None:
        """Clean up GPIO resources."""
        if self._gpiod_available and self._request:
            try:
                self._request.release()
            except Exception as e:
                logger.warning(f"Failed to release LED '{self.config.name}': {e}")
    
    @property
    def is_connected(self) -> bool:
        return True  # Even mock devices are "connected"
    
    def toggle(self) -> Optional[bool]:
        """Toggle the LED state and return new state."""
        current = self.read()
        if current is None:
            return None
        new_state = not current
        if self.write(new_state):
            return new_state
        return None


class PotentiometerDevice(IODevice):
    """
    Potentiometer (analog input) device implementation.
    
    Reads analog values from an ADC (Analog-to-Digital Converter).
    Supports MCP3008 (10-bit, 8-channel) via SPI as a common ADC for Raspberry Pi.
    
    Falls back to mock mode if hardware is not available.
    """
    
    # Common ADC configurations
    ADC_MCP3008 = "mcp3008"  # 10-bit, 8-channel ADC
    ADC_ADS1115 = "ads1115"  # 16-bit, 4-channel ADC
    
    def __init__(self, config: PotentiometerConfig):
        self.config = config
        self._hardware_available = False
        self._mock_value: float = 0.5  # Default midpoint for mock
        self._adc = None
        self._spi = None
        
        # Try to initialize hardware
        self._init_hardware()
        
        if not self._hardware_available:
            logger.warning(f"ADC not available for potentiometer '{config.name}'. Using mock mode.")
    
    def _init_hardware(self) -> None:
        """Initialize ADC hardware if available."""
        try:
            # Try MCP3008 first (SPI-based, common for RPi)
            try:
                import spidev
                import RPi.GPIO as GPIO
                
                # SPI configuration
                self._spi = spidev.SpiDev()
                self._spi.open(0, 0)  # CE0 on Raspberry Pi
                self._spi.max_speed_hz = 1000000
                self._adc_type = self.ADC_MCP3008
                self._channel = self.config.adc_channel
                self._hardware_available = True
                logger.info(f"Initialized potentiometer '{self.config.name}' on ADC channel {self.config.adc_channel}")
                return
                
            except (ImportError, AttributeError, OSError):
                # Try ADS1115 (I2C-based)
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
        """Read raw value from MCP3008 ADC (0-1023)."""
        if not self._spi:
            return 0
        
        # MCP3008 command format: [start, SGL/DIF, ODD/SIGN, MSBF, channel, 0, 0, 0]
        # Single-ended mode
        cmd = 0b11 << 6  # Start bit + single-ended
        cmd |= (channel & 0x07) << 3  # Channel bits
        
        # Send command and read response
        adc = self._spi.xfer2([cmd, 0, 0])
        data = ((adc[1] & 0x03) << 8) | adc[2]
        return data
    
    def _read_ads1115(self, channel: int) -> int:
        """Read raw value from ADS1115 ADC (0-32767)."""
        if not self._adc:
            return 0
        return self._adc.read_adc(channel, gain=1)
    
    def read(self) -> Optional[float]:
        """
        Read the current potentiometer value.
        
        Returns:
            Normalized value between 0.0 and 1.0, or None on error
        """
        if not self.is_connected:
            return None
        
        if self._hardware_available:
            try:
                if self._adc_type == self.ADC_MCP3008:
                    raw = self._read_mcp3008(self._channel)
                    max_value = 1023  # 10-bit ADC
                elif self._adc_type == self.ADC_ADS1115:
                    raw = self._read_ads1115(self._channel)
                    max_value = 32767  # 15-bit ADC
                else:
                    return None
                
                # Normalize to 0.0-1.0
                normalized = max(0, min(1, raw / max_value))
                
                # Apply inversion if needed
                if self.config.is_inverted:
                    normalized = 1.0 - normalized
                
                return normalized
                
            except Exception as e:
                logger.warning(f"Failed to read potentiometer '{self.config.name}': {e}")
                return None
        else:
            return self._mock_value
    
    def read_scaled(self) -> Optional[float]:
        """
        Read the potentiometer value scaled to user-defined range.
        
        Returns:
            Value scaled between min_value and max_value, or None on error
        """
        normalized = self.read()
        if normalized is None:
            return None
        return self.config.min_value + normalized * (self.config.max_value - self.config.min_value)
    
    def write(self, value: Union[bool, float]) -> bool:
        """
        Potentiometers are read-only devices.
        
        This method is provided for interface compatibility but always fails.
        """
        logger.warning(f"Cannot write to read-only potentiometer '{self.config.name}'")
        return False
    
    def close(self) -> None:
        """Clean up ADC resources."""
        if self._spi:
            try:
                self._spi.close()
            except Exception:
                pass
        self._spi = None
        self._adc = None
    
    @property
    def is_connected(self) -> bool:
        return True  # Even mock devices are "connected"
    
    def set_mock_value(self, value: float) -> None:
        """Set mock value for testing (0.0-1.0)."""
        self._mock_value = max(0.0, min(1.0, value))


class ButtonDevice(IODevice):
    """
    Button (digital input) device implementation.
    
    Supports debouncing and pull-up/pull-down configuration.
    Falls back to mock mode if gpiod is not available.
    """
    
    def __init__(self, config: ButtonConfig):
        self.config = config
        self._gpiod_available = False
        self._mock_state = False
        self._device = None
        self._last_read_time = 0
        self._last_read_value = False
        
        try:
            import gpiod
            from gpiod.line import Direction, Value
            
            # Configure pull direction
            pull = gpiod.line.Pull.UP if config.pull_up else gpiod.line.Pull.DOWN
            
            self._request = gpiod.request_lines(
                "/dev/gpiochip0",
                consumer="demo_io",
                config={
                    config.gpio_pin: gpiod.LineSettings(
                        direction=Direction.INPUT,
                        pull=pull
                    )
                }
            )
            self._gpiod_available = True
            self._pin = config.gpio_pin
            self._active_high = config.is_active_high
            self._debounce_time = config.debounce_time
            
            logger.info(f"Initialized button '{config.name}' on GPIO {config.gpio_pin}")
            
        except (ImportError, OSError, ValueError, AttributeError) as e:
            logger.warning(f"gpiod not available for button '{config.name}': {e}. Using mock mode.")
            self._gpiod_available = False
    
    def read(self) -> Optional[bool]:
        """Read the current button state."""
        if not self.is_connected:
            return None
        
        if self._gpiod_available:
            try:
                import time
                import gpiod
                from gpiod.line import Value
                
                # Debounce check
                current_time = time.time()
                if current_time - self._last_read_time < self._debounce_time:
                    return self._last_read_value
                
                raw_value = self._request.get_value(self._pin)
                
                # Handle active high/low
                if self._active_high:
                    state = raw_value == Value.ACTIVE
                else:
                    state = raw_value == Value.INACTIVE
                
                self._last_read_time = current_time
                self._last_read_value = state
                return state
                
            except Exception as e:
                logger.warning(f"Failed to read button '{self.config.name}': {e}")
                return None
        else:
            return self._mock_state
    
    def write(self, value: Union[bool, float]) -> bool:
        """
        Buttons are read-only devices.
        
        This method is provided for interface compatibility but always fails.
        """
        logger.warning(f"Cannot write to read-only button '{self.config.name}'")
        return False
    
    def close(self) -> None:
        """Clean up GPIO resources."""
        if self._gpiod_available and self._request:
            try:
                self._request.release()
            except Exception as e:
                logger.warning(f"Failed to release button '{self.config.name}': {e}")
    
    @property
    def is_connected(self) -> bool:
        return True
    
    def set_mock_state(self, state: bool) -> None:
        """Set mock state for testing."""
        self._mock_state = bool(state)


# ==================== MOCK DEVICES (FOR TESTING) ====================

class MockLEDDevice(LEDDevice):
    """Mock LED device for testing without hardware."""
    
    def __init__(self, config: LEDConfig):
        # Force mock mode
        config_copy = LEDConfig(
            name=config.name,
            gpio_pin=config.gpio_pin,
            description=config.description,
            initial_state=config.initial_state,
            is_active_high=config.is_active_high,
            brightness=config.brightness,
        )
        super().__init__(config_copy)
        self._gpiod_available = False
        self._mock_state = config.initial_state


class MockPotentiometerDevice(PotentiometerDevice):
    """Mock potentiometer device for testing without hardware."""
    
    def __init__(self, config: PotentiometerConfig):
        super().__init__(config)
        self._hardware_available = False


# ==================== DEVICE FACTORY ====================

class DeviceFactory:
    """
    Factory for creating IO devices from configurations.
    
    Usage:
        factory = DeviceFactory()
        led = factory.create_device(led_config)
        pot = factory.create_device(pot_config)
    """
    
    @staticmethod
    def create_device(config: DeviceConfig) -> IODevice:
        """
        Create an IO device from a configuration.
        
        Args:
            config: Device configuration
            
        Returns:
            IODevice instance appropriate for the config type
            
        Raises:
            ValueError: If device type is not supported
        """
        device_classes = {
            DeviceType.LED: LEDDevice,
            DeviceType.POTENTIOMETER: PotentiometerDevice,
            DeviceType.BUTTON: ButtonDevice,
            DeviceType.PWM: LEDDevice,  # PWM can use LEDDevice with brightness
            DeviceType.DAC: LEDDevice,  # Placeholder - implement as needed
            DeviceType.RELAY: LEDDevice,  # Relay acts like digital output
            DeviceType.BUZZER: LEDDevice,  # Buzzer acts like digital output
            DeviceType.SENSOR: PotentiometerDevice,  # Generic sensor like analog
        }
        
        device_class = device_classes.get(config.device_type)
        if device_class is None:
            raise ValueError(f"Unsupported device type: {config.device_type}")
        
        return device_class(config)
    
    @staticmethod
    def create_mock_device(config: DeviceConfig) -> IODevice:
        """Create a mock device for testing."""
        mock_classes = {
            DeviceType.LED: MockLEDDevice,
            DeviceType.POTENTIOMETER: MockPotentiometerDevice,
            DeviceType.BUTTON: ButtonDevice,  # ButtonDevice already has mock mode
        }
        
        device_class = mock_classes.get(config.device_type, LEDDevice)
        return device_class(config)


# ==================== VALIDATION ====================

# Valid GPIO pin ranges for Raspberry Pi models
RASPBERRY_PI_VALID_GPIO = set(range(0, 28))  # GPIO 0-27

# Valid ADC channels for common ADCs
MCP3008_VALID_CHANNELS = set(range(0, 8))  # 8 channels (0-7)
ADS1115_VALID_CHANNELS = set(range(0, 4))  # 4 channels (0-3)


def validate_device_config(config: DeviceConfig) -> bool:
    """
    Validate a device configuration.
    
    Args:
        config: Device configuration to validate
        
    Returns:
        True if valid, False otherwise
        
    Raises:
        ValueError: If configuration is invalid
    """
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
    
    return True
