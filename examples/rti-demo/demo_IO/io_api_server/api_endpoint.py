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


# ==================== ACSI Integration Models ====================

class ACSIMappingRequest(BaseModel):
    """Request body for setting ACSI mapping for a device."""
    objRef: str = Field(
        ...,
        description="IEC61850 object reference to map to",
        json_schema_extra={"example": "LD0/LLN0$ST$Mod"}
    )
    fc: str = Field(
        default="ST",
        description="Functional constraint",
        json_schema_extra={"example": "ST"}
    )


class ACSIConfigRequest(BaseModel):
    """Request body for configuring ACSI server connection."""
    url: str = Field(
        default="http://localhost:5001",
        description="ACSI server URL",
        json_schema_extra={"example": "http://localhost:5001"}
    )
    enabled: bool = Field(
        default=True,
        description="Whether ACSI sync is enabled"
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
            {"name": "ACSI Integration", "description": "IEC61850 ACSI server integration"},
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
        "/devices/{name}/reset-latch",
        summary="Reset Latch",
        description="Reset the latched state of a latching button to False.",
        response_description="Reset confirmation",
        responses={
            200: {"description": "Latch reset successfully"},
            404: {"description": "Device not found or not a latching button"},
            500: {"description": "Error resetting latch"}
        },
        tags=["Device Control"]
    )
    async def api_reset_latch(name: str, request: Request):
        """Reset the latched state of a button to False."""
        try:
            _get_device_or_404(name)
            if not _ensure_initialized():
                raise HTTPException(status_code=500, detail="Failed to initialize IO")
            
            result = io_controller.reset_latch(name)
            if result is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Device '{name}' not found or does not support latch reset"
                )
            
            logger.info(f"Reset latch for device '{name}'")
            return {
                "ok": True,
                "name": name,
                "message": "Latch reset successfully"
            }
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"Reset latch for device '{name}' failed: {exc}")
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
    
    # ==================== Configuration Management ====================
    
    @router.post(
        "/config/save",
        summary="Save Configuration",
        description="Save all device configurations to the JSON configuration file.",
        response_description="Save confirmation",
        responses={
            200: {"description": "Configuration saved successfully"},
            500: {"description": "Failed to save configuration"}
        },
        tags=["Configuration"]
    )
    async def api_save_config(request: Request):
        """Save all device configurations to the io_config.json file."""
        try:
            success = io_controller.save_config()
            if not success:
                raise HTTPException(status_code=500, detail="Failed to save configuration")
            
            logger.info("IO configuration saved successfully")
            return {
                "ok": True,
                "message": "Configuration saved successfully",
                "device_count": len(io_controller.configs)
            }
        except Exception as exc:
            logger.error(f"Save configuration failed: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.post(
        "/config/load",
        summary="Load Configuration",
        description="Load device configurations from the JSON configuration file. Replaces existing configurations.",
        response_description="Load confirmation",
        responses={
            200: {"description": "Configuration loaded successfully"},
            404: {"description": "Configuration file not found"},
            500: {"description": "Failed to load configuration"}
        },
        tags=["Configuration"]
    )
    async def api_load_config(request: Request):
        """Load device configurations from the io_config.json file."""
        try:
            # Clear existing configs first
            io_controller.clear_config()
            
            success = io_controller.load_config()
            if not success:
                raise HTTPException(status_code=404, detail="Configuration file not found")
            
            # Re-initialize with loaded configs
            init_success = io_controller.initialize()
            if not init_success:
                raise HTTPException(status_code=500, detail="Failed to initialize devices from configuration")
            
            logger.info("IO configuration loaded successfully")
            return {
                "ok": True,
                "message": "Configuration loaded successfully",
                "device_count": len(io_controller.configs),
                "devices": list(io_controller.configs.keys())
            }
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"Load configuration failed: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.get(
        "/config",
        summary="Get Full Configuration",
        description="Get the full IO configuration including devices, ACSI server settings, and mappings.",
        response_description="Full configuration",
        responses={
            200: {"description": "Configuration returned successfully"},
            500: {"description": "Failed to get configuration"}
        },
        tags=["Configuration"]
    )
    async def api_get_config(request: Request):
        """Get the full IO configuration."""
        try:
            from io_config import _config_to_dict
            from io_controller import get_acsi_config, _device_mappings as global_mappings
            
            devices_list = []
            for name, config in io_controller.configs.items():
                devices_list.append(_config_to_dict(config))
            
            # Get ACSI configuration
            acsi_config = get_acsi_config()
            acsi_dict = None
            if acsi_config:
                acsi_dict = {"url": acsi_config.url, "enabled": acsi_config.enabled}
            
            return {
                "ok": True,
                "devices": devices_list,
                "device_count": len(devices_list),
                "acsi_server": acsi_dict,
                "mappings": dict(global_mappings)
            }
        except Exception as exc:
            logger.error(f"Get configuration failed: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.post(
        "/config/reload",
        summary="Reload Configuration",
        description="Reload device configurations from the JSON file without clearing existing configs.",
        response_description="Reload confirmation",
        responses={
            200: {"description": "Configuration reloaded successfully"},
            404: {"description": "Configuration file not found"},
            500: {"description": "Failed to reload configuration"}
        },
        tags=["Configuration"]
    )
    async def api_reload_config(request: Request):
        """Reload device configurations from the io_config.json file (adds to existing)."""
        try:
            success = io_controller.load_config()
            if not success:
                raise HTTPException(status_code=404, detail="Configuration file not found")
            
            # Re-initialize with updated configs
            init_success = io_controller.initialize()
            if not init_success:
                raise HTTPException(status_code=500, detail="Failed to initialize devices from configuration")
            
            logger.info("IO configuration reloaded successfully")
            return {
                "ok": True,
                "message": "Configuration reloaded successfully",
                "device_count": len(io_controller.configs),
                "devices": list(io_controller.configs.keys())
            }
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"Reload configuration failed: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.post(
        "/config/update",
        summary="Update Full Configuration",
        description="Update the full IO configuration including devices, ACSI server settings, and mappings. "
                    "This endpoint saves all changes to the io_config.json file.",
        response_description="Update confirmation",
        responses={
            200: {"description": "Configuration updated successfully"},
            400: {"description": "Invalid configuration"},
            500: {"description": "Failed to update configuration"}
        },
        tags=["Configuration"]
    )
    async def api_update_full_config(request: Request):
        """Update the full IO configuration from request body and save to file."""
        try:
            body = await request.json()
            
            # Update device configurations if provided
            if "devices" in body:
                from io_config import _dict_to_config
                new_configs = body["devices"]
                for device_dict in new_configs:
                    config = _dict_to_config(device_dict)
                    if config:
                        # Add or update device
                        if config.name in io_controller.configs:
                            io_controller.remove_device(config.name)
                        io_controller.add_device(config)
            
            # Update ACSI configuration if provided
            if "acsi_server" in body:
                acsi_data = body["acsi_server"]
                from io_controller import configure_acsi, ACSIConfig
                acsi_config = ACSIConfig(
                    url=acsi_data.get("url", "http://localhost:5001"),
                    enabled=acsi_data.get("enabled", False)
                )
                configure_acsi(acsi_config)
            
            # Update mappings if provided
            if "mappings" in body:
                from io_controller import _device_mappings as global_mappings
                new_mappings = body["mappings"]
                for device_name, mapping in new_mappings.items():
                    global_mappings[device_name] = mapping
            
            # Save full configuration to file
            from io_config import save_full_config, get_config_path
            from io_controller import _acsi_config, _device_mappings as global_mappings
            config_path = get_config_path()
            acsi_dict = {"url": _acsi_config.url, "enabled": _acsi_config.enabled} if _acsi_config else None
            success = save_full_config(
                devices_config=io_controller.configs,
                acsi_config=acsi_dict,
                device_mappings=global_mappings,
                path=config_path
            )
            
            if not success:
                raise HTTPException(status_code=500, detail="Failed to save configuration to file")
            
            # Re-initialize with updated configs
            init_success = io_controller.initialize()
            if not init_success:
                raise HTTPException(status_code=500, detail="Failed to initialize devices from configuration")
            
            logger.info("Full IO configuration updated and saved successfully")
            return {
                "ok": True,
                "message": "Full configuration updated and saved",
                "device_count": len(io_controller.configs),
                "devices": list(io_controller.configs.keys())
            }
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"Update full configuration failed: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    # ==================== ACSI Mappings ====================

    @router.post(
        "/acsi/mappings/{device_name}",
        summary="Set ACSI Mapping",
        description="Set the IEC61850 object reference mapping for an IO device. "
                    "When the device value changes, it will be written to the ACSI server at the mapped objRef.",
        response_description="Mapping set confirmation",
        responses={
            200: {"description": "Mapping set successfully"},
            404: {"description": "Device not found"},
            500: {"description": "Failed to set mapping"}
        },
        tags=["ACSI Integration"]
    )
    async def api_set_acsi_mapping(
        device_name: str,
        request: ACSIMappingRequest
    ):
        """Set ACSI mapping for a specific device.
        
        Args:
            device_name: Name of the IO device
            request: ACSIMappingRequest with objRef and fc
            
        Returns:
            JSONResponse: {"ok": True, "device": str, "objRef": str, "fc": str}
        """
        from io_controller import _device_mappings as global_mappings
        
        # Check if device exists
        if device_name not in io_controller.configs:
            raise HTTPException(
                status_code=404,
                detail=f"Device '{device_name}' not found"
            )
        
        # Update the global device mappings
        global_mappings[device_name] = {
            "objRef": request.objRef,
            "fc": request.fc
        }
        
        # Persist mappings to file
        from io_controller import _acsi_config
        from io_config import save_full_config, get_config_path
        config_path = get_config_path()
        acsi_dict = {"url": _acsi_config.url, "enabled": _acsi_config.enabled} if _acsi_config else None
        save_full_config(
            devices_config=io_controller.configs,
            device_mappings=global_mappings,
            acsi_config=acsi_dict,
            path=config_path
        )
        
        logger.info(f"Set ACSI mapping: {device_name} -> {request.objRef} (fc={request.fc})")
        return {
            "ok": True,
            "device": device_name,
            "objRef": request.objRef,
            "fc": request.fc,
            "message": "Mapping set and saved to config file"
        }

    @router.get(
        "/acsi/mappings",
        summary="Get All ACSI Mappings",
        description="Returns all device-to-ACSI mappings.",
        response_description="All ACSI mappings",
        responses={
            200: {"description": "List of all ACSI mappings"}
        },
        tags=["ACSI Integration"]
    )
    async def api_get_acsi_mappings(request: Request):
        """Get all device-to-ACSI mappings."""
        from io_controller import _device_mappings as global_mappings
        return {
            "ok": True,
            "mappings": dict(global_mappings),
            "count": len(global_mappings)
        }

    @router.get(
        "/acsi/mappings/{device_name}",
        summary="Get ACSI Mapping",
        description="Get the ACSI mapping for a specific device.",
        response_description="ACSI mapping for device",
        responses={
            200: {"description": "Mapping found"},
            404: {"description": "Device or mapping not found"}
        },
        tags=["ACSI Integration"]
    )
    async def api_get_acsi_mapping(device_name: str):
        """Get ACSI mapping for a specific device."""
        from io_controller import get_device_mapping
        
        mapping = get_device_mapping(device_name)
        if not mapping:
            raise HTTPException(
                status_code=404,
                detail=f"No ACSI mapping found for device '{device_name}'"
            )
        
        return {
            "ok": True,
            "device": device_name,
            "mapping": mapping
        }

    @router.delete(
        "/acsi/mappings/{device_name}",
        summary="Remove ACSI Mapping",
        description="Remove the ACSI mapping for a device.",
        response_description="Mapping removed confirmation",
        responses={
            200: {"description": "Mapping removed"},
            404: {"description": "Device or mapping not found"}
        },
        tags=["ACSI Integration"]
    )
    async def api_remove_acsi_mapping(device_name: str):
        """Remove ACSI mapping for a specific device."""
        from io_controller import _device_mappings as global_mappings
        
        if device_name not in global_mappings:
            raise HTTPException(
                status_code=404,
                detail=f"No ACSI mapping found for device '{device_name}'"
            )
        
        del global_mappings[device_name]
        logger.info(f"Removed ACSI mapping for device: {device_name}")
        return {
            "ok": True,
            "device": device_name,
            "message": "ACSI mapping removed"
        }

    @router.post(
        "/acsi/config",
        summary="Configure ACSI Server",
        description="Configure the ACSI server connection for automatic device sync.",
        response_description="ACSI configuration confirmation",
        responses={
            200: {"description": "ACSI server configured"},
            500: {"description": "Failed to configure ACSI server"}
        },
        tags=["ACSI Integration"]
    )
    async def api_configure_acsi(request: ACSIConfigRequest):
        """Configure ACSI server connection."""
        from io_controller import configure_acsi, ACSIConfig, _acsi_config, _device_mappings
        from io_config import save_full_config, get_config_path
        
        acsi_config = ACSIConfig(url=request.url, enabled=request.enabled)
        configure_acsi(acsi_config)
        
        # Persist ACSI config to file along with current devices and mappings
        acsi_dict = {"url": request.url, "enabled": request.enabled}
        config_path = get_config_path()
        save_full_config(
            devices_config=io_controller.configs,
            acsi_config=acsi_dict,
            device_mappings=_device_mappings,
            path=config_path
        )
        
        logger.info(f"ACSI server configured: {request.url} (enabled={request.enabled})")
        return {
            "ok": True,
            "url": request.url,
            "enabled": request.enabled,
            "message": "ACSI server configuration updated and saved to file"
        }

    @router.get(
        "/acsi/config",
        summary="Get ACSI Configuration",
        description="Get the current ACSI server configuration.",
        response_description="ACSI configuration",
        responses={
            200: {"description": "ACSI configuration"}
        },
        tags=["ACSI Integration"]
    )
    async def api_get_acsi_config(request: Request):
        """Get current ACSI server configuration."""
        from io_controller import get_acsi_config
        
        config = get_acsi_config()
        if not config:
            return {
                "ok": True,
                "configured": False,
                "message": "ACSI server not configured"
            }
        
        return {
            "ok": True,
            "configured": True,
            "url": config.url,
            "enabled": config.enabled
        }

    @router.post(
        "/acsi/sync-mappings",
        summary="Sync All ACSI Mappings",
        description="Replace all ACSI mappings with the provided mappings.",
        response_description="Mappings synced confirmation",
        responses={
            200: {"description": "Mappings synced successfully"},
            500: {"description": "Failed to sync mappings"}
        },
        tags=["ACSI Integration"]
    )
    async def api_sync_acsi_mappings(request: Request):
        """Replace all ACSI mappings with mappings from the request body.
        
        Request body should be: {"mappings": {"device_name": {"objRef": "...", "fc": "..."}, ...}}
        """
        from io_controller import _device_mappings as global_mappings
        
        try:
            body = await request.json()
            new_mappings = body.get("mappings", {})
            
            # Clear existing mappings
            global_mappings.clear()
            
            # Add new mappings
            for device_name, mapping in new_mappings.items():
                global_mappings[device_name] = mapping
            
            # Persist mappings to file
            from io_controller import _acsi_config
            from io_config import save_full_config, get_config_path
            config_path = get_config_path()
            acsi_dict = {"url": _acsi_config.url, "enabled": _acsi_config.enabled} if _acsi_config else None
            save_full_config(
                devices_config=io_controller.configs,
                device_mappings=global_mappings,
                acsi_config=acsi_dict,
                path=config_path
            )
            
            logger.info(f"Synced {len(new_mappings)} ACSI mappings")
            return {
                "ok": True,
                "count": len(global_mappings),
                "mappings": new_mappings,
                "message": "ACSI mappings synced successfully and saved to file"
            }
        except Exception as exc:
            logger.error(f"Failed to sync ACSI mappings: {exc}")
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
