"""
Main entry point for the Raspberry Pi GPIO LED Control API

This module demonstrates how to use the gpio_controller and api_endpoint
modules to create a complete LED control service.

Usage:
    # Run with default port (8000)
    python main.py
    
    # Run with custom port
    PORT=8080 python main.py
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import FastAPI
from gpio_controller import GPIOController
from api_endpoint import create_fastapi_app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application with pre-configured LEDs.
    
    This function:
    1. Creates a GPIOController instance
    2. Configures default LEDs (GPIO 17, 18, 22)
    3. Initializes the controller
    4. Creates and returns the FastAPI app
    
    Returns:
        FastAPI application instance
    """
    # Create GPIO controller
    gpio_controller = GPIOController()
    
    # Configure default LEDs
    # These are common GPIO pins on Raspberry Pi
    # Physical pin numbers:
    # - GPIO 17 = Pin 11
    # - GPIO 18 = Pin 12
    # - GPIO 22 = Pin 15
    gpio_controller.add_led(
        name="led1",
        gpio_pin=17,
        description="LED 1 on GPIO 17 (Pin 11)",
        initial_state=False
    )
    gpio_controller.add_led(
        name="led2",
        gpio_pin=18,
        description="LED 2 on GPIO 18 (Pin 12)",
        initial_state=False
    )
    gpio_controller.add_led(
        name="led3",
        gpio_pin=22,
        description="LED 3 on GPIO 22 (Pin 15)",
        initial_state=False
    )
    
    logger.info("Configured default LEDs: led1 (GPIO 17), led2 (GPIO 18), led3 (GPIO 22)")
    
    # Initialize GPIO (will use mock LEDs if gpiozero is not available)
    if not gpio_controller.initialize():
        logger.error("Failed to initialize GPIO controller")
    else:
        logger.info("GPIO controller initialized successfully")
    
    # Create FastAPI app
    app = create_fastapi_app(gpio_controller)
    
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
    
    logger.info(f"Starting GPIO LED Control API on port {port}")
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
