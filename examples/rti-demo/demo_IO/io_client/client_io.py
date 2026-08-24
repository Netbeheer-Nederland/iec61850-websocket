"""
Client for connecting to demo_IO IO Device Control API.

This module provides a client interface to remotely control IO devices
(LEDs, potentiometers, buttons) exposed by the demo_IO service's BFF endpoints.

Features:
- Connection pooling for better performance
- Automatic retry with exponential backoff
- Configurable timeout
- Comprehensive error handling
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional, Union

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .mapping_manager import IOMappingManager

logger = logging.getLogger(__name__)


# ==================== DEFAULT CONFIGURATION ====================

DEFAULT_TIMEOUT = 5.0  # seconds
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_FACTOR = 0.5  # Exponential backoff: 0.5s, 1s, 2s
DEFAULT_RETRY_STATUS_CODES = [429, 500, 502, 503, 504]  # Status codes to retry


# ==================== CUSTOM EXCEPTIONS ====================

class DemoIOClientError(Exception):
    """Base exception for demo_IO client errors."""
    pass


class ConnectionError(DemoIOClientError):
    """Connection to demo_IO service failed."""
    def __init__(self, message: str, base_url: str):
        self.base_url = base_url
        super().__init__(f"Connection to {base_url} failed: {message}")


class RequestTimeoutError(DemoIOClientError):
    """Request to demo_IO service timed out."""
    def __init__(self, message: str, endpoint: str, timeout: float):
        self.endpoint = endpoint
        self.timeout = timeout
        super().__init__(f"Request to {endpoint} timed out after {timeout}s: {message}")


class APIError(DemoIOClientError):
    """demo_IO API returned an error."""
    def __init__(self, message: str, status_code: int, endpoint: str):
        self.status_code = status_code
        self.endpoint = endpoint
        super().__init__(f"API error {status_code} on {endpoint}: {message}")


class DeviceNotFoundError(DemoIOClientError):
    """Requested device does not exist."""
    def __init__(self, device_name: str):
        self.device_name = device_name
        super().__init__(f"Device '{device_name}' not found")


class AuthenticationError(DemoIOClientError):
    """Authentication failed."""
    def __init__(self, message: str = "Authentication required"):
        super().__init__(f"Authentication error: {message}")


class DemoIOClient:
    """HTTP client for the demo_IO IO Device Control API.
    
    This client provides methods to:
    - Connect to a running demo_IO instance
    - Configure and manage IO devices (LEDs, potentiometers, buttons)
    - Control individual or all devices
    - Get device states and IO controller status
    
    Features:
    - Connection pooling for better performance
    - Automatic retry with exponential backoff
    - Configurable timeout and retry behavior
    - Custom exception hierarchy
    
    Usage:
        # Basic usage
        client = DemoIOClient(base_url="http://localhost:8080")
        
        # Configure an LED
        client.config_led(name="led1", gpio_pin=17)
        
        # Turn LED on
        client.set_led("led1", state=True)
        
        # Configure a potentiometer
        client.config_device(
            name="pot1",
            device_type="potentiometer",
            adc_channel=0,
            min_value=0,
            max_value=100
        )
        
        # Read potentiometer value
        value = client.read_device("pot1")
        
        # Toggle LED
        client.toggle_led("led1")
        
        # Custom configuration
        client = DemoIOClient(
            base_url="http://demo-io:8080",
            timeout=10.0,
            max_retries=5,
            api_key="your-api-key"
        )
    """
    
    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        mapping_file: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
        retry_status_codes: Optional[List[int]] = None,
        api_key: Optional[str] = None
    ):
        """Initialize the demo_IO client.
        
        Args:
            base_url: Base URL of the demo_IO service (without /api/io suffix)
            mapping_file: Optional path to io_mapping.json file
            timeout: Request timeout in seconds (default: 5.0)
            max_retries: Maximum number of retry attempts (default: 3)
            backoff_factor: Exponential backoff factor (default: 0.5)
            retry_status_codes: HTTP status codes to retry on (default: 429, 500, 502, 503, 504)
            api_key: Optional API key for authentication
        """
        self.base_url = base_url.rstrip('/')
        self.io_base = f"{self.base_url}/api/io"
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.retry_status_codes = retry_status_codes or DEFAULT_RETRY_STATUS_CODES
        self.api_key = api_key
        
        # Configure connection pooling and retry
        self._session = self._create_session()
        
        self.mapping = IOMappingManager(mapping_file=mapping_file)
        logger.info(f"Initialized DemoIOClient with base URL: {self.io_base}, timeout: {timeout}s, retries: {max_retries}")
    
    def _create_session(self) -> requests.Session:
        """Create a requests Session with connection pooling and retry configuration."""
        session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=self.backoff_factor,
            status_forcelist=self.retry_status_codes,
            allowed_methods=["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"],
            raise_on_status=False  # We handle status codes manually
        )
        
        # Mount adapter with retry for both http and https
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=100)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def _request(
        self,
        method: str,
        endpoint: str,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
        raise_on_error: bool = True
    ) -> Any:
        """Make an HTTP request to the demo_IO API with retry and error handling.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path (without /api/io prefix)
            json: Request body as dict
            params: Query parameters as dict
            raise_on_error: If True, raise custom exceptions on error (default: True)
            
        Returns:
            Parsed JSON response
            
        Raises:
            ConnectionError: If cannot connect to the service
            RequestTimeoutError: If request times out
            APIError: If API returns an error status code
            AuthenticationError: If authentication fails
        """
        url = f"{self.io_base}{endpoint}"
        
        # Add API key header if configured
        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        
        attempt = 0
        last_exception = None
        
        while attempt <= self.max_retries:
            try:
                response = self._session.request(
                    method=method,
                    url=url,
                    json=json,
                    params=params,
                    headers=headers,
                    timeout=self.timeout
                )
                
                # Check for authentication failure
                if response.status_code == 401:
                    if raise_on_error:
                        raise AuthenticationError(f"Authentication failed for {url}")
                    return None
                
                # Check for device not found
                if response.status_code == 404:
                    if raise_on_error:
                        # Try to extract device name from error message
                        try:
                            error_data = response.json()
                            error_msg = error_data.get("detail", "")
                            if "not found" in error_msg.lower():
                                # Extract device name from message like "Device 'led1' not found"
                                import re
                                match = re.search(r"'([^']+)' not found", error_msg)
                                if match:
                                    raise DeviceNotFoundError(match.group(1))
                        except:
                            pass
                        raise APIError(f"Not found", response.status_code, endpoint)
                    return None
                
                # Raise for server errors (unless we should retry)
                if response.status_code >= 400:
                    if response.status_code in self.retry_status_codes and attempt < self.max_retries:
                        attempt += 1
                        delay = self.backoff_factor * (2 ** (attempt - 1))
                        logger.warning(f"Request to {url} failed with {response.status_code}, retrying in {delay:.1f}s (attempt {attempt}/{self.max_retries})")
                        time.sleep(delay)
                        continue
                    else:
                        if raise_on_error:
                            try:
                                error_data = response.json()
                                error_msg = error_data.get("detail", "") or error_data.get("message", "")
                            except:
                                error_msg = response.text
                            raise APIError(error_msg, response.status_code, endpoint)
                        return None
                
                # Success - parse and return
                try:
                    return response.json()
                except ValueError:
                    return response.text
                    
            except requests.exceptions.Timeout as e:
                last_exception = e
                if attempt < self.max_retries:
                    attempt += 1
                    delay = self.backoff_factor * (2 ** (attempt - 1))
                    logger.warning(f"Request to {url} timed out, retrying in {delay:.1f}s (attempt {attempt}/{self.max_retries})")
                    time.sleep(delay)
                    continue
                else:
                    if raise_on_error:
                        raise RequestTimeoutError(str(e), endpoint, self.timeout)
                    return None
                    
            except requests.exceptions.ConnectionError as e:
                last_exception = e
                if attempt < self.max_retries:
                    attempt += 1
                    delay = self.backoff_factor * (2 ** (attempt - 1))
                    logger.warning(f"Connection to {url} failed, retrying in {delay:.1f}s (attempt {attempt}/{self.max_retries})")
                    time.sleep(delay)
                    continue
                else:
                    if raise_on_error:
                        raise ConnectionError(str(e), self.base_url)
                    return None
                    
            except requests.exceptions.RequestException as e:
                last_exception = e
                if raise_on_error:
                    logger.error(f"Request to {url} failed: {e}")
                raise
        
        # Should not reach here, but just in case
        if raise_on_error and last_exception:
            raise last_exception
        return None
    
    def close(self) -> None:
        """Close the client session and clean up resources."""
        if self._session:
            self._session.close()
            logger.info("DemoIOClient session closed")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close session."""
        self.close()
        return False
    
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
    
    def get_api_info(self) -> Dict[str, Any]:
        """Get API information and available endpoints."""
        return self._request("GET", "/")
    
    def get_auth_status(self) -> Dict[str, Any]:
        """Check if API key authentication is enabled and configured."""
        return self._request("GET", "/auth/status")
    
    # ==================== LED Configuration ====================
    
    def config_led(self, name: str, gpio_pin: int, description: str = "", 
                   initial_state: bool = False) -> Dict[str, Any]:
        """Configure an LED on the demo_IO service.
        
        This is a convenience method that uses the device API internally.
        
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
            "device_type": "led",
            "identifier": gpio_pin,
            "description": description,
            "initial_state": initial_state
        }
        return self._request("POST", "/devices/config", json=data)
    
    def list_leds(self) -> Dict[str, Any]:
        """List all configured LEDs and their states.
        
        This is a convenience method that filters devices by LED type.
        
        Returns:
            Dictionary with LED information
        """
        all_devices = self._request("GET", "/devices")
        # Filter to only return LED devices
        leds = {}
        if "details" in all_devices:
            for name, detail in all_devices["details"].items():
                if detail.get("type") == "led":
                    leds[name] = detail.get("value", False)
        return leds
    
    def get_led_config(self, name: str) -> Dict[str, Any]:
        """Get the configuration of a specific LED.
        
        This is a convenience method that uses the device API internally.
        
        Args:
            name: LED identifier
            
        Returns:
            LED configuration details
            
        Raises:
            requests.HTTPError: If LED not found (404)
        """
        return self._request("GET", f"/devices/{name}")
    
    # ==================== LED Control ====================
    
    def get_led_state(self, name: str) -> Dict[str, Any]:
        """Get the current state of a specific LED.
        
        This is a convenience method that uses the device API internally.
        
        Args:
            name: LED identifier
            
        Returns:
            Dictionary with LED name and state
            
        Raises:
            requests.HTTPError: If LED not found (404)
        """
        # Use read_device which returns {"name": name, "value": value}
        result = self._request("POST", f"/devices/{name}/read")
        # Return in LED format for backward compatibility
        if result and "value" in result:
            return {"name": name, "state": bool(result["value"])}
        return {"name": name, "state": False}
    
    def set_led(self, name: str, state: bool) -> Dict[str, Any]:
        """Set a specific LED to ON or OFF state.
        
        This is a convenience method that uses the device API internally.
        
        Args:
            name: LED identifier
            state: True for ON, False for OFF
            
        Returns:
            Confirmation with new state
            
        Raises:
            requests.HTTPError: If LED not found (404) or set fails (500)
        """
        # Use set_device which accepts a state parameter
        data = {"state": state}
        return self._request("POST", f"/devices/{name}/set", json=data)
    
    def toggle_led(self, name: str) -> Dict[str, Any]:
        """Toggle the state of a specific LED.
        
        This is a convenience method that uses the device API internally.
        
        Args:
            name: LED identifier
            
        Returns:
            Confirmation with new state
            
        Raises:
            requests.HTTPError: If LED not found (404) or toggle fails (500)
        """
        return self._request("POST", f"/devices/{name}/toggle", json={})
    
    # ==================== Bulk Operations ====================
    
    def set_all_leds(self, state: bool) -> Dict[str, Any]:
        """Set all configured LEDs to a specific state.
        
        This is a convenience method that uses the device API internally.
        
        Args:
            state: True for ON, False for OFF
            
        Returns:
            Confirmation with resulting states of all LEDs
        """
        # Use set_all_outputs which sets all output devices
        # Note: This affects ALL output devices, not just LEDs
        data = {"state": state}
        result = self._request("POST", "/devices/outputs/set-all", json=data)
        # Filter to only return LED results for backward compatibility
        led_results = {}
        if "results" in result:
            for name, value in result["results"].items():
                # We need to check if it's an LED - for now, just return all
                led_results[name] = value
        result["results"] = led_results
        return result
    
    def all_leds_on(self) -> Dict[str, Any]:
        """Turn all configured LEDs ON.
        
        This is a convenience method that calls set_all_leds(True).
        
        Returns:
            Confirmation with results
        """
        return self.set_all_leds(True)
    
    def all_leds_off(self) -> Dict[str, Any]:
        """Turn all configured LEDs OFF.
        
        This is a convenience method that calls set_all_leds(False).
        
        Returns:
            Confirmation with results
        """
        return self.set_all_leds(False)
    
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

    # ==================== IEC 61850 Mapping Methods ====================

    def config_led_with_mapping(
        self,
        led_name: str,
        gpio_pin: int,
        obj_ref: Optional[str] = None,
        description: str = "",
        initial_state: bool = False,
        **extra_properties: Any
    ) -> Dict[str, Any]:
        """Configure an LED with IEC 61850 mapping and send to demo_io.
        
        Args:
            led_name: Unique LED identifier
            gpio_pin: GPIO pin number
            obj_ref: IEC 61850 object reference (optional)
            description: LED description
            initial_state: Initial LED state
            **extra_properties: Additional custom properties
            
        Returns:
            dict: Result with both mapping and demo_io configuration
        """
        # Get demo_io config from mapping manager
        demoio_config = self.mapping.config_led_with_mapping(
            led_name=led_name,
            gpio_pin=gpio_pin,
            obj_ref=obj_ref,
            description=description,
            initial_state=initial_state,
            **extra_properties
        )
        
        # Configure on demo_io service
        demo_io_result = self.config_led(
            name=led_name,
            gpio_pin=gpio_pin,
            description=description or f"Mapped to {obj_ref}" if obj_ref else "",
            initial_state=initial_state
        )
        
        # Save mapping to file
        self.mapping.save()
        
        return {
            "demo_io": demo_io_result,
            "mapping": demoio_config,
            "led_name": led_name,
            "objRef": obj_ref
        }

    def write_iec61850_value(
        self,
        obj_ref: str,
        value: Any,
        data_type: str = "unknown"
    ) -> bool:
        """Handle IEC 61850 write by syncing to mapped LED if exists.
        
        Args:
            obj_ref: IEC 61850 object reference
            value: Value to write
            data_type: Data type (unused for LED sync)
            
        Returns:
            bool: True if LED was synced, False if no mapping found
        """
        return self.mapping.sync_led_from_iec61850(obj_ref, value, client=self)

    def get_mapping_manager(self) -> IOMappingManager:
        """Get the mapping manager instance.
        
        Returns:
            IOMappingManager: The mapping manager for this client
        """
        return self.mapping
    
    # ==================== NEW DEVICE METHODS (v2.0+) ====================
    
    def list_devices(self) -> Dict[str, Any]:
        """List all configured devices.
        
        Returns:
            Dictionary with device list and details
        """
        return self._request("GET", "/devices")
    
    def list_device_types(self) -> Dict[str, Any]:
        """List supported device types.
        
        Returns:
            Dictionary with list of device types
        """
        return self._request("GET", "/devices/types")
    
    def get_device_status(self, name: str) -> Dict[str, Any]:
        """Get detailed status of a specific device.
        
        Args:
            name: Device identifier
            
        Returns:
            Device status dictionary
        """
        return self._request("GET", f"/devices/{name}")
    
    def config_device(
        self,
        name: str,
        device_type: str,
        identifier: Optional[int] = None,
        description: str = "",
        **kwargs
    ) -> Dict[str, Any]:
        """Configure a new IO device.
        
        Args:
            name: Unique device identifier
            device_type: Type of device (led, potentiometer, button, etc.)
            identifier: GPIO pin or ADC channel number
            description: Device description
            **kwargs: Additional device-specific parameters
            
        Returns:
            Configuration confirmation
        """
        data = {
            "name": name,
            "device_type": device_type,
            "identifier": identifier,
            "description": description,
            **kwargs
        }
        return self._request("POST", "/devices/config", json=data)
    
    def write_device(self, name: str, value: Union[bool, float]) -> Dict[str, Any]:
        """Write a value to a device.
        
        Args:
            name: Device identifier
            value: Value to write (bool for digital, float for analog)
            
        Returns:
            Write confirmation with actual value
        """
        data = {"value": value}
        return self._request("POST", f"/devices/{name}/write", json=data)
    
    def read_device(self, name: str) -> Dict[str, Any]:
        """Read the current value from a device.
        
        Args:
            name: Device identifier
            
        Returns:
            Dictionary with device name and value
        """
        return self._request("POST", f"/devices/{name}/read")
    
    def toggle_device(self, name: str) -> Dict[str, Any]:
        """Toggle a device state.
        
        Args:
            name: Device identifier
            
        Returns:
            Toggle confirmation with new state
        """
        return self._request("POST", f"/devices/{name}/toggle")
    
    def set_device(self, name: str, state: bool) -> Dict[str, Any]:
        """Set a device to a specific boolean state.
        
        Args:
            name: Device identifier
            state: True for ON/High, False for OFF/Low
            
        Returns:
            Set confirmation with new state
        """
        data = {"state": state}
        return self._request("POST", f"/devices/{name}/set", json=data)
    
    def read_all_inputs(self) -> Dict[str, Any]:
        """Read values from all input devices.
        
        Returns:
            Dictionary with all input device values
        """
        return self._request("POST", "/devices/inputs/read-all")
    
    def set_all_outputs(self, state: bool) -> Dict[str, Any]:
        """Set all output devices to a specific state.
        
        Args:
            state: True for ON/High, False for OFF/Low
            
        Returns:
            Dictionary with results for all output devices
        """
        data = {"state": state}
        return self._request("POST", "/devices/outputs/set-all", json=data)
    
    # ==================== DEVICE-SPECIFIC CONVENIENCE METHODS ====================
    
    def config_potentiometer(
        self,
        name: str,
        adc_channel: int,
        min_value: float = 0.0,
        max_value: float = 100.0,
        description: str = "",
        is_inverted: bool = False
    ) -> Dict[str, Any]:
        """Configure a potentiometer device.
        
        Args:
            name: Unique potentiometer identifier
            adc_channel: ADC channel number (0-7 for MCP3008)
            min_value: Minimum value for scaled readings
            max_value: Maximum value for scaled readings
            description: Potentiometer description
            is_inverted: Whether to invert the reading
            
        Returns:
            Configuration confirmation
        """
        return self.config_device(
            name=name,
            device_type="potentiometer",
            adc_channel=adc_channel,
            min_value=min_value,
            max_value=max_value,
            description=description,
            is_inverted=is_inverted
        )
    
    def read_potentiometer(self, name: str) -> Dict[str, Any]:
        """Read the current value from a potentiometer.
        
        Args:
            name: Potentiometer identifier
            
        Returns:
            Dictionary with potentiometer name and normalized value (0.0-1.0)
        """
        return self.read_device(name)
    
    def read_potentiometer_scaled(self, name: str) -> float:
        """Read the scaled value from a potentiometer.
        
        This is a convenience method that reads the normalized value and scales it
        to the configured min/max range.
        
        Args:
            name: Potentiometer identifier
            
        Returns:
            Scaled value (between configured min_value and max_value)
        """
        result = self.read_device(name)
        if result and "value" in result:
            return float(result["value"])
        return 0.0
    
    def config_button(
        self,
        name: str,
        gpio_pin: int,
        description: str = "",
        debounce_time: float = 0.05,
        pull_up: bool = True
    ) -> Dict[str, Any]:
        """Configure a button device.
        
        Args:
            name: Unique button identifier
            gpio_pin: GPIO pin number (BCM numbering)
            description: Button description
            debounce_time: Debounce time in seconds
            pull_up: Use internal pull-up resistor
            
        Returns:
            Configuration confirmation
        """
        return self.config_device(
            name=name,
            device_type="button",
            gpio_pin=gpio_pin,
            description=description,
            debounce_time=debounce_time,
            pull_up=pull_up
        )
    
    def read_button(self, name: str) -> bool:
        """Read the current state of a button.
        
        Args:
            name: Button identifier
            
        Returns:
            True if pressed, False if released
        """
        result = self.read_device(name)
        if result and "value" in result:
            return bool(result["value"])
        return False
    
    # ==================== BATCH DEVICE OPERATIONS ====================
    
    def config_multiple_devices(self, devices: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Configure multiple devices in batch.
        
        Args:
            devices: List of device configurations
            
        Returns:
            List of configuration confirmations
        """
        results = []
        for device_config in devices:
            try:
                result = self.config_device(**device_config)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to configure device {device_config.get('name')}: {e}")
                results.append({"error": str(e), "name": device_config.get("name")})
        return results
