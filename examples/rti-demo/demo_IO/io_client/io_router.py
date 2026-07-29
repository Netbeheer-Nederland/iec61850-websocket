"""
IO Router for FSP BFF - Provides LED control routes that proxy to demo_IO.

This module creates a FastAPI router that provides IO/LED control endpoints
for the FSP service, which proxy requests to a connected demo_IO instance.

The IO router allows FSP to:
- Expose LED control endpoints to its clients
- Proxy LED control requests to demo_IO
- Manage connection to demo_IO service
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .client_io import DemoIOClient

logger = logging.getLogger(__name__)


# ==================== Pydantic Models ====================

class LEDConfigRequest(BaseModel):
    """Request body for configuring an LED via FSP IO proxy."""
    name: str = Field(
        ...,
        description="Unique identifier for the LED",
        json_schema_extra={"example": "led1"}
    )
    gpio_pin: int = Field(
        ...,
        description="GPIO pin number (BCM numbering)",
        ge=0,
        json_schema_extra={"example": 17}
    )
    description: str = Field(
        default="",
        description="Optional description of the LED",
        json_schema_extra={"example": "Status indicator LED"}
    )
    initial_state: bool = Field(
        default=False,
        description="Initial state when initialized",
        json_schema_extra={"example": False}
    )


class LEDStateRequest(BaseModel):
    """Request body for setting LED state via FSP IO proxy."""
    state: bool = Field(
        ...,
        description="True for ON, False for OFF",
        json_schema_extra={"example": True}
    )


class IOConnectionConfig(BaseModel):
    """Configuration for demo_IO connection."""
    base_url: str = Field(
        default="http://localhost:8080",
        description="Base URL of the demo_IO service",
        json_schema_extra={"example": "http://demo-io:8080"}
    )


# Global demo_IO client instance (lazy initialized)
_io_client: Optional[DemoIOClient] = None


def get_io_client() -> Optional[DemoIOClient]:
    """Get or create the demo_IO client instance."""
    global _io_client
    return _io_client


def set_io_client(client: DemoIOClient) -> None:
    """Set the demo_IO client instance."""
    global _io_client
    _io_client = client
    logger.info(f"DemoIOClient configured with base URL: {client.base_url}")


def create_io_router() -> APIRouter:
    """Create a FastAPI router for IO/LED control via demo_IO proxy.
    
    This router provides endpoints that proxy LED control requests to a 
    connected demo_IO service. The demo_IO connection is configured via
    environment variable DEMO_IO_URL or through the /api/io/connect endpoint.
    
    Note: If DEMO_IO_URL is set, the client will be auto-configured on router creation.
    
    Returns:
        APIRouter instance with all IO endpoints configured
    """
    router = APIRouter(
        prefix="/api/io",
        tags=["IO Control"],
        responses={404: {"description": "Not found"}, 500: {"description": "Internal server error"}}
    )
    
    # Initialize client from environment variable if explicitly set (not default)
    demo_io_url = os.getenv("DEMO_IO_URL")
    if demo_io_url:
        set_io_client(DemoIOClient(base_url=demo_io_url))
        logger.info(f"DemoIOClient auto-configured from DEMO_IO_URL: {demo_io_url}")
    
    # ==================== Helper Functions ====================
    
    def _get_client_or_error() -> DemoIOClient:
        """Get demo_IO client or raise error if not configured."""
        client = get_io_client()
        if client is None:
            raise HTTPException(
                status_code=500,
                detail="demo_IO client not configured. "
                       "Configure connection via POST /api/io/connect or set DEMO_IO_URL environment variable."
            )
        
        # Check if service is healthy
        if not client.is_healthy():
            raise HTTPException(
                status_code=503,
                detail=f"demo_IO service at {client.base_url} is not responding. "
                       "Check if the service is running and accessible."
            )
        
        return client
    
    def _handle_io_error(func_name: str):
        """Decorator to handle demo_IO client errors."""
        def decorator(func):
            async def wrapper(*args, **kwargs):
                try:
                    client = _get_client_or_error()
                    return await func(client, *args, **kwargs)
                except HTTPException:
                    raise
                except Exception as exc:
                    logger.error(f"IO {func_name} failed: {exc}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"demo_IO operation failed: {str(exc)}"
                    )
            return wrapper
        return decorator
    
    # ==================== Connection Management ====================
    
    @router.post(
        "/connect",
        summary="Connect to demo_IO",
        description="Configure the connection to a demo_IO service. "
                    "This must be called before using IO endpoints if DEMO_IO_URL is not set.",
        response_description="Connection confirmation",
        responses={
            200: {"description": "Connected successfully"},
            500: {"description": "Connection failed"}
        },
        tags=["IO Connection"]
    )
    async def api_connect_io(config: IOConnectionConfig, request: Request):
        """Connect to a demo_IO service.
        
        Request Body:
            IOConnectionConfig: {
                "base_url": str  # Base URL of demo_IO service
            }
        
        Returns:
            dict: Connection confirmation with health check
        """
        try:
            client = DemoIOClient(base_url=config.base_url)
            
            # Test connection
            if not client.is_healthy():
                raise HTTPException(
                    status_code=400,
                    detail=f"demo_IO service at {config.base_url} is not responding"
                )
            
            set_io_client(client)
            
            logger.info(f"Connected to demo_IO at {config.base_url}")
            return {
                "ok": True,
                "message": f"Connected to demo_IO at {config.base_url}",
                "base_url": config.base_url,
                "healthy": True
            }
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"Failed to connect to demo_IO: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.get(
        "/connection",
        summary="Get IO Connection Status",
        description="Returns the current demo_IO connection status.",
        response_description="Connection status",
        responses={
            200: {"description": "Connection status returned"},
            500: {"description": "Client not configured"}
        },
        tags=["IO Connection"]
    )
    async def api_get_connection_status(request: Request):
        """Get current demo_IO connection status.
        
        Returns:
            dict: Connection status including base URL and health
        """
        client = get_io_client()
        if client is None:
            return {
                "connected": False,
                "base_url": None,
                "healthy": False,
                "error": "Client not configured"
            }
        
        return {
            "connected": True,
            "base_url": client.base_url,
            "healthy": client.is_healthy()
        }
    
    @router.post(
        "/disconnect",
        summary="Disconnect from demo_IO",
        description="Disconnect from the current demo_IO service.",
        response_description="Disconnection confirmation",
        responses={
            200: {"description": "Disconnected successfully"}
        },
        tags=["IO Connection"]
    )
    async def api_disconnect_io(request: Request):
        """Disconnect from demo_IO service.
        
        Returns:
            dict: Disconnection confirmation
        """
        global _io_client
        old_url = _io_client.base_url if _io_client else None
        _io_client = None
        
        logger.info(f"Disconnected from demo_IO at {old_url}")
        return {
            "ok": True,
            "message": "Disconnected from demo_IO",
            "old_base_url": old_url
        }
    
    # ==================== Health and Status ====================
    
    @router.get(
        "/health",
        summary="IO Health Check",
        description="Check health of demo_IO connection.",
        response_description="Health status",
        responses={
            200: {"description": "Service is healthy"},
            503: {"description": "Service is unavailable"}
        },
        tags=["IO Health"]
    )
    async def api_io_health(request: Request):
        """Check demo_IO service health."""
        try:
            client = _get_client_or_error()
            health = client.health_check()
            return {
                "status": "ok",
                "demo_io_healthy": True,
                "demo_io_info": health
            }
        except HTTPException:
            raise
        except Exception as exc:
            return {
                "status": "error",
                "demo_io_healthy": False,
                "error": str(exc)
            }
    
    @router.get(
        "/status",
        summary="Get GPIO Status",
        description="Returns the current status of the demo_IO GPIO controller.",
        response_description="GPIO controller status",
        responses={
            200: {"description": "GPIO status returned successfully"},
            503: {"description": "demo_IO not connected"}
        },
        tags=["GPIO Status"]
    )
    async def api_io_status(request: Request):
        """Get current GPIO controller status from demo_IO."""
        client = _get_client_or_error()
        return client.get_status()
    
    # ==================== LED Configuration ====================
    
    @router.post(
        "/leds/config",
        summary="Configure LED",
        description="Add or configure an LED on the demo_IO service.",
        response_description="Configuration confirmation",
        responses={
            200: {"description": "LED configured successfully"},
            503: {"description": "demo_IO not connected"}
        },
        tags=["LED Configuration"]
    )
    async def api_config_led(request: LEDConfigRequest):
        """Configure an LED on demo_IO.
        
        Request Body:
            LEDConfigRequest: {
                "name": str,        # Required - LED identifier
                "gpio_pin": int,    # Required - GPIO pin number
                "description": str, # Optional - Description
                "initial_state": bool  # Optional - Initial state
            }
        
        Returns:
            dict: Confirmation of configuration
        """
        client = _get_client_or_error()
        return client.config_led(
            name=request.name,
            gpio_pin=request.gpio_pin,
            description=request.description,
            initial_state=request.initial_state
        )

    # ==================== Bulk Operations (MOVED BEFORE single-LED routes) ====================

    @router.post(
        "/leds/all/set",
        summary="Set All LEDs",
        description="Set all configured LEDs to a specific state on demo_IO.",
        response_description="Bulk set confirmation",
        responses={
            200: {"description": "All LEDs set successfully"},
            503: {"description": "demo_IO not connected"}
        },
        tags=["Bulk Operations"]
    )
    async def api_set_all_leds(request: LEDStateRequest):
        """Set all LEDs to a specific state on demo_IO.
        
        Request Body:
            LEDStateRequest: {
                "state": bool  # Required - True for ON, False for OFF
            }
        
        Returns:
            dict: Confirmation with resulting states of all LEDs
        """
        client = _get_client_or_error()
        return client.set_all_leds(request.state)
    
    @router.post(
        "/leds/all/on",
        summary="All LEDs On",
        description="Turn all configured LEDs ON on demo_IO.",
        response_description="Bulk on confirmation",
        responses={
            200: {"description": "All LEDs turned ON successfully"},
            503: {"description": "demo_IO not connected"}
        },
        tags=["Bulk Operations"]
    )
    async def api_all_on(request: Request):
        """Turn all LEDs ON on demo_IO."""
        client = _get_client_or_error()
        return client.all_leds_on()
    
    @router.post(
        "/leds/all/off",
        summary="All LEDs Off",
        description="Turn all configured LEDs OFF on demo_IO.",
        response_description="Bulk off confirmation",
        responses={
            200: {"description": "All LEDs turned OFF successfully"},
            503: {"description": "demo_IO not connected"}
        },
        tags=["Bulk Operations"]
    )
    async def api_all_off(request: Request):
        """Turn all LEDs OFF on demo_IO."""
        client = _get_client_or_error()
        return client.all_leds_off()
    
    # ==================== LED Status ====================
    
    @router.get(
        "/leds",
        summary="List All LEDs",
        description="Returns the state of all configured LEDs on demo_IO.",
        response_description="All LED states",
        responses={
            200: {"description": "LED states returned successfully"},
            503: {"description": "demo_IO not connected"}
        },
        tags=["GPIO Status"]
    )
    async def api_list_leds(request: Request):
        """Get state of all LEDs from demo_IO."""
        client = _get_client_or_error()
        return client.list_leds()
    
    @router.get(
        "/leds/{name}",
        summary="Get LED State",
        description="Returns the current state of a specific LED from demo_IO.",
        response_description="LED state",
        responses={
            200: {"description": "LED state returned successfully"},
            404: {"description": "LED not found on demo_IO"},
            503: {"description": "demo_IO not connected"}
        },
        tags=["GPIO Status"]
    )
    async def api_get_led_state(name: str, request: Request):
        """Get state of a specific LED from demo_IO.
        
        Args:
            name: LED identifier
        
        Returns:
            dict: LED name and its current state
        """
        client = _get_client_or_error()
        return client.get_led_state(name)
    
    # ==================== LED Control ====================
    
    @router.post(
        "/leds/{name}/set",
        summary="Set LED State",
        description="Set a specific LED to ON or OFF state on demo_IO.",
        response_description="Set confirmation",
        responses={
            200: {"description": "LED state set successfully"},
            404: {"description": "LED not found on demo_IO"},
            503: {"description": "demo_IO not connected"}
        },
        tags=["LED Control"]
    )
    async def api_set_led(name: str, request: LEDStateRequest):
        """Set LED to a specific state on demo_IO.
        
        Args:
            name: LED identifier
        
        Request Body:
            LEDStateRequest: {
                "state": bool  # Required - True for ON, False for OFF
            }
        
        Returns:
            dict: Confirmation with new state
        """
        client = _get_client_or_error()
        return client.set_led(name, request.state)
    
    @router.post(
        "/leds/{name}/toggle",
        summary="Toggle LED",
        description="Toggle the state of a specific LED on demo_IO.",
        response_description="Toggle confirmation",
        responses={
            200: {"description": "LED toggled successfully"},
            404: {"description": "LED not found on demo_IO"},
            503: {"description": "demo_IO not connected"}
        },
        tags=["LED Control"]
    )
    async def api_toggle_led(name: str, request: Request):
        """Toggle an LED state on demo_IO.
        
        Args:
            name: LED identifier
        
        Returns:
            dict: Confirmation with new state
        """
        client = _get_client_or_error()
        return client.toggle_led(name)
    
    @router.post(
        "/leds/{name}/on",
        summary="Turn LED On",
        description="Turn a specific LED ON on demo_IO.",
        response_description="On confirmation",
        responses={
            200: {"description": "LED turned ON successfully"},
            404: {"description": "LED not found on demo_IO"},
            503: {"description": "demo_IO not connected"}
        },
        tags=["LED Control"]
    )
    async def api_turn_on(name: str, request: Request):
        """Turn an LED ON on demo_IO.
        
        Args:
            name: LED identifier
        
        Returns:
            dict: Confirmation with new state
        """
        client = _get_client_or_error()
        return client.turn_on(name)
    
    @router.post(
        "/leds/{name}/off",
        summary="Turn LED Off",
        description="Turn a specific LED OFF on demo_IO.",
        response_description="Off confirmation",
        responses={
            200: {"description": "LED turned OFF successfully"},
            404: {"description": "LED not found on demo_IO"},
            503: {"description": "demo_IO not connected"}
        },
        tags=["LED Control"]
    )
    async def api_turn_off(name: str, request: Request):
        """Turn an LED OFF on demo_IO.
        
        Args:
            name: LED identifier
        
        Returns:
            dict: Confirmation with new state
        """
        client = _get_client_or_error()
        return client.turn_off(name)
    
    # ==================== GPIO Management ====================
    
    @router.post(
        "/initialize",
        summary="Initialize GPIO",
        description="Initialize the GPIO controller on demo_IO.",
        response_description="Initialization confirmation",
        responses={
            200: {"description": "GPIO initialized successfully"},
            503: {"description": "demo_IO not connected"}
        },
        tags=["GPIO Management"]
    )
    async def api_initialize(request: Request):
        """Initialize GPIO controller on demo_IO."""
        client = _get_client_or_error()
        return client.initialize()
    
    @router.post(
        "/cleanup",
        summary="Cleanup GPIO",
        description="Clean up GPIO resources on demo_IO.",
        response_description="Cleanup confirmation",
        responses={
            200: {"description": "GPIO cleaned up successfully"},
            503: {"description": "demo_IO not connected"}
        },
        tags=["GPIO Management"]
    )
    async def api_cleanup(request: Request):
        """Clean up GPIO resources on demo_IO."""
        client = _get_client_or_error()
        return client.cleanup()
    
    return router
