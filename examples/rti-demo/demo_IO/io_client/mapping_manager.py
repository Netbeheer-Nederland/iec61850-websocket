"""
IO Mapping Manager - Manages mapping between IEC 61850 object references and IO device configurations.

This module provides:
- Loading/saving IO device configurations with IEC 61850 objRef mappings from JSON
- Querying mappings by objRef or device name
- Synchronizing IO device states when IEC 61850 values change
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class IOMappingManager:
    """Manages the bidirectional mapping between IEC 61850 object references and IO device configurations.

    The mapping file stores IO device configurations with an optional objRef field
    for IEC 61850 integration. This allows:
    - Configuring IO devices with their IEC 61850 counterpart
    - Finding IO devices by objRef when writing IEC 61850 values
    - Synchronizing IO device states with IEC 61850 writes

    Usage:
        manager = IOMappingManager(mapping_file="io_mapping.json")

        # Add a mapping
        manager.add_mapping(
            device_name="device1",
            obj_ref="LD0/GGIO1$ST$Ind1",
            gpio_pin=17,
            description="GGIO Indication 1"
        )

        # Find IO device by objRef
        device_config = manager.get_device_by_objref("LD0/GGIO1$ST$Ind1")
        # Returns: {"device_name": "device1", "gpio_pin": 17, "objRef": "LD0/GGIO1$ST$Ind1", ...}

        # Get all mappings
        all_mappings = manager.get_all_mappings()
    """

    DEFAULT_MAPPING_FILE = "io_mapping.json"

    def __init__(self, mapping_file: Optional[str] = None, mapping_dir: Optional[str] = None):
        """Initialize the mapping manager.

        Args:
            mapping_file: Path to the mapping JSON file (relative or absolute)
            mapping_dir: Directory to look for the mapping file (default: same as this module)
        """
        if mapping_file:
            self.mapping_path = Path(mapping_file)
        else:
            # Default: look for io_mapping.json in the same directory as this module
            module_dir = Path(__file__).parent
            self.mapping_path = module_dir / self.DEFAULT_MAPPING_FILE

        self._mappings: Dict[str, Dict[str, Any]] = {}
        self._objref_index: Dict[str, List[str]] = {}  # objRef -> list of device_names

        # Load existing mappings
        self.load()

    def load(self, path: Optional[str] = None) -> bool:
        """Load mappings from JSON file.

        Args:
            path: Optional path override (default: uses self.mapping_path)

        Returns:
            bool: True if loaded successfully, False otherwise
        """
        load_path = Path(path) if path else self.mapping_path

        if not load_path.exists():
            logger.warning(f"Mapping file not found: {load_path}")
            self._mappings = {}
            self._objref_index = {}
            return False

        try:
            with open(load_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Handle both formats: flat dict or {"leds": {...}, "buttons": {...}, etc.}
            if isinstance(data, dict):
                # Normalize all device type sections (leds, buttons, potentiometers, etc.)
                self._mappings = {}
                
                # Process each device type section
                for device_type_section in ["leds", "buttons", "potentiometers", "sensors"]:
                    if device_type_section in data:
                        for key, config in data[device_type_section].items():
                            device_name = key
                            # Normalize the config to include device_name
                            normalized_config = {k: v for k, v in config.items() if k != "led_name"}
                            self._mappings[device_name] = {
                                **normalized_config,
                                "device_name": device_name
                            }
                
                # Also handle old objRef-indexed format for backward compatibility
                if not self._mappings and "mappings" in data:
                    # Convert from objRef-indexed format
                    self._mappings = {}
                    for objref, device_config in data["mappings"].items():
                        device_name = device_config.get("device_name") or device_config.get("led_name", objref)
                        # Normalize the config to use device_name
                        normalized_config = {k: v for k, v in device_config.items() if k != "led_name"}
                        self._mappings[device_name] = {
                            **normalized_config,
                            "device_name": device_name,
                            "objRef": objref
                        }

            # Build objRef index (support multiple devices per objRef)
            self._objref_index = {}
            for device_name, config in self._mappings.items():
                objref = config.get("objRef")
                if objref:
                    if objref not in self._objref_index:
                        self._objref_index[objref] = []
                    self._objref_index[objref].append(device_name)

            logger.info(f"Loaded {len(self._mappings)} IO device mappings from {load_path}")
            return True

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in mapping file {load_path}: {e}")
            self._mappings = {}
            self._objref_index = {}
            return False
        except Exception as e:
            logger.error(f"Failed to load mapping file {load_path}: {e}")
            self._mappings = {}
            self._objref_index = {}
            return False

    def save(self, path: Optional[str] = None) -> bool:
        """Save mappings to JSON file.

        Args:
            path: Optional path override (default: uses self.mapping_path)

        Returns:
            bool: True if saved successfully, False otherwise
        """
        save_path = Path(path) if path else self.mapping_path

        try:
            # Organize mappings by device type based on direction
            leds = {k: v for k, v in self._mappings.items() 
                    if v.get("direction") == "output" or not v.get("direction")}
            buttons = {k: v for k, v in self._mappings.items() 
                      if v.get("direction") == "input" and v.get("device_type") == "button"}
            potentiometers = {k: v for k, v in self._mappings.items() 
                            if v.get("direction") == "input" and v.get("device_type") == "potentiometer"}
            # Input devices without specific device_type
            other_inputs = {k: v for k, v in self._mappings.items() 
                           if v.get("direction") == "input" and v.get("device_type") not in ["button", "potentiometer"]}
            
            # Build data structure
            data = {}
            if leds:
                data["leds"] = leds
            if buttons:
                data["buttons"] = buttons
            if potentiometers:
                data["potentiometers"] = potentiometers
            if other_inputs:
                data["inputs"] = other_inputs
            
            # If no type was specified, use flat format for backward compatibility
            if not data:
                data = {"leds": self._mappings}

            # Ensure parent directory exists
            save_path.parent.mkdir(parents=True, exist_ok=True)

            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.info(f"Saved {len(self._mappings)} IO device mappings to {save_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save mapping file {save_path}: {e}")
            return False

    # ==================== Mapping CRUD Operations ====================

    def add_mapping(
        self,
        device_name: str,
        obj_ref: Optional[str] = None,
        description: str = "",
        initial_state: bool = False,
        **extra_properties: Any
    ) -> Dict[str, Any]:
        """Add or update a mapping.

        Args:
            device_name: Unique IO device identifier
            obj_ref: IEC 61850 object reference (optional)
            description: IO device description
            initial_state: Initial IO device state
            **extra_properties: Additional custom properties

        Returns:
            dict: The stored mapping configuration
        """
        config: Dict[str, Any] = {
            "device_name": device_name,
        }

        if obj_ref is not None:
            config["objRef"] = obj_ref
        if description:
            config["description"] = description
        if initial_state:
            config["initial_state"] = initial_state

        config.update(extra_properties)

        self._mappings[device_name] = config

        # Update objRef index (support multiple devices per objRef)
        if obj_ref:
            if obj_ref not in self._objref_index:
                self._objref_index[obj_ref] = []
            if device_name not in self._objref_index[obj_ref]:
                self._objref_index[obj_ref].append(device_name)

        logger.info(f"Added/updated mapping: {device_name} -> {obj_ref or 'N/A'}")

        return config

    def remove_mapping(self, device_name: str) -> bool:
        """Remove a mapping by IO device name.

        Args:
            device_name: IO device identifier to remove

        Returns:
            bool: True if removed, False if not found
        """
        if device_name not in self._mappings:
            return False

        # Remove from objRef index if present
        config = self._mappings[device_name]
        obj_ref = config.get("objRef")
        if obj_ref and obj_ref in self._objref_index:
            # Remove device_name from the list
            if device_name in self._objref_index[obj_ref]:
                self._objref_index[obj_ref].remove(device_name)
            # Clean up empty lists
            if not self._objref_index[obj_ref]:
                del self._objref_index[obj_ref]

        del self._mappings[device_name]
        logger.info(f"Removed mapping: {device_name}")

        return True

    def remove_mapping_by_objref(self, obj_ref: str) -> bool:
        """Remove a mapping by IEC 61850 object reference.

        Args:
            obj_ref: IEC 61850 object reference

        Returns:
            bool: True if at least one mapping was removed, False if not found
        """
        device_names = self._objref_index.get(obj_ref, [])
        if not device_names:
            return False

        # Remove all mappings for this objRef
        removed = False
        for device_name in device_names[:]:  # Copy list to avoid modification during iteration
            if self.remove_mapping(device_name):
                removed = True
        return removed

    def get_mapping(self, device_name: str) -> Optional[Dict[str, Any]]:
        """Get mapping configuration by IO device name.

        Args:
            device_name: IO device identifier

        Returns:
            dict: Mapping configuration, or None if not found
        """
        return self._mappings.get(device_name)

    def get_device_by_objref(self, obj_ref: str) -> Optional[Dict[str, Any]]:
        """Get IO device configuration by IEC 61850 object reference.

        Args:
            obj_ref: IEC 61850 object reference

        Returns:
            dict: IO device configuration with device_name, or None if not found
            Note: If multiple devices are mapped to the same objRef, returns the first one.
            Use get_devices_by_objref() to get all devices for an objRef.
        """
        device_names = self._objref_index.get(obj_ref, [])
        if not device_names:
            return None

        # Return the first device for backward compatibility
        device_name = device_names[0]
        config = self._mappings.get(device_name)
        if config:
            # Return copy with device_name included
            return {**config, "device_name": device_name}
        return None

    def get_devices_by_objref(self, obj_ref: str) -> List[Dict[str, Any]]:
        """Get all IO device configurations mapped to an IEC 61850 object reference.

        Args:
            obj_ref: IEC 61850 object reference

        Returns:
            list: List of device configurations with device_name, empty list if not found
        """
        device_names = self._objref_index.get(obj_ref, [])
        results = []
        for device_name in device_names:
            config = self._mappings.get(device_name)
            if config:
                # Return copy with device_name included
                results.append({**config, "device_name": device_name})
        return results

    def get_all_mappings(self) -> Dict[str, Dict[str, Any]]:
        """Get all mappings.

        Returns:
            dict: All mappings indexed by device_name
        """
        return dict(self._mappings)

    def get_all_by_objref(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get all mappings indexed by objRef.

        Returns:
            dict: All mappings indexed by objRef (only those with objRef), each value is a list of device configs
        """
        result = {}
        for obj_ref, device_names in self._objref_index.items():
            configs = []
            for device_name in device_names:
                config = self._mappings.get(device_name)
                if config:
                    configs.append({**config, "device_name": device_name})
            if configs:
                result[obj_ref] = configs
        return result

    def clear(self) -> None:
        """Clear all mappings."""
        self._mappings = {}
        self._objref_index = {}
        logger.info("Cleared all mappings")

    # ==================== Sync Utilities ====================

    def sync_device_from_iec61850(
        self,
        obj_ref: str,
        value: Any,
        client: Any = None
    ) -> bool:
        """Synchronize IO device state based on IEC 61850 value.

        Args:
            obj_ref: IEC 61850 object reference that was written
            value: The value that was written
            client: Optional DemoIOClient instance for direct control

        Returns:
            bool: True if at least one IO device was synced, False if no mapping found
        """
        device_configs = self.get_devices_by_objref(obj_ref)
        if not device_configs:
            return False

        # Convert IEC 61850 value to boolean once
        device_state = self._convert_to_bool(value)
        
        synced = False
        for device_config in device_configs:
            device_name = device_config["device_name"]
            
            # Only sync to OUTPUT devices (LEDs, etc.) - not INPUT devices (buttons, potentiometers)
            device_direction = device_config.get("direction", "").lower()
            device_type = device_config.get("type", "").lower()
            
            # Skip input devices - they should not be written to from ACSI
            if device_direction == "input":
                logger.debug(f"Skipping sync to input device '{device_name}' (from {obj_ref}) - input devices are read-only")
                continue
            
            # Also skip known input device types
            if device_type in ("button", "potentiometer", "sensor"):
                logger.debug(f"Skipping sync to input device '{device_name}' (type: {device_type}) (from {obj_ref}) - input devices are read-only")
                continue

            if client:
                try:
                    # Call set_device - both sync and async clients have this method
                    # For async clients, the caller must handle awaiting
                    client.set_device(device_name, device_state)
                    logger.info(f"Synced IO device '{device_name}' to {device_state} (from {obj_ref}={value})")
                    synced = True
                except Exception as e:
                    logger.error(f"Failed to sync IO device '{device_name}': {e}")
        
        return synced
    
    async def sync_device_from_iec61850_async(
        self,
        obj_ref: str,
        value: Any,
        client: Any = None
    ) -> bool:
        """Async version of sync_device_from_iec61850 for async clients."""
        device_configs = self.get_devices_by_objref(obj_ref)
        if not device_configs:
            return False

        # Convert IEC 61850 value to boolean once
        device_state = self._convert_to_bool(value)
        
        synced = False
        for device_config in device_configs:
            device_name = device_config["device_name"]
            
            # Only sync to OUTPUT devices (LEDs, etc.) - not INPUT devices (buttons, potentiometers)
            device_direction = device_config.get("direction", "").lower()
            device_type = device_config.get("type", "").lower()
            
            # Skip input devices - they should not be written to from ACSI
            if device_direction == "input":
                logger.debug(f"Skipping sync to input device '{device_name}' (from {obj_ref}) - input devices are read-only")
                continue
            
            # Also skip known input device types
            if device_type in ("button", "potentiometer", "sensor"):
                logger.debug(f"Skipping sync to input device '{device_name}' (type: {device_type}) (from {obj_ref}) - input devices are read-only")
                continue

            if client:
                try:
                    await client.set_device(device_name, device_state)
                    logger.info(f"Synced IO device '{device_name}' to {device_state} (from {obj_ref}={value})")
                    synced = True
                except Exception as e:
                    logger.error(f"Failed to sync IO device '{device_name}': {e}")
        
        return synced

    def _convert_to_bool(self, value: Any) -> bool:
        """Convert an IEC 61850 value to a boolean LED state."""
        if isinstance(value, bool):
            return value

        if isinstance(value, (int, float)):
            return bool(value)

        if isinstance(value, str):
            return value.upper() in (
                "ON", "TRUE", "1", "YES", "CLOSED", "OPEN", "ACTIVE"
            )

        return bool(value)

    # ==================== LED Configuration Sync ====================

    def config_device_with_mapping(
        self,
        device_name: str,
        gpio_pin: int,
        obj_ref: Optional[str] = None,
        description: str = "",
        initial_state: bool = False,
        **extra_properties: Any
    ) -> Dict[str, Any]:
        """Configure an IO device and add it to the mapping.

        This is a convenience method that:
        1. Adds the mapping to the manager (without gpio_pin - that's device-specific)
        2. Returns the config that can be sent to demo_io (which includes gpio_pin)

        Args:
            device_name: Unique IO device identifier
            gpio_pin: GPIO pin number (for demo_io device config, not stored in mapping)
            obj_ref: IEC 61850 object reference (optional)
            description: IO device description
            initial_state: Initial IO device state
            **extra_properties: Additional custom properties

        Returns:
            dict: Configuration suitable for demo_io config_led endpoint (includes gpio_pin)
        """
        # Add to mapping (without gpio_pin - that belongs to device config, not mapping)
        demoio_config = self.add_mapping(
            device_name=device_name,
            obj_ref=obj_ref,
            description=description,
            initial_state=initial_state,
            **extra_properties
        )

        # Return config for demo_io (includes gpio_pin for device configuration)
        return {
            "name": device_name,
            "gpio_pin": gpio_pin,
            "description": description or f"Mapped to {obj_ref}" if obj_ref else "",
            "initial_state": initial_state
        }

    def get_device_config_for_demoio(self, device_name: str) -> Optional[Dict[str, Any]]:
        """Get IO device configuration in the format expected by demo_io.
        
        Note: gpio_pin is NOT included as it's device-specific config stored in demo_io,
        not in the mapping.

        Args:
            device_name: IO device identifier

        Returns:
            dict: Configuration for demo_io config_led (without gpio_pin), or None if not found
        """
        config = self.get_mapping(device_name)
        if not config:
            return None

        return {
            "name": device_name,
            "description": config.get("description", ""),
            "initial_state": config.get("initial_state", False)
        }

    def get_all_device_configs_for_demoio(self) -> List[Dict[str, Any]]:
        """Get all IO device configurations in demo_io format.
        
        Note: gpio_pin is NOT included as it's device-specific config stored in demo_io,
        not in the mapping.

        Returns:
            list: All IO device configurations for bulk demo_io setup (without gpio_pin)
        """
        configs = []
        for device_name, config in self._mappings.items():
            configs.append({
                "name": device_name,
                "description": config.get("description", ""),
                "initial_state": config.get("initial_state", False)
            })
        return configs

    def list_mapped_devices(self) -> List[str]:
        """List all IO device names that have mappings.

        Returns:
            list: All IO device names with configurations
        """
        return list(self._mappings.keys())

    def list_mapped_objrefs(self) -> List[str]:
        """List all IEC 61850 object references that have mappings.

        Returns:
            list: All objRefs with IO device mappings
        """
        return list(self._objref_index.keys())
