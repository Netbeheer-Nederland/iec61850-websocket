"""
IO Router for FSP BFF - Provides IO device control routes that proxy to demo_IO.

This module creates a FastAPI router that provides IO/device control endpoints
for the FSP service, which proxy requests to a connected demo_IO instance.

The IO router allows FSP to:
- Expose device control endpoints to its clients (primarily LED control)
- Proxy device control requests to demo_IO
- Manage connection to demo_IO service
- Manage IEC 61850 object mappings to IO devices
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .async_client_io import AsyncDemoIOClient
from .mapping_manager import IOMappingManager

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


# ==================== Mapping Models ====================

class IOMappingRequest(BaseModel):
    """Request body for adding/updating an IO mapping."""
    device_name: str = Field(
        ...,
        description="Unique IO device identifier",
        json_schema_extra={"example": "LD0/GGIO1$ST$Ind1"}
    )
    objRef: Optional[str] = Field(
        default=None,
        description="IEC 61850 object reference (optional)",
        json_schema_extra={"example": "LD0/GGIO1$ST$Ind1"}
    )
    description: str = Field(
        default="",
        description="IO device description",
        json_schema_extra={"example": "GGIO Indication 1"}
    )


class IOMappingResponse(BaseModel):
    """Response for IO mapping operations."""
    device_name: str
    objRef: Optional[str] = None
    description: str = ""
    initial_state: bool = False


class MappingListResponse(BaseModel):
    """Response for listing all IO mappings."""
    mappings: Dict[str, IOMappingResponse] = Field(
        default_factory=dict,
        description="Dictionary of all IO device mappings by device_name"
    )
    count: int = Field(default=0, description="Total number of mappings")


# ==================== Router State Management ====================
# 
# Using module-level state but with better encapsulation.
# For production, consider using FastAPI's app.state or dependency injection.
#
# State container class to avoid global variable pollution

class _IORouterState:
    """Container for IO router state to avoid global variables."""
    def __init__(self):
        self.io_client: Optional[AsyncDemoIOClient] = None
        self.mapping_manager: Optional[IOMappingManager] = None
        self._lock = threading.Lock()

# Module-level state instance
_router_state = _IORouterState()


def get_io_client() -> Optional[AsyncDemoIOClient]:
    """Get the demo_IO async client instance."""
    return _router_state.io_client


def set_io_client(client: AsyncDemoIOClient) -> None:
    """Set the demo_IO async client instance."""
    with _router_state._lock:
        _router_state.io_client = client
        logger.info(f"AsyncDemoIOClient configured with base URL: {client.base_url}")


def get_mapping_manager() -> IOMappingManager:
    """Get or create the mapping manager instance."""
    with _router_state._lock:
        if _router_state.mapping_manager is None:
            _router_state.mapping_manager = IOMappingManager()
        return _router_state.mapping_manager


def set_mapping_manager(manager: IOMappingManager) -> None:
    """Set the mapping manager instance."""
    with _router_state._lock:
        _router_state.mapping_manager = manager
        logger.info("IOMappingManager configured")


def create_io_router() -> APIRouter:
    """Create a FastAPI router for IO/device control via demo_IO proxy.
    
    This router provides endpoints that proxy device control requests (IO devices)
    to a connected demo_IO service. The demo_IO connection is configured via
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
        set_io_client(AsyncDemoIOClient(base_url=demo_io_url))
        logger.info(f"AsyncDemoIOClient auto-configured from DEMO_IO_URL: {demo_io_url}")
    
    # ==================== Helper Functions ====================
    
    async def _get_client_or_error() -> AsyncDemoIOClient:
        """Get demo_IO async client or raise error if not configured."""
        client = get_io_client()
        if client is None:
            raise HTTPException(
                status_code=500,
                detail="demo_IO client not configured. "
                       "Configure connection via POST /api/io/connect or set DEMO_IO_URL environment variable."
            )
        
        # Check if service is healthy (async call)
        if not await client.is_healthy():
            raise HTTPException(
                status_code=503,
                detail=f"demo_IO service at {client.base_url} is not responding. "
                       "Check if the service is running and accessible."
            )
        
        return client
    
    def _handle_io_error(func_name: str):
        """Decorator to handle demo_IO async client errors."""
        def decorator(func):
            async def wrapper(*args, **kwargs):
                try:
                    client = await _get_client_or_error()
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
            client = AsyncDemoIOClient(base_url=config.base_url)
            
            # Test connection (async)
            if not await client.is_healthy():
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
            "healthy": await client.is_healthy()
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
        old_url = _router_state.io_client.base_url if _router_state.io_client else None
        with _router_state._lock:
            # Close the async client connection
            if _router_state.io_client:
                await _router_state.io_client.aclose()
            _router_state.io_client = None
        
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
            client = await _get_client_or_error()
            health = await client.health_check()
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
        client = await _get_client_or_error()
        return await client.get_status()
    
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
        client = await _get_client_or_error()
        return await client.config_led(
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
        client = await _get_client_or_error()
        return await client.set_all_leds(request.state)
    
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
        client = await _get_client_or_error()
        return await client.all_leds_on()
    
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
        client = await _get_client_or_error()
        return await client.all_leds_off()
    
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
        client = await _get_client_or_error()
        return await client.list_leds()
    
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
        client = await _get_client_or_error()
        return await client.get_led_state(name)
    
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
        client = await _get_client_or_error()
        return await client.set_device(name, request.state)
    
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
        client = await _get_client_or_error()
        return await client.toggle_led(name)
    
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
        client = await _get_client_or_error()
        return await client.turn_on(name)
    
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
        client = await _get_client_or_error()
        return await client.turn_off(name)
    
    # ==================== Device Control (Generic) ====================
    
    @router.post(
        "/devices/{name}/set",
        summary="Set Device State",
        description="Set a specific device to ON or OFF state on demo_IO. Generic endpoint for all devices.",
        response_description="Set confirmation",
        responses={
            200: {"description": "Device state set successfully"},
            404: {"description": "Device not found on demo_IO"},
            503: {"description": "demo_IO not connected"}
        },
        tags=["Device Control"]
    )
    async def api_set_device(name: str, request: LEDStateRequest):
        """Set a device to a specific state on demo_IO.
        
        This is a generic endpoint that works for all output devices (LEDs, etc.).
        
        Args:
            name: Device identifier
        
        Request Body:
            LEDStateRequest: {
                "state": bool  # Required - True for ON, False for OFF
            }
        
        Returns:
            dict: Confirmation with new state
        """
        client = await _get_client_or_error()
        return await client.set_device(name, request.state)
    
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
        client = await _get_client_or_error()
        return await client.initialize()
    
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
        client = await _get_client_or_error()
        return await client.cleanup()
    
    # ==================== Mapping Management ====================
    
    @router.post(
        "/mappings/add",
        summary="Add IO Mapping",
        description="Add a new mapping between IEC 61850 object reference and IO device.",
        response_description="Mapping added successfully",
        responses={
            200: {"description": "Mapping added successfully"},
            409: {"description": "Mapping already exists"},
            500: {"description": "Failed to add mapping"}
        },
        tags=["IO Mapping"]
    )
    async def api_add_mapping(request: IOMappingRequest):
        """Add a new IO mapping.
        
        Request Body:
            IOMappingRequest: {
                "device_name": str,        # Required - IO device identifier
                "objRef": str,           # Optional - IEC 61850 object reference
                "description": str,      # Optional - IO device description
                "initial_state": bool    # Optional - Initial state
            }
        
        Returns:
            dict: Confirmation of mapping addition
        """
        try:
            manager = get_mapping_manager()
            mapping = manager.add_mapping(
                device_name=request.device_name,
                obj_ref=request.objRef,
                description=request.description,
                initial_state=request.initial_state
            )
            manager.save()
            
            logger.info(f"Added mapping: {request.device_name} -> {request.objRef}")
            return {
                "ok": True,
                "message": f"Mapping added for {request.device_name}",
                "mapping": mapping
            }
        except Exception as exc:
            logger.error(f"Failed to add mapping: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.get(
        "/mappings",
        summary="List All Mappings",
        description="Returns all IO mappings between IEC 61850 references and IO devices.",
        response_description="List of all IO mappings",
        responses={
            200: {"description": "List of all mappings"}
        },
        tags=["IO Mapping"]
    )
    async def api_list_mappings(request: Request):
        """Get all IO mappings.
        
        Returns:
            dict: All mappings with their configurations
        """
        try:
            manager = get_mapping_manager()
            mappings = manager.get_all_mappings()
            
            # Convert to response format
            response_mappings = {}
            for device_name, config in mappings.items():
                response_mappings[device_name] = IOMappingResponse(
                    device_name=device_name,
                    objRef=config.get("objRef"),
                    description=config.get("description", ""),
                    initial_state=config.get("initial_state", False)
                )
            
            return MappingListResponse(
                mappings=response_mappings,
                count=len(response_mappings)
            )
        except Exception as exc:
            logger.error(f"Failed to list mappings: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.get(
        "/mappings/{device_name}",
        summary="Get Mapping",
        description="Get a specific IO mapping by device name.",
        response_description="Mapping configuration",
        responses={
            200: {"description": "Mapping found"},
            404: {"description": "Mapping not found"}
        },
        tags=["IO Mapping"]
    )
    async def api_get_mapping(device_name: str, request: Request):
        """Get a specific IO mapping by device name.
        
        Args:
            device_name: IO device identifier
            
        Returns:
            dict: Mapping configuration
        """
        try:
            manager = get_mapping_manager()
            mapping = manager.get_mapping(device_name)
            
            if not mapping:
                raise HTTPException(
                    status_code=404,
                    detail=f"No mapping found for device: {device_name}"
                )
            
            return IOMappingResponse(
                device_name=device_name,
                objRef=mapping.get("objRef"),
                description=mapping.get("description", ""),
                initial_state=mapping.get("initial_state", False)
            )
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"Failed to get mapping for {device_name}: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.get(
        "/mappings/by-objref/{objRef:path}",
        summary="Get Mapping by objRef",
        description="Get IO mapping by IEC 61850 object reference.",
        response_description="Mapping configuration",
        responses={
            200: {"description": "Mapping found"},
            404: {"description": "Mapping not found"}
        },
        tags=["IO Mapping"]
    )
    async def api_get_mapping_by_objref(objRef: str, request: Request):
        """Get IO mapping by IEC 61850 object reference.
        
        Args:
            objRef: IEC 61850 object reference
            
        Returns:
            dict: Mapping configuration with device_name
        """
        try:
            manager = get_mapping_manager()
            mapping = manager.get_device_by_objref(objRef)
            
            if not mapping:
                raise HTTPException(
                    status_code=404,
                    detail=f"No mapping found for objRef: {objRef}"
                )
            
            return {
                "ok": True,
                "device_name": mapping["device_name"],
                "mapping": IOMappingResponse(
                    device_name=mapping["device_name"],
                    objRef=mapping.get("objRef"),
                    description=mapping.get("description", ""),
                    initial_state=mapping.get("initial_state", False)
                )
            }
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"Failed to get mapping for objRef {objRef}: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.delete(
        "/mappings/{device_name}",
        summary="Remove Mapping",
        description="Remove an IO mapping by device name.",
        response_description="Deletion confirmation",
        responses={
            200: {"description": "Mapping removed successfully"},
            404: {"description": "Mapping not found"},
            500: {"description": "Failed to remove mapping"}
        },
        tags=["IO Mapping"]
    )
    async def api_remove_mapping(device_name: str, request: Request):
        """Remove an IO mapping by device name.
        
        Args:
            device_name: IO device identifier
            
        Returns:
            dict: Deletion confirmation
        """
        try:
            manager = get_mapping_manager()
            if not manager.remove_mapping(device_name):
                raise HTTPException(
                    status_code=404,
                    detail=f"No mapping found for device: {device_name}"
                )
            
            manager.save()
            logger.info(f"Removed mapping: {device_name}")
            return {
                "ok": True,
                "message": f"Mapping removed for {device_name}"
            }
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"Failed to remove mapping for {device_name}: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.post(
        "/mappings/load",
        summary="Load Mappings",
        description="Reload mappings from the JSON file.",
        response_description="Load confirmation",
        responses={
            200: {"description": "Mappings loaded successfully"},
            500: {"description": "Failed to load mappings"}
        },
        tags=["IO Mapping"]
    )
    async def api_load_mappings(request: Request):
        """Reload mappings from the JSON file.
        
        Returns:
            dict: Load confirmation with count of mappings
        """
        try:
            manager = get_mapping_manager()
            success = manager.load()
            
            return {
                "ok": success,
                "message": "Mappings reloaded",
                "count": len(manager.get_all_mappings())
            }
        except Exception as exc:
            logger.error(f"Failed to load mappings: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.post(
        "/mappings/save",
        summary="Save Mappings",
        description="Save current mappings to the JSON file.",
        response_description="Save confirmation",
        responses={
            200: {"description": "Mappings saved successfully"},
            500: {"description": "Failed to save mappings"}
        },
        tags=["IO Mapping"]
    )
    async def api_save_mappings(request: Request):
        """Save current mappings to the JSON file.
        
        Returns:
            dict: Save confirmation with count of mappings
        """
        try:
            manager = get_mapping_manager()
            success = manager.save()
            
            return {
                "ok": success,
                "message": "Mappings saved",
                "count": len(manager.get_all_mappings())
            }
        except Exception as exc:
            logger.error(f"Failed to save mappings: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.post(
        "/mappings/clear",
        summary="Clear All Mappings",
        description="Remove all IO device mappings.",
        response_description="Clear confirmation",
        responses={
            200: {"description": "All mappings cleared successfully"},
            500: {"description": "Failed to clear mappings"}
        },
        tags=["IO Mapping"]
    )
    async def api_clear_mappings(request: Request):
        """Clear all IO device mappings.
        
        Returns:
            dict: Clear confirmation
        """
        try:
            manager = get_mapping_manager()
            manager.clear()
            manager.save()
            
            logger.info("Cleared all IO device mappings")
            return {
                "ok": True,
                "message": "All mappings cleared"
            }
        except Exception as exc:
            logger.error(f"Failed to clear mappings: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.get(
        "/mappings/objrefs",
        summary="List All objRefs",
        description="Returns all IEC 61850 object references that have IO device mappings.",
        response_description="List of objRefs",
        responses={
            200: {"description": "List of objRefs"}
        },
        tags=["IO Mapping"]
    )
    async def api_list_objrefs(request: Request):
        """Get all IEC 61850 object references with IO device mappings.
        
        Returns:
            dict: List of all objRefs with mappings
        """
        try:
            manager = get_mapping_manager()
            objrefs = manager.list_mapped_objrefs()
            
            return {
                "ok": True,
                "objRefs": objrefs,
                "count": len(objrefs)
            }
        except Exception as exc:
            logger.error(f"Failed to list objRefs: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    return router
