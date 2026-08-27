"""
IO Controller Module - Generic controller for all IO devices on Raspberry Pi.

This module provides a unified interface for managing various IO devices:
- LEDs (digital output)
- Potentiometers (analog input)
- Buttons (digital input)
- PWM outputs
- And more

It uses the devices module for device-specific implementations.

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
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

# Handle both relative and absolute imports
try:
    from .devices import (
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
        LCDConfig,
        validate_device_config,
        RASPBERRY_PI_VALID_GPIO,
    )
except ImportError:
    # Fallback to absolute import when running as standalone
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
        LCDConfig,
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
    
    def __post_init__(self):
        """Initialize the controller."""
        self.devices = {}
        self.configs = {}
        self._initialized = False
    
    # ==================== Device Management ====================
    
    def add_device(self, config: DeviceConfig) -> None:
        """
        Add a device to the controller configuration.
        
        Args:
            config: Device configuration
            
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
    
    def initialize(self) -> bool:
        """
        Initialize all configured devices.
        
        Returns:
            True if initialization succeeded, False otherwise
        """
        if self._initialized:
            logger.warning("IO already initialized")
            return True
        
        self._initialized = True
        
        factory = DeviceFactory()
        
        init_errors = []
        for name, config in self.configs.items():
            try:
                device = factory.create_device(config)
                
                self.devices[name] = device
                logger.info(f"Initialized device '{name}' (type: {config.device_type.value})")
                
            except Exception as e:
                error_msg = f"Failed to initialize device '{name}': {e}"
                logger.error(error_msg)
                init_errors.append(error_msg)
        
        if init_errors:
            for error in init_errors:
                logger.error(error)
            logger.warning(f"Initialized {len(self.devices)}/{len(self.configs)} devices (some failed)")
        else:
            logger.info(f"IO Controller initialized with {len(self.devices)} devices")
        
        # Blink all LEDs at startup for visual confirmation
        import time
        led_devices = [name for name, config in self.configs.items() 
                       if config.device_type == DeviceType.LED]
        if led_devices:
            logger.info(f"Blinking {len(led_devices)} LEDs at startup...")
            for _ in range(3):  # Blink 3 times
                for name in led_devices:
                    self.write(name, True)
                time.sleep(0.3)
                for name in led_devices:
                    self.write(name, False)
                time.sleep(0.3)
            logger.info("LED blink sequence complete")
        
        return len(self.devices) > 0
    
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
        self._initialized = False
        logger.info("Cleared all device configurations")


# ==================== ACSI Server Integration ====================


class ACSIConfig:
    """Configuration for ACSI server connection."""
    
    def __init__(self, url: str = "http://localhost:5001", enabled: bool = False):
        self.url = url
        self.enabled = enabled
    
    def to_dict(self) -> Dict[str, Any]:
        return {"url": self.url, "enabled": self.enabled}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ACSIConfig":
        return cls(
            url=data.get("url", "http://localhost:5001"),
            enabled=data.get("enabled", False)
        )


# Global ACSI configuration
_acsi_config: Optional[ACSIConfig] = None
_device_mappings: Dict[str, Dict[str, Any]] = {}  # device_name -> {"objRef": ..., "fc": ...}


def configure_acsi(acsi_config: ACSIConfig, device_mappings: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
    """Configure ACSI server connection and device mappings.
    
    Args:
        acsi_config: ACSI server configuration
        device_mappings: Optional dict mapping device names to {"objRef": ..., "fc": ...}
    """
    global _acsi_config, _device_mappings
    _acsi_config = acsi_config
    if device_mappings:
        _device_mappings = device_mappings
    logger.info(f"ACSI server configured: {acsi_config.url} (enabled={acsi_config.enabled})")
    if device_mappings:
        logger.info(f"Loaded {len(device_mappings)} device mappings for ACSI")


def get_acsi_config() -> Optional[ACSIConfig]:
    """Get the current ACSI configuration."""
    return _acsi_config


def get_device_mapping(device_name: str) -> Optional[Dict[str, Any]]:
    """Get the ACSI mapping for a device."""
    return _device_mappings.get(device_name)


async def write_to_acsi_async(obj_ref: str, value: Any, fc: str = "ST") -> bool:
    """Write a value to the ACSI server via HTTP POST (async version).
    
    Args:
        obj_ref: IEC61850 object reference
        value: Value to write
        fc: Functional constraint
        
    Returns:
        True if write succeeded, False otherwise
    """
    if not _acsi_config or not _acsi_config.enabled:
        logger.debug("ACSI server not configured or disabled, skipping write")
        return False
    
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as http_client:
            response = await http_client.post(
                f"{_acsi_config.url}/api/writevalue",
                json={
                    "objRef": obj_ref,
                    "fc": fc,
                    "value": str(value),
                    "dataType": ""
                }
            )
            if response.status_code == 200:
                logger.info(f"ACSI write successful: {obj_ref}={value}")
                return True
            logger.error(f"ACSI write failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"ACSI write error: {e}")
        return False


def write_to_acsi(obj_ref: str, value: Any, fc: str = "ST") -> bool:
    """Write a value to the ACSI server via HTTP POST (synchronous version).
    
    Args:
        obj_ref: IEC61850 object reference
        value: Value to write
        fc: Functional constraint
        
    Returns:
        True if write succeeded, False otherwise
    """
    if not _acsi_config or not _acsi_config.enabled:
        logger.debug("ACSI server not configured or disabled, skipping write")
        return False
    
    try:
        import httpx
        with httpx.Client(timeout=5.0) as http_client:
            response = http_client.post(
                f"{_acsi_config.url}/api/writevalue",
                json={
                    "objRef": obj_ref,
                    "fc": fc,
                    "value": str(value),
                    "dataType": ""
                }
            )
            if response.status_code == 200:
                logger.info(f"ACSI write successful: {obj_ref}={value}")
                return True
            logger.error(f"ACSI write failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"ACSI write error: {e}")
        return False


def sync_device_to_acsi(device_name: str, value: Any) -> bool:
    """Sync an IO device change to ACSI server if mapping exists (synchronous version).
    
    Args:
        device_name: Name of the IO device that changed
        value: New value of the device
        
    Returns:
        True if sync succeeded, False otherwise
    """
    mapping = get_device_mapping(device_name)
    if not mapping:
        return False
    
    obj_ref = mapping.get("objRef")
    fc = mapping.get("fc", "ST")
    
    if not obj_ref:
        return False
    
    return write_to_acsi(obj_ref, value, fc)


async def sync_device_to_acsi_async(device_name: str, value: Any) -> bool:
    """Sync an IO device change to ACSI server if mapping exists (async version).
    
    Args:
        device_name: Name of the IO device that changed
        value: New value of the device
        
    Returns:
        True if sync succeeded, False otherwise
    """
    mapping = get_device_mapping(device_name)
    if not mapping:
        return False
    
    obj_ref = mapping.get("objRef")
    fc = mapping.get("fc", "ST")
    
    if not obj_ref:
        return False
    
    return await write_to_acsi_async(obj_ref, value, fc)


# Global IOController instance
_io_controller: Optional[IOController] = None


def get_io_controller() -> Optional[IOController]:
    """Get the global IOController instance, creating it if necessary."""
    global _io_controller
    if _io_controller is None:
        _io_controller = IOController()
    return _io_controller
