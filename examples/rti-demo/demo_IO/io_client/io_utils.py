"""
IO utility functions for ACSI BFF endpoints.
Reusable across SO, FSP, and other projects.
"""

from __future__ import annotations
import asyncio
import logging

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


async def blink_led_task(io_client, obj_ref: str, interval: float = 0.2, count: int = 1):
    """Blink an LED. Fire-and-forget.
    
    Args:
        io_client: IO client instance
        led_ref: IEC61850 object reference for the LED
        interval: Blink interval in seconds (default: 0.2s)
        count: Number of blink cycles (default: 1)
    """
    try:
        if await io_client.is_healthy():
            for _ in range(count):
                await io_client.write_iec61850_value(obj_ref, True)
                await asyncio.sleep(interval)
                await io_client.write_iec61850_value(obj_ref, False)
                await asyncio.sleep(interval)
            logger.info(f"Blinked {obj_ref} {count} times at {interval}s interval")
        else:
            logger.debug("IO client not healthy, skipping LED blink")
    except Exception as sync_exc:
        logger.warning(f"LED blink failed for {obj_ref}: {sync_exc}")
