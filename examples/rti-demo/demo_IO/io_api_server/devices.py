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


# ==================== GPIOZERO WRAPPER FOR LED ====================

class _GpioZeroLED:
    """Internal wrapper for gpiozero LED with proper error handling."""
    
    def __init__(self, gpio_pin: int, active_high: bool = True, initial_value: bool = False):
        self._hardware_available = False
        self._mock_state = initial_value
        self._led = None
        
        try:
            from gpiozero import LED
            self._led = LED(gpio_pin, active_high=active_high, initial_value=initial_value)
            self._hardware_available = True
            logger.info(f"Initialized gpiozero LED on GPIO {gpio_pin}")
        except Exception as e:
            logger.warning(f"gpiozero not available for GPIO {gpio_pin}: {e}. Using mock mode.")
            self._hardware_available = False
    
    @property
    def value(self) -> bool:
        if self._hardware_available:
            try:
                return self._led.value
            except Exception:
                return self._mock_state
        return self._mock_state
    
    @value.setter
    def value(self, val: bool) -> None:
        if self._hardware_available:
            try:
                self._led.value = val
            except Exception:
                self._mock_state = val
        else:
            self._mock_state = val
    
    def on(self) -> None:
        self.value = True
    
    def off(self) -> None:
        self.value = False
    
    def toggle(self) -> None:
        if self._hardware_available:
            try:
                self._led.toggle()
            except Exception:
                self._mock_state = not self._mock_state
        else:
            self._mock_state = not self._mock_state
    
    def close(self) -> None:
        if self._hardware_available and self._led:
            try:
                if hasattr(self._led, 'close'):
                    self._led.close()
            except Exception:
                pass


# ==================== HARDWARE DEVICE IMPLEMENTATIONS ====================

class LEDDevice(IODevice):
    """
    LED device implementation using gpiozero for hardware control.
    
    Falls back to mock mode if gpiozero is not available.
    """
    
    def __init__(self, config: LEDConfig):
        self.config = config
        self._gpiozero_led = _GpioZeroLED(
            gpio_pin=config.gpio_pin,
            active_high=config.is_active_high,
            initial_value=config.initial_state
        )
        self._mock_state = config.initial_state
        logger.info(f"Initialized LED device '{config.name}' on GPIO {config.gpio_pin}")
    
    def read(self) -> Optional[bool]:
        """Read the current LED state."""
        try:
            return self._gpiozero_led.value
        except Exception as e:
            logger.warning(f"Failed to read LED '{self.config.name}': {e}")
            return self._mock_state
    
    def write(self, value: Union[bool, float]) -> bool:
        """Set the LED state (True=ON, False=OFF)."""
        state = bool(value)
        try:
            self._gpiozero_led.value = state
            self._mock_state = state
            return True
        except Exception as e:
            logger.warning(f"Failed to write to LED '{self.config.name}': {e}")
            self._mock_state = state
            return False
    
    def close(self) -> None:
        """Clean up GPIO resources."""
        self._gpiozero_led.close()
    
    @property
    def is_connected(self) -> bool:
        return True
    
    def toggle(self) -> Optional[bool]:
        """Toggle the LED state and return new state."""
        self._gpiozero_led.toggle()
        new_state = self.read()
        if new_state is None:
            self._mock_state = not self._mock_state
            return self._mock_state
        return new_state


class PotentiometerDevice(IODevice):
    """
    Potentiometer (analog input) device implementation.
    
    Reads analog values from an ADC (Analog-to-Digital Converter).
    Falls back to mock mode if hardware is not available.
    """
    
    ADC_MCP3008 = "mcp3008"
    ADC_ADS1115 = "ads1115"
    
    def __init__(self, config: PotentiometerConfig):
        self.config = config
        self._hardware_available = False
        self._mock_value: float = 0.5
        self._adc = None
        self._spi = None
        self._init_hardware()
        if not self._hardware_available:
            logger.warning(f"ADC not available for potentiometer '{config.name}'. Using mock mode.")
    
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
        if self._hardware_available:
            try:
                if self._adc_type == self.ADC_MCP3008:
                    raw = self._read_mcp3008(self._channel)
                    max_value = 1023
                elif self._adc_type == self.ADC_ADS1115:
                    raw = self._read_ads1115(self._channel)
                    max_value = 32767
                else:
                    return None
                normalized = max(0, min(1, raw / max_value))
                if self.config.is_inverted:
                    normalized = 1.0 - normalized
                return normalized
            except Exception as e:
                logger.warning(f"Failed to read potentiometer '{self.config.name}': {e}")
                return None
        else:
            return self._mock_value
    
    def read_scaled(self) -> Optional[float]:
        normalized = self.read()
        if normalized is None:
            return None
        return self.config.min_value + normalized * (self.config.max_value - self.config.min_value)
    
    def write(self, value: Union[bool, float]) -> bool:
        logger.warning(f"Cannot write to read-only potentiometer '{self.config.name}'")
        return False
    
    def close(self) -> None:
        if self._spi:
            try:
                self._spi.close()
            except Exception:
                pass
        self._spi = None
        self._adc = None
    
    @property
    def is_connected(self) -> bool:
        return True
    
    def set_mock_value(self, value: float) -> None:
        self._mock_value = max(0.0, min(1.0, value))


class ButtonDevice(IODevice):
    """
    Button (digital input) device implementation.
    
    Falls back to mock mode if hardware is not available.
    
    When latching=True, the button toggles its state on each press (rising edge)
    and maintains that state even after release. This is useful for momentary
    buttons that should act like toggle switches.
    """
    
    def __init__(self, config: ButtonConfig):
        self.config = config
        self._hardware_available = False
        self._mock_state = False
        self._last_read_time = 0
        self._last_read_value = False
        self._latched_state = False
        self._previous_physical_state = False
        
        try:
            from gpiozero import Button as GpioZeroButton
            from gpiozero import Device
            Device.pin_factory = None
            self._button = GpioZeroButton(
                config.gpio_pin,
                pull_up=config.pull_up,
                bounce_time=config.debounce_time
            )
            self._hardware_available = True
            self._active_high = config.is_active_high
            logger.info(f"Initialized button '{config.name}' on GPIO {config.gpio_pin}" + 
                       (" (latching)" if config.latching else ""))
        except Exception as e:
            logger.warning(f"Hardware not available for button '{config.name}': {e}. Using mock mode.")
            self._hardware_available = False
    
    def _get_physical_state(self) -> Optional[bool]:
        """Read the actual physical state of the button (pressed/released)."""
        if not self.is_connected:
            return None
        if self._hardware_available:
            try:
                import time
                current_time = time.time()
                if current_time - self._last_read_time < self.config.debounce_time:
                    return self._last_read_value
                raw_value = self._button.is_pressed
                if self.config.is_active_high:
                    state = raw_value
                else:
                    state = not raw_value
                self._last_read_time = current_time
                self._last_read_value = state
                return state
            except Exception as e:
                logger.warning(f"Failed to read button '{self.config.name}': {e}")
                return self._mock_state
        else:
            return self._mock_state
    
    def read(self) -> Optional[bool]:
        """Read button state.
        
        If latching=True: returns the latched state (toggles on press, stays until next press)
        If latching=False: returns the current physical state (True=pressed, False=released)
        """
        physical_state = self._get_physical_state()
        
        if physical_state is None:
            return None
        
        if self.config.latching:
            # Latching mode: detect rising edge (press) and toggle latched state
            if self._previous_physical_state == False and physical_state == True:
                self._latched_state = not self._latched_state
                logger.debug(f"Button '{self.config.name}' pressed - toggled latched state to {self._latched_state}")
            self._previous_physical_state = physical_state
            return self._latched_state
        else:
            # Normal mode: return current physical state
            return physical_state
    
    def reset_latch(self) -> None:
        """Reset latched state to False (for latching buttons)."""
        self._latched_state = False
        logger.info(f"Reset latched state for button '{self.config.name}'")
    
    def write(self, value: Union[bool, float]) -> bool:
        logger.warning(f"Cannot write to read-only button '{self.config.name}'")
        return False
    
    def close(self) -> None:
        if self._hardware_available and hasattr(self._button, 'close'):
            try:
                self._button.close()
            except Exception as e:
                logger.warning(f"Failed to release button '{self.config.name}': {e}")
    
    @property
    def is_connected(self) -> bool:
        return True
    
    def set_mock_state(self, state: bool) -> None:
        self._mock_state = bool(state)


# ==================== MOCK DEVICES ====================

class MockLEDDevice(LEDDevice):
    """Mock LED device for testing without hardware."""
    
    def __init__(self, config: LEDConfig):
        config_copy = LEDConfig(
            name=config.name,
            gpio_pin=config.gpio_pin,
            description=config.description,
            initial_state=config.initial_state,
            is_active_high=config.is_active_high,
            brightness=config.brightness,
        )
        super().__init__(config_copy)
        self._gpiozero_led._hardware_available = False
        self._gpiozero_led._mock_state = config.initial_state


class MockPotentiometerDevice(PotentiometerDevice):
    """Mock potentiometer device for testing without hardware."""
    
    def __init__(self, config: PotentiometerConfig):
        super().__init__(config)
        self._hardware_available = False


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
    
    @staticmethod
    def create_mock_device(config: DeviceConfig) -> IODevice:
        mock_classes = {
            DeviceType.LED: MockLEDDevice,
            DeviceType.POTENTIOMETER: MockPotentiometerDevice,
            DeviceType.BUTTON: ButtonDevice,
        }
        device_class = mock_classes.get(config.device_type, LEDDevice)
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
    return True
