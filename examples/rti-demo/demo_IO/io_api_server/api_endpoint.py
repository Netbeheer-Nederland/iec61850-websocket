"""
FastAPI Endpoint for Raspberry Pi GPIO/LED Control

This module exposes FastAPI endpoints that interact with the GPIO controller,
handling LED state management and providing a REST API for remote control.

Following the pattern from bff_endpoint.py in the SO module.
"""

from __future__ import annotations

import logging
import traceback
from typing import Any, Dict, Optional

from fastapi import FastAPI, APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict

from gpio_controller import GPIOController

logger = logging.getLogger(__name__)

# ==================== Pydantic Models ====================


class LEDConfigRequest(BaseModel):
    """Request body for configuring an LED.
    
    Used by: POST /api/leds/config
    """
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
    """Request body for setting LED state.
    
    Used by: POST /api/leds/{name}/set
    """
    state: bool = Field(
        ...,
        description="True for ON, False for OFF",
        json_schema_extra={"example": True}
    )


class LEDToggleRequest(BaseModel):
    """Request body for toggling LED state.
    
    Used by: POST /api/leds/{name}/toggle
    """
    pass  # Empty body, just the action matters


class AllLEDsStateRequest(BaseModel):
    """Request body for setting all LEDs state.
    
    Used by: POST /api/leds/all/set
    """
    state: bool = Field(
        ...,
        description="True for ON, False for OFF",
        json_schema_extra={"example": False}
    )


# ==================== FastAPI Application ====================

def create_fastapi_app(gpio_controller: Optional[GPIOController] = None) -> FastAPI:
    """Create and configure the FastAPI application for GPIO LED control.
    
    Args:
        gpio_controller: Optional GPIOController instance. If None, a new one is created.
        
    Returns:
        FastAPI application instance
    """
    # Create GPIO controller if not provided
    if gpio_controller is None:
        gpio_controller = GPIOController()
    
    app = FastAPI(
        title="Raspberry Pi GPIO LED Control API",
        description="Backend for Frontend (BFF) endpoint providing REST API for Raspberry Pi GPIO LED control. "
                    "This service manages LED states, provides remote control capabilities, "
                    "and offers comprehensive monitoring of GPIO status.",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        openapi_tags=[
            {"name": "GPIO Status", "description": "Get GPIO controller status and LED states"},
            {"name": "LED Configuration", "description": "Configure and manage LED definitions"},
            {"name": "LED Control", "description": "Control individual LED states"},
            {"name": "Bulk Operations", "description": "Control all LEDs at once"},
            {"name": "Health", "description": "Service health checks and status monitoring"},
            {"name": "Discovery", "description": "API introspection and endpoint discovery"}
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
    
    # Create router with the controller
    router = create_io_router(app, gpio_controller)
    app.include_router(router)
    
    # Store controller reference in app state
    app.state.gpio_controller = gpio_controller
    
    return app


def create_io_router(app: FastAPI, gpio_controller: GPIOController) -> APIRouter:
    """Create a FastAPI router for the GPIO LED control API.
    
    Args:
        app: FastAPI application instance
        gpio_controller: GPIOController instance
        
    Returns:
        APIRouter instance with all endpoints configured
    """
    router = APIRouter(
        prefix="/api/io",
        tags=["gpio-led-control"],
        responses={404: {"description": "Not found"}, 500: {"description": "Internal server error"}}
    )
    
    # ==================== Helper Functions ====================
    
    def _ensure_initialized() -> bool:
        """Ensure GPIO controller is initialized."""
        if not gpio_controller._initialized:
            if not gpio_controller.initialize():
                logger.error("Failed to initialize GPIO controller")
                return False
        return True
    
    def _get_led_or_404(name: str):
        """Get LED config or raise 404."""
        if name not in gpio_controller.config:
            raise HTTPException(
                status_code=404,
                detail=f"LED '{name}' not found. Available LEDs: {list(gpio_controller.config.keys())}"
            )
        return gpio_controller.config[name]
    
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
        return {
            "message": "Raspberry Pi GPIO LED Control API",
            "version": "1.0.0",
            "docs": "/api/io/docs",
            "available_endpoints": {
                "GET /api/io/status": "Get GPIO controller status",
                "GET /api/io/leds": "List all LEDs and their states",
                "GET /api/io/leds/{name}": "Get state of a specific LED",
                "POST /api/io/leds/config": "Configure a new LED",
                "POST /api/io/leds/{name}/set": "Set LED on/off",
                "POST /api/io/leds/{name}/toggle": "Toggle LED state",
                "POST /api/io/leds/all/set": "Set all LEDs on/off",
                "POST /api/io/leds/all/on": "Turn all LEDs on",
                "POST /api/io/leds/all/off": "Turn all LEDs off",
                "POST /api/io/initialize": "Initialize GPIO controller",
                "POST /api/io/cleanup": "Clean up GPIO resources",
                "GET /api/io/health": "Health check endpoint"
            }
        }
    
    @router.get(
        "/status",
        summary="Get GPIO Status",
        description="Returns the current status of the GPIO controller, including all LED states.",
        response_description="GPIO controller status",
        responses={
            200: {"description": "GPIO status returned successfully"},
            500: {"description": "Error retrieving GPIO status"}
        },
        tags=["GPIO Status"]
    )
    async def api_status(request: Request):
        """Get current GPIO controller status.
        
        Returns:
            dict: GPIO controller status including:
                - initialized: Whether GPIO is initialized
                - led_count: Number of configured LEDs
                - led_config: Configuration of all LEDs
                - states: Current state of all LEDs
        """
        try:
            return gpio_controller.get_status()
        except Exception as exc:
            logger.error(f"Get GPIO status failed: {exc}")
            logger.exception("Exception in api_status")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.get(
        "/leds",
        summary="List All LEDs",
        description="Returns the state of all configured LEDs.",
        response_description="All LED states",
        responses={
            200: {"description": "LED states returned successfully"},
            500: {"description": "Error retrieving LED states"}
        },
        tags=["GPIO Status"]
    )
    async def api_list_leds(request: Request):
        """Get state of all LEDs.
        
        Returns:
            dict: Dictionary of LED names to their current states
        """
        try:
            if not _ensure_initialized():
                raise HTTPException(status_code=500, detail="Failed to initialize GPIO")
            return gpio_controller.get_all_states()
        except Exception as exc:
            logger.error(f"Get LED states failed: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.get(
        "/leds/{name}",
        summary="Get LED State",
        description="Returns the current state of a specific LED.",
        response_description="LED state",
        responses={
            200: {"description": "LED state returned successfully"},
            404: {"description": "LED not found"},
            500: {"description": "Error retrieving LED state"}
        },
        tags=["GPIO Status"]
    )
    async def api_get_led_state(name: str, request: Request):
        """Get state of a specific LED.
        
        Args:
            name: LED identifier
            
        Returns:
            dict: LED name and its current state
        """
        try:
            _get_led_or_404(name)  # Will raise 404 if not found
            if not _ensure_initialized():
                raise HTTPException(status_code=500, detail="Failed to initialize GPIO")
            
            state = gpio_controller.get_led_state(name)
            return {"name": name, "state": state}
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"Get LED '{name}' state failed: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.post(
        "/leds/config",
        summary="Configure LED",
        description="Add or configure an LED in the controller. Multiple calls for the same LED will update its configuration.",
        response_description="Configuration confirmation",
        responses={
            200: {"description": "LED configured successfully"},
            400: {"description": "Invalid configuration parameters"},
            500: {"description": "Error configuring LED"}
        },
        tags=["LED Configuration"]
    )
    async def api_config_led(request: LEDConfigRequest):
        """Configure an LED.
        
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
        try:
            gpio_controller.add_led(
                name=request.name,
                gpio_pin=request.gpio_pin,
                description=request.description,
                initial_state=request.initial_state
            )
            logger.info(f"Configured LED: {request.name} on GPIO {request.gpio_pin}")
            return {
                "ok": True,
                "message": f"LED '{request.name}' configured",
                "name": request.name,
                "gpio_pin": request.gpio_pin
            }
        except Exception as exc:
            logger.error(f"Configure LED failed: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.post(
        "/leds/{name}/set",
        summary="Set LED State",
        description="Set a specific LED to ON or OFF state.",
        response_description="Set confirmation",
        responses={
            200: {"description": "LED state set successfully"},
            404: {"description": "LED not found"},
            500: {"description": "Error setting LED state"}
        },
        tags=["LED Control"]
    )
    async def api_set_led(name: str, request: LEDStateRequest):
        """Set LED to a specific state.
        
        Args:
            name: LED identifier
            
        Request Body:
            LEDStateRequest: {
                "state": bool  # Required - True for ON, False for OFF
            }
        
        Returns:
            dict: Confirmation with new state
        """
        try:
            _get_led_or_404(name)  # Will raise 404 if not found
            if not _ensure_initialized():
                raise HTTPException(status_code=500, detail="Failed to initialize GPIO")
            
            success = gpio_controller.set_led(name, request.state)
            if not success:
                raise HTTPException(status_code=500, detail=f"Failed to set LED '{name}'")
            
            new_state = gpio_controller.get_led_state(name)
            logger.info(f"Set LED '{name}' to {'ON' if request.state else 'OFF'}")
            return {
                "ok": True,
                "name": name,
                "state": request.state,
                "actual_state": new_state
            }
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"Set LED '{name}' failed: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.post(
        "/leds/{name}/toggle",
        summary="Toggle LED",
        description="Toggle the state of a specific LED (ON to OFF or OFF to ON).",
        response_description="Toggle confirmation",
        responses={
            200: {"description": "LED toggled successfully"},
            404: {"description": "LED not found"},
            500: {"description": "Error toggling LED"}
        },
        tags=["LED Control"]
    )
    async def api_toggle_led(name: str, request: LEDToggleRequest):
        """Toggle an LED state.
        
        Args:
            name: LED identifier
            
        Returns:
            dict: Confirmation with new state
        """
        try:
            _get_led_or_404(name)  # Will raise 404 if not found
            if not _ensure_initialized():
                raise HTTPException(status_code=500, detail="Failed to initialize GPIO")
            
            new_state = gpio_controller.toggle_led(name)
            if new_state is None:
                raise HTTPException(status_code=500, detail=f"Failed to toggle LED '{name}'")
            
            logger.info(f"Toggled LED '{name}' to {'ON' if new_state else 'OFF'}")
            return {
                "ok": True,
                "name": name,
                "state": new_state
            }
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"Toggle LED '{name}' failed: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.post(
        "/leds/all/set",
        summary="Set All LEDs",
        description="Set all configured LEDs to a specific state.",
        response_description="Bulk set confirmation",
        responses={
            200: {"description": "All LEDs set successfully"},
            500: {"description": "Error setting LEDs"}
        },
        tags=["Bulk Operations"]
    )
    async def api_set_all_leds(request: AllLEDsStateRequest):
        """Set all LEDs to a specific state.
        
        Request Body:
            AllLEDsStateRequest: {
                "state": bool  # Required - True for ON, False for OFF
            }
        
        Returns:
            dict: Confirmation with resulting states of all LEDs
        """
        try:
            if not _ensure_initialized():
                raise HTTPException(status_code=500, detail="Failed to initialize GPIO")
            
            results = gpio_controller.set_all_leds(request.state)
            logger.info(f"Set all {len(results)} LEDs to {'ON' if request.state else 'OFF'}")
            return {
                "ok": True,
                "state": request.state,
                "results": results
            }
        except Exception as exc:
            logger.error(f"Set all LEDs failed: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.post(
        "/leds/all/on",
        summary="All LEDs On",
        description="Turn all configured LEDs ON.",
        response_description="Bulk on confirmation",
        responses={
            200: {"description": "All LEDs turned ON successfully"},
            500: {"description": "Error turning LEDs ON"}
        },
        tags=["Bulk Operations"]
    )
    async def api_all_on(request: Request):
        """Turn all LEDs ON."""
        try:
            if not _ensure_initialized():
                raise HTTPException(status_code=500, detail="Failed to initialize GPIO")
            
            results = gpio_controller.set_all_leds(True)
            logger.info(f"Turned all {len(results)} LEDs ON")
            return {
                "ok": True,
                "message": "All LEDs turned ON",
                "results": results
            }
        except Exception as exc:
            logger.error(f"All LEDs ON failed: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.post(
        "/leds/all/off",
        summary="All LEDs Off",
        description="Turn all configured LEDs OFF.",
        response_description="Bulk off confirmation",
        responses={
            200: {"description": "All LEDs turned OFF successfully"},
            500: {"description": "Error turning LEDs OFF"}
        },
        tags=["Bulk Operations"]
    )
    async def api_all_off(request: Request):
        """Turn all LEDs OFF."""
        try:
            if not _ensure_initialized():
                raise HTTPException(status_code=500, detail="Failed to initialize GPIO")
            
            results = gpio_controller.set_all_leds(False)
            logger.info(f"Turned all {len(results)} LEDs OFF")
            return {
                "ok": True,
                "message": "All LEDs turned OFF",
                "results": results
            }
        except Exception as exc:
            logger.error(f"All LEDs OFF failed: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.post(
        "/initialize",
        summary="Initialize GPIO",
        description="Initialize the GPIO controller. This must be called before controlling LEDs.",
        response_description="Initialization confirmation",
        responses={
            200: {"description": "GPIO initialized successfully"},
            500: {"description": "Error initializing GPIO"}
        },
        tags=["GPIO Status"]
    )
    async def api_initialize(request: Request):
        """Initialize GPIO controller."""
        try:
            success = gpio_controller.initialize()
            if success:
                logger.info("GPIO controller initialized via API")
                return {
                    "ok": True,
                    "message": "GPIO controller initialized",
                    "led_count": len(gpio_controller.leds)
                }
            else:
                raise HTTPException(status_code=500, detail="Failed to initialize GPIO")
        except Exception as exc:
            logger.error(f"GPIO initialization failed: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.post(
        "/cleanup",
        summary="Cleanup GPIO",
        description="Clean up GPIO resources. Call this when done to free resources.",
        response_description="Cleanup confirmation",
        responses={
            200: {"description": "GPIO cleaned up successfully"},
            500: {"description": "Error during cleanup"}
        },
        tags=["GPIO Status"]
    )
    async def api_cleanup(request: Request):
        """Clean up GPIO resources."""
        try:
            gpio_controller.cleanup()
            logger.info("GPIO controller cleaned up via API")
            return {
                "ok": True,
                "message": "GPIO resources cleaned up"
            }
        except Exception as exc:
            logger.error(f"GPIO cleanup failed: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    @router.get(
        "/health",
        summary="Health Check",
        description="Generic health endpoint used by external discovery systems.",
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
            return {
                "status": "ok",
                "service": "GPIO LED Control",
                "version": "1.0.0",
                "gpio_initialized": gpio_controller._initialized,
                "led_count": len(gpio_controller.leds)
            }
        except Exception as exc:
            logger.error(f"Health check failed: {exc}")
            raise HTTPException(status_code=500, detail=str(exc))
    
    return router


if __name__ == "__main__":
    import uvicorn
    import os
    import platform
    
    # Create the FastAPI app with a GPIO controller
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
