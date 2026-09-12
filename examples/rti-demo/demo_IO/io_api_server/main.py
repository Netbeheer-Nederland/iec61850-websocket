"""
Main entry point for the Raspberry Pi IO Device Control API

This module demonstrates how to use the io_controller and api_endpoint
modules to create a complete IO device control service.

Supports:
- LEDs (digital output)
- Potentiometers (analog input)
- Buttons (digital input)
- And more

Usage:
    # Run with default port (8000)
    python main.py
    
    # Run with custom port
    PORT=8080 python main.py
    
    # Use custom config file
    IO_CONFIG_FILE=/path/to/io_config.json python main.py
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI

from io_controller import IOController, configure_acsi, ACSIConfig
from devices import LEDConfig, PotentiometerConfig, ButtonConfig, DeviceType

from api_endpoint import create_fastapi_app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_acsi_config(config_path: Path) -> Optional[ACSIConfig]:
    """Load ACSI configuration from JSON config file."""
    if not config_path.exists():
        return None
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        acsi_data = data.get("acsi_server", {})
        if acsi_data:
            return ACSIConfig.from_dict(acsi_data)
    except Exception as e:
        logger.warning(f"Failed to load ACSI config from {config_path}: {e}")
    
    return None


def load_device_mappings(config_path: Path) -> Optional[Dict[str, Dict[str, Any]]]:
    """Load device mappings from JSON config file."""
    if not config_path.exists():
        return None
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        return data.get("mappings", {})
    except Exception as e:
        logger.warning(f"Failed to load device mappings from {config_path}: {e}")
    
    return None


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application with pre-configured devices.
    
    This function:
    1. Creates an IOController instance
    2. Loads configurations from io_config.json if it exists
    3. Otherwise configures default devices (led1, led2, led3, pot1, button1)
    4. Initializes the controller
    5. Creates and returns the FastAPI app
    
    Returns:
        FastAPI application instance
    """
    # Create IO controller
    io_controller = IOController()
    
    # Get config file path
    config_path = Path(__file__).parent / "io_config.json"
    
    # Try to load configuration from io_config.json
    config_loaded = io_controller.load_config(str(config_path))
    
    # Load and configure ACSI server integration
    acsi_config = load_acsi_config(config_path)
    device_mappings = load_device_mappings(config_path)
    if acsi_config and (device_mappings or acsi_config.enabled):
        configure_acsi(acsi_config, device_mappings)
        if acsi_config.enabled:
            logger.info(f"ACSI server integration enabled: {acsi_config.url}")
            if device_mappings:
                logger.info(f"Loaded {len(device_mappings)} device-to-ACSI mappings")
        else:
            logger.info("ACSI server integration configured but disabled")
    else:
        logger.debug("ACSI server integration not configured")
    
    if config_loaded:
        logger.info("Loaded IO configuration from io_config.json")
    else:
        # No config file found, use defaults
        logger.info("No io_config.json found, using default device configuration")
        
        # Configure default LEDs
        io_controller.add_device(LEDConfig(
            name="led1",
            gpio_pin=17,
            description="LED 1 on GPIO 17 (Pin 11)",
            initial_state=False
        ))
        io_controller.add_device(LEDConfig(
            name="led2",
            gpio_pin=18,
            description="LED 2 on GPIO 18 (Pin 12)",
            initial_state=False
        ))
        io_controller.add_device(LEDConfig(
            name="led3",
            gpio_pin=22,
            description="LED 3 on GPIO 22 (Pin 15)",
            initial_state=False
        ))
        
        # Configure a default potentiometer (if ADC is available)
        try:
            io_controller.add_device(PotentiometerConfig(
                name="pot1",
                adc_channel=0,
                description="Potentiometer on ADC channel 0",
                min_value=0.0,
                max_value=100.0
            ))
            logger.info("Configured default potentiometer: pot1 (ADC channel 0)")
        except Exception as e:
            logger.warning(f"Failed to configure default potentiometer: {e}")
        
        # Configure a default button on GPIO 10
        try:
            io_controller.add_device(ButtonConfig(
                name="button1",
                gpio_pin=10,
                description="Button on GPIO 10 (Pin 19)",
                debounce_time=0.05,
                pull_up=False,
                latching=True  # Button toggles and maintains state on press
            ))
            logger.info("Configured default button: button1 (GPIO 10, latching)")
        except Exception as e:
            logger.warning(f"Failed to configure default button: {e}")
        
        logger.info("Configured default devices: led1 (GPIO 17), led2 (GPIO 18), led3 (GPIO 22), pot1 (ADC 0), button1 (GPIO 10)")
    
    # Initialize IO
    if not io_controller.initialize():
        logger.error("Failed to initialize IO controller")
    else:
        logger.info("IO controller initialized successfully")
        
        # Blink all LEDs at startup for visual confirmation
        import time
        led_names = io_controller.get_output_devices()
        led_names = [name for name in led_names if io_controller.get_config(name).device_type.value == "led"]
        if led_names:
            logger.info(f"Blinking {len(led_names)} LEDs at startup...")
            for _ in range(3):
                for name in led_names:
                    io_controller.write(name, True)
                time.sleep(0.3)
                for name in led_names:
                    io_controller.write(name, False)
                time.sleep(0.3)
            logger.info("LED blink sequence complete")
    
    # Create FastAPI app
    app = create_fastapi_app(io_controller)
    
    return app


def main():
    """Main entry point."""
    import uvicorn
    
    app = create_app()
    
    # Get port from environment or use default
    # On Windows, port 8000 might be reserved, so we use 8080 as default
    port = int(os.getenv("PORT", "8080"))
    
    # On Windows, use localhost instead of 0.0.0.0 to avoid permission issues
    # On Linux/macOS, 0.0.0.0 allows external access
    import platform
    if platform.system() == "Windows":
        host = "localhost"
        logger.info(f"Running on Windows - using host='localhost' for compatibility")
    else:
        host = "0.0.0.0"
    
    logger.info(f"Starting IO Device Control API on port {port}")
    logger.info(f"Access the API documentation at: http://{host}:{port}/api/io/docs")
    logger.info(f"Access the health endpoint at: http://{host}:{port}/api/io/health")
    
    # Run the server
    try:
        uvicorn.run(app, host=host, port=port)
    except OSError as e:
        logger.error(f"Failed to start server on {host}:{port}: {e}")
        logger.error(f"Try using a different port by setting the PORT environment variable.")
        logger.error(f"Example: PORT=8081 python main.py")
        raise


if __name__ == "__main__":
    main()
