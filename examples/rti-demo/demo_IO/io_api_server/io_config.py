"""
IO Configuration Manager - Save and load IO device configurations to/from JSON files.

This module provides:
- Loading/saving IO device configurations from JSON files
- Converting between JSON config and device config objects
- API endpoints for managing configurations
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from devices import (
    DeviceConfig,
    DeviceType,
    DeviceDirection,
    LEDConfig,
    ButtonConfig,
    PotentiometerConfig,
    PWMConfig,
    LCDConfig,
    LCDI2CConfig,
)

logger = logging.getLogger(__name__)


# ==================== CONFIG FILE FORMAT ====================
#
# The JSON config file has this structure:
# {
#     "devices": [
#         {
#             "name": "led1",
#             "type": "led",
#             "device_type": "led",
#             "identifier": 17,
#             "gpio_pin": 17,
#             "description": "LED 1 on GPIO 17",
#             "direction": "output",
#             "initial_state": false,
#             "is_active_high": true
#         },
#         {
#             "name": "button1",
#             "type": "button",
#             "device_type": "button",
#             "identifier": 10,
#             "gpio_pin": 10,
#             "description": "Button on GPIO 10",
#             "direction": "input",
#             "debounce_time": 0.05,
#             "pull_up": true,
#             "latching": true
#         }
#     ]
# }


DEFAULT_CONFIG_FILE = "io_config.json"


def get_default_config_path() -> str:
    """Get the default config path, first checking script directory, then current directory."""
    import os
    from pathlib import Path
    
    # Try to get the script directory
    script_dir = Path(__file__).parent
    script_config = script_dir / DEFAULT_CONFIG_FILE
    
    if script_config.exists():
        return str(script_config)
    
    # Fall back to current directory
    return DEFAULT_CONFIG_FILE


def _config_to_dict(config: DeviceConfig) -> Dict[str, Any]:
    """Convert a device config object to a dictionary for JSON serialization."""
    base_dict = {
        "name": config.name,
        "device_type": config.device_type.value,
        "identifier": config.identifier,
        "description": config.description,
        "direction": config.direction.value,
    }
    
    # Add type-specific fields
    if config.device_type == DeviceType.LED:
        base_dict["type"] = "led"
        base_dict["gpio_pin"] = config.identifier if isinstance(config.identifier, int) else 0
        base_dict["initial_state"] = getattr(config, "initial_state", False)
        base_dict["is_active_high"] = getattr(config, "is_active_high", True)
    
    elif config.device_type == DeviceType.BUTTON:
        base_dict["type"] = "button"
        base_dict["gpio_pin"] = config.identifier if isinstance(config.identifier, int) else 0
        base_dict["debounce_time"] = getattr(config, "debounce_time", 0.05)
        base_dict["pull_up"] = getattr(config, "pull_up", True)
        base_dict["latching"] = getattr(config, "latching", False)
        base_dict["is_active_high"] = getattr(config, "is_active_high", True)
    
    elif config.device_type == DeviceType.POTENTIOMETER:
        base_dict["type"] = "potentiometer"
        base_dict["adc_channel"] = config.identifier if isinstance(config.identifier, int) else 0
        base_dict["min_value"] = getattr(config, "min_value", 0.0)
        base_dict["max_value"] = getattr(config, "max_value", 100.0)
        base_dict["i2c_address"] = getattr(config, "i2c_address", 0x48)
        base_dict["i2c_bus"] = getattr(config, "i2c_bus", 1)
        base_dict["adc_type"] = getattr(config, "adc_type", "ads1115")
    
    elif config.device_type == DeviceType.PWM:
        base_dict["type"] = "pwm"
        base_dict["gpio_pin"] = config.identifier if isinstance(config.identifier, int) else 0
        base_dict["frequency"] = getattr(config, "frequency", 100)
        base_dict["initial_duty_cycle"] = getattr(config, "initial_duty_cycle", 0.0)
    
    elif config.device_type == DeviceType.LCD:
        base_dict["type"] = "lcd"
        base_dict["gpio_rs"] = getattr(config, "gpio_rs", 26)
        base_dict["gpio_e"] = getattr(config, "gpio_e", 19)
        base_dict["gpio_data"] = getattr(config, "gpio_data", [13, 12, 16, 20])
        base_dict["gpio_rw"] = getattr(config, "gpio_rw", None)
        base_dict["columns"] = getattr(config, "columns", 16)
        base_dict["rows"] = getattr(config, "rows", 2)
        base_dict["backlight"] = getattr(config, "backlight", True)
        base_dict["backlight_pin"] = getattr(config, "backlight_pin", None)
    
    elif config.device_type == DeviceType.LCD_I2C:
        base_dict["type"] = "lcd_i2c"
        base_dict["i2c_address"] = getattr(config, "i2c_address", 0x27)
        base_dict["i2c_bus"] = getattr(config, "i2c_bus", 1)
        base_dict["columns"] = getattr(config, "columns", 16)
        base_dict["rows"] = getattr(config, "rows", 2)
        base_dict["backlight"] = getattr(config, "backlight", True)
        base_dict["rs_bit"] = getattr(config, "rs_bit", 0)
        base_dict["rw_bit"] = getattr(config, "rw_bit", 1)
        base_dict["e_bit"] = getattr(config, "e_bit", 2)
        base_dict["backlight_bit"] = getattr(config, "backlight_bit", 3)
        base_dict["d4_bit"] = getattr(config, "d4_bit", 4)
        base_dict["d5_bit"] = getattr(config, "d5_bit", 5)
        base_dict["d6_bit"] = getattr(config, "d6_bit", 6)
        base_dict["d7_bit"] = getattr(config, "d7_bit", 7)
    
    return base_dict


def _dict_to_config(device_dict: Dict[str, Any]) -> Optional[DeviceConfig]:
    """Convert a dictionary from JSON to a device config object."""
    device_type_str = device_dict.get("device_type", "").lower()
    
    try:
        if device_type_str == "led" or device_dict.get("type") == "led":
            return LEDConfig(
                name=device_dict.get("name", ""),
                gpio_pin=device_dict.get("gpio_pin", device_dict.get("identifier", 0)),
                description=device_dict.get("description", ""),
                initial_state=device_dict.get("initial_state", False),
                is_active_high=device_dict.get("is_active_high", True),
            )
        
        elif device_type_str == "button" or device_dict.get("type") == "button":
            return ButtonConfig(
                name=device_dict.get("name", ""),
                gpio_pin=device_dict.get("gpio_pin", device_dict.get("identifier", 0)),
                description=device_dict.get("description", ""),
                debounce_time=device_dict.get("debounce_time", 0.05),
                pull_up=device_dict.get("pull_up", True),
                latching=device_dict.get("latching", False),
                is_active_high=device_dict.get("is_active_high", True),
            )
        
        elif device_type_str == "potentiometer" or device_dict.get("type") == "potentiometer":
            return PotentiometerConfig(
                name=device_dict.get("name", ""),
                adc_channel=device_dict.get("adc_channel", device_dict.get("identifier", 0)),
                description=device_dict.get("description", ""),
                min_value=device_dict.get("min_value", 0.0),
                max_value=device_dict.get("max_value", 100.0),
                i2c_address=device_dict.get("i2c_address", 0x48),
                i2c_bus=device_dict.get("i2c_bus", 1),
                adc_type=device_dict.get("adc_type", "ads1115"),
            )
        
        elif device_type_str == "pwm" or device_dict.get("type") == "pwm":
            return PWMConfig(
                name=device_dict.get("name", ""),
                gpio_pin=device_dict.get("gpio_pin", device_dict.get("identifier", 0)),
                description=device_dict.get("description", ""),
                frequency=device_dict.get("frequency", 100),
                initial_duty_cycle=device_dict.get("initial_duty_cycle", 0.0),
            )
        
        elif device_type_str == "lcd" or device_dict.get("type") == "lcd":
            return LCDConfig(
                name=device_dict.get("name", ""),
                gpio_rs=device_dict.get("gpio_rs", 26),
                gpio_e=device_dict.get("gpio_e", 19),
                gpio_data=device_dict.get("gpio_data", [13, 12, 16, 20]),
                gpio_rw=device_dict.get("gpio_rw", None),
                columns=device_dict.get("columns", 16),
                rows=device_dict.get("rows", 2),
                backlight=device_dict.get("backlight", True),
                backlight_pin=device_dict.get("backlight_pin", None),
                description=device_dict.get("description", ""),
            )
        
        elif device_type_str == "lcd_i2c" or device_dict.get("type") == "lcd_i2c":
            return LCDI2CConfig(
                name=device_dict.get("name", ""),
                identifier=device_dict.get("identifier", 0),
                description=device_dict.get("description", ""),
                i2c_address=device_dict.get("i2c_address", 0x27),
                i2c_bus=device_dict.get("i2c_bus", 1),
                columns=device_dict.get("columns", 16),
                rows=device_dict.get("rows", 2),
                backlight=device_dict.get("backlight", True),
                rs_bit=device_dict.get("rs_bit", 0),
                rw_bit=device_dict.get("rw_bit", 1),
                e_bit=device_dict.get("e_bit", 2),
                backlight_bit=device_dict.get("backlight_bit", 3),
                d4_bit=device_dict.get("d4_bit", 4),
                d5_bit=device_dict.get("d5_bit", 5),
                d6_bit=device_dict.get("d6_bit", 6),
                d7_bit=device_dict.get("d7_bit", 7),
            )
        
        else:
            logger.warning(f"Unknown device type: {device_type_str}")
            return None
            
    except Exception as e:
        logger.error(f"Failed to create config from dict: {e}")
        return None


def save_config(configs: Dict[str, DeviceConfig], path: str = DEFAULT_CONFIG_FILE) -> bool:
    """
    Save IO device configurations to a JSON file.
    
    Args:
        configs: Dictionary of device name to DeviceConfig objects
        path: Path to the JSON file
        
    Returns:
        True if saved successfully, False otherwise
    """
    try:
        devices_list = []
        for name, config in configs.items():
            devices_list.append(_config_to_dict(config))
        
        config_data = {
            "devices": devices_list,
            "version": 1
        }
        
        # Ensure directory exists
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved IO configuration to {path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to save IO configuration: {e}")
        return False


def load_config(path: str = DEFAULT_CONFIG_FILE) -> Optional[Dict[str, DeviceConfig]]:
    """
    Load IO device configurations from a JSON file.
    
    Args:
        path: Path to the JSON file
        
    Returns:
        Dictionary of device name to DeviceConfig objects, or None on error
    """
    if not os.path.exists(path):
        logger.warning(f"IO configuration file not found: {path}")
        return None
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            config_data = json.load(f)
        
        configs = {}
        for device_dict in config_data.get("devices", []):
            config = _dict_to_config(device_dict)
            if config:
                configs[config.name] = config
        
        if configs:
            logger.info(f"Loaded {len(configs)} device configurations from {path}")
        return configs
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in IO configuration file {path}: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to load IO configuration from {path}: {e}")
        return None


def get_config_path() -> str:
    """Get the path to the IO configuration file from environment or default."""
    env_path = os.getenv("IO_CONFIG_FILE")
    if env_path:
        return env_path
    return get_default_config_path()


def load_full_config(path: str = DEFAULT_CONFIG_FILE) -> Optional[Dict[str, Any]]:
    """
    Load full IO configuration from a JSON file, including devices, ACSI server, and mappings.
    
    Args:
        path: Path to the JSON file
        
    Returns:
        Full configuration dictionary or None on error
    """
    if not os.path.exists(path):
        logger.warning(f"IO configuration file not found: {path}")
        return None
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in IO configuration file {path}: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to load IO configuration from {path}: {e}")
        return None


def save_full_config(
    devices_config: Optional[Dict[str, DeviceConfig]] = None,
    acsi_config: Optional[Dict[str, Any]] = None,
    device_mappings: Optional[Dict[str, Dict[str, Any]]] = None,
    path: str = DEFAULT_CONFIG_FILE
) -> bool:
    """
    Save full IO configuration to a JSON file, including devices, ACSI server, and mappings.
    
    Args:
        devices_config: Dictionary of device name to DeviceConfig objects
        acsi_config: ACSI server configuration dict with 'url' and 'enabled' keys
        device_mappings: Dictionary of device name to mapping dict
        path: Path to the JSON file
        
    Returns:
        True if saved successfully, False otherwise
    """
    try:
        config_data: Dict[str, Any] = {}
        
        # Save devices
        if devices_config:
            devices_list = []
            for name, config in devices_config.items():
                devices_list.append(_config_to_dict(config))
            config_data["devices"] = devices_list
        
        # Save version
        config_data["version"] = 1
        
        # Save ACSI config if provided
        if acsi_config:
            config_data["acsi_server"] = acsi_config
        
        # Save mappings if provided
        if device_mappings:
            config_data["mappings"] = device_mappings
        
        # Ensure directory exists
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved full IO configuration to {path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to save full IO configuration: {e}")
        return False


def create_default_config() -> Dict[str, DeviceConfig]:
    """Create a default IO configuration with common devices."""
    from devices import DeviceType, DeviceDirection
    
    return {
        "led1": LEDConfig(
            name="led1",
            gpio_pin=17,
            description="LED 1 on GPIO 17 (Pin 11)",
            initial_state=False
        ),
        "led2": LEDConfig(
            name="led2",
            gpio_pin=18,
            description="LED 2 on GPIO 18 (Pin 12)",
            initial_state=False
        ),
        "led3": LEDConfig(
            name="led3",
            gpio_pin=22,
            description="LED 3 on GPIO 22 (Pin 15)",
            initial_state=False
        ),
        "button1": ButtonConfig(
            name="button1",
            gpio_pin=10,
            description="Button on GPIO 10 (Pin 19)",
            debounce_time=0.05,
            pull_up=False,
            latching=True
        ),
    }
