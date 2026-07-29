"""
Client for connecting to demo_IO GPIO LED Control API.

This module provides a client interface to remotely control GPIO LEDs
exposed by the demo_IO service's BFF endpoints.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class DemoIOClient:
    """HTTP client for the demo_IO GPIO LED Control API.
    
    This client provides methods to:
    - Connect to a running demo_IO instance
    - Configure and manage LEDs
    - Control individual or all LEDs
    - Get LED states and GPIO status
    
    Usage:
        client = DemoIOClient(base_url="http://localhost:8080")
        
        # Configure an LED
        client.config_led(name="led1", gpio_pin=17)
        
        # Turn LED on
        client.set_led("led1", state=True)
        
        # Toggle LED
        client.toggle_led("led1")
        
        # Get LED state
        state = client.get_led_state("led1")
    """
    
    def __init__(self, base_url: str = "http://localhost:8080"):
        """Initialize the demo_IO client.
        
        Args:
            base_url: Base URL of the demo_IO service (without /api/io suffix)
        """
        self.base_url = base_url.rstrip('/')
        self.io_base = f"{self.base_url}/api/io"
        logger.info(f"Initialized DemoIOClient with base URL: {self.io_base}")
    
    def _request(self, method: str, endpoint: str, json: Optional[dict] = None, 
                 params: Optional[dict] = None) -> Any:
        """Make an HTTP request to the demo_IO API.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path (without /api/io prefix)
            json: Request body as dict
            params: Query parameters as dict
            
        Returns:
            Parsed JSON response or raw text
            
        Raises:
            requests.HTTPError: If the request fails
            ConnectionError: If cannot connect to the service
        """
        url = f"{self.io_base}{endpoint}"
        
        try:
            response = requests.request(
                method=method,
                url=url,
                json=json,
                params=params,
                timeout=15
            )
            
            response.raise_for_status()
            
            try:
                return response.json()
            except ValueError:
                return response.text
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Request to {url} failed: {e}")
            raise
    
    # ==================== Health and Status ====================
    
    def health_check(self) -> Dict[str, Any]:
        """Check the health of the demo_IO service.
        
        Returns:
            Health status dictionary
        """
        return self._request("GET", "/health")
    
    def is_healthy(self) -> bool:
        """Check if the demo_IO service is healthy.
        
        Returns:
            True if service is healthy, False otherwise
        """
        try:
            health = self.health_check()
            return health.get("status") == "ok"
        except Exception:
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get the current GPIO controller status.
        
        Returns:
            Dictionary containing:
            - initialized: Whether GPIO is initialized
            - led_count: Number of configured LEDs
            - led_config: Configuration of all LEDs
            - states: Current state of all LEDs
        """
        return self._request("GET", "/status")
    
    # ==================== LED Configuration ====================
    
    def config_led(self, name: str, gpio_pin: int, description: str = "", 
                   initial_state: bool = False) -> Dict[str, Any]:
        """Configure an LED on the demo_IO service.
        
        Args:
            name: Unique identifier for the LED
            gpio_pin: GPIO pin number (BCM numbering)
            description: Optional description
            initial_state: Initial state when initialized
            
        Returns:
            Configuration confirmation
        """
        data = {
            "name": name,
            "gpio_pin": gpio_pin,
            "description": description,
            "initial_state": initial_state
        }
        return self._request("POST", "/leds/config", json=data)
    
    def list_leds(self) -> Dict[str, bool]:
        """List all configured LEDs and their states.
        
        Returns:
            Dictionary mapping LED names to their current states
        """
        return self._request("GET", "/leds")
    
    def get_led_config(self, name: str) -> Dict[str, Any]:
        """Get the configuration of a specific LED.
        
        Args:
            name: LED identifier
            
        Returns:
            LED configuration details
            
        Raises:
            requests.HTTPError: If LED not found (404)
        """
        return self._request("GET", f"/leds/{name}")
    
    # ==================== LED Control ====================
    
    def get_led_state(self, name: str) -> Dict[str, Any]:
        """Get the current state of a specific LED.
        
        Args:
            name: LED identifier
            
        Returns:
            Dictionary with LED name and state
            
        Raises:
            requests.HTTPError: If LED not found (404)
        """
        return self._request("GET", f"/leds/{name}")
    
    def set_led(self, name: str, state: bool) -> Dict[str, Any]:
        """Set a specific LED to ON or OFF state.
        
        Args:
            name: LED identifier
            state: True for ON, False for OFF
            
        Returns:
            Confirmation with new state
            
        Raises:
            requests.HTTPError: If LED not found (404) or set fails (500)
        """
        data = {"state": state}
        return self._request("POST", f"/leds/{name}/set", json=data)
    
    def toggle_led(self, name: str) -> Dict[str, Any]:
        """Toggle the state of a specific LED.
        
        Args:
            name: LED identifier
            
        Returns:
            Confirmation with new state
            
        Raises:
            requests.HTTPError: If LED not found (404) or toggle fails (500)
        """
        return self._request("POST", f"/leds/{name}/toggle", json={})
    
    # ==================== Bulk Operations ====================
    
    def set_all_leds(self, state: bool) -> Dict[str, Any]:
        """Set all configured LEDs to a specific state.
        
        Args:
            state: True for ON, False for OFF
            
        Returns:
            Confirmation with resulting states of all LEDs
        """
        data = {"state": state}
        return self._request("POST", "/leds/all/set", json=data)
    
    def all_leds_on(self) -> Dict[str, Any]:
        """Turn all configured LEDs ON.
        
        Returns:
            Confirmation with results
        """
        return self._request("POST", "/leds/all/on")
    
    def all_leds_off(self) -> Dict[str, Any]:
        """Turn all configured LEDs OFF.
        
        Returns:
            Confirmation with results
        """
        return self._request("POST", "/leds/all/off")
    
    # ==================== GPIO Management ====================
    
    def initialize(self) -> Dict[str, Any]:
        """Initialize the GPIO controller on the demo_IO service.
        
        Returns:
            Initialization confirmation
        """
        return self._request("POST", "/initialize")
    
    def cleanup(self) -> Dict[str, Any]:
        """Clean up GPIO resources on the demo_IO service.
        
        Returns:
            Cleanup confirmation
        """
        return self._request("POST", "/cleanup")
    
    # ==================== Convenience Methods ====================
    
    def turn_on(self, name: str) -> Dict[str, Any]:
        """Convenience method to turn an LED ON.
        
        Args:
            name: LED identifier
            
        Returns:
            Confirmation with new state
        """
        return self.set_led(name, state=True)
    
    def turn_off(self, name: str) -> Dict[str, Any]:
        """Convenience method to turn an LED OFF.
        
        Args:
            name: LED identifier
            
        Returns:
            Confirmation with new state
        """
        return self.set_led(name, state=False)
    
    def add_led(self, name: str, gpio_pin: int, description: str = "", 
                initial_state: bool = False) -> Dict[str, Any]:
        """Convenience method to add and configure an LED.
        
        This is an alias for config_led().
        
        Args:
            name: Unique identifier for the LED
            gpio_pin: GPIO pin number (BCM numbering)
            description: Optional description
            initial_state: Initial state when initialized
            
        Returns:
            Configuration confirmation
        """
        return self.config_led(name, gpio_pin, description, initial_state)
    
    def get_all_states(self) -> Dict[str, bool]:
        """Get the state of all LEDs.
        
        Returns:
            Dictionary mapping LED names to their current states
        """
        return self.list_leds()
    
    def create_led(self, name: str, gpio_pin: int, **kwargs) -> Dict[str, Any]:
        """Create and configure a new LED.
        
        Args:
            name: Unique identifier for the LED
            gpio_pin: GPIO pin number (BCM numbering)
            **kwargs: Additional configuration (description, initial_state)
            
        Returns:
            Configuration confirmation
        """
        return self.config_led(name, gpio_pin, **kwargs)
