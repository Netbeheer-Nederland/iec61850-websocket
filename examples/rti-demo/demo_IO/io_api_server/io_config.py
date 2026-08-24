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
    
    elif config.device_type == DeviceType.PWM:
        base_dict["type"] = "pwm"
        base_dict["gpio_pin"] = config.identifier if isinstance(config.identifier, int) else 0
        base_dict["frequency"] = getattr(config, "frequency", 100)
        base_dict["initial_duty_cycle"] = getattr(config, "initial_duty_cycle", 0.0)
    
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
            )
        
        elif device_type_str == "pwm" or device_dict.get("type") == "pwm":
            return PWMConfig(
                name=device_dict.get("name", ""),
                gpio_pin=device_dict.get("gpio_pin", device_dict.get("identifier", 0)),
                description=device_dict.get("description", ""),
                frequency=device_dict.get("frequency", 100),
                initial_duty_cycle=device_dict.get("initial_duty_cycle", 0.0),
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
    return os.getenv("IO_CONFIG_FILE", DEFAULT_CONFIG_FILE)


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
