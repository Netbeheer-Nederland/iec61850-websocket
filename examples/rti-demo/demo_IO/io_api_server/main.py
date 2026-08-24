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
    
    # Run with mock devices only (no hardware)
    MOCK_MODE=true python main.py
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import FastAPI

from io_controller import IOController
from devices import LEDConfig, PotentiometerConfig, DeviceType

from api_endpoint import create_fastapi_app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application with pre-configured devices.
    
    This function:
    1. Creates an IOController instance
    2. Configures default LEDs (GPIO 17, 18, 22)
    3. Optionally configures a potentiometer (ADC channel 0)
    4. Initializes the controller
    5. Creates and returns the FastAPI app
    
    Returns:
        FastAPI application instance
    """
    # Check if we should use mock mode (from environment variable)
    use_mock = os.getenv("MOCK_MODE", "false").lower() in ("true", "1", "yes")
    
    # Create IO controller
    io_controller = IOController()
    
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
    
    logger.info("Configured default devices: led1 (GPIO 17), led2 (GPIO 18), led3 (GPIO 22), pot1 (ADC 0)")
    
    # Initialize IO with optional mock mode
    if not io_controller.initialize(use_mock=use_mock):
        logger.error("Failed to initialize IO controller")
    else:
        logger.info("IO controller initialized successfully" + (" (mock mode)" if use_mock else ""))
    
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
