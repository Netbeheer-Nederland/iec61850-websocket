"""
GPIO Controller Module for Raspberry Pi I/O Operations

This module provides a clean abstraction for controlling GPIO pins connected to LEDs.
It uses gpiozero for simplicity and safety, with fallback handling for non-Pi environments.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class LEDConfig:
    """Configuration for a single LED."""
    name: str
    gpio_pin: int
    description: str = ""
    initial_state: bool = False


@dataclass
class GPIOController:
    """
    Controller for managing GPIO-connected LEDs on Raspberry Pi.
    
    Provides methods to:
    - Initialize and cleanup GPIO resources
    - Turn LEDs on/off
    - Toggle LED state
    - Get current LED states
    - Set multiple LEDs at once
    """
    
    leds: Dict[str, Any] = field(default_factory=dict)  # name -> LED device
    config: Dict[str, LEDConfig] = field(default_factory=dict)
    _initialized: bool = False
    
    def __post_init__(self):
        """Initialize the controller."""
        self.leds = {}
        self.config = {}
        self._initialized = False
    
    def add_led(self, name: str, gpio_pin: int, description: str = "", initial_state: bool = False) -> None:
        """
        Add an LED to the controller configuration.
        
        Args:
            name: Unique identifier for the LED
            gpio_pin: GPIO pin number (BCM numbering)
            description: Optional description
            initial_state: Initial state (on/off) when initialized
        """
        self.config[name] = LEDConfig(
            name=name,
            gpio_pin=gpio_pin,
            description=description,
            initial_state=initial_state
        )
        logger.info(f"Added LED configuration: {name} on GPIO {gpio_pin}")
    
    def initialize(self) -> bool:
        """
        Initialize all configured LEDs.
        
        Returns:
            True if initialization succeeded, False otherwise
        """
        if self._initialized:
            logger.warning("GPIO already initialized")
            return True
        
        try:
            # Import gpiozero here to allow graceful failure on non-Pi systems
            from gpiozero import LED, Device
            from gpiozero.pins.native import NativeFactory

            Device.pin_factory = NativeFactory()
            
            for name, config in self.config.items():
                try:
                    led = LED(config.gpio_pin)
                    if config.initial_state:
                        led.on()
                    else:
                        led.off()
                    self.leds[name] = led
                    logger.info(f"Initialized LED '{name}' on GPIO {config.gpio_pin} (state: {'ON' if config.initial_state else 'OFF'})")
                except Exception as e:
                    logger.error(f"Failed to initialize LED '{name}': {e}")
                    return False
            
            self._initialized = True
            logger.info(f"GPIO Controller initialized with {len(self.leds)} LEDs")
            return True
            
        except ImportError as e:
            logger.warning(f"gpiozero not available: {e}. Running in simulation mode.")
            # Create mock LED objects for testing without hardware
            for name, config in self.config.items():
                self.leds[name] = _MockLED(config.gpio_pin, config.initial_state)
            self._initialized = True
            logger.info(f"GPIO Controller initialized in simulation mode with {len(self.leds)} LEDs")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize GPIO: {e}")
            return False
    
    def cleanup(self) -> None:
        """Clean up all GPIO resources."""
        if not self._initialized:
            return
        
        try:
            # Close all LED connections
            for name, led in self.leds.items():
                try:
                    if hasattr(led, 'close'):
                        led.close()
                    elif hasattr(led, 'off'):
                        led.off()
                except Exception as e:
                    logger.error(f"Error cleaning up LED '{name}': {e}")
            
            self.leds.clear()
            self._initialized = False
            logger.info("GPIO Controller cleaned up")
            
        except Exception as e:
            logger.error(f"Error during GPIO cleanup: {e}")
    
    def set_led(self, name: str, state: bool) -> bool:
        """
        Set an LED to a specific state.
        
        Args:
            name: LED identifier
            state: True for ON, False for OFF
            
        Returns:
            True if successful, False if LED not found or error
        """
        if not self._initialized:
            logger.warning("GPIO not initialized. Call initialize() first.")
            return False
        
        if name not in self.leds:
            logger.error(f"LED '{name}' not found")
            return False
        
        try:
            led = self.leds[name]
            if state:
                led.on()
            else:
                led.off()
            logger.debug(f"Set LED '{name}' to {'ON' if state else 'OFF'}")
            return True
        except Exception as e:
            logger.error(f"Failed to set LED '{name}': {e}")
            return False
    
    def get_led_state(self, name: str) -> Optional[bool]:
        """
        Get the current state of an LED.
        
        Args:
            name: LED identifier
            
        Returns:
            True if ON, False if OFF, None if LED not found or error
        """
        if not self._initialized:
            logger.warning("GPIO not initialized. Call initialize() first.")
            return None
        
        if name not in self.leds:
            logger.error(f"LED '{name}' not found")
            return None
        
        try:
            led = self.leds[name]
            # gpiozero LED has is_lit property
            if hasattr(led, 'is_lit'):
                return led.is_lit
            # Mock LED has _state attribute
            elif hasattr(led, '_state'):
                return led._state
            else:
                logger.warning(f"LED '{name}' has no state property")
                return None
        except Exception as e:
            logger.error(f"Failed to get state of LED '{name}': {e}")
            return None
    
    def toggle_led(self, name: str) -> Optional[bool]:
        """
        Toggle an LED state.
        
        Args:
            name: LED identifier
            
        Returns:
            New state (True=ON, False=OFF) if successful, None otherwise
        """
        current = self.get_led_state(name)
        if current is None:
            return None
        
        new_state = not current
        if self.set_led(name, new_state):
            return new_state
        return None
    
    def set_all_leds(self, state: bool) -> Dict[str, bool]:
        """
        Set all LEDs to a specific state.
        
        Args:
            state: True for ON, False for OFF
            
        Returns:
            Dictionary of LED names to their resulting states
        """
        results = {}
        for name in self.leds:
            success = self.set_led(name, state)
            results[name] = state if success else self.get_led_state(name)
        return results
    
    def get_all_states(self) -> Dict[str, Optional[bool]]:
        """
        Get the state of all LEDs.
        
        Returns:
            Dictionary of LED names to their current states
        """
        return {name: self.get_led_state(name) for name in self.leds}
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of the GPIO controller.
        
        Returns:
            Dictionary containing:
            - initialized: Whether GPIO is initialized
            - led_count: Number of configured LEDs
            - states: Current state of all LEDs
        """
        return {
            "initialized": self._initialized,
            "led_count": len(self.leds),
            "led_config": {name: {"gpio_pin": config.gpio_pin, "description": config.description} 
                          for name, config in self.config.items()},
            "states": self.get_all_states()
        }


class _MockLED:
    """Mock LED for testing without Raspberry Pi hardware."""
    
    def __init__(self, pin: int, initial_state: bool = False):
        self.pin = pin
        self._state = initial_state
        logger.info(f"Created mock LED on GPIO {pin} (state: {'ON' if initial_state else 'OFF'})")
    
    def on(self) -> None:
        self._state = True
    
    def off(self) -> None:
        self._state = False
    
    @property
    def is_lit(self) -> bool:
        return self._state
    
    def close(self) -> None:
        self.off()


# Global controller instance for convenience
controller = GPIOController()
