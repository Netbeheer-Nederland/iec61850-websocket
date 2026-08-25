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
from typing import Any, Callable, Dict, List, Optional, Union

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
    """Internal wrapper for gpiozero LED. Requires GPIO hardware."""
    
    def __init__(self, gpio_pin: int, active_high: bool = True, initial_value: bool = False):
        self._led = None
        
        try:
            from gpiozero import LED
            self._led = LED(gpio_pin, active_high=active_high, initial_value=initial_value)
            logger.info(f"Initialized gpiozero LED on GPIO {gpio_pin}")
        except Exception as e:
            raise RuntimeError(f"gpiozero not available for GPIO {gpio_pin}: {e}. LED requires GPIO hardware.")
    
    @property
    def value(self) -> bool:
        try:
            return self._led.value
        except Exception:
            raise RuntimeError(f"Failed to read LED value. Hardware may be disconnected.")
    
    @value.setter
    def value(self, val: bool) -> None:
        try:
            self._led.value = val
        except Exception:
            raise RuntimeError(f"Failed to write LED value. Hardware may be disconnected.")
    
    def on(self) -> None:
        self.value = True
    
    def off(self) -> None:
        self.value = False
    
    def toggle(self) -> None:
        try:
            self._led.toggle()
        except Exception:
            raise RuntimeError(f"Failed to toggle LED. Hardware may be disconnected.")
    
    def close(self) -> None:
        if self._led:
            try:
                if hasattr(self._led, 'close'):
                    self._led.close()
            except Exception:
                pass


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
    LED device implementation using gpiozero for hardware control.
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
        self._init_hardware()
        if not self._hardware_available:
            raise RuntimeError(f"ADC not available for potentiometer '{config.name}'. Hardware required.")
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
            else:
                return None
            normalized = max(0, min(1, raw / max_value))
            if self.config.is_inverted:
                normalized = 1.0 - normalized
            return normalized
        except Exception as e:
            logger.warning(f"Failed to read potentiometer '{self.config.name}': {e}")
            return None
    
    def read_scaled(self) -> Optional[float]:
        normalized = self.read()
        if normalized is None:
            return None
        return self.config.min_value + normalized * (self.config.max_value - self.config.min_value)
    
    def write(self, value: Union[bool, float]) -> bool:
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
    - Hardware interrupt-based edge detection (via gpiozero callbacks)
    - Change detection callbacks
    """
    
    def __init__(self, config: ButtonConfig):
        super().__init__(config)
        self._last_read_time = 0
        self._last_read_value = False
        self._latched_state = False
        self._previous_physical_state = False
        self._button = None
        self._active_high = config.is_active_high
        
        try:
            from gpiozero import Button as GpioZeroButton
            self._button = GpioZeroButton(
                config.gpio_pin,
                pull_up=config.pull_up,
                bounce_time=config.debounce_time
            )
            self._hardware_available = True
            
            # === Edge Detection Callbacks ===
            if config.latching and self._hardware_available:
                # Use gpiozero callbacks for immediate edge detection
                # This works even when not actively polling
                button_self = self
                def on_press():
                    button_self._latched_state = not button_self._latched_state
                    logger.info(f"Button '{config.name}' pressed - toggled to {button_self._latched_state}")
                    button_self._notify_change(not button_self._latched_state, button_self._latched_state)
                def on_release():
                    # Track release for debugging/state management
                    logger.debug(f"Button '{config.name}' released")
                self._button.when_pressed = on_press
                self._button.when_released = on_release
            
            # Initialize previous state to current physical state
            # This prevents false edge detection on first read
            if self._hardware_available:
                try:
                    # Wait briefly for hardware to stabilize
                    import time
                    time.sleep(0.1)
                    raw_value = self._button.is_pressed
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
            raw_value = self._button.is_pressed
            if self.config.is_active_high:
                return raw_value
            else:
                return not raw_value
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
            return None
    
    def read(self) -> Optional[bool]:
        """Read button state.
        
        If latching=True: returns the latched state (toggles on press via callback)
        If latching=False: returns the current physical state (True=pressed, False=released)
        """
        if self.config.latching:
            # Latched state is updated automatically by gpiozero callbacks
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
        # Clean up gpiozero button
        if self._hardware_available and hasattr(self._button, 'close'):
            try:
                self._button.close()
            except Exception as e:
                logger.warning(f"Failed to release button '{self.config.name}': {e}")
    



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
    return True
