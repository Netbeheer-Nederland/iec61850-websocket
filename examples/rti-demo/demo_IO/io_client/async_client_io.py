"""
Async Client for connecting to demo_IO IO Device Control API.

This module provides an async HTTP client interface using httpx for
asynchronous control of IO devices exposed by the demo_IO service.

Perfect for use in async FastAPI applications or any async context.

Usage:
    import asyncio
    from async_client_io import AsyncDemoIOClient
    
    async def main():
        async with AsyncDemoIOClient(base_url="http://localhost:8080") as client:
            # Configure a device
            await client.config_led(name="led1", gpio_pin=17)
            
            # Turn device on
            await client.set_device("led1", state=True)
            
            # Read state
            state = await client.get_led_state("led1")
            print(f"LED state: {state}")
            
            # Configure potentiometer
            await client.config_potentiometer(
                name="pot1",
                adc_channel=0,
                min_value=0,
                max_value=100
            )
            
            # Read potentiometer
            value = await client.read_potentiometer_scaled("pot1")
            print(f"Potentiometer value: {value}")
    
    asyncio.run(main())
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, Dict, List, Optional, Union

import httpx

from .mapping_manager import IOMappingManager

logger = logging.getLogger(__name__)

# Lazy import to avoid circular dependencies
def _get_shared_mapping_manager() -> IOMappingManager:
    """Get the shared mapping manager instance from io_router."""
    from .io_router import get_mapping_manager
    return get_mapping_manager()


# ==================== DEFAULT CONFIGURATION ====================

DEFAULT_TIMEOUT = 5.0  # seconds
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_FACTOR = 0.5
DEFAULT_RETRY_STATUS_CODES = [429, 500, 502, 503, 504]


# ==================== EXCEPTION CLASSES ====================
# Define exception classes locally (previously imported from client_io)

class DemoIOClientError(Exception):
    """Base exception for demo_IO client errors."""
    pass

class ConnectionError(Exception):
    """Connection to demo_IO server failed."""
    pass

class RequestTimeoutError(Exception):
    """Request to demo_IO server timed out."""
    pass

class APIError(Exception):
    """API error from demo_IO server."""
    pass

class DeviceNotFoundError(Exception):
    """Requested device not found in demo_IO."""
    pass

class AuthenticationError(Exception):
    """Authentication failed for demo_IO."""
    pass

__all__ = [
    "AsyncDemoIOClient",
    "DemoIOClient",
    "DemoIOClientError",
    "ConnectionError",
    "RequestTimeoutError",
    "APIError",
    "DeviceNotFoundError",
    "AuthenticationError",
]


class AsyncDemoIOClient:
    """Async HTTP client for the demo_IO IO Device Control API.
    
    Uses httpx.AsyncClient for async HTTP requests, providing:
    - Full async/await support
    - Connection pooling
    - Automatic retry with exponential backoff
    - Context manager support
    - Same interface as sync DemoIOClient
    
    Usage:
        from async_client_io import AsyncDemoIOClient
        
        async with AsyncDemoIOClient(base_url="http://localhost:8080") as client:
            await client.set_device("led1", True)
            state = await client.get_led_state("led1")
    """
    
    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        mapping_file: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
        retry_status_codes: Optional[List[int]] = None,
        api_key: Optional[str] = None,
        # httpx specific options
        follow_redirects: bool = True,
        limits: Optional[httpx.Limits] = None,
        # ACSI server URL for IEC61850 writes
        acsi_base_url: Optional[str] = None
    ):
        """Initialize the async demo_IO client.
        
        Args:
            base_url: Base URL of the demo_IO service (without /api/io suffix)
            mapping_file: Optional path to io_mapping.json file
            timeout: Request timeout in seconds (default: 5.0)
            max_retries: Maximum number of retry attempts (default: 3)
            backoff_factor: Exponential backoff factor (default: 0.5)
            retry_status_codes: HTTP status codes to retry on
            api_key: Optional API key for authentication
            follow_redirects: Whether to follow HTTP redirects (default: True)
            limits: httpx connection limits
            acsi_base_url: Base URL of ACSI server for IEC61850 writes (optional)
        """
        self.base_url = base_url.rstrip('/')
        self.io_base = f"{self.base_url}/api/io"
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.retry_status_codes = retry_status_codes or DEFAULT_RETRY_STATUS_CODES
        self.api_key = api_key
        self.follow_redirects = follow_redirects
        self.limits = limits or httpx.Limits(max_connections=10, max_keepalive_connections=5)
        
        # ACSI server configuration for IEC61850 writes
        self._acsi_base_url = acsi_base_url or os.getenv("ACSI_BASE_URL", "http://localhost:5001")
        
        # Use shared mapping manager if available, otherwise create local instance
        try:
            self.mapping = _get_shared_mapping_manager()
        except (ImportError, AttributeError):
            # Fallback to local instance if io_router is not available
            self.mapping = IOMappingManager(mapping_file=mapping_file)
        self._client: Optional[httpx.AsyncClient] = None
        self._is_closed = True
        
        logger.info(f"Initialized AsyncDemoIOClient with base URL: {self.io_base}")
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the httpx AsyncClient."""
        if self._client is None or self._is_closed:
            headers = {"X-API-Key": self.api_key} if self.api_key else {}
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                follow_redirects=self.follow_redirects,
                limits=self.limits,
                headers=headers
            )
            self._is_closed = False
        return self._client
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
        raise_on_error: bool = True
    ) -> Any:
        """Make an async HTTP request to the demo_IO API.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path (without /api/io prefix)
            json: Request body as dict
            params: Query parameters as dict
            raise_on_error: If True, raise custom exceptions on error
            
        Returns:
            Parsed JSON response
            
        Raises:
            ConnectionError: If cannot connect to the service
            RequestTimeoutError: If request times out
            APIError: If API returns an error status code
            AuthenticationError: If authentication fails
        """
        client = await self._get_client()
        url = f"{self.io_base}{endpoint}"
        
        # Add API key header if configured (not already in client)
        headers = {}
        if self.api_key and not self._client.headers.get("X-API-Key"):
            headers["X-API-Key"] = self.api_key
        
        attempt = 0
        last_exception = None
        
        while attempt <= self.max_retries:
            try:
                response = await client.request(
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
                        try:
                            error_data = response.json()
                            error_msg = error_data.get("detail", "")
                            if "not found" in error_msg.lower():
                                match = re.search(r"'([^']+)' not found", error_msg)
                                if match:
                                    raise DeviceNotFoundError(match.group(1))
                        except:
                            pass
                        raise APIError(f"Not found", response.status_code, endpoint)
                    return None
                
                # Retry on server errors
                if response.status_code >= 400:
                    if response.status_code in self.retry_status_codes and attempt < self.max_retries:
                        attempt += 1
                        delay = self.backoff_factor * (2 ** (attempt - 1))
                        logger.warning(f"Request to {url} failed with {response.status_code}, retrying in {delay:.1f}s (attempt {attempt}/{self.max_retries})")
                        await asyncio.sleep(delay)
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
                
                # Success
                try:
                    return response.json()
                except ValueError:
                    return response.text
                    
            except httpx.TimeoutException as e:
                last_exception = e
                if attempt < self.max_retries:
                    attempt += 1
                    delay = self.backoff_factor * (2 ** (attempt - 1))
                    logger.warning(f"Request to {url} timed out, retrying in {delay:.1f}s (attempt {attempt}/{self.max_retries})")
                    await asyncio.sleep(delay)
                    continue
                else:
                    if raise_on_error:
                        raise RequestTimeoutError(str(e), endpoint, self.timeout)
                    return None
                    
            except httpx.ConnectError as e:
                last_exception = e
                if attempt < self.max_retries:
                    attempt += 1
                    delay = self.backoff_factor * (2 ** (attempt - 1))
                    logger.warning(f"Connection to {url} failed, retrying in {delay:.1f}s (attempt {attempt}/{self.max_retries})")
                    await asyncio.sleep(delay)
                    continue
                else:
                    if raise_on_error:
                        raise ConnectionError(str(e), self.base_url)
                    return None
                    
            except httpx.RequestError as e:
                last_exception = e
                if raise_on_error:
                    logger.error(f"Request to {url} failed: {e}")
                raise
        
        if raise_on_error and last_exception:
            raise last_exception
        return None
    
    # ==================== HEALTH AND STATUS ====================
    
    async def health_check(self) -> Dict[str, Any]:
        """Check the health of the demo_IO service."""
        return await self._request("GET", "/health")
    
    async def is_healthy(self) -> bool:
        """Check if the demo_IO service is healthy."""
        try:
            health = await self.health_check()
            return health.get("status") == "ok"
        except Exception:
            return False
    
    async def get_status(self) -> Dict[str, Any]:
        """Get the current IO controller status."""
        return await self._request("GET", "/status")
    
    async def get_api_info(self) -> Dict[str, Any]:
        """Get API information and available endpoints."""
        return await self._request("GET", "/")
    
    async def get_auth_status(self) -> Dict[str, Any]:
        """Check if API key authentication is enabled and configured."""
        return await self._request("GET", "/auth/status")
    
    # ==================== LED METHODS (Convenience wrappers for device API) ====================
    
    async def config_led(self, name: str, gpio_pin: int, description: str = "", 
                        initial_state: bool = False) -> Dict[str, Any]:
        """Configure an LED on the demo_IO service.
        
        This is a convenience method that uses the device API internally.
        """
        data = {
            "name": name,
            "device_type": "led",
            "identifier": gpio_pin,
            "description": description,
            "initial_state": initial_state
        }
        return await self._request("POST", "/devices/config", json=data)
    
    async def list_leds(self) -> Dict[str, Any]:
        """List all configured LEDs and their states.
        
        This is a convenience method that filters devices by LED type.
        """
        all_devices = await self._request("GET", "/devices")
        # Filter to only return LED devices
        leds = {}
        if "details" in all_devices:
            for name, detail in all_devices["details"].items():
                if detail.get("type") == "led":
                    leds[name] = detail.get("value", False)
        return leds
    
    async def get_led_state(self, name: str) -> Dict[str, Any]:
        """Get the current state of a specific LED.
        
        This is a convenience method that uses the device API internally.
        """
        result = await self._request("POST", f"/devices/{name}/read")
        if result and "value" in result:
            return {"name": name, "state": bool(result["value"])}
        return {"name": name, "state": False}
    
    async def set_device(self, name: str, state: bool) -> Dict[str, Any]:
        """Set a specific device to ON or OFF state.
        
        This is a convenience method that uses the device API internally.
        """
        data = {"state": state}
        return await self._request("POST", f"/devices/{name}/set", json=data)
    
    async def toggle_led(self, name: str) -> Dict[str, Any]:
        """Toggle the state of a specific LED.
        
        This is a convenience method that uses the device API internally.
        """
        return await self._request("POST", f"/devices/{name}/toggle", json={})
    
    async def set_all_leds(self, state: bool) -> Dict[str, Any]:
        """Set all configured LEDs to a specific state.
        
        This is a convenience method that uses the device API internally.
        Note: This affects ALL output devices, not just LEDs.
        """
        data = {"state": state}
        result = await self._request("POST", "/devices/outputs/set-all", json=data)
        led_results = {}
        if "results" in result:
            for name, value in result["results"].items():
                led_results[name] = value
        result["results"] = led_results
        return result
    
    async def all_leds_on(self) -> Dict[str, Any]:
        """Turn all configured LEDs ON.
        
        This is a convenience method that calls set_all_leds(True).
        """
        return await self.set_all_leds(True)
    
    async def all_leds_off(self) -> Dict[str, Any]:
        """Turn all configured LEDs OFF.
        
        This is a convenience method that calls set_all_leds(False).
        """
        return await self.set_all_leds(False)
    
    async def initialize(self) -> Dict[str, Any]:
        """Initialize the IO controller on the demo_IO service."""
        return await self._request("POST", "/initialize")
    
    async def cleanup(self) -> Dict[str, Any]:
        """Clean up IO resources on the demo_IO service."""
        return await self._request("POST", "/cleanup")
    
    # ==================== CONVENIENCE METHODS (LEGACY) ====================
    
    async def turn_on(self, name: str) -> Dict[str, Any]:
        """Turn a device ON."""
        return await self.set_device(name, state=True)
    
    async def turn_off(self, name: str) -> Dict[str, Any]:
        """Turn a device OFF."""
        return await self.set_device(name, state=False)
    
    async def add_led(self, name: str, gpio_pin: int, description: str = "", 
                     initial_state: bool = False) -> Dict[str, Any]:
        """Add and configure an LED."""
        return await self.config_led(name, gpio_pin, description, initial_state)
    
    async def get_all_states(self) -> Dict[str, bool]:
        """Get the state of all LEDs."""
        return await self.list_leds()
    
    # ==================== NEW DEVICE METHODS (v2.0+) ====================
    
    async def list_devices(self) -> Dict[str, Any]:
        """List all configured devices."""
        return await self._request("GET", "/devices")
    
    async def list_device_types(self) -> Dict[str, Any]:
        """List supported device types."""
        return await self._request("GET", "/devices/types")
    
    async def get_device_status(self, name: str) -> Dict[str, Any]:
        """Get detailed status of a specific device."""
        return await self._request("GET", f"/devices/{name}")
    
    async def config_device(
        self,
        name: str,
        device_type: str,
        identifier: Optional[int] = None,
        description: str = "",
        **kwargs
    ) -> Dict[str, Any]:
        """Configure a new IO device."""
        data = {
            "name": name,
            "device_type": device_type,
            "identifier": identifier,
            "description": description,
            **kwargs
        }
        return await self._request("POST", "/devices/config", json=data)
    
    async def write_device(self, name: str, value: Union[bool, float]) -> Dict[str, Any]:
        """Write a value to a device."""
        data = {"value": value}
        return await self._request("POST", f"/devices/{name}/write", json=data)
    
    async def read_device(self, name: str) -> Dict[str, Any]:
        """Read the current value from a device."""
        return await self._request("POST", f"/devices/{name}/read")
    
    async def toggle_device(self, name: str) -> Dict[str, Any]:
        """Toggle a device state."""
        return await self._request("POST", f"/devices/{name}/toggle")
    
    async def set_device(self, name: str, state: bool) -> Dict[str, Any]:
        """Set a device to a specific boolean state."""
        data = {"state": state}
        return await self._request("POST", f"/devices/{name}/set", json=data)
    
    async def read_all_inputs(self) -> Dict[str, Any]:
        """Read values from all input devices."""
        return await self._request("POST", "/devices/inputs/read-all")
    
    async def set_all_outputs(self, state: bool) -> Dict[str, Any]:
        """Set all output devices to a specific state."""
        data = {"state": state}
        return await self._request("POST", "/devices/outputs/set-all", json=data)
    
    # ==================== DEVICE-SPECIFIC CONVENIENCE METHODS ====================
    
    async def config_potentiometer(
        self,
        name: str,
        adc_channel: int,
        min_value: float = 0.0,
        max_value: float = 100.0,
        description: str = "",
        is_inverted: bool = False
    ) -> Dict[str, Any]:
        """Configure a potentiometer device."""
        return await self.config_device(
            name=name,
            device_type="potentiometer",
            adc_channel=adc_channel,
            min_value=min_value,
            max_value=max_value,
            description=description,
            is_inverted=is_inverted
        )
    
    async def read_potentiometer(self, name: str) -> Dict[str, Any]:
        """Read the current value from a potentiometer."""
        return await self.read_device(name)
    
    async def read_potentiometer_scaled(self, name: str) -> float:
        """Read the scaled value from a potentiometer."""
        result = await self.read_device(name)
        if result and "value" in result:
            return float(result["value"])
        return 0.0
    
    async def config_button(
        self,
        name: str,
        gpio_pin: int,
        description: str = "",
        debounce_time: float = 0.05,
        pull_up: bool = True
    ) -> Dict[str, Any]:
        """Configure a button device."""
        return await self.config_device(
            name=name,
            device_type="button",
            gpio_pin=gpio_pin,
            description=description,
            debounce_time=debounce_time,
            pull_up=pull_up
        )
    
    async def read_button(self, name: str) -> bool:
        """Read the current state of a button."""
        result = await self.read_device(name)
        if result and "value" in result:
            return bool(result["value"])
        return False
    
    # ==================== IEC 61850 MAPPING METHODS ====================
    
    async def config_device_with_mapping(
        self,
        device_name: str,
        gpio_pin: int,
        obj_ref: Optional[str] = None,
        description: str = "",
        initial_state: bool = False,
        **extra_properties: Any
    ) -> Dict[str, Any]:
        """Configure an IO device with IEC 61850 mapping."""
        demoio_config = self.mapping.config_device_with_mapping(
            device_name=device_name,
            gpio_pin=gpio_pin,
            obj_ref=obj_ref,
            description=description,
            initial_state=initial_state,
            **extra_properties
        )
        
        demo_io_result = await self.config_led(
            name=device_name,
            gpio_pin=gpio_pin,
            description=description or f"Mapped to {obj_ref}" if obj_ref else "",
            initial_state=initial_state
        )
        
        self.mapping.save()
        
        return {
            "demo_io": demo_io_result,
            "mapping": demoio_config,
            "device_name": device_name,
            "objRef": obj_ref
        }
    
    # ==================== LCD SPECIFIC METHODS ====================
    
    async def write_lcd(
        self,
        device_name: str,
        text: Union[str, List[str]]
    ) -> Dict[str, Any]:
        """Write text to an LCD display.
        
        Args:
            device_name: Name of the LCD device (e.g., "lcd1")
            text: Text to display. Can be a single string or list of strings (one per line)
        
        Returns:
            Write confirmation
        """
        data = {"text": text}
        return await self._request("POST", f"/lcd/{device_name}/write", json=data)
    
    async def write_lcd_line(
        self,
        device_name: str,
        line_number: int,
        text: str
    ) -> Dict[str, Any]:
        """Write text to a specific line on an LCD display.
        
        Args:
            device_name: Name of the LCD device
            line_number: Line number (0-indexed)
            text: Text to write to the specified line
        
        Returns:
            Write confirmation
        """
        data = {"line_number": line_number, "text": text}
        return await self._request("POST", f"/lcd/{device_name}/write-line", json=data)
    
    async def clear_lcd(self, device_name: str) -> Dict[str, Any]:
        """Clear an LCD display.
        
        Args:
            device_name: Name of the LCD device
        
        Returns:
            Clear confirmation
        """
        return await self._request("POST", f"/lcd/{device_name}/clear")
    
    async def write_iec61850_value(
        self,
        obj_ref: str,
        value: Any
    ) -> bool:
        """Handle IEC 61850 write by syncing to mapped device."""
        return await self.mapping.sync_device_from_iec61850_async(obj_ref, value, client=self)
    
    async def write_to_iec61850(
        self,
        obj_ref: str,
        value: Any,
        fc: str = "ST",
        data_type: str = ""
    ) -> bool:
        """Write to IEC61850 server via standard /writevalue endpoint.
        
        This method allows IO input devices to write to the ACSI server's IEC61850 model.
        It makes an HTTP POST to the ACSI's /api/writevalue endpoint with no special handling.
        
        Args:
            obj_ref: IEC61850 object reference to write to
            value: Value to write (will be converted to string)
            fc: Functional constraint (default: "ST")
            data_type: Data type for the value (e.g., "BOOLEAN", "INT32", "FLOAT32")
            
        Returns:
            bool: True if write succeeded, False otherwise
        """
        import httpx
        try:
            async with httpx.AsyncClient(timeout=5.0) as http_client:
                response = await http_client.post(
                    f"{self._acsi_base_url}/api/writevalue",
                    json={
                        "objRef": obj_ref,
                        "fc": fc,
                        "value": str(value),
                        "dataType": data_type
                    }
                )
                if response.status_code == 200:
                    logger.info(f"IEC61850 write successful: {obj_ref}={value}")
                    return True
                logger.error(f"IEC61850 write failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"IEC61850 write error: {e}")
            return False
    
    async def operate_to_iec61850(
        self,
        obj_ref: str,
        value: Any,
        value_type: str = "BOOLEAN",
        cp: str = "cp1"
    ) -> bool:
        """Send an Operate command to IEC61850 server via /api/operate endpoint.
        
        This method allows IO input devices to send IEC61850 Operate commands to the ACSI server.
        It makes an HTTP POST to the ACSI's /api/operate endpoint.
        
        Use this for controllable data objects that require IEC61850 Operate service
        (e.g., control objects like CSWI, XCBR).
        
        Args:
            obj_ref: IEC61850 controllable DO object reference (e.g., "LD0/MMXU.WMaxSpt")
            value: Value to set via operate (will be converted to string)
            value_type: Value type hint for coercion (BOOLEAN, INT32, FLOAT32, etc.)
            cp: Communication point identifier (default: "cp1")
            
        Returns:
            bool: True if operate succeeded, False otherwise
        """
        import httpx
        try:
            async with httpx.AsyncClient(timeout=5.0) as http_client:
                response = await http_client.post(
                    f"{self._acsi_base_url}/api/operate",
                    json={
                        "objRef": obj_ref,
                        "value": value,
                        "value_type": value_type,
                        "cp": cp
                    }
                )
                if response.status_code == 200:
                    logger.info(f"IEC61850 operate successful: {obj_ref}={value}")
                    return True
                logger.error(f"IEC61850 operate failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"IEC61850 operate error: {e}")
            return False
    
    def set_acsi_base_url(self, url: str) -> None:
        """Set the ACSI server base URL at runtime.
        
        This allows changing the ACSI server URL without restarting the service.
        Input device callbacks will use this URL for IEC61850 writes.
        
        Args:
            url: Base URL of the ACSI server (e.g., "http://localhost:5001")
        """
        self._acsi_base_url = url.rstrip('/')
        logger.info(f"ACSI base URL updated to: {self._acsi_base_url}")
    
    def get_acsi_base_url(self) -> str:
        """Get the currently configured ACSI server base URL.
        
        Returns:
            str: The ACSI base URL
        """
        return self._acsi_base_url
    
    def get_mapping_manager(self) -> IOMappingManager:
        """Get the mapping manager instance."""
        return self.mapping
    
    # ==================== SESSION MANAGEMENT ====================
    
    async def aclose(self) -> None:
        """Close the async client session."""
        if self._client and not self._is_closed:
            await self._client.aclose()
            self._is_closed = True
            logger.info("AsyncDemoIOClient session closed")
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self._get_client()  # Ensure client is created
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.aclose()
        return False
    
    def __del__(self):
        """Destructor - ensure session is closed."""
        # Note: In async contexts, prefer using async with or explicit aclose()
        # This is a fallback for garbage collection
        if hasattr(self, '_client') and self._client and not self._is_closed:
            # We can't await in __del__, so we schedule the close
            # This is not ideal but prevents resource leaks
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.aclose())
                else:
                    loop.run_until_complete(self.aclose())
            except:
                pass


class DemoIOClient:
    """Synchronous wrapper for AsyncDemoIOClient.
    
    This class provides a synchronous interface to the demo_IO API by wrapping
    the async methods of AsyncDemoIOClient. It uses asyncio.run() to execute
    async code synchronously.
    
    Note: This should only be used in synchronous contexts. For async applications,
    use AsyncDemoIOClient directly.
    
    Usage:
        from demo_IO.io_client.async_client_io import DemoIOClient
        
        client = DemoIOClient(base_url="http://localhost:8080")
        # Use synchronous methods
        state = client.get_led_state("led1")
        client.set_device("led1", state=True)
    """
    
    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        mapping_file: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
        retry_status_codes: Optional[List[int]] = None,
        api_key: Optional[str] = None,
        follow_redirects: bool = True,
        limits: Optional[httpx.Limits] = None,
        acsi_base_url: Optional[str] = None
    ):
        """Initialize the synchronous demo_IO client.
        
        This creates an AsyncDemoIOClient internally and wraps its methods.
        
        Args:
            base_url: Base URL of the demo_IO service
            mapping_file: Optional path to io_mapping.json file
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            backoff_factor: Exponential backoff factor
            retry_status_codes: HTTP status codes to retry on
            api_key: Optional API key for authentication
            follow_redirects: Whether to follow HTTP redirects
            limits: httpx connection limits
            acsi_base_url: Base URL of ACSI server for IEC61850 writes
        """
        self._async_client = AsyncDemoIOClient(
            base_url=base_url,
            mapping_file=mapping_file,
            timeout=timeout,
            max_retries=max_retries,
            backoff_factor=backoff_factor,
            retry_status_codes=retry_status_codes,
            api_key=api_key,
            follow_redirects=follow_redirects,
            limits=limits,
            acsi_base_url=acsi_base_url
        )
    
    def _sync(self, coro):
        """Run an async coroutine synchronously."""
        return asyncio.run(coro)
    
    # Properties that delegate to async client
    @property
    def base_url(self):
        return self._async_client.base_url
    
    @property
    def io_base(self):
        return self._async_client.io_base
    
    @property
    def timeout(self):
        return self._async_client.timeout
    
    @timeout.setter
    def timeout(self, value):
        self._async_client.timeout = value
    
    @property
    def max_retries(self):
        return self._async_client.max_retries
    
    @max_retries.setter
    def max_retries(self, value):
        self._async_client.max_retries = value
    
    @property
    def api_key(self):
        return self._async_client.api_key
    
    @api_key.setter
    def api_key(self, value):
        self._async_client.api_key = value
    
    @property
    def mapping(self):
        return self._async_client.mapping
    
    def get_mapping_manager(self):
        return self._async_client.get_mapping_manager()
    
    def set_acsi_base_url(self, url: str):
        return self._async_client.set_acsi_base_url(url)
    
    def get_acsi_base_url(self) -> str:
        return self._async_client.get_acsi_base_url()
    
    # Synchronous wrapper methods for all async methods
    def health_check(self) -> Dict[str, Any]:
        return self._sync(self._async_client.health_check())
    
    def is_healthy(self) -> bool:
        return self._sync(self._async_client.is_healthy())
    
    def get_status(self) -> Dict[str, Any]:
        return self._sync(self._async_client.get_status())
    
    def get_api_info(self) -> Dict[str, Any]:
        return self._sync(self._async_client.get_api_info())
    
    def get_auth_status(self) -> Dict[str, Any]:
        return self._sync(self._async_client.get_auth_status())
    
    def config_led(self, name: str, gpio_pin: int, description: str = "", 
                  initial_state: bool = False) -> Dict[str, Any]:
        return self._sync(self._async_client.config_led(name, gpio_pin, description, initial_state))
    
    def list_leds(self) -> Dict[str, Any]:
        return self._sync(self._async_client.list_leds())
    
    def get_led_state(self, name: str) -> Dict[str, Any]:
        return self._sync(self._async_client.get_led_state(name))
    
    def set_led(self, name: str, state: bool) -> Dict[str, Any]:
        return self._sync(self._async_client.set_led(name, state))
    
    def toggle_led(self, name: str) -> Dict[str, Any]:
        return self._sync(self._async_client.toggle_led(name))
    
    def set_all_leds(self, state: bool) -> Dict[str, Any]:
        return self._sync(self._async_client.set_all_leds(state))
    
    def all_leds_on(self) -> Dict[str, Any]:
        return self._sync(self._async_client.all_leds_on())
    
    def all_leds_off(self) -> Dict[str, Any]:
        return self._sync(self._async_client.all_leds_off())
    
    def initialize(self) -> Dict[str, Any]:
        return self._sync(self._async_client.initialize())
    
    def cleanup(self) -> Dict[str, Any]:
        return self._sync(self._async_client.cleanup())
    
    def get_device(self, name: str) -> Dict[str, Any]:
        return self._sync(self._async_client.get_device(name))
    
    def set_device(self, name: str, state: Union[bool, int, float]) -> Dict[str, Any]:
        return self._sync(self._async_client.set_device(name, state))
    
    def get_device_state(self, name: str) -> Dict[str, Any]:
        return self._sync(self._async_client.get_device_state(name))
    
    def set_all_devices(self, state: Union[bool, int, float]) -> Dict[str, Any]:
        return self._sync(self._async_client.set_all_devices(state))
    
    def get_all_states(self) -> Dict[str, Any]:
        return self._sync(self._async_client.get_all_states())
    
    def list_devices(self) -> List[str]:
        return self._sync(self._async_client.list_devices())
    
    def get_device_info(self, name: str) -> Dict[str, Any]:
        return self._sync(self._async_client.get_device_info(name))
    
    def delete_device(self, name: str) -> Dict[str, Any]:
        return self._sync(self._async_client.delete_device(name))
    
    # Convenience methods
    def turn_on(self, name: str) -> Dict[str, Any]:
        return self.set_device(name, True)
    
    def turn_off(self, name: str) -> Dict[str, Any]:
        return self.set_device(name, False)
    
    def add_led(self, name: str, gpio_pin: int, description: str = "", initial_state: bool = False) -> Dict[str, Any]:
        return self.config_led(name, gpio_pin, description, initial_state)
    
    def create_led(self, name: str, gpio_pin: int, description: str = "", initial_state: bool = False) -> Dict[str, Any]:
        return self.config_led(name, gpio_pin, description, initial_state)
    
    # Potentiometer methods
    def config_potentiometer(self, name: str, adc_channel: int, min_value: float = 0.0, 
                            max_value: float = 100.0, description: str = "") -> Dict[str, Any]:
        return self._sync(self._async_client.config_potentiometer(name, adc_channel, min_value, max_value, description))
    
    def read_potentiometer(self, name: str) -> Dict[str, Any]:
        return self._sync(self._async_client.read_potentiometer(name))
    
    def read_potentiometer_scaled(self, name: str) -> float:
        return self._sync(self._async_client.read_potentiometer_scaled(name))
    
    def list_potentiometers(self) -> List[str]:
        return self._sync(self._async_client.list_potentiometers())
    
    # Button methods
    def config_button(self, name: str, gpio_pin: int, description: str = "", 
                     debounce_ms: int = 50) -> Dict[str, Any]:
        return self._sync(self._async_client.config_button(name, gpio_pin, description, debounce_ms))
    
    def get_button_state(self, name: str) -> Dict[str, Any]:
        return self._sync(self._async_client.get_button_state(name))
    
    def list_buttons(self) -> List[str]:
        return self._sync(self._async_client.list_buttons())
    
    # Generic IO methods
    def read_analog(self, channel: int) -> Dict[str, Any]:
        return self._sync(self._async_client.read_analog(channel))
    
    def read_digital(self, pin: int) -> Dict[str, Any]:
        return self._sync(self._async_client.read_digital(pin))
    
    def write_digital(self, pin: int, state: bool) -> Dict[str, Any]:
        return self._sync(self._async_client.write_digital(pin, state))
    
    def write_pwm(self, pin: int, duty_cycle: float) -> Dict[str, Any]:
        return self._sync(self._async_client.write_pwm(pin, duty_cycle))
    
    # IEC61850 write method
    def write_iec61850(self, obj_ref: str, value: Any, fc: str = "ST") -> bool:
        return self._sync(self._async_client.write_iec61850(obj_ref, value, fc))
    
    # IEC61850 operate method
    def operate_to_iec61850(self, obj_ref: str, value: Any, value_type: str = "BOOLEAN", cp: str = "cp1") -> bool:
        return self._sync(self._async_client.operate_to_iec61850(obj_ref, value, value_type, cp))
    
    # Session management
    def close(self):
        """Close the underlying async client."""
        self._sync(self._async_client.aclose())
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
    
    def __del__(self):
        """Destructor - ensure session is closed."""
        try:
            self.close()
        except:
            pass
