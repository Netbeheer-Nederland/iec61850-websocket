"""
FastAPI Endpoint for Raspberry Pi IO Device Control

This module exposes FastAPI endpoints that interact with the IO controller,
handling device state management and providing a REST API for remote control.

Supports multiple device types:
- LEDs (digital output)
- Potentiometers (analog input)
- Buttons (digital input)
- And more

All endpoints use the unified IOController and device abstraction.
Legacy LED-only endpoints have been removed.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Union

from fastapi import FastAPI, APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from io_controller import IOController
from devices import DeviceType, LEDConfig, PotentiometerConfig, ButtonConfig

logger = logging.getLogger(__name__)


# ==================== API KEY AUTHENTICATION ====================

# API Key can be set via environment variable or will be None (no authentication required)
API_KEY_ENV_VAR = "DEMO_IO_API_KEY"
API_KEY: Optional[str] = os.getenv(API_KEY_ENV_VAR)

# If API_KEY_FILE is set, read the key from that file
API_KEY_FILE = os.getenv("DEMO_IO_API_KEY_FILE")
if API_KEY_FILE and os.path.exists(API_KEY_FILE):
    try:
        with open(API_KEY_FILE, 'r') as f:
            API_KEY = f.read().strip()
        logger.info(f"Loaded API key from file: {API_KEY_FILE}")
    except Exception as e:
        logger.error(f"Failed to read API key from {API_KEY_FILE}: {e}")

# Auth disabled by default if no key is configured
AUTH_ENABLED = API_KEY is not None and API_KEY != ""


# ==================== Pydantic Models ====================


class DeviceConfigRequest(BaseModel):
    """Request body for configuring any IO device.
    
    Used by: POST /api/io/devices/config
    
    The device_type field determines which specific fields are used:
    - "led": uses identifier as gpio_pin
    - "potentiometer": uses adc_channel (or identifier)
    - "button": uses identifier as gpio_pin
    """
    name: str = Field(
        ...,
        description="Unique identifier for the device",
        json_schema_extra={"example": "led1"}
    )
    device_type: str = Field(
        ...,
        description="Type of device: led, potentiometer, button, pwm, etc.",
        json_schema_extra={"example": "led"}
    )
    identifier: Optional[int] = Field(
        default=None,
        description="GPIO pin or ADC channel number",
        ge=0,
        json_schema_extra={"example": 17}
    )
    description: str = Field(
        default="",
        description="Optional description of the device",
        json_schema_extra={"example": "Status indicator LED"}
    )
    initial_state: Optional[bool] = Field(
        default=None,
        description="Initial state for output devices",
        json_schema_extra={"example": False}
    )
    # Potentiometer-specific
    adc_channel: Optional[int] = Field(
        default=None,
        description="ADC channel number (for potentiometer)",
        ge=0,
        le=7,
        json_schema_extra={"example": 0}
    )
    min_value: Optional[float] = Field(
        default=None,
        description="Minimum value for potentiometer readings",
        json_schema_extra={"example": 0.0}
    )
    max_value: Optional[float] = Field(
        default=None,
        description="Maximum value for potentiometer readings",
        json_schema_extra={"example": 100.0}
    )
    is_inverted: Optional[bool] = Field(
        default=None,
        description="Whether to invert potentiometer readings",
        json_schema_extra={"example": False}
    )
    # Button-specific
    debounce_time: Optional[float] = Field(
        default=None,
        description="Debounce time in seconds for buttons",
        json_schema_extra={"example": 0.05}
    )
    pull_up: Optional[bool] = Field(
        default=None,
        description="Use internal pull-up resistor for buttons",
        json_schema_extra={"example": True}
    )


class DeviceWriteRequest(BaseModel):
    """Request body for writing to a device."""
    value: Union[bool, float] = Field(
        ...,
        description="Value to write (bool for digital, float for analog)",
        json_schema_extra={"example": True}
    )


class DeviceSetStateRequest(BaseModel):
    """Request body for setting device state (bool only)."""
    state: bool = Field(
        ...,
        description="True for ON/High, False for OFF/Low",
        json_schema_extra={"example": True}
    )


# ==================== FastAPI Application ====================


def create_fastapi_app(io_controller: Optional[IOController] = None) -> FastAPI:
    """Create and configure the FastAPI application for IO device control.
    
    Args:
        io_controller: Optional IOController instance. If None, a new one is created.
        
    Returns:
        FastAPI application instance
    """
    # Create IO controller if not provided
    if io_controller is None:
        io_controller = IOController()
    
    app = FastAPI(
        title="Raspberry Pi IO Device Control API",
        description="REST API for Raspberry Pi IO device control. "
                    "Manages various IO devices (LEDs, potentiometers, buttons), "
                    "provides remote control capabilities, and offers comprehensive device monitoring.",
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        openapi_tags=[
            {"name": "Discovery", "description": "API introspection and endpoint discovery"},
            {"name": "Health", "description": "Service health checks and status monitoring"},
            {"name": "Device Configuration", "description": "Configure and manage IO devices"},
            {"name": "Device Control", "description": "Control individual IO device states"},
            {"name": "Bulk Operations", "description": "Control multiple devices at once"},
            {"name": "Device Status", "description": "Get IO controller and device status"},
        ]
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Add API key authentication middleware if enabled
    if AUTH_ENABLED:
        @app.middleware("http")
        async def api_key_middleware(request: Request, call_next):
            """Middleware to check API key on all requests when authentication is enabled."""
            # Skip authentication for health check, auth status, and docs
            if request.url.path in ["/api/io/health", "/api/io/auth/status", "/docs", "/openapi.json", "/redoc"]:
                return await call_next(request)
            
            x_api_key = request.headers.get("x-api-key")
            
            if not x_api_key:
                logger.warning(f"Missing API key in request: {request.method} {request.url}")
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Authentication required. Provide X-API-Key header."},
                    headers={"WWW-Authenticate": "ApiKey"}
                )
            
            if x_api_key != API_KEY:
                logger.warning(f"Invalid API key attempt: {request.method} {request.url}")
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid API key."},
                    headers={"WWW-Authenticate": "ApiKey"}
                )
            
            return await call_next(request)
    
    # Create router with the controller
    router = create_io_router(app, io_controller)
    app.include_router(router)
    
    # Store controller reference in app state
    app.state.io_controller = io_controller
    
    return app


def create_io_router(app: FastAPI, io_controller: IOController) -> APIRouter:
    """Create a FastAPI router for the IO device control API.
    
    Args:
        app: FastAPI application instance
        io_controller: IOController instance
        
    Returns:
        APIRouter instance with all endpoints configured
    """
    router = APIRouter(
        prefix="/api/io",
        tags=["io-device-control"],
        responses={404: {"description": "Not found"}, 500: {"description": "Internal server error"}}
    )
    
    # ==================== Helper Functions ====================
    
    def _ensure_initialized() -> bool:
        """Ensure IO controller is initialized."""
        if not io_controller._initialized:
            if not io_controller.initialize():
                logger.error("Failed to initialize IO controller")
                return False
        return True
    
    def _get_device_or_404(name: str):
        """Get device config or raise 404."""
        if name not in io_controller.configs:
            raise HTTPException(
                status_code=404,
                detail=f"Device '{name}' not found. Available devices: {list(io_controller.configs.keys())}"
            )
        return io_controller.configs[name]
    
    # ==================== Route Handlers ====================
    
    @router.get(
        "/",
        summary="API Root",
        description="Returns basic API information and available endpoints.",
        response_description="API information",
        tags=["Discovery"]
    )
    async def api_root(request: Request):
        """Get API root information."""
        endpoints = {
            "GET /api/io/": "API information",
            "GET /api/io/health": "Health check endpoint",
            "GET /api/io/auth/status": "Authentication status",
            "GET /api/io/status": "Get IO controller status",
            "POST /api/io/initialize": "Initialize IO controller",
            "POST /api/io/cleanup": "Clean up IO resources",
            "GET /api/io/devices": "List all IO devices",
            "GET /api/io/devices/types": "List supported device types",
            "GET /api/io/devices/{name}": "Get device status",
            "POST /api/io/devices/config": "Configure a new IO device",
            "POST /api/io/devices/{name}/write": "Write to a device",
            "POST /api/io/devices/{name}/read": "Read from a device",
            "POST /api/io/devices/{name}/toggle": "Toggle device state",
            "POST /api/io/devices/{name}/set": "Set device boolean state",
            "POST /api/io/devices/inputs/read-all": "Read all input devices",
            "POST /api/io/devices/outputs/set-all": "Set all output devices",
        }
        
        return {
            "message": "Raspberry Pi IO Device Control API",
            "version": "2.0.0",
            "docs": "/api/io/docs",
            "available_endpoints": endpoints
        }
    
    @router.get(
        "/status",
        summary="Get IO Controller Status",
        description="Returns the current status of the IO controller, including all device states.",
        response_description="IO controller status",
        responses={
            200: {"description": "IO status returned successfully"},
            500: {"description": "Error retrieving IO status"}
        },
        tags=["Device Status"]
    )
    async def api_status(request: Request):
        """Get current IO controller status."""
        try:
            return io_controller.get_status()
        except Exception as exc:
            logger.error(f"Get IO status failed: {exc}")
            logger.exception("Exception in api_status")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.get(
        "/health",
        summary="Health Check",
        description="Generic health endpoint used by external discovery systems. No authentication required.",
        response_description="Health status",
        responses={
            200: {"description": "Service is healthy"},
            500: {"description": "Service is unhealthy"}
        },
        tags=["Health"]
    )
    async def api_health(request: Request):
        """Generic health endpoint for external discovery."""
        try:
            device_count = len(io_controller.devices)
            
            return {
                "status": "ok",
                "service": "IO Device Control",
                "version": "2.0.0",
                "io_initialized": io_controller._initialized,
                "device_count": device_count,
                "auth_enabled": AUTH_ENABLED,
            }
        except Exception as exc:
            logger.error(f"Health check failed: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.get(
        "/auth/status",
        summary="Authentication Status",
        description="Check if API key authentication is enabled. No authentication required.",
        response_description="Authentication status",
        responses={
            200: {"description": "Authentication status returned"}
        },
        tags=["Health"]
    )
    async def api_auth_status(request: Request):
        """Check if authentication is enabled."""
        return {
            "auth_enabled": AUTH_ENABLED,
            "api_key_configured": API_KEY is not None and API_KEY != "",
            "api_key_env_var": API_KEY_ENV_VAR,
            "message": "Authentication is enabled" if AUTH_ENABLED else "Authentication is disabled - no API key configured"
        }
    
    @router.post(
        "/initialize",
        summary="Initialize IO",
        description="Initialize the IO controller. This must be called before controlling devices.",
        response_description="Initialization confirmation",
        responses={
            200: {"description": "IO initialized successfully"},
            500: {"description": "Error initializing IO"}
        },
        tags=["Device Status"]
    )
    async def api_initialize(request: Request):
        """Initialize IO controller."""
        try:
            success = io_controller.initialize()
            if success:
                device_count = len(io_controller.devices)
                logger.info("IO controller initialized via API")
                return {
                    "ok": True,
                    "message": "IO controller initialized",
                    "device_count": device_count
                }
            else:
                raise HTTPException(status_code=500, detail="Failed to initialize IO")
        except Exception as exc:
            logger.error(f"IO initialization failed: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.post(
        "/cleanup",
        summary="Cleanup IO",
        description="Clean up IO resources. Call this when done to free resources.",
        response_description="Cleanup confirmation",
        responses={
            200: {"description": "IO cleaned up successfully"},
            500: {"description": "Error during cleanup"}
        },
        tags=["Device Status"]
    )
    async def api_cleanup(request: Request):
        """Clean up IO resources."""
        try:
            io_controller.cleanup()
            logger.info("IO controller cleaned up via API")
            return {
                "ok": True,
                "message": "IO resources cleaned up"
            }
        except Exception as exc:
            logger.error(f"IO cleanup failed: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    # ==================== DEVICE ENDPOINTS ====================
    
    @router.get(
        "/devices",
        summary="List All Devices",
        description="Returns information about all configured IO devices.",
        response_description="All device information",
        responses={
            200: {"description": "Device list returned successfully"},
            500: {"description": "Error retrieving device list"}
        },
        tags=["Device Configuration"]
    )
    async def api_list_devices(request: Request):
        """Get list of all configured devices."""
        try:
            if not _ensure_initialized():
                raise HTTPException(status_code=500, detail="Failed to initialize IO")
            
            devices = io_controller.list_devices()
            device_types = io_controller.list_device_types()
            device_details = {}
            
            for name in devices:
                status = io_controller.get_device_status(name)
                device_details[name] = status
            
            return {
                "ok": True,
                "devices": devices,
                "device_types": {name: dt.value for name, dt in device_types.items()},
                "details": device_details
            }
        except Exception as exc:
            logger.error(f"List devices failed: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.get(
        "/devices/types",
        summary="List Device Types",
        description="Returns list of supported device types.",
        response_description="Supported device types",
        tags=["Device Configuration"]
    )
    async def api_list_device_types(request: Request):
        """Get list of supported device types."""
        try:
            return {
                "ok": True,
                "types": [dt.value for dt in DeviceType]
            }
        except Exception as exc:
            logger.error(f"List device types failed: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.get(
        "/devices/{name}",
        summary="Get Device Status",
        description="Returns detailed status of a specific device.",
        response_description="Device status",
        responses={
            200: {"description": "Device status returned successfully"},
            404: {"description": "Device not found"},
            500: {"description": "Error retrieving device status"}
        },
        tags=["Device Configuration"]
    )
    async def api_get_device(name: str, request: Request):
        """Get detailed status of a specific device."""
        try:
            _get_device_or_404(name)
            return io_controller.get_device_status(name)
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"Get device '{name}' status failed: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.post(
        "/devices/config",
        summary="Configure Device",
        description="Configure a new IO device (LED, potentiometer, button, etc.).",
        response_description="Configuration confirmation",
        responses={
            200: {"description": "Device configured successfully"},
            400: {"description": "Invalid configuration"},
            500: {"description": "Error configuring device"}
        },
        tags=["Device Configuration"]
    )
    async def api_config_device(request: DeviceConfigRequest):
        """Configure a new IO device."""
        try:
            device_type = DeviceType(request.device_type)
            
            # Create appropriate config based on device type
            if device_type == DeviceType.LED:
                config = LEDConfig(
                    name=request.name,
                    gpio_pin=request.identifier or 0,
                    description=request.description or "",
                    initial_state=request.initial_state or False
                )
            elif device_type == DeviceType.POTENTIOMETER:
                config = PotentiometerConfig(
                    name=request.name,
                    adc_channel=request.adc_channel or request.identifier or 0,
                    description=request.description or "",
                    min_value=request.min_value or 0.0,
                    max_value=request.max_value or 100.0,
                    is_inverted=request.is_inverted or False
                )
            elif device_type == DeviceType.BUTTON:
                config = ButtonConfig(
                    name=request.name,
                    gpio_pin=request.identifier or 0,
                    description=request.description or "",
                    initial_state=request.initial_state or False,
                    debounce_time=request.debounce_time or 0.05,
                    pull_up=request.pull_up or True
                )
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Device type '{request.device_type}' not yet supported for configuration via API"
                )
            
            io_controller.add_device(config)
            logger.info(f"Configured device: {request.name} (type: {request.device_type})")
            
            return {
                "ok": True,
                "message": f"Device '{request.name}' configured",
                "name": request.name,
                "device_type": request.device_type
            }
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"Configure device failed: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.post(
        "/devices/{name}/write",
        summary="Write to Device",
        description="Write a value to a device.",
        response_description="Write confirmation",
        responses={
            200: {"description": "Value written successfully"},
            404: {"description": "Device not found"},
            400: {"description": "Invalid value for device"},
            500: {"description": "Error writing to device"}
        },
        tags=["Device Control"]
    )
    async def api_write_device(name: str, request: DeviceWriteRequest):
        """Write a value to a device."""
        try:
            _get_device_or_404(name)
            if not _ensure_initialized():
                raise HTTPException(status_code=500, detail="Failed to initialize IO")
            
            success = io_controller.write(name, request.value)
            if not success:
                raise HTTPException(status_code=500, detail=f"Failed to write to device '{name}'")
            
            new_value = io_controller.read(name)
            logger.info(f"Wrote to device '{name}': {request.value}")
            
            return {
                "ok": True,
                "name": name,
                "value": request.value,
                "actual_value": new_value
            }
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"Write to device '{name}' failed: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.post(
        "/devices/{name}/read",
        summary="Read from Device",
        description="Read the current value from a device.",
        response_description="Device value",
        responses={
            200: {"description": "Value read successfully"},
            404: {"description": "Device not found"},
            500: {"description": "Error reading from device"}
        },
        tags=["Device Control"]
    )
    async def api_read_device(name: str, request: Request):
        """Read the current value from a device."""
        try:
            _get_device_or_404(name)
            if not _ensure_initialized():
                raise HTTPException(status_code=500, detail="Failed to initialize IO")
            
            value = io_controller.read(name)
            logger.info(f"Read from device '{name}': {value}")
            
            return {
                "ok": True,
                "name": name,
                "value": value
            }
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"Read from device '{name}' failed: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.post(
        "/devices/{name}/toggle",
        summary="Toggle Device",
        description="Toggle the state of a device (ON/OFF or High/Low).",
        response_description="Toggle confirmation",
        responses={
            200: {"description": "Device toggled successfully"},
            404: {"description": "Device not found"},
            500: {"description": "Error toggling device"}
        },
        tags=["Device Control"]
    )
    async def api_toggle_device(name: str, request: Request):
        """Toggle a device state."""
        try:
            _get_device_or_404(name)
            if not _ensure_initialized():
                raise HTTPException(status_code=500, detail="Failed to initialize IO")
            
            new_state = io_controller.toggle(name)
            if new_state is None:
                raise HTTPException(status_code=500, detail=f"Failed to toggle device '{name}'")
            
            logger.info(f"Toggled device '{name}' to {'ON' if new_state else 'OFF'}")
            
            return {
                "ok": True,
                "name": name,
                "state": new_state
            }
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"Toggle device '{name}' failed: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.post(
        "/devices/{name}/set",
        summary="Set Device State",
        description="Set a device to a specific boolean state.",
        response_description="Set confirmation",
        responses={
            200: {"description": "Device state set successfully"},
            404: {"description": "Device not found"},
            500: {"description": "Error setting device state"}
        },
        tags=["Device Control"]
    )
    async def api_set_device(name: str, request: DeviceSetStateRequest):
        """Set a device to a specific boolean state."""
        try:
            _get_device_or_404(name)
            if not _ensure_initialized():
                raise HTTPException(status_code=500, detail="Failed to initialize IO")
            
            success = io_controller.write(name, request.state)
            if not success:
                raise HTTPException(status_code=500, detail=f"Failed to set device '{name}'")
            
            new_value = io_controller.read(name)
            logger.info(f"Set device '{name}' to {'ON' if request.state else 'OFF'}")
            
            return {
                "ok": True,
                "name": name,
                "state": request.state,
                "actual_value": new_value
            }
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"Set device '{name}' failed: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.post(
        "/devices/inputs/read-all",
        summary="Read All Inputs",
        description="Read values from all input devices.",
        response_description="All input device values",
        tags=["Bulk Operations"]
    )
    async def api_read_all_inputs(request: Request):
        """Read all input devices."""
        try:
            if not _ensure_initialized():
                raise HTTPException(status_code=500, detail="Failed to initialize IO")
            
            values = io_controller.read_all_inputs()
            logger.info(f"Read all {len(values)} input devices")
            
            return {
                "ok": True,
                "inputs": values
            }
        except Exception as exc:
            logger.error(f"Read all inputs failed: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.post(
        "/devices/outputs/set-all",
        summary="Set All Outputs",
        description="Set all output devices to a specific state.",
        response_description="Bulk set confirmation",
        tags=["Bulk Operations"]
    )
    async def api_set_all_outputs(request: DeviceSetStateRequest):
        """Set all output devices to a specific state."""
        try:
            if not _ensure_initialized():
                raise HTTPException(status_code=500, detail="Failed to initialize IO")
            
            results = io_controller.set_all_outputs(request.state)
            logger.info(f"Set all {len(results)} output devices to {'ON' if request.state else 'OFF'}")
            
            return {
                "ok": True,
                "state": request.state,
                "results": results
            }
        except Exception as exc:
            logger.error(f"Set all outputs failed: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    return router


if __name__ == "__main__":
    import uvicorn
    import os
    import platform
    
    # Create the FastAPI app with an IOController
    app = create_fastapi_app()
    
    # Get port from environment or use default
    # On Windows, port 8000 might be reserved, so we use 8080 as default
    port = int(os.getenv("PORT", "8080"))
    
    # On Windows, use localhost instead of 0.0.0.0 to avoid permission issues
    if platform.system() == "Windows":
        host = "localhost"
    else:
        host = "0.0.0.0"
    
    # Run the server
    uvicorn.run(app, host=host, port=port)
