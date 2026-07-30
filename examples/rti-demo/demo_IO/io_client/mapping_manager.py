"""
IO Mapping Manager - Manages mapping between IEC 61850 object references and LED configurations.

This module provides:
- Loading/saving LED configurations with IEC 61850 objRef mappings from JSON
- Querying mappings by objRef or LED name
- Synchronizing LED states when IEC 61850 values change
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class IOMappingManager:
    """Manages the bidirectional mapping between IEC 61850 object references and LED configurations.

    The mapping file stores LED configurations with an optional objRef field
    for IEC 61850 integration. This allows:
    - Configuring LEDs with their IEC 61850 counterpart
    - Finding LEDs by objRef when writing IEC 61850 values
    - Synchronizing LED states with IEC 61850 writes

    Usage:
        manager = IOMappingManager(mapping_file="io_mapping.json")

        # Add a mapping
        manager.add_mapping(
            led_name="led1",
            obj_ref="LD0/GGIO1$ST$Ind1",
            gpio_pin=17,
            description="GGIO Indication 1"
        )

        # Find LED by objRef
        led_config = manager.get_led_by_objref("LD0/GGIO1$ST$Ind1")
        # Returns: {"led_name": "led1", "gpio_pin": 17, "objRef": "LD0/GGIO1$ST$Ind1", ...}

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
        self._objref_index: Dict[str, str] = {}  # objRef -> led_name

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

            # Handle both formats: flat dict or {"leds": {...}}
            if isinstance(data, dict):
                if "leds" in data:
                    self._mappings = data["leds"]
                elif "mappings" in data:
                    # Convert from objRef-indexed format
                    self._mappings = {}
                    for objref, led_config in data["mappings"].items():
                        led_name = led_config.get("led_name", objref)
                        self._mappings[led_name] = {
                            **led_config,
                            "objRef": objref
                        }
                else:
                    # Assume it's already in led_name-indexed format
                    self._mappings = data

            # Build objRef index
            self._objref_index = {}
            for led_name, config in self._mappings.items():
                objref = config.get("objRef")
                if objref:
                    self._objref_index[objref] = led_name

            logger.info(f"Loaded {len(self._mappings)} LED mappings from {load_path}")
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
            # Save in led_name-indexed format
            data = {"leds": self._mappings}

            # Ensure parent directory exists
            save_path.parent.mkdir(parents=True, exist_ok=True)

            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.info(f"Saved {len(self._mappings)} LED mappings to {save_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save mapping file {save_path}: {e}")
            return False

    # ==================== Mapping CRUD Operations ====================

    def add_mapping(
        self,
        led_name: str,
        obj_ref: Optional[str] = None,
        gpio_pin: Optional[int] = None,
        description: str = "",
        initial_state: bool = False,
        **extra_properties: Any
    ) -> Dict[str, Any]:
        """Add or update a mapping.

        Args:
            led_name: Unique LED identifier
            obj_ref: IEC 61850 object reference (optional)
            gpio_pin: GPIO pin number
            description: LED description
            initial_state: Initial LED state
            **extra_properties: Additional custom properties

        Returns:
            dict: The stored mapping configuration
        """
        config: Dict[str, Any] = {
            "led_name": led_name,
        }

        if obj_ref is not None:
            config["objRef"] = obj_ref
        if gpio_pin is not None:
            config["gpio_pin"] = gpio_pin
        if description:
            config["description"] = description
        if initial_state:
            config["initial_state"] = initial_state

        config.update(extra_properties)

        self._mappings[led_name] = config

        # Update objRef index
        if obj_ref:
            self._objref_index[obj_ref] = led_name

        logger.info(f"Added/updated mapping: {led_name} -> {obj_ref or 'N/A'}")

        return config

    def remove_mapping(self, led_name: str) -> bool:
        """Remove a mapping by LED name.

        Args:
            led_name: LED identifier to remove

        Returns:
            bool: True if removed, False if not found
        """
        if led_name not in self._mappings:
            return False

        # Remove from objRef index if present
        config = self._mappings[led_name]
        obj_ref = config.get("objRef")
        if obj_ref and obj_ref in self._objref_index:
            del self._objref_index[obj_ref]

        del self._mappings[led_name]
        logger.info(f"Removed mapping: {led_name}")

        return True

    def remove_mapping_by_objref(self, obj_ref: str) -> bool:
        """Remove a mapping by IEC 61850 object reference.

        Args:
            obj_ref: IEC 61850 object reference

        Returns:
            bool: True if removed, False if not found
        """
        led_name = self._objref_index.get(obj_ref)
        if not led_name:
            return False

        return self.remove_mapping(led_name)

    def get_mapping(self, led_name: str) -> Optional[Dict[str, Any]]:
        """Get mapping configuration by LED name.

        Args:
            led_name: LED identifier

        Returns:
            dict: Mapping configuration, or None if not found
        """
        return self._mappings.get(led_name)

    def get_led_by_objref(self, obj_ref: str) -> Optional[Dict[str, Any]]:
        """Get LED configuration by IEC 61850 object reference.

        Args:
            obj_ref: IEC 61850 object reference

        Returns:
            dict: LED configuration with led_name, or None if not found
        """
        led_name = self._objref_index.get(obj_ref)
        if not led_name:
            return None

        config = self._mappings.get(led_name)
        if config:
            # Return copy with led_name included
            return {**config, "led_name": led_name}
        return None

    def get_all_mappings(self) -> Dict[str, Dict[str, Any]]:
        """Get all mappings.

        Returns:
            dict: All mappings indexed by led_name
        """
        return dict(self._mappings)

    def get_all_by_objref(self) -> Dict[str, Dict[str, Any]]:
        """Get all mappings indexed by objRef.

        Returns:
            dict: All mappings indexed by objRef (only those with objRef)
        """
        result = {}
        for obj_ref, led_name in self._objref_index.items():
            config = self._mappings.get(led_name)
            if config:
                result[obj_ref] = {**config, "led_name": led_name}
        return result

    def clear(self) -> None:
        """Clear all mappings."""
        self._mappings = {}
        self._objref_index = {}
        logger.info("Cleared all mappings")

    # ==================== Sync Utilities ====================

    def sync_led_from_iec61850(
        self,
        obj_ref: str,
        value: Any,
        client: Any = None
    ) -> bool:
        """Synchronize LED state based on IEC 61850 value.

        Args:
            obj_ref: IEC 61850 object reference that was written
            value: The value that was written
            client: Optional DemoIOClient instance for direct control

        Returns:
            bool: True if LED was synced, False if no mapping found
        """
        led_config = self.get_led_by_objref(obj_ref)
        if not led_config:
            return False

        led_name = led_config["led_name"]

        # Convert IEC 61850 value to boolean
        led_state = self._convert_to_bool(value)

        if client:
            try:
                client.set_led(led_name, led_state)
                logger.info(f"Synced LED '{led_name}' to {led_state} (from {obj_ref}={value})")
                return True
            except Exception as e:
                logger.error(f"Failed to sync LED '{led_name}': {e}")
                return False

        return False

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

    def config_led_with_mapping(
        self,
        led_name: str,
        gpio_pin: int,
        obj_ref: Optional[str] = None,
        description: str = "",
        initial_state: bool = False,
        **extra_properties: Any
    ) -> Dict[str, Any]:
        """Configure an LED and add it to the mapping.

        This is a convenience method that:
        1. Adds the mapping to the manager
        2. Returns the config that can be sent to demo_io

        Args:
            led_name: Unique LED identifier
            gpio_pin: GPIO pin number
            obj_ref: IEC 61850 object reference (optional)
            description: LED description
            initial_state: Initial LED state
            **extra_properties: Additional custom properties

        Returns:
            dict: Configuration suitable for demo_io config_led endpoint
        """
        # Add to mapping
        demoio_config = self.add_mapping(
            led_name=led_name,
            obj_ref=obj_ref,
            gpio_pin=gpio_pin,
            description=description,
            initial_state=initial_state,
            **extra_properties
        )

        # Return config for demo_io
        return {
            "name": led_name,
            "gpio_pin": gpio_pin,
            "description": description or f"Mapped to {obj_ref}" if obj_ref else "",
            "initial_state": initial_state
        }

    def get_led_config_for_demoio(self, led_name: str) -> Optional[Dict[str, Any]]:
        """Get LED configuration in the format expected by demo_io.

        Args:
            led_name: LED identifier

        Returns:
            dict: Configuration for demo_io config_led, or None if not found
        """
        config = self.get_mapping(led_name)
        if not config:
            return None

        return {
            "name": led_name,
            "gpio_pin": config.get("gpio_pin"),
            "description": config.get("description", ""),
            "initial_state": config.get("initial_state", False)
        }

    def get_all_led_configs_for_demoio(self) -> List[Dict[str, Any]]:
        """Get all LED configurations in demo_io format.

        Returns:
            list: All LED configurations for bulk demo_io setup
        """
        configs = []
        for led_name, config in self._mappings.items():
            configs.append({
                "name": led_name,
                "gpio_pin": config.get("gpio_pin"),
                "description": config.get("description", ""),
                "initial_state": config.get("initial_state", False)
            })
        return configs

    def list_mapped_leds(self) -> List[str]:
        """List all LED names that have mappings.

        Returns:
            list: All LED names with configurations
        """
        return list(self._mappings.keys())

    def list_mapped_objrefs(self) -> List[str]:
        """List all IEC 61850 object references that have mappings.

        Returns:
            list: All objRefs with LED mappings
        """
        return list(self._objref_index.keys())
