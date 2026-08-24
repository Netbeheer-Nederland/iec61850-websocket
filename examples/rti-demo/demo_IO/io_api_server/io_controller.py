"""
IO Controller Module - Generic controller for all IO devices on Raspberry Pi.

This module provides a unified interface for managing various IO devices:
- LEDs (digital output)
- Potentiometers (analog input)
- Buttons (digital input)
- PWM outputs
- And more

It uses the devices module for device-specific implementations,
with fallback to mock devices for non-Pi environments.

Usage:
    from io_controller import IOController
    from devices import LEDConfig, PotentiometerConfig, DeviceType
    
    controller = IOController()
    
    # Add an LED
    controller.add_device(LEDConfig(name="led1", gpio_pin=17))
    
    # Add a potentiometer
    controller.add_device(PotentiometerConfig(name="pot1", adc_channel=0))
    
    # Initialize all devices
    controller.initialize()
    
    # Control devices
    controller.write("led1", True)
    value = controller.read("pot1")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from devices import (
    DeviceConfig,
    DeviceFactory,
    DeviceType,
    DeviceDirection,
    IODevice,
    LEDConfig,
    PotentiometerConfig,
    ButtonConfig,
    DigitalDeviceConfig,
    PWMConfig,
    validate_device_config,
    RASPBERRY_PI_VALID_GPIO,
)

logger = logging.getLogger(__name__)


# ==================== NEW IO CONTROLLER ====================

@dataclass
class IOController:
    """
    Controller for managing all types of IO devices on Raspberry Pi.
    
    This is the main interface for IO device management, providing:
    - Device registration and configuration
    - Device initialization and cleanup
    - Unified read/write operations
    - Device state management
    - Bulk operations
    
    Supports multiple device types:
    - LEDs (digital output)
    - Potentiometers (analog input)
    - Buttons (digital input)
    - PWM outputs
    - DACs
    - Relays
    
    Usage:
        controller = IOController()
        
        # Add devices
        controller.add_device(LEDConfig(name="led1", gpio_pin=17))
        controller.add_device(PotentiometerConfig(name="pot1", adc_channel=0))
        
        # Initialize
        controller.initialize()
        
        # Control
        controller.write("led1", True)
        value = controller.read("pot1")
    """
    
    devices: Dict[str, IODevice] = field(default_factory=dict)  # name -> IODevice
    configs: Dict[str, DeviceConfig] = field(default_factory=dict)  # name -> DeviceConfig
    _initialized: bool = False
    _use_mock: bool = False  # Force mock mode for testing
    
    def __post_init__(self):
        """Initialize the controller."""
        self.devices = {}
        self.configs = {}
        self._initialized = False
        self._use_mock = False
    
    # ==================== Device Management ====================
    
    def add_device(self, config: DeviceConfig, use_mock: bool = False) -> None:
        """
        Add a device to the controller configuration.
        
        Args:
            config: Device configuration
            use_mock: If True, create a mock device instead of hardware
            
        Raises:
            ValueError: If device name already exists or config is invalid
        """
        # Validate configuration
        validate_device_config(config)
        
        # Check for duplicate name
        if config.name in self.configs:
            raise ValueError(f"Device '{config.name}' already exists. Use a unique name.")
        
        # Store configuration
        self.configs[config.name] = config
        logger.info(f"Added device configuration: {config.name} (type: {config.device_type.value})")
    
    def remove_device(self, name: str) -> bool:
        """
        Remove a device from the controller.
        
        Args:
            name: Device name
            
        Returns:
            True if removed, False if not found
        """
        if name not in self.configs:
            return False
        
        # Clean up the device if initialized
        if name in self.devices:
            self.devices[name].close()
            del self.devices[name]
        
        del self.configs[name]
        logger.info(f"Removed device: {name}")
        return True
    
    def get_device(self, name: str) -> Optional[IODevice]:
        """Get a device by name."""
        return self.devices.get(name)
    
    def get_config(self, name: str) -> Optional[DeviceConfig]:
        """Get device configuration by name."""
        return self.configs.get(name)
    
    def list_devices(self) -> List[str]:
        """List all configured device names."""
        return list(self.configs.keys())
    
    def list_device_types(self) -> Dict[str, DeviceType]:
        """List all devices with their types."""
        return {name: config.device_type for name, config in self.configs.items()}
    
    # ==================== Initialization ====================
    
    def initialize(self, use_mock: bool = False) -> bool:
        """
        Initialize all configured devices.
        
        Args:
            use_mock: If True, force all devices to use mock mode
            
        Returns:
            True if initialization succeeded, False otherwise
        """
        if self._initialized:
            logger.warning("IO already initialized")
            return True
        
        self._use_mock = use_mock
        self._initialized = True
        
        factory = DeviceFactory()
        
        for name, config in self.configs.items():
            try:
                if use_mock:
                    device = factory.create_mock_device(config)
                else:
                    device = factory.create_device(config)
                
                self.devices[name] = device
                logger.info(f"Initialized device '{name}' (type: {config.device_type.value})")
                
            except Exception as e:
                logger.error(f"Failed to initialize device '{name}': {e}")
                # Clean up any partially initialized devices
                for device in self.devices.values():
                    device.close()
                self.devices.clear()
                self._initialized = False
                return False
        
        logger.info(f"IO Controller initialized with {len(self.devices)} devices")
        return True
    
    def cleanup(self) -> None:
        """Clean up all device resources."""
        if not self._initialized:
            return
        
        try:
            for name, device in self.devices.items():
                try:
                    device.close()
                except Exception as e:
                    logger.error(f"Error cleaning up device '{name}': {e}")
            
            self.devices.clear()
            self._initialized = False
            logger.info("IO Controller cleaned up")
            
        except Exception as e:
            logger.error(f"Error during IO cleanup: {e}")
    
    # ==================== Read/Write Operations ====================
    
    def read(self, name: str) -> Optional[Union[bool, float]]:
        """
        Read value from a device.
        
        Args:
            name: Device name
            
        Returns:
            Device value (bool for digital, float for analog), or None on error
        """
        if not self._initialized:
            logger.warning("IO not initialized. Call initialize() first.")
            return None
        
        device = self.devices.get(name)
        if device is None:
            logger.error(f"Device '{name}' not found")
            return None
        
        try:
            return device.read()
        except Exception as e:
            logger.error(f"Failed to read from device '{name}': {e}")
            return None
    
    def write(self, name: str, value: Union[bool, float]) -> bool:
        """
        Write value to a device.
        
        Args:
            name: Device name
            value: Value to write (bool for digital, float for analog)
            
        Returns:
            True if successful, False on error
        """
        if not self._initialized:
            logger.warning("IO not initialized. Call initialize() first.")
            return False
        
        device = self.devices.get(name)
        if device is None:
            logger.error(f"Device '{name}' not found")
            return False
        
        try:
            return device.write(value)
        except Exception as e:
            logger.error(f"Failed to write to device '{name}': {e}")
            return False
    
    def read_all(self) -> Dict[str, Optional[Union[bool, float]]]:
        """
        Read values from all devices.
        
        Returns:
            Dictionary mapping device names to their values
        """
        if not self._initialized:
            logger.warning("IO not initialized. Call initialize() first.")
            return {}
        
        results = {}
        for name, device in self.devices.items():
            try:
                results[name] = device.read()
            except Exception as e:
                logger.error(f"Failed to read from device '{name}': {e}")
                results[name] = None
        return results
    
    def write_all(self, value: Union[bool, float]) -> Dict[str, bool]:
        """
        Write value to all writable devices.
        
        Args:
            value: Value to write
            
        Returns:
            Dictionary mapping device names to success status
        """
        if not self._initialized:
            logger.warning("IO not initialized. Call initialize() first.")
            return {}
        
        results = {}
        for name, device in self.devices.items():
            try:
                results[name] = device.write(value)
            except Exception as e:
                logger.error(f"Failed to write to device '{name}': {e}")
                results[name] = False
        return results
    
    # ==================== Device-Specific Operations ====================
    
    def reset_latch(self, name: str) -> Optional[bool]:
        """
        Reset the latched state of a latching button.
        
        Args:
            name: Device name
            
        Returns:
            True if successful, None on error
        """
        device = self.devices.get(name)
        if device is None:
            logger.error(f"Device '{name}' not found")
            return None
        
        if hasattr(device, 'reset_latch'):
            try:
                device.reset_latch()
                return True
            except Exception as e:
                logger.error(f"Failed to reset latch for device '{name}': {e}")
                return None
        else:
            logger.warning(f"Device '{name}' does not support latch reset")
            return None

    def toggle(self, name: str) -> Optional[bool]:
        """
        Toggle a device state (for devices that support it).
        
        Args:
            name: Device name
            
        Returns:
            New state if successful, None on error
        """
        device = self.devices.get(name)
        if device is None:
            logger.error(f"Device '{name}' not found")
            return None
        
        if hasattr(device, 'toggle'):
            try:
                return device.toggle()
            except Exception as e:
                logger.error(f"Failed to toggle device '{name}': {e}")
                return None
        else:
            # For devices without toggle, do read-then-write
            current = self.read(name)
            if current is None:
                return None
            new_state = not current if isinstance(current, bool) else None
            if new_state is not None and self.write(name, new_state):
                return new_state
            return None
    
    def get_device_status(self, name: str) -> Dict[str, Any]:
        """
        Get detailed status of a specific device.
        
        Args:
            name: Device name
            
        Returns:
            Dictionary with device information
        """
        config = self.configs.get(name)
        device = self.devices.get(name)
        
        if config is None:
            return {"error": f"Device '{name}' not found"}
        
        value = device.read() if device else None
        
        return {
            "name": name,
            "type": config.device_type.value,
            "description": config.description,
            "direction": config.direction.value,
            "identifier": config.identifier,
            "value": value,
            "is_connected": device.is_connected if device else False,
        }
    
    # ==================== Bulk Operations ====================
    
    def set_all_outputs(self, value: Union[bool, float]) -> Dict[str, bool]:
        """
        Set all output devices to a value.
        
        Args:
            value: Value to set
            
        Returns:
            Dictionary mapping device names to success status
        """
        results = {}
        for name, config in self.configs.items():
            if config.direction == DeviceDirection.OUTPUT:
                results[name] = self.write(name, value)
        return results
    
    def read_all_inputs(self) -> Dict[str, Optional[Union[bool, float]]]:
        """
        Read all input devices.
        
        Returns:
            Dictionary mapping device names to their values
        """
        results = {}
        for name, config in self.configs.items():
            if config.direction == DeviceDirection.INPUT:
                results[name] = self.read(name)
        return results
    
    # ==================== Utility Methods ====================
    
    def get_output_devices(self) -> List[str]:
        """
        Get the current status of the IO controller (backward compatibility).
        
        Returns:
            Dictionary containing:
            - initialized: Whether IO is initialized
            - device_count: Number of configured devices
            - devices: Information about all devices
        """
        device_info = {}
        for name, config in self.configs.items():
            device_info[name] = {
                "type": config.device_type.value,
                "description": config.description,
                "direction": config.direction.value,
            }
        
        return {
            "initialized": self._initialized,
            "device_count": len(self.devices),
            "device_config": device_info,
            "states": self.get_all_states(),
        }
    
    # ==================== Utility Methods ====================
    
    def get_output_devices(self) -> List[str]:
        """Get list of output device names."""
        return [name for name, config in self.configs.items() 
                if config.direction == DeviceDirection.OUTPUT]
    
    def get_input_devices(self) -> List[str]:
        """Get list of input device names."""
        return [name for name, config in self.configs.items() 
                if config.direction == DeviceDirection.INPUT]
    
    def get_devices_by_type(self, device_type: DeviceType) -> List[str]:
        """Get list of device names of a specific type."""
        return [name for name, config in self.configs.items() 
                if config.device_type == device_type]
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of the IO controller.
        
        Returns:
            Dictionary containing:
            - initialized: Whether IO is initialized
            - device_count: Number of configured devices
            - devices: Information about all devices
            - states: Current state of all devices
        """
        device_info = {}
        for name, config in self.configs.items():
            device_info[name] = {
                "type": config.device_type.value,
                "description": config.description,
                "direction": config.direction.value,
            }
        
        return {
            "initialized": self._initialized,
            "device_count": len(self.devices),
            "device_config": device_info,
            "states": self.read_all(),
        }
    
    # ==================== Configuration Persistence ====================
    
    def save_config(self, path: str = None) -> bool:
        """
        Save all device configurations to a JSON file.
        
        Args:
            path: Path to save the configuration file (uses IO_CONFIG_FILE env var if not provided)
            
        Returns:
            True if saved successfully, False otherwise
        """
        from io_config import save_config as _save_config, get_config_path
        
        save_path = path or get_config_path()
        return _save_config(self.configs, save_path)
    
    def load_config(self, path: str = None) -> bool:
        """
        Load device configurations from a JSON file and add them to the controller.
        
        Args:
            path: Path to the configuration file (uses IO_CONFIG_FILE env var if not provided)
            
        Returns:
            True if loaded successfully, False otherwise
        """
        from io_config import load_config as _load_config, get_config_path
        
        load_path = path or get_config_path()
        configs = _load_config(load_path)
        
        if configs is None:
            return False
        
        for name, config in configs.items():
            try:
                self.add_device(config)
            except Exception as e:
                logger.error(f"Failed to add device '{name}' from config: {e}")
                return False
        
        logger.info(f"Loaded {len(configs)} device configurations")
        return True
    
    def clear_config(self) -> None:
        """Clear all device configurations."""
        self.configs.clear()
        self.devices.clear()
        logger.info("Cleared all device configurations")
