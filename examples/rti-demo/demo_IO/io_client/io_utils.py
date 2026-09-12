"""
IO utility functions for ACSI BFF endpoints.
Reusable across SO, FSP, and other projects.
"""

from __future__ import annotations
import asyncio
import logging
from typing import TYPE_CHECKING, Any, List, Optional, Union

if TYPE_CHECKING:
    from .mapping_manager import IOMappingManager

logger = logging.getLogger(__name__)


async def sync_to_io_device(io_client, obj_ref: str, value):
    """Sync a write to IO devices. Fire-and-forget.
    
    Args:
        io_client: IO client instance (must have write_iec61850_value method)
        obj_ref: IEC61850 object reference (e.g., "LD0/GGIO1.LED1")
        value: Value to write
    """
    try:
        if await io_client.is_healthy():
            await io_client.write_iec61850_value(obj_ref, value)
            logger.info(f"Synced IEC61850 write to device: {obj_ref}={value}")
        else:
            logger.debug("IO client not healthy, skipping device sync")
    except Exception as sync_exc:
        logger.warning(f"Device sync failed for {obj_ref}: {sync_exc}")


async def write_to_lcd(io_client, obj_ref: str, text: Union[str, List[str]], mapping_manager: Optional[IOMappingManager] = None):
    """Write text to an LCD display. Fire-and-forget. Only works with LCD devices.
    
    Args:
        io_client: IO client instance (must have write_lcd method)
        obj_ref: IEC61850 object reference to find mapped LCD devices
        text: Text to display on the LCD (can be a string or list of strings for multiple lines)
        mapping_manager: Optional IOMappingManager to find LCD devices mapped to obj_ref
    
    Note: If mapping_manager is provided, finds LCD devices mapped to obj_ref.
          Writes to all LCD devices found. Uses io_client.write_lcd() which accepts text directly.
    """
    # Find LCD devices mapped to this obj_ref
    lcd_devices = []
    if mapping_manager:
        device_configs = mapping_manager.get_devices_by_objref(obj_ref)
        for config in device_configs:
            device_type = config.get("type", config.get("device_type", "")).lower()
            if device_type == "lcd":
                lcd_devices.append(config["device_name"])
    else:
        # Fallback: treat obj_ref as device name if no mapping_manager
        lcd_devices = [obj_ref]
    
    # Skip if no LCD devices found
    if not lcd_devices:
        logger.debug(f"Skipping LCD write for obj_ref '{obj_ref}' - no LCD devices mapped")
        return
    
    try:
        if await io_client.is_healthy():
            # Write to all LCD devices mapped to this obj_ref
            for device_name in lcd_devices:
                await io_client.write_lcd(device_name, text)
                logger.info(f"Wrote text to LCD '{device_name}': {text}")
        else:
            logger.debug("IO client not healthy, skipping LCD write")
    except Exception as sync_exc:
        logger.warning(f"LCD write failed for {lcd_devices}: {sync_exc}")


async def blink_led_task(io_client, obj_ref: str, interval: float = 0.2, count: int = 1, mapping_manager=None):
    """Blink an LED. Fire-and-forget. Only works with LED devices.
    
    Args:
        io_client: IO client instance
        obj_ref: IEC61850 object reference for the LED
        interval: Blink interval in seconds (default: 0.2s)
        count: Number of blink cycles (default: 1)
        mapping_manager: Optional IOMappingManager to get LED device names
    
    Note: If mapping_manager is provided, only blinks LED devices mapped to the obj_ref.
          Writes directly to device names instead of obj_ref to avoid affecting non-LED devices.
    """
    # Get all LED devices mapped to this obj_ref
    led_devices = []
    if mapping_manager:
        device_configs = mapping_manager.get_devices_by_objref(obj_ref)
        for config in device_configs:
            device_type = config.get("type", config.get("device_type", "")).lower()
            if device_type == "led":
                led_devices.append(config["device_name"])
    else:
        # Fallback: treat obj_ref as device name if no mapping_manager
        led_devices = [obj_ref]
    
    # Skip if no LED devices found
    if not led_devices:
        logger.debug(f"Skipping blink for {obj_ref} - no LED devices found")
        return
    
    try:
        if await io_client.is_healthy():
            for _ in range(count):
                # Set all LED devices to ON
                for device_name in led_devices:
                    await io_client.set_device(device_name, True)
                await asyncio.sleep(interval)
                # Set all LED devices to OFF
                for device_name in led_devices:
                    await io_client.set_device(device_name, False)
                await asyncio.sleep(interval)
            logger.info(f"Blinked {led_devices} {count} times at {interval}s interval")
        else:
            logger.debug("IO client not healthy, skipping LED blink")
    except Exception as sync_exc:
        logger.warning(f"LED blink failed for {led_devices}: {sync_exc}")
