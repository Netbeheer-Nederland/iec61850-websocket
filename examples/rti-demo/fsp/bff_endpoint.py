"""Backend for Frontend (BFF) endpoint providing REST API for ACSI server control.

This module exposes REST API endpoints that interact with the ACSI server,
handling model management, server lifecycle, and value operations.
"""
from __future__ import annotations

import importlib
import logging
import os
import sys
from typing import Optional
from concurrent.futures import TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Any, Dict, List, Optional
from acsi_server import ACSIServer
from ws61850.iec61850.data_model.ied_model import DataAttribute, DataObject, IedModel
from fastapi import FastAPI, APIRouter, Request, HTTPException, status, UploadFile, File
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict
import ssl
from ws61850.security.tls import TLSConfig
import asyncio
import json
import httpx

def resolve_log_level(value: Optional[str], default: int = logging.INFO) -> int:
    """Map a level name (case-insensitive) to a logging constant.

    Falls back to ``default`` for unknown/empty values instead of letting
    ``basicConfig`` raise ``ValueError`` and abort startup. Also accepts a
    numeric string (e.g. "10") and uvicorn's "trace" alias.
    """
    if value is None:
        return default
    name = str(value).strip().upper()
    if not name:
        return default
    if name.isdigit():
        return int(name)
    if name == "TRACE":  # uvicorn alias, no stdlib equivalent
        return logging.DEBUG
    level = logging.getLevelName(name)  # returns int for known names, str otherwise
    return level if isinstance(level, int) else default


# Module-level default from the environment; the __main__ CLI can override it.
LOG_LEVEL = resolve_log_level(os.getenv("LOG_LEVEL"))

logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(threadName)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)  # Force stdout for Docker
    ],
    force=True  # Override any existing config
)

# Apply the severity to the root logger here at import time, not only in the
# __main__ block, so every entry point honours LOG_LEVEL: `python
# fsp/bff_endpoint.py`, `uvicorn fsp.bff_endpoint:app`, a service wrapper, or
# pytest importing create_fastapi_app. Child loggers (acsi_server, ws61850.*)
# and any background event-loop thread inherit this level.
logging.getLogger().setLevel(LOG_LEVEL)

logger = logging.getLogger(__name__)

# Global flag to control io_plugin usage
_use_io_plugin = False  # Default to False, will be enabled if files exist

# Directory for dynamically loaded io_plugin files
# Configurable via IO_PLUGIN_STORAGE environment variable
# Default: /app/io_plugin_dynamic (good for Docker volumes)
# Fallback: temp directory if not specified
IO_PLUGIN_STORAGE = os.getenv("IO_PLUGIN_STORAGE", "/app/io_plugin_dynamic")
io_plugin_dynamic_DIR = Path(IO_PLUGIN_STORAGE)

# Global reference to loaded io_plugin modules
_io_plugin_module = None
_mapping_manager_module = None
_io_utils_module = None

# ==================== IO Plugin Connection Management ====================

class IOPluginConnectionStatus:
    """Track the connection status to IO server and file download status."""
    
    def __init__(self):
        self.connected = False
        self.last_connection_time = None
        self.last_disconnect_time = None
        self.last_fetch_time = None
        self.last_error = None
        self.fetch_attempts = 0
        self.successful_fetches = 0
        self.io_server_url = None
        self.connection_history = []
    
    def connect(self, server_url: str):
        """Mark connection as established."""
        self.connected = True
        self.io_server_url = server_url
        self.last_connection_time = asyncio.get_event_loop().time() if asyncio.get_event_loop().is_running() else None
        self.connection_history.append({
            "action": "connect",
            "timestamp": self.last_connection_time,
            "server_url": server_url
        })
    
    def disconnect(self):
        """Mark connection as closed."""
        self.connected = False
        self.last_disconnect_time = asyncio.get_event_loop().time() if asyncio.get_event_loop().is_running() else None
        self.connection_history.append({
            "action": "disconnect",
            "timestamp": self.last_disconnect_time
        })
    
    def record_fetch(self, success: bool, error: str = None, files_fetched: int = 0):
        """Record a file fetch attempt."""
        self.fetch_attempts += 1
        self.last_fetch_time = asyncio.get_event_loop().time() if asyncio.get_event_loop().is_running() else None
        if success:
            self.successful_fetches += 1
            self.last_error = None
        else:
            self.last_error = error
        self.connection_history.append({
            "action": "fetch",
            "timestamp": self.last_fetch_time,
            "success": success,
            "error": error,
            "files_fetched": files_fetched
        })
    
    def get_status(self) -> Dict[str, Any]:
        """Get current connection status as dictionary."""
        import time
        current_time = time.time()
        
        # Calculate time since last activity
        last_activity = None
        if self.last_connection_time:
            last_activity = current_time - self.last_connection_time
        elif self.last_disconnect_time:
            last_activity = current_time - self.last_disconnect_time
        elif self.last_fetch_time:
            last_activity = current_time - self.last_fetch_time
        
        return {
            "connected": self.connected,
            "io_server_url": self.io_server_url,
            "last_connection_time": self.last_connection_time,
            "last_disconnect_time": self.last_disconnect_time,
            "last_fetch_time": self.last_fetch_time,
            "fetch_attempts": self.fetch_attempts,
            "successful_fetches": self.successful_fetches,
            "last_error": self.last_error,
            "connection_duration": last_activity,
            "connection_history_count": len(self.connection_history),
            "status": "connected" if self.connected else ("error" if self.last_error else "disconnected")
        }

# Global IO Plugin connection status manager
io_plugin_connection_status = IOPluginConnectionStatus()

# Configuration for IO server connection
IO_SERVER_URL = os.getenv("IO_SERVER_URL", "http://localhost:8000")
io_plugin_MAX_RETRIES = int(os.getenv("io_plugin_MAX_RETRIES", "3"))
io_plugin_RETRY_DELAY = float(os.getenv("io_plugin_RETRY_DELAY", "1.0"))

# Default files to fetch from IO server
io_plugin_REQUIRED_FILES = [
    "io_router.py",
    "io_utils.py", 
    "mapping_manager.py",
    "__init__.py",
    "async_client_io.py"
]

import httpx

# ==================== Dynamic IO Plugin Loading ====================

def ensure_io_plugin_dir():
    """Ensure the dynamic io_plugin directory exists."""
    io_plugin_dynamic_DIR.mkdir(parents=True, exist_ok=True)
    return io_plugin_dynamic_DIR


def get_io_plugin_file_path(relative_path: str) -> Path:
    """Get the full path for a io_plugin file in the dynamic directory."""
    ensure_io_plugin_dir()
    return io_plugin_dynamic_DIR / relative_path


def check_required_io_plugin_files() -> bool:
    """Check if all required io_plugin files exist."""
    required_files = [
        "io_router.py",
        "io_utils.py", 
        "mapping_manager.py",
        "__init__.py",
        "async_client_io.py"
    ]
    
    for file in required_files:
        file_path = get_io_plugin_file_path(file)
        if not file_path.exists():
            logger.debug(f"Required io_plugin file not found: {file_path}")
            return False
    
    return True


def load_io_plugin_modules() -> bool:
    """Dynamically load io_plugin modules from the dynamic directory."""
    global _io_plugin_module, _mapping_manager_module, _io_utils_module
    
    if not check_required_io_plugin_files():
        logger.warning("Required io_plugin files are missing")
        return False
    
    try:
        # Add the dynamic directory to sys.path so imports work
        if str(io_plugin_dynamic_DIR) not in sys.path:
            sys.path.insert(0, str(io_plugin_dynamic_DIR))

        # Load async_client_io module (dependency of io_router) — must load first
        async_client_io_path = get_io_plugin_file_path("async_client_io.py")
        spec = importlib.util.spec_from_file_location("async_client_io", async_client_io_path)
        if spec and spec.loader:
            async_client_io_module = importlib.util.module_from_spec(spec)
            sys.modules["async_client_io"] = async_client_io_module
            spec.loader.exec_module(async_client_io_module)
            logger.info(f"Successfully loaded async_client_io from {async_client_io_path}")
        else:
            logger.error(f"Failed to load async_client_io from {async_client_io_path}")
            return False

        # Load io_router module
        io_router_path = get_io_plugin_file_path("io_router.py")
        spec = importlib.util.spec_from_file_location("io_router", io_router_path)
        if spec and spec.loader:
            _io_plugin_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(_io_plugin_module)
            logger.info(f"Successfully loaded io_router from {io_router_path}")
        else:
            logger.error(f"Failed to load io_router from {io_router_path}")
            return False
        
        # Load io_utils module
        io_utils_path = get_io_plugin_file_path("io_utils.py")
        spec = importlib.util.spec_from_file_location("io_utils", io_utils_path)
        if spec and spec.loader:
            _io_utils_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(_io_utils_module)
            logger.info(f"Successfully loaded io_utils from {io_utils_path}")
        else:
            logger.error(f"Failed to load io_utils from {io_utils_path}")
            return False
        
        # Load mapping_manager module
        mapping_manager_path = get_io_plugin_file_path("mapping_manager.py")
        spec = importlib.util.spec_from_file_location("mapping_manager", mapping_manager_path)
        if spec and spec.loader:
            _mapping_manager_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(_mapping_manager_module)
            logger.info(f"Successfully loaded mapping_manager from {mapping_manager_path}")
        else:
            logger.error(f"Failed to load mapping_manager from {mapping_manager_path}")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to load io_plugin modules: {e}")
        return False


def get_io_plugin_dynamic():
    """Get the io_plugin instance from dynamically loaded modules."""
    if _io_plugin_module is None:
        if not load_io_plugin_modules():
            return None
    
    try:
        return _io_plugin_module.get_io_plugin()
    except AttributeError:
        logger.error("io_router module doesn't have get_io_plugin function")
        return None


def get_mapping_manager_dynamic():
    """Get the mapping_manager instance from dynamically loaded modules."""
    if _mapping_manager_module is None:
        if not load_io_plugin_modules():
            return None
    
    try:
        return _mapping_manager_module.get_mapping_manager()
    except AttributeError:
        logger.error("mapping_manager module doesn't have get_mapping_manager function")
        return None


def get_sync_to_io_device_dynamic():
    """Get the sync_to_io_device function from dynamically loaded modules."""
    if _io_utils_module is None:
        if not load_io_plugin_modules():
            return None
    
    try:
        return _io_utils_module.sync_to_io_device
    except AttributeError:
        logger.error("io_utils module doesn't have sync_to_io_device function")
        return None


def get_write_to_lcd_dynamic():
    """Get the write_to_lcd function from dynamically loaded modules."""
    if _io_utils_module is None:
        if not load_io_plugin_modules():
            return None
    
    try:
        return _io_utils_module.write_to_lcd
    except AttributeError:
        logger.error("io_utils module doesn't have write_to_lcd function")
        return None


def get_blink_led_task_dynamic():
    """Get the blink_led_task function from dynamically loaded modules."""
    if _io_utils_module is None:
        if not load_io_plugin_modules():
            return None
    
    try:
        return _io_utils_module.blink_led_task
    except AttributeError:
        logger.error("io_utils module doesn't have blink_led_task function")
        return None


def update_io_plugin_usage():
    """Update the _use_io_plugin flag based on file availability."""
    global _use_io_plugin
    _use_io_plugin = check_required_io_plugin_files() and load_io_plugin_modules()
    logger.info(f"IO Plugin usage updated to: {_use_io_plugin}")


def clear_io_plugin_modules():
    """Clear all loaded io_plugin modules."""
    global _io_plugin_module, _mapping_manager_module, _io_utils_module
    _io_plugin_module = None
    _mapping_manager_module = None
    _io_utils_module = None
    # Remove dynamic directory from sys.path
    if str(io_plugin_dynamic_DIR) in sys.path:
        sys.path.remove(str(io_plugin_dynamic_DIR))


# ==================== IO Plugin HTTP Client Functions ====================

async def download_file_from_io_server(server_url: str, filename: str, timeout: float = 10.0) -> Optional[str]:
    """Download a single file from the IO server.
    
    Args:
        server_url: URL of the IO server (e.g., 'http://localhost:8000')
        filename: Name of the file to download
        timeout: Timeout in seconds
        
    Returns:
        File content as string if successful, None otherwise
    """
    try:
        url = f"{server_url.rstrip('/')}/api/io-plugin/files/{filename}"
        logger.info(f"Downloading file from: {url}")
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("ok", False):
                    content = data.get("content", "")
                    logger.info(f"Successfully downloaded file '{filename}' ({len(content)} bytes)")
                    return content
                else:
                    logger.error(f"Server returned error for file '{filename}': {data.get('error', 'Unknown error')}")
                    return None
            elif response.status_code == 404:
                logger.warning(f"File '{filename}' not found on IO server")
                return None
            else:
                logger.error(f"Failed to download file '{filename}': HTTP {response.status_code}")
                return None
                
    except httpx.TimeoutException:
        logger.error(f"Timeout downloading file '{filename}' from IO server")
        return None
    except httpx.ConnectError:
        logger.error(f"Failed to connect to IO server at {server_url}")
        return None
    except Exception as e:
        logger.error(f"Error downloading file '{filename}': {e}")
        return None

async def download_io_plugin_files(server_url: str, files: List[str] = None, timeout: float = 10.0) -> Dict[str, Any]:
    """Download multiple io_plugin files from the IO server with retry logic.
    
    Args:
        server_url: URL of the IO server
        files: List of filenames to download (defaults to io_plugin_REQUIRED_FILES)
        timeout: Timeout per file download in seconds
        
    Returns:
        Dictionary with results: {"success": bool, "downloaded": list, "failed": list, "errors": dict}
    """
    if files is None:
        files = io_plugin_REQUIRED_FILES
    
    results = {
        "success": False,
        "downloaded": [],
        "failed": [],
        "errors": {},
        "total_files": len(files),
        "downloaded_count": 0
    }
    
    try:
        # Ensure target directory exists
        ensure_io_plugin_dir()
        
        for filename in files:
            for attempt in range(io_plugin_MAX_RETRIES):
                try:
                    content = await download_file_from_io_server(server_url, filename, timeout)
                    
                    if content is not None:
                        # Save the file
                        file_path = get_io_plugin_file_path(filename)
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                        
                        results["downloaded"].append(filename)
                        results["downloaded_count"] += 1
                        logger.info(f"Saved file '{filename}' to {file_path}")
                        break
                    else:
                        error_msg = f"Failed to download '{filename}' (attempt {attempt + 1}/{io_plugin_MAX_RETRIES})"
                        results["errors"][filename] = error_msg
                        if attempt < io_plugin_MAX_RETRIES - 1:
                            await asyncio.sleep(io_plugin_RETRY_DELAY)
                        
                except Exception as e:
                    error_msg = f"Error downloading '{filename}': {e} (attempt {attempt + 1}/{io_plugin_MAX_RETRIES})"
                    results["errors"][filename] = error_msg
                    if attempt < io_plugin_MAX_RETRIES - 1:
                        await asyncio.sleep(io_plugin_RETRY_DELAY)
            
            if filename not in results["downloaded"]:
                results["failed"].append(filename)
        
        # Mark success if we got all required files
        results["success"] = len(results["failed"]) == 0
        
        return results
        
    except Exception as e:
        logger.error(f"Error in download_io_plugin_files: {e}")
        results["success"] = False
        results["error"] = str(e)
        return results

async def check_io_server_health(server_url: str, timeout: float = 5.0) -> Dict[str, Any]:
    """Check if the IO server is healthy and available.
    
    Args:
        server_url: URL of the IO server
        timeout: Timeout in seconds
        
    Returns:
        Dictionary with health check results
    """
    try:
        url = f"{server_url.rstrip('/')}/api/io/health"
        logger.info(f"Checking IO server health at: {url}")
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "healthy": True,
                    "server_url": server_url,
                    "status": data.get("status", "unknown"),
                    "service": data.get("service", "unknown"),
                    "version": data.get("version", "unknown"),
                    "files_available": data.get("files_available", False),
                    "files_count": data.get("files_count", 0)
                }
            else:
                return {
                    "healthy": False,
                    "server_url": server_url,
                    "error": f"HTTP {response.status_code}",
                    "status": "unreachable"
                }
                
    except httpx.TimeoutException:
        return {
            "healthy": False,
            "server_url": server_url,
            "error": "Timeout",
            "status": "timeout"
        }
    except httpx.ConnectError:
        return {
            "healthy": False,
            "server_url": server_url,
            "error": "Connection failed",
            "status": "connection_failed"
        }
    except Exception as e:
        return {
            "healthy": False,
            "server_url": server_url,
            "error": str(e),
            "status": "error"
        }

async def fetch_and_load_io_plugin_files(server_url: str) -> Dict[str, Any]:
    """Connect to IO server, download files, and load modules.
    
    This is the main function for on-demand IO Plugin connection.
    
    Args:
        server_url: URL of the IO server
        
    Returns:
        Dictionary with connection and loading results
    """
    results = {
        "connection_success": False,
        "download_success": False,
        "load_success": False,
        "server_healthy": False,
        "files_downloaded": [],
        "files_failed": [],
        "modules_loaded": [],
        "errors": {}
    }
    
    try:
        # Step 1: Check server health
        health_check = await check_io_server_health(server_url)
        if not health_check.get("healthy", False):
            results["errors"]["server_check"] = health_check.get("error", "Server unhealthy")
            return results
        
        results["server_healthy"] = True
        results["health_check"] = health_check
        
        # Step 2: Download files
        download_result = await download_io_plugin_files(server_url)
        results["download_success"] = download_result.get("success", False)
        results["files_downloaded"] = download_result.get("downloaded", [])
        results["files_failed"] = download_result.get("failed", [])
        results["download_errors"] = download_result.get("errors", {})
        
        if not download_result.get("success", False):
            results["errors"]["download"] = "Failed to download all required files"
            return results
        
        # Step 3: Clear existing modules and reload
        clear_io_plugin_modules()
        
        # Step 4: Load the newly downloaded modules
        modules_loaded = load_io_plugin_modules()
        if modules_loaded:
            update_io_plugin_usage()
            results["load_success"] = True
            results["modules_loaded"] = ["io_router", "io_utils", "mapping_manager"]
            results["use_io_plugin_enabled"] = _use_io_plugin
        else:
            results["errors"]["load"] = "Failed to load modules"
        
        results["connection_success"] = True
        
        return results
        
    except Exception as e:
        logger.error(f"Error in fetch_and_load_io_plugin_files: {e}")
        results["errors"]["general"] = str(e)
        return results

# ==================== Pydantic Models ====================
class WritevalueRequest(BaseModel):

    """Request body for writing a value to the ACSI server model."""
    objRef: str = Field(
        ...,
        description="Object reference in ACSI format (e.g., 'LD0/LLN0$ST$Mod')",
        json_schema_extra={"example": "LD0/LLN0$ST$Mod"}
    )
    fc: str = Field(
        ...,
        description="Functional constraint (ST, MX, CO, etc.)",
        json_schema_extra={"example": "ST"}
    )
    value: str = Field(
        ...,
        description="Value to write as string representation",
        json_schema_extra={"example": "ON"}
    )
    dataType: str = Field(
        default="",
        description="Optional data type for value coercion",
        json_schema_extra={"example": "BOOLEAN"}
    )

class UpdateIedmodelRequest(BaseModel):
    """Request body for updating the IED model file."""
    modelPy: str = Field(
        ...,
        description="Complete Python code for model.py file",
        json_schema_extra={"example": "from ws61850... import IedModel\nmodel = IedModel(...)"}
    )

class StartRequest(BaseModel):
    """Request body for starting the ACSI WebSocket Passive."""
    host: str = Field(
        default="0.0.0.0",
        description="Hostname or IP address to bind to",
        json_schema_extra={"example": "0.0.0.0"}
    )
    port: str = Field(
        default="8765",
        description="Port number to listen on",
        json_schema_extra={"example": "8765"}
    )
    mode: str = Field(
        default="server",
        description="Operating mode (only 'server' supported)",
        json_schema_extra={"example": "server"}
    )
    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"}
    )

class ReadvalueRequest(BaseModel):

    """Request body for reading a value from the ACSI server model."""
    objRef: str = Field(
        ...,
        description="Object reference in ACSI format",
        json_schema_extra={"example": "LD0/MMXU1$MX$volA"}
    )
    fc: str = Field(
        default="",
        description="Functional constraint (optional)",
        json_schema_extra={"example": "MX"}
    )

class TLSConnectionCreateConfigRequest(BaseModel):
    """Request body for creating a new connection."""

    host: str = Field(
        default="0.0.0.0",
        description="Hostname or IP address to bind to",
        json_schema_extra={"example": "0.0.0.0"}
    )
    port: str = Field(
        default="8765",
        description="Port number to listen on",
        json_schema_extra={"example": "8765"}
    )

    connection_name: str = Field(..., description="Human-readable name for the connection", json_schema_extra={"example": "RTI-FSP-01"})
    enable_tls: bool = Field(default=False, description="enable TLS", json_schema_extra={"example": False})
    tls_version: str = Field(default= "1.2", description="TLS version", json_schema_extra={"example": "1.2"})

    server_key: str | None = Field(
        default=None,
        description="Server private key",
        json_schema_extra={"example": "-----BEGIN PRIVATE KEY-----..."},
    )
    server_cert: str | None = Field(
        default=None,
        description="Server certificate",
        json_schema_extra={"example": "-----BEGIN CERTIFICATE-----..."},
    )
    server_ca: str | None = Field(
        default=None,
        description="Server CA certificate",
        json_schema_extra={"example": "-----BEGIN CERTIFICATE-----..."},
    )

    ws_mode : str = Field(default="passive", description="WebSocket mode (passive or active)", json_schema_extra={"example": "passive"})

class OAUTHCreateConfigRequest(BaseModel):
    """Request body for OAuth reconfiguration."""
    connection_name: Optional[str] = Field(default=None, description="Connection name (optional, auto-detected)", json_schema_extra={"example": "RTI-FSP-01"})
    enable_oauth: bool = Field(default=False, description="Enable OAuth authentication", json_schema_extra={"example": False})
    host: str = Field(default="127.0.0.1", description="ws host", json_schema_extra={"example": "127.0.0.1"})
    port: str = Field(default="8765", description="ws port", json_schema_extra={"example": "8765"})
    cp: str = Field(default="cp1", description="Communication point identifier", json_schema_extra={"example": "cp1"})
    ws_mode: str = Field(default="active", description="WebSocket mode (passive or active)", json_schema_extra={"example": "active"})
    # OAuth settings for FSP (active mode)
    token_endpoint_url: Optional[str] = Field(default=None, description="OAuth Token endpoint URL", json_schema_extra={"example": "https://auth.example.com/token"})
    client_id: Optional[str] = Field(default=None, description="OAuth Client ID", json_schema_extra={"example": "my-client-id"})
    client_secret: Optional[str] = Field(default=None, description="OAuth Client Secret", json_schema_extra={"example": "my-client-secret"})
    ca_certificate: Optional[str] = Field(default=None, description="Server CA certificate", json_schema_extra={"example": "-----BEGIN CERTIFICATE-----..."})
    enable_token_refresh: bool = Field(default=False, description="Enable token refresh", json_schema_extra={"example": False})

class IoPluginConfigRequest(BaseModel):
    """Request body for enabling/disabling io_plugin usage."""
    enabled: bool = Field(
        ...,
        description="Whether to enable io_plugin for device sync",
        json_schema_extra={"example": True}
    )

class IoPluginFileUploadRequest(BaseModel):
    """Request body for uploading io_plugin files."""
    file_path: str = Field(
        ...,
        description="The path where the file should be stored (relative to io_plugin dynamic directory)",
        json_schema_extra={"example": "io_router.py"}
    )
    overwrite: bool = Field(
        default=False,
        description="Whether to overwrite existing files",
        json_schema_extra={"example": False}
    )


class IoClientReloadRequest(BaseModel):
    """Request body for reloading io_plugin modules."""
    force: bool = Field(
        default=False,
        description="Force reload even if files haven't changed",
        json_schema_extra={"example": False}
    )


# ==================== IO Plugin Connection Models ====================

class IoClientConnectRequest(BaseModel):
    """Request body for connecting to IO server and fetching files."""
    server_url: str = Field(
        default=IO_SERVER_URL,
        description="URL of the IO server to connect to",
        json_schema_extra={"example": "http://localhost:8000"}
    )
    files: Optional[List[str]] = Field(
        default=None,
        description="Specific files to fetch. If None, fetches all required files",
        json_schema_extra={"example": ["io_router.py", "io_utils.py", "mapping_manager.py", "__init__.py"]}
    )
    timeout: float = Field(
        default=10.0,
        description="Timeout in seconds for file downloads",
        json_schema_extra={"example": 10.0}
    )
    enable_io_plugin: bool = Field(
        default=True,
        description="Whether to enable io_plugin usage after successful connection",
        json_schema_extra={"example": True}
    )

class IoClientDisconnectRequest(BaseModel):
    """Request body for disconnecting from IO server."""
    clear_files: bool = Field(
        default=False,
        description="Whether to clear downloaded files from the dynamic directory",
        json_schema_extra={"example": False}
    )
    disable_io_plugin: bool = Field(
        default=True,
        description="Whether to disable io_plugin usage after disconnection",
        json_schema_extra={"example": True}
    )

class IOPluginConnectionStatusResponse(BaseModel):
    """Response model for IO Plugin connection status."""
    connected: bool = Field(
        default=False,
        description="Whether currently connected to IO server"
    )
    io_server_url: Optional[str] = Field(
        default=None,
        description="Current IO server URL"
    )
    last_connection_time: Optional[float] = Field(
        default=None,
        description="Timestamp of last successful connection"
    )
    last_disconnect_time: Optional[float] = Field(
        default=None,
        description="Timestamp of last disconnection"
    )
    last_fetch_time: Optional[float] = Field(
        default=None,
        description="Timestamp of last file fetch"
    )
    fetch_attempts: int = Field(
        default=0,
        description="Total number of fetch attempts"
    )
    successful_fetches: int = Field(
        default=0,
        description="Number of successful fetches"
    )
    last_error: Optional[str] = Field(
        default=None,
        description="Last error message if any"
    )
    connection_duration: Optional[float] = Field(
        default=None,
        description="Time since last connection activity in seconds"
    )
    status: str = Field(
        default="disconnected",
        description="Connection status: connected, disconnected, error"
    )

def create_bff_router(
    factory_dir,
    scl_default_path: Optional[Path] = None,
) -> tuple[APIRouter, ACSIServer]:
    """Create a FastAPI router for the ACSI server BFF API.

    Args:
        factory_dir: Path to the fsp directory containing model.py
        scl_default_path: Unused. Kept only for backward compatibility.

    Returns:
        Tuple of (APIRouter, ACSIServer instance)
    """

        # Initialize dynamic io_plugin loading system
    ensure_io_plugin_dir()
    update_io_plugin_usage()

    router = APIRouter(
        prefix="/api",
        tags=["ACSI-Server"],
        responses={404: {"description": "Not found"}, 500: {"description": "Internal server error"}}
    )

    rti_fsp = ACSIServer(factory_dir)

    def on_connected_callback(associate_response):
        """Callback for sent associateResponse messages."""
        logger.info(f"[FSP CONNECTED] associateResponse: {associate_response}")
        
        if _use_io_plugin:
            try:
                # Use dynamic loading functions
                io_plugin = get_io_plugin_dynamic()
                mapping_manager = get_mapping_manager_dynamic()
                sync_to_io_device = get_sync_to_io_device_dynamic()
                write_to_lcd = get_write_to_lcd_dynamic()
                
                if io_plugin is None or mapping_manager is None or sync_to_io_device is None or write_to_lcd is None:
                    logger.warning("Dynamic io_plugin loading failed, falling back to disabled state")
                    _use_io_plugin = False
                    return
                logger.info(f"[FSP] IO Plugin for connected: {io_plugin}")
                if io_plugin:
                    # Use associateId as identifier, or a default
                    associate_id = associate_response.get("associateId", "fsp_connected")
                    # Turn LED ON (write True/1 to the LED reference)
                    asyncio.create_task(
                        sync_to_io_device(io_plugin, "connected", True)
                    )
                    
                    # Write connection info to LCD
                    value = f"FSP Connected: {associate_id}"
                    asyncio.create_task(
                        write_to_lcd(io_plugin, "connected", value, mapping_manager=mapping_manager)
                    )
                else:
                    logger.warning("[FSP] IO Plugin is None - cannot turn on LED. Call /api/io/connect first.")
            except ImportError as e:
                logger.error(f"[FSP] ImportError - Cannot import IO Plugin: {e}")
            except Exception as e:
                logger.error(f"[FSP] Exception in IO connected callback: {e}")
        
    def on_operate_received_callback(operate_data):
        """Callback for received operate request messages - blinks LED."""
        logger.info(f"[FSP OPERATE RECEIVED] operate request: {operate_data}")
        
        if _use_io_plugin:
            try:
                # Use dynamic loading functions
                io_plugin = get_io_plugin_dynamic()
                mapping_manager = get_mapping_manager_dynamic()
                blink_led_task = get_blink_led_task_dynamic()
                
                if io_plugin is None or mapping_manager is None or blink_led_task is None:
                    logger.warning("Dynamic io_plugin loading failed, falling back to disabled state")
                    _use_io_plugin = False
                    return
                if io_plugin:
                
                    asyncio.create_task(
                        blink_led_task(io_plugin, "oper_rcv", interval=0.2, count=1, mapping_manager=mapping_manager)
                    )
                else:
                    logger.warning("[FSP] IO Plugin is None - cannot blink LED. Call /api/io/connect first.")
            except ImportError as e:
                logger.error(f"[FSP] ImportError - Cannot import IO Plugin: {e}")
            except Exception as e:
                logger.error(f"[FSP] Exception in operate received callback: {e}")

        

    def on_operate_response_callback(operate_response):
        """Callback for sent operate response messages - prints to LCD."""
        logger.info(f"[FSP OPERATE RESPONSE] operate response: {operate_response}")
        
        if _use_io_plugin:
            try:
                # Use dynamic loading functions
                io_plugin = get_io_plugin_dynamic()
                mapping_manager = get_mapping_manager_dynamic()
                write_to_lcd = get_write_to_lcd_dynamic()
                
                if io_plugin is None or mapping_manager is None or write_to_lcd is None:
                    logger.warning("Dynamic io_plugin loading failed, falling back to disabled state")
                    _use_io_plugin = False
                    return
                
                if io_plugin:

                    success = operate_response.get("success", False)
                    add_cause = operate_response.get("addCause", "")
                    
                    if success:
                        value = "Operation: SUCCESS"
                    else:
                        value = f"Operation: FAILED - {add_cause}" if add_cause else "Operation: FAILED"
                    
                    asyncio.create_task(
                        write_to_lcd(io_plugin, "oper_send", value, mapping_manager=mapping_manager)
                    )
                else:
                    logger.warning("[FSP] IO Plugin is None - cannot write to LCD. Call /api/io/connect first.")
            except ImportError as e:
                logger.error(f"[FSP] ImportError - Cannot import IO Plugin: {e}")
            except Exception as e:
                logger.error(f"[FSP] Exception in operate response callback: {e}")

        
    rti_fsp.install_connected_callback(on_connected_callback)
    rti_fsp.install_operate_received_callback(on_operate_received_callback)
    rti_fsp.install_operate_response_callback(on_operate_response_callback)

    # ==================== Helper Functions ====================
    def serialize_data_attribute(da: DataAttribute) -> Dict[str, Any]:
        """Serialize a DataAttribute to JSON-compatible dict."""
        return {
            "kind": "DA",
            "type": "DA",
            "name": da.name,
            "fc": da.fc.name if da.fc is not None else None,
            "bType": da.type.name if da.type is not None else None,
            "children": [serialize_data_attribute(child) for child in (da.data_attributes or [])],
        }

    def serialize_data_object(do: DataObject) -> Dict[str, Any]:
        """Serialize a DataObject to JSON-compatible dict."""
        children: List[Dict[str, Any]] = []
        for item in do.do_or_da or []:
            if isinstance(item, DataObject):
                children.append(serialize_data_object(item))
            elif isinstance(item, DataAttribute):
                children.append(serialize_data_attribute(item))

        return {
            "kind": "DO",
            "type": "DO",
            "name": do.name,
            "cdc": do.cdc,
            "children": children,
        }

    def serialize_ied_tree(ied: IedModel) -> Dict[str, Any]:
        """Serialize an IED model tree to JSON-compatible dict."""
        return {
            "kind": "IED",
            "type": "IED",
            "name": ied.name,
            "children": [
                {
                    "kind": "LD",
                    "type": "LDevice",
                    "name": ld.name,
                    "ldName": ld.ldName,
                    "children": [
                        {
                            "kind": "LN",
                            "type": "LogicalNode",
                            "name": ln.name,
                            "children": (
                                [
                                    {
                                        "kind": "Group",
                                        "type": "Group",
                                        "name": "DataSets",
                                        "children": [
                                            {
                                                "kind": "DataSet",
                                                "type": "DataSet",
                                                "name": ds.name,
                                                "ref": f"{ld.name}/{ln.name}.{ds.name}"
                                            }
                                            for ds in (ln.data_sets or [])
                                        ]
                                    }
                                ] if (ln.data_sets or []) else []
                            ) + (
                                [
                                    {
                                        "kind": "Group",
                                        "type": "Group",
                                        "name": "ReportControls",
                                        "children": [
                                            {
                                                "kind": "BRCB" if rcb.buffered else "URCB",
                                                "type": "ReportControl",
                                                "name": rcb.name,
                                                "ref": f"{ld.name}/{ln.name}.{rcb.name}"
                                            }
                                            for rcb in (ln.rcbs or [])
                                        ]
                                    }
                                ] if (ln.rcbs or []) else []
                            ) + [
                                serialize_data_object(do) for do in (ln.data_objects or [])
                            ]
                        }
                        for ln in (ld.logical_nodes or [])
                    ],
                }
                for ld in (ied.logical_devices or [])
            ],
        }

    def collect_da_paths_from_do(data_object: DataObject, prefix: str) -> List[tuple]:
        """Collect flattened (path, fc_name) tuples under a DO path."""
        results: List[tuple] = []
        for item in (data_object.do_or_da or []):
            if isinstance(item, DataAttribute):
                da_path = f"{prefix}.{item.name}"
                fc_name = item.fc.name if item.fc is not None else None
                results.append((da_path, fc_name))
                results.extend(collect_da_paths_from_da(item, da_path))
            elif isinstance(item, DataObject):
                sub_prefix = f"{prefix}.{item.name}"
                results.extend(collect_da_paths_from_do(item, sub_prefix))
        return results

    def collect_da_paths_from_da(data_attribute: DataAttribute, prefix: str) -> List[tuple]:
        """Collect flattened (path, fc_name) tuples for nested DA paths."""
        results: List[tuple] = []
        for child in (data_attribute.data_attributes or []):
            child_path = f"{prefix}.{child.name}"
            fc_name = child.fc.name if child.fc is not None else None
            results.append((child_path, fc_name))
            results.extend(collect_da_paths_from_da(child, child_path))
        return results

    def build_logical_node_details(ied_model: Optional[IedModel]) -> Dict[str, Dict[str, Any]]:
        """Build UI-friendly logical node details."""
        details: Dict[str, Dict[str, Any]] = {}
        if ied_model is None:
            return details

        for ld in (ied_model.logical_devices or []):
            for ln in (ld.logical_nodes or []):
                data_objects: List[Dict[str, Any]] = []
                data_attributes: List[str] = []
                da_fc_map: Dict[str, str] = {}
                report_control_blocks: List[Dict[str, Any]] = []
                datasets: List[Dict[str, Any]] = []
                ln_prefix = f"{ld.name}/{ln.name}."

                for data_object in (ln.data_objects or []):
                    cdc = (data_object.cdc or "").lower()
                    obj_info = {"name": data_object.name, "cdc": data_object.cdc}
                    
                    # Collect DataSets (from DataObjects with cdc="dataset")
                    if cdc == "dataset":
                        datasets.append(obj_info)
                    # Collect Report Control Blocks (RCB, BRCB, URCB) from DataObjects
                    elif cdc in ("rcb", "brcb", "urcb"):
                        report_control_blocks.append(obj_info)
                    
                    data_objects.append(obj_info)
                    for da_path, fc_name in collect_da_paths_from_do(data_object, data_object.name):
                        data_attributes.append(da_path)
                        if fc_name:
                            da_fc_map[f"{ln_prefix}{da_path}"] = fc_name

                # Also collect DataSets from ln.data_sets
                for ds in (ln.data_sets or []):
                    datasets.append({"name": ds.name, "cdc": "dataset"})

                # Also collect ReportControls from ln.rcbs
                for rcb in (ln.rcbs or []):
                    report_control_blocks.append({"name": rcb.name, "cdc": "rcb"})

                ln_key = f"{ld.name}/{ln.name}"
                details[ln_key] = {
                    "dataObjects": data_objects,
                    "dataAttributes": sorted(set(data_attributes)),
                    "dataAttributeFcs": da_fc_map,
                    "reportControlBlocks": report_control_blocks,
                    "dataSets": datasets,
                }

        return details

    def extract_tpa_info(websocket_info: Any) -> Dict[str, Any]:
        """Extract TPA (Three Part Address) and connection info from websocket_info."""
        info = {
            "peer_address": None,
            "peer_port": None,
            "role": "ACSI-Server",
            "ws_mode": "active",
            "remote_role": None,
            "tpa": None,
            "status": "active",
        }

        try:
            if hasattr(websocket_info, "remote_address"):
                addr_tuple = websocket_info.remote_address
                if isinstance(addr_tuple, tuple) and len(addr_tuple) >= 2:
                    info["peer_address"] = addr_tuple[0]
                    info["peer_port"] = addr_tuple[1]
            elif hasattr(websocket_info, "peername"):
                addr_tuple = websocket_info.peername()
                if isinstance(addr_tuple, tuple) and len(addr_tuple) >= 2:
                    info["peer_address"] = addr_tuple[0]
                    info["peer_port"] = addr_tuple[1]

            if hasattr(websocket_info, "tpa"):
                info["tpa"] = str(websocket_info.tpa)
            elif hasattr(websocket_info, "request") and hasattr(websocket_info.request, "headers"):
                headers = websocket_info.request.headers
                if "X-TPA" in headers:
                    info["tpa"] = headers["X-TPA"]

            if hasattr(websocket_info, "connected") and not websocket_info.connected:
                info["status"] = "disconnected"
            elif hasattr(websocket_info, "is_open") and not websocket_info.is_open():
                info["status"] = "disconnected"
        except Exception:
            pass

        return info

    # ==================== Route Handlers ====================

    @router.get(
        "/apis",
        summary="List All API Endpoints",
        description="Returns a comprehensive list of all available API endpoints with their HTTP methods, request body schemas, and response formats.",
        response_description="List of all endpoints with their metadata",
        tags=["Discovery"]
    )
    async def api_list_all_endpoints():
        """List all API endpoints with their schemas and metadata.

        This endpoint provides introspection capabilities, returning:
        - All available routes under /api/
        - HTTP methods supported by each endpoint
        - Request body schemas (when applicable)
        - Endpoint names for programmatic access

        Returns:
            dict: {
                "ok": True,
                "count": int,
                "endpoints": [
                    {
                        "path": str,
                        "methods": list[str],
                        "endpoint": str,
                        "body_schema": dict | None
                    }
                ]
            }
        """
        from pydantic import TypeAdapter

        routes = []
        for route in router.routes:
            path = f"/api{route.path}"
            methods = list(route.methods)

            body_schema = None
            if hasattr(route, 'body_field') and route.body_field:
                try:
                    model = route.body_field.annotation
                    if model is not Any:
                        adapter = TypeAdapter(model)
                        body_schema = adapter.json_schema()
                except Exception:
                    body_schema = None

            routes.append({
                "path": path,
                "methods": methods,
                "endpoint": route.name,
                "body_schema": body_schema
            })

        return {
            "ok": True,
            "count": len(routes),
            "endpoints": sorted(routes, key=lambda x: x["path"]),
        }

    @router.get(
        "/status",
        summary="Get Server Status",
        description="Retrieves the current operational status of the ACSI WebSocket.",
        response_description="Server status information",
        responses={
            200: {"description": "Server status returned successfully"},
            500: {"description": "Error retrieving server status"}
        },
        tags=["Server Control"]
    )
    def api_status():
        """Get current server status.

        Returns:
            JSONResponse: {
                "ok": True,
                "status": str  # One of: "stopped", "starting", "listening", "stopping", "error"
            }
        """
        try:
            return JSONResponse(
                content={"ok": True, "status": str(rti_fsp.get_status())},
                status_code=200
            )
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.get(
        "/health",
        summary="Health Check",
        description="Health check endpoint for service discovery and monitoring. Returns the service status and connection information.",
        response_description="Health status and service information",
        responses={
            200: {"description": "Service is healthy and running"},
            500: {"description": "Service is unhealthy"}
        },
        tags=["Health"]
    )
    def api_health():
        """Generic health endpoint used by external discovery (e.g., BFF network scan).

        Returns:
            dict: {
                "status": "ok",
                "service": "ACSI-Server",
                "server": {
                    "status": str | None,
                    "host": str | None,
                    "port": int | None
                }
            }
        """
        try:
            status = rti_fsp.get_status()
            return {
                "status": "ok",
                "service": "ACSI-Server",
                "server": {
                    "status": status.get("status"),
                    "host": status.get("host"),
                    "port": status.get("port"),
                },
            }
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.get(
        "/connections",
        summary="List Active Connections",
        description="Returns information about all currently connected active WebSockets, including peer addresses and connection status.",
        response_description="List of active WebSocket connections",
        responses={
            200: {"description": "List of connections returned successfully"},
            500: {"description": "Error retrieving connections"}
        },
        tags=["Connections"]
    )
    def api_connections():
        """Get TPA information for all connected servers.

        Returns:
            dict: {
                "ok": True,
                "role": "ACSI-Server",
                "ws_mode": "active",
                "connected_servers": int,
                "connections": list[dict]  # Each containing peer_address, peer_port, tpa, status
            }
        """
        try:
            endpoint = rti_fsp.runtime.endpoint
            connections = []

            if endpoint is not None and hasattr(endpoint, "websocket_info_list"):
                for ws_info in endpoint.websocket_info_list:
                    tpa_data = extract_tpa_info(ws_info)
                    connections.append(tpa_data)

            return {
                "ok": True,
                "role": "ACSI-Server",
                "ws_mode": "active",
                "connected_servers": len(connections),
                "connections": connections,
            }
        except Exception as exc:
            rti_fsp._log_action(f"Get connections failed: {exc}", "error")
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.get(
        "/properties",
        summary="Get Server Properties",
        description="Returns the static properties and capabilities of the ACSI server.",
        response_description="Server role and mode properties",
        tags=["Server Control"]
    )
    def api_roles():
        """Get property information for the server.

        Returns:
            dict: {
                "ok": True,
                "acsi_role": "ACSI-Server",
                "ws_mode": "Active"
            }
        """
        return {
            "ok": True,
            "acsi_role": "ACSI-Server",
            "ws_mode": "Active",
        }

    @router.get(
        "/model",
        summary="Get IED Model",
        description="Returns the current loaded IED model descriptor for UI rendering, including the complete hierarchy of logical devices, logical nodes, data objects, and data attributes.",
        response_description="Complete IED model tree structure",
        responses={
            200: {"description": "IED model data returned successfully"},
            500: {"description": "Error retrieving model"}
        },
        tags=["Model"]
    )
    def api_model():
        """Return current loaded model descriptor for UI rendering.

        The response includes:
        - Server information and access points
        - Complete IED model tree
        - Logical device map
        - Detailed logical node information with data objects and attributes

        Returns:
            dict: {
                "status": "ready",
                "accessPoints": list[str],
                "model": {
                    "server": {...},
                    "tree": {...},
                    "source": str,
                    "iedName": str,
                    "logicalDeviceMap": dict,
                    "logicalNodeDetails": dict
                }
            }
        """
        try:

            print("getting model for cp in fsp: ", rti_fsp.runtime.cp)
            ied_model: Optional[IedModel] = rti_fsp.runtime.ied_model
            source = rti_fsp.runtime.model_source
            selected_ied = rti_fsp.runtime.model_ied_name
            access_points = [rti_fsp.runtime.cp or "cp1"]

            print("selected_ied in fsp: ", selected_ied)

            logical_devices: List[str] = []
            if ied_model is not None:
                logical_devices = [ld.name for ld in (ied_model.logical_devices or [])]

            tree_data = serialize_ied_tree(ied_model) if ied_model is not None else None
            logical_node_details = build_logical_node_details(ied_model)

            result = {
                "status": "ready",
                "accessPoints": access_points,
                "model": {
                    "server": {
                        "name": "ACSI Server WS Active",
                        "mode": "active",
                        "logicalDevices": logical_devices,
                        "iedName": selected_ied,
                        "iedNames": [selected_ied] if selected_ied else [],
                    },
                    "tree": tree_data,
                    "source": source,
                    "iedName": selected_ied,
                    "logicalDeviceMap": {
                        ld.name: [ln.name for ln in (ld.logical_nodes or [])]
                        for ld in (ied_model.logical_devices or [])
                    }
                    if ied_model is not None
                    else {"-": ["No model loaded. Upload an .scl/.scd file."]},
                    "logicalNodeDetails": logical_node_details,
                },
            }
            has_tree = tree_data is not None
            print(
                f"[GET /ap/model] "
                f"ied_model={ied_model is not None} "
                f"has_tree={has_tree} "
                f"source={source!r} "
                f"iedName={selected_ied!r} "
                f"logicalDevices={logical_devices}"
            )
            return result
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.post(
        "/update-iedmodel",
        summary="Update IED Model",
        description="Updates the model.py file in the ACSI-Server directory and reloads the IED model. Supports dynamic hot-swap while server is running.",
        response_description="Model update confirmation",
        responses={
            200: {"description": "Model updated successfully"},
            202: {"description": "Model update accepted, hot-swap in progress"},
            400: {"description": "Invalid request"},
            500: {"description": "Error updating model"}
        },
        tags=["Model"]
    )
    def api_update_iedmodel(request: UpdateIedmodelRequest):
        """Update model.py in fsp directory and reload IED model.

        Supports dynamic model updates while the server is running (hot-swap).
        The new model will be applied immediately if the server is running,
        or loaded when the server starts.

        Request Body:
            UpdateIedmodelRequest: { "modelPy": str }

        Returns:
            dict: {
                "ok": True,
                "source": str,  # Path to the updated model file
                "ied": str,     # Name of the IED model
                "modelVersion": int,  # New model version number
                "dynamicReload": bool, # Whether hot-swap was performed
                "status": str   # "loaded" or "reloading"
            }
        """
        try:
            model_py = request.modelPy

            if not isinstance(model_py, str) or not model_py.strip():
                return JSONResponse(
                    content={"ok": False, "error": "modelPy is required and must be a non-empty string."},
                    status_code=400
                )

            # Check server status
            server_status = rti_fsp.get_status()
            is_running = server_status.get("status") == "listening"

            # Always apply dynamically if server is running
            ied_model = rti_fsp.update_model_file(model_py, apply_dynamically=True)

            rti_fsp._log_action(
                "IED model updated",
                detail={
                    "source": str(rti_fsp.model_file),
                    "ied": ied_model.name,
                    "dynamic": is_running,
                    "version": rti_fsp.runtime.model_version
                },
            )

            # Check if hot-swap is in progress
            if is_running and rti_fsp.runtime.model_reload_in_progress:
                return JSONResponse(
                    content={
                        "ok": True,
                        "source": str(rti_fsp.model_file),
                        "ied": ied_model.name,
                        "modelVersion": rti_fsp.runtime.model_version,
                        "dynamicReload": True,
                        "status": "reloading"
                    },
                    status_code=202  # Accepted - hot-swap in progress
                )
            else:
                return {
                    "ok": True,
                    "source": str(rti_fsp.model_file),
                    "ied": ied_model.name,
                    "modelVersion": rti_fsp.runtime.model_version,
                    "dynamicReload": is_running,
                    "status": "loaded"
                }

        except Exception as exc:
            rti_fsp._log_action(f"IED model update failed: {exc}", "error")
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=400
            )

    @router.post(
        "/update-iedmodel-file",
        summary="Update IED Model from File",
        description="Upload a model.py file directly. Supports dynamic hot-swap while server is running.",
        response_description="Model update confirmation",
        responses={
            200: {"description": "Model updated successfully"},
            202: {"description": "Model update accepted, hot-swap in progress"},
            400: {"description": "Invalid request"},
            500: {"description": "Error updating model"}
        },
        tags=["Model"]
    )
    async def api_update_iedmodel_file(file: UploadFile = File(...)):
        """Upload model.py file directly for update.

        Accepts multipart/form-data with a 'file' field containing the model.py content.
        Supports the same hot-swap behavior as the JSON endpoint.

        Args:
            file: UploadFile - The model.py file to upload

        Returns:
            dict: {
                "ok": True,
                "source": str,  # Path to the updated model file
                "ied": str,     # Name of the IED model
                "modelVersion": int,  # New model version number
                "dynamicReload": bool, # Whether hot-swap was performed
                "status": str   # "loaded" or "reloading"
            }
        """
        try:
            # Read file content as string
            model_py = await file.read()
            model_py = model_py.decode('utf-8')

            if not model_py.strip():
                return JSONResponse(
                    content={"ok": False, "error": "Uploaded file is empty."},
                    status_code=400
                )

            # Reuse existing logic
            server_status = rti_fsp.get_status()
            is_running = server_status.get("status") == "listening"

            ied_model = rti_fsp.update_model_file(model_py, apply_dynamically=True)

            rti_fsp._log_action(
                "IED model updated from file",
                detail={
                    "source": str(rti_fsp.model_file),
                    "ied": ied_model.name,
                    "dynamic": is_running,
                    "version": rti_fsp.runtime.model_version,
                    "filename": file.filename
                },
            )

            # Check if hot-swap is in progress
            if is_running and rti_fsp.runtime.model_reload_in_progress:
                return JSONResponse(
                    content={
                        "ok": True,
                        "source": str(rti_fsp.model_file),
                        "ied": ied_model.name,
                        "modelVersion": rti_fsp.runtime.model_version,
                        "dynamicReload": True,
                        "status": "reloading"
                    },
                    status_code=202  # Accepted - hot-swap in progress
                )
            else:
                return {
                    "ok": True,
                    "source": str(rti_fsp.model_file),
                    "ied": ied_model.name,
                    "modelVersion": rti_fsp.runtime.model_version,
                    "dynamicReload": is_running,
                    "status": "loaded"
                }

        except Exception as exc:
            rti_fsp._log_action(f"IED model file update failed: {exc}", "error")
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=400
            )

    @router.post(
        "/start",
        summary="Start Server",
        description="Starts the ACSI server - Active WebSocket on the specified host and port. Only 'server' mode is supported.",
        response_description="Server start confirmation",
        responses={
            200: {"description": "Server started successfully"},
            400: {"description": "Invalid parameters or server error"}
        },
        tags=["Server Control"]
    )
    def api_start(request: StartRequest):
        """Start the ACSI WebSocket server.

        Request Body:
            StartRequest: {
                "host": str,    # Hostname/IP to bind to
                "port": str,    # Port number to listen on
                "mode": str,    # Only 'server' mode supported
                "cp": str       # Communication point identifier
            }

        Returns:
            dict: {
                "ok": True,
                "status": "listening",
                "host": str,
                "port": int
            }

        Raises:
            HTTPException 400: If mode is not 'server' or port is invalid
            HTTPException 400: If server fails to start
        """
        try:
            host = request.host
            raw_port = request.port
            mode = request.mode
            cp = request.cp

            if mode != "active":
                rti_fsp._log_action("Only 'active' mode is supported in this app", "error")
                return JSONResponse(
                    content={"ok": False, "error": "Only 'active' mode is supported in this app."},
                    status_code=400
                )
            try:
                port = int(raw_port)
            except (TypeError, ValueError):
                return JSONResponse(
                    content={"ok": False, "error": f"Invalid port value: {raw_port!r}"},
                    status_code=400
                )

            if cp:
                try:
                    rti_fsp._set_runtime_state(cp=cp)
                except Exception as exc:
                    return JSONResponse(
                        content={"ok": False, "error": f"Failed to set runtime state: {exc}"},
                        status_code=400
                    )

            try:
                rti_fsp.start_server(host, port)
            except Exception as exc:
                return JSONResponse(
                    content={"ok": False, "error": f"Failed to start server: {exc}"},
                    status_code=400
                )

            return {"ok": True, "status": "listening", "host": host, "port": port}
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": f"Unexpected error: {exc}"},
                status_code=400
            )

    @router.post(
        "/stop",
        summary="Stop Server",
        description="Stops the currently running ACSI WebSocket.",
        response_description="Server stop confirmation",
        responses={
            200: {"description": "Server stopped or stopping"},
            500: {"description": "Error stopping server"}
        },
        tags=["Server Control"]
    )
    def api_stop():
        """Stop the ACSI WebSocket Active.

        Returns:
            dict: {
                "ok": True,
                "status": str  # "stopped" or "stopping"
            }

        Raises:
            HTTPException 500: If error occurs during stop
        """
        try:
            status = rti_fsp.runtime.status
            if status in (None, "stopped"):
                return {"ok": True, "status": "stopped"}

            try:
                rti_fsp.stop_server()

                if _use_io_plugin:
                    try:
                        # Use dynamic loading functions
                        io_plugin = get_io_plugin_dynamic()
                        mapping_manager = get_mapping_manager_dynamic()
                        sync_to_io_device = get_sync_to_io_device_dynamic()
                        write_to_lcd = get_write_to_lcd_dynamic()
                        
                        if io_plugin is None or mapping_manager is None or sync_to_io_device is None or write_to_lcd is None:
                            logger.warning("Dynamic io_plugin loading failed, falling back to disabled state")
                            _use_io_plugin = False
                            return
                        logger.info(f"[FSP] IO Plugin for connected: {io_plugin}")
                        if io_plugin:
                            # Use associateId as identifier, or a default
                            # Turn LED ON (write True/1 to the LED reference)
                            asyncio.create_task(
                                sync_to_io_device(io_plugin, "stopped", False)
                            )
                            
                            # Write connection info to LCD
                            asyncio.create_task(
                                write_to_lcd(io_plugin, "stopped", "Stopped", mapping_manager=mapping_manager)
                            )
                        else:
                            logger.warning("[FSP] IO Plugin is None - cannot turn on LED. Call /api/io/connect first.")
                    except ImportError as e:
                        logger.error(f"[FSP] ImportError - Cannot import IO Plugin: {e}")
                    except Exception as e:
                        logger.error(f"[FSP] Exception in IO connected callback: {e}")
                

                current = rti_fsp.runtime.status
                if current in ("stopping", "starting"):
                    return {"ok": True, "status": "stopping"}
                return {"ok": True, "status": "stopped"}
            except Exception as exc:
                current = rti_fsp.runtime.status
                if current in ("stopping", "stopped"):
                    return {"ok": True, "status": current}
                rti_fsp._log_action(f"Stop failed: {exc}", "error")
                return JSONResponse(
                    content={"ok": False, "error": f"Unexpected error: {exc}"},
                    status_code=500
                )
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": f"Unexpected error: {exc}"},
                status_code=500
            )

    async def _wait_for_runtime_loop(rti_fsp, timeout: float = 5.0) -> asyncio.AbstractEventLoop:
        """Poll until the server's background event loop is created and running,
        or raise if it doesn't show up within `timeout` seconds."""
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            loop = rti_fsp.runtime.loop
            if loop is not None and loop.is_running():
                return loop
            if asyncio.get_event_loop().time() >= deadline:
                raise RuntimeError("server-failed-to-start")
            await asyncio.sleep(0.05)

    @router.post(
        "/reconfig-connection",
        summary="Get Connection Info",
        description="Returns detailed information about the current WebSocket connection, including peer address, port, and connection status.",
        response_description="Connection details",
        responses={
            200: {"description": "Connection information returned successfully"},
            500: {"description": "Error retrieving connection info"}
        },
        tags=["Client Status"]
    )
    async def api_reconfig_connection(request: TLSConnectionCreateConfigRequest):
        """Reconfigure the connection with a new communication point."""
        try:
            rti_fsp._log_action(f"Starting connection reconfiguration for host: {request.host}, port: {request.port}", "info")
            # Normalize tls_version to handle "1.2", "1.3", "TLSv1_2", "TLSv1_3" formats
            tls_version_str = (request.tls_version or "1.3").lower()
            if "1.2" in tls_version_str or "1_2" in tls_version_str:
                tls_version = ssl.TLSVersion.TLSv1_2
            else:
                tls_version = ssl.TLSVersion.TLSv1_3
            rti_fsp._log_action(f"TLS version determined: {tls_version} (from request: {request.tls_version})", "info")
            print("tls_version in reconfig connection: ", tls_version, "(from request:", request.tls_version, ")")
            host = request.host
            request_port = request.port
            if request.ws_mode.lower() == "active":
                # Only create TLSConfig if TLS is enabled
                tls_config = None
                if request.enable_tls:
                    tls_config = TLSConfig(
                        mode="client",
                        cafile=request.server_ca,
                        min_version=tls_version,
                        max_version=tls_version,
                        keylog_file=os.path.join("/app/fsp", "tlskeys.log"),
                    )
                cp = os.getenv("CP", "cp1")

                loop = rti_fsp.runtime.loop
                if loop is None or not loop.is_running():
                    rti_fsp._log_action("Server not running, starting server instance", "info")
                    print("server not running, starting server instance")
                    rti_fsp.start_server(host, int(request_port))
                    loop = await _wait_for_runtime_loop(rti_fsp, timeout=5.0)
                    rti_fsp._log_action("Server instance started", "info")

                endpoint = rti_fsp.runtime.endpoint
                if endpoint is None:
                    return JSONResponse(
                        content={"ok": False, "error": "Endpoint not initialized"},
                        status_code=500,
                    )

                # Call reconfigure_connection on the endpoint's event loop
                # The library handles TLS config and task restart internally
                rti_fsp._log_action(f"Calling reconfigure_connection for host: {host}, port: {request_port}, TLS: {request.enable_tls}", "info")
                fut = asyncio.run_coroutine_threadsafe(
                    endpoint.reconfigure_connection(
                        host, request_port, cp, request.enable_tls, tls_config=tls_config
                    ),
                    loop,
                )
                # Wait for the reconfiguration to complete
                try:
                    await asyncio.wrap_future(fut)
                    rti_fsp._log_action("Connection reconfigured successfully", "info")
                except Exception as e:
                    rti_fsp._log_action(f"Error during reconfigure_connection: {e}", "error")
                    print(f"Error during reconfigure_connection: {e}")
                    # Don't fail the endpoint - the connection may still have been restarted
                    # Just log and continue
                
                rti_fsp.runtime.tasks["ws"] = endpoint._connect_task

                print("Reconfigured connection with TLS enabled:", request.enable_tls)
                return JSONResponse(
                    content={"ok": True, "status": "reconfigured", "ws_mode": request.ws_mode,
                             "enable_tls": request.enable_tls},
                    status_code=200,
                )
            else:
                return JSONResponse(
                    content={"ok": False, "error": "Only active mode is supported for reconfiguration."},
                    status_code=400,
                )
        except Exception as exc:
            rti_fsp._log_action(f"api_reconfig_connection failed: {exc}", "error")
            return JSONResponse(content={"ok": False, "error": str(exc)}, status_code=500)

    @router.get(
        "/tls-config",
        summary="Get TLS Configuration",
        description="Returns the current TLS configuration from runtime variables.",
        response_description="TLS configuration from runtime",
        responses={
            200: {"description": "TLS configuration returned successfully"},
            500: {"description": "Error retrieving TLS configuration"}
        },
        tags=["TLS"]
    )
    def api_get_tls_config():
        """Get current TLS configuration from runtime.

        Returns: TLS configuration from the endpoint's runtime state including:
        - enable_tls: Whether TLS is enabled
        - tls_version: TLS version (1.2 or 1.3)
        - server_key: Server private key (for server mode)
        - server_cert: Server certificate (for server mode)
        - server_ca: CA certificate (for client mode)
        - ws_mode: WebSocket mode (active or passive)
        """
        try:
            endpoint = rti_fsp.runtime.endpoint
            if endpoint is None:
                return JSONResponse(
                    content={"ok": False, "error": "Endpoint not available"},
                    status_code=500
                )

            # Get TLS config from runtime
            enable_tls = False
            tls_version = "1.2"
            server_key = None
            server_cert = None
            server_ca = None

            if hasattr(endpoint, '_tls_config') and endpoint._tls_config is not None:
                tls_config = endpoint._tls_config
                enable_tls = True
                # Extract TLS version from config
                if hasattr(tls_config, 'min_version'):
                    if tls_config.min_version == ssl.TLSVersion.TLSv1_3:
                        tls_version = "1.3"
                    elif tls_config.min_version == ssl.TLSVersion.TLSv1_2:
                        tls_version = "1.2"
                if hasattr(tls_config, 'cafile'):
                    server_ca = tls_config.cafile
                if hasattr(tls_config, 'certfile'):
                    server_cert = tls_config.certfile
                if hasattr(tls_config, 'keyfile'):
                    server_key = tls_config.keyfile
            
            # Get ws_mode
            ws_mode = "active"
            if hasattr(endpoint, 'ws_mode'):
                ws_mode = endpoint.ws_mode
            elif hasattr(rti_fsp.runtime, 'ws_mode'):
                ws_mode = rti_fsp.runtime.ws_mode

            return {
                "ok": True,
                "enable_tls": enable_tls,
                "tls_version": tls_version,
                "server_key": server_key,
                "server_cert": server_cert,
                "server_ca": server_ca,
                "ws_mode": ws_mode
            }
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.post(
        "/reconfig-oauth",
        summary="Get Connection Info",
        description="Returns detailed information about the current WebSocket connection, including peer address, port, and connection status.",
        response_description="Connection details",
        responses={
            200: {"description": "Connection information returned successfully"},
            500: {"description": "Error retrieving connection info"}
        },
        tags=["Client Status"]
    )
    async def api_reconfig_oauth(request: OAUTHCreateConfigRequest):
        """Reconfigure OAuth settings. OAuth config should be provided in the request by BFF."""
        try:
            rti_fsp._log_action(f"Starting OAuth reconfiguration for connection: {request.connection_name or 'unknown'}", "info")
            cp = request.cp or os.getenv("CP", "cp1")
            host = request.host
            oauth_port = request.port
            
            # Get OAuth settings from request (BFF should provide these from connections.json)
            token_endpoint = getattr(request, 'token_endpoint_url', None) or getattr(request, 'token_endpoint', None)
            client_id = getattr(request, 'client_id', None)
            client_secret = getattr(request, 'client_secret', None)
            ca_certificate = getattr(request, 'ca_certificate', None)
            enable_token_refresh = getattr(request, 'enable_token_refresh', False)
            
            connection_name = request.connection_name or "unknown"
            rti_fsp._log_action(f"OAuth configuration - enable: {request.enable_oauth}, connection: {connection_name}", "info")
            
            # Validate that required OAuth settings are provided
            if request.enable_oauth and not token_endpoint:
                error_msg = f"token_endpoint is required for OAuth but was not provided in request for connection: {connection_name}"
                rti_fsp._log_action(error_msg, "error")
                raise ValueError(error_msg)
            
            # When disabling OAuth, pass None to signal that OAuth should be disabled
            # The underlying library should handle None properly
            if not request.enable_oauth:
                rti_fsp._log_action("Disabling OAuth for connection", "info")
                token_endpoint = None
                client_id = None
                client_secret = None
                ca_certificate = None
            
            print("Reconfiguring OAuth with connection: ", connection_name)
            print(f"OAuth enable: {request.enable_oauth}, token_endpoint: {token_endpoint}")

            loop = rti_fsp.runtime.loop
            if loop is None or not loop.is_running():
                rti_fsp._log_action("Server not running, starting server instance for OAuth reconfig", "info")
                print("server not running, starting server instance")
                rti_fsp.start_server(host, int(oauth_port))
                loop = await _wait_for_runtime_loop(rti_fsp, timeout=5.0)
                rti_fsp._log_action("Server instance started for OAuth reconfig", "info")

            # When disabling OAuth, stop the endpoint first to avoid issues with ClientCredentialsProvider
            if not request.enable_oauth:
                rti_fsp._log_action("Disabling OAuth - stopping endpoint first", "info")
                print("Disabling OAuth - stopping endpoint first")
                # Stop the current connection if it exists
                if hasattr(rti_fsp.runtime.endpoint, '_connect_task') and rti_fsp.runtime.endpoint._connect_task is not None:
                    stop_fut = asyncio.run_coroutine_threadsafe(
                        rti_fsp.runtime.endpoint._cancel_task(rti_fsp.runtime.endpoint._connect_task),
                        loop,
                    )
                    await asyncio.wrap_future(stop_fut)
                rti_fsp._log_action("Endpoint stopped, now reconfiguring with OAuth disabled", "info")
                print("Endpoint stopped, now reconfiguring with OAuth disabled")

            # Call reconfigure_oauth with settings from connection
            rti_fsp._log_action(f"Calling reconfigure_oauth for host: {host}, port: {oauth_port}, OAuth: {request.enable_oauth}", "info")
            fut = asyncio.run_coroutine_threadsafe(
                rti_fsp.runtime.endpoint.reconfigure_oauth(
                    host=host,
                    port=str(oauth_port),
                    cp=cp,
                    oauth_enable=request.enable_oauth,
                    token_endpoint=token_endpoint,
                    client_id=client_id,
                    client_secret=client_secret,
                    kc_cert=ca_certificate,
                    enable_token_refresh=enable_token_refresh,
                ),
                loop,
            )
            await asyncio.wrap_future(fut)
            rti_fsp._log_action("OAuth reconfigured successfully", "info")
            rti_fsp.runtime.tasks["ws"] = rti_fsp.runtime.endpoint._connect_task

            return JSONResponse(
                content={"ok": True, "status": "reconfigured", "ws_mode": "active",
                         "enable_oauth": request.enable_oauth},
                status_code=200,
            )
        except Exception as exc:
            import traceback
            print("Reconfig OAuth error:", exc)
            print("Traceback:", traceback.format_exc())
            rti_fsp._log_action(f"api_reconfig_oauth failed: {exc}", "error")
            return JSONResponse(content={"ok": False, "error": str(exc)}, status_code=500)

    @router.get(
        "/oauth-status",
        summary="Get OAuth Status",
        description="Returns whether OAuth is currently enabled or disabled for this FSP server.",
        response_description="OAuth enable status",
        responses={
            200: {"description": "OAuth status returned successfully"},
            500: {"description": "Error retrieving OAuth status"}
        },
        tags=["OAuth"]
    )
    def api_get_oauth_status():
        """Get current OAuth enable/disable status from the FSP server.

        Returns:
            dict: {
                "ok": True,
                "enable_oauth": bool  # Current OAuth status
            }
        """
        try:
            # Check the runtime endpoint's OAuth enable status
            if hasattr(rti_fsp.runtime, 'endpoint') and hasattr(rti_fsp.runtime.endpoint, '_oauth_enable'):
                enable_oauth = rti_fsp.runtime.endpoint._oauth_enable
                return {"ok": True, "enable_oauth": enable_oauth}
            else:
                # If endpoint not available or attribute not found, check if OAuth is configured
                return {"ok": True, "enable_oauth": False}
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.get(
        "/actions-logs",
        summary="Get Action Log",
        description="Retrieves the logged server actions for debugging and auditing purposes.",
        response_description="List of logged actions",
        responses={
            200: {"description": "List of actions returned successfully"},
            500: {"description": "Error retrieving actions"}
        },
        tags=["Logging"]
    )
    def api_actions():
        """Get logged server actions.

        Returns:
            dict: { "actions": list[dict] }
        """
        try:
            return {"actions": rti_fsp.get_actions()}
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": f"Unexpected error: {exc}"},
                status_code=500
            )

    @router.post(
        "/clear-logs",
        summary="Clear Action Log",
        description="Clears all logged server actions.",
        response_description="Action log clear confirmation",
        responses={
            200: {"description": "Actions cleared successfully"},
            500: {"description": "Error clearing actions"}
        },
        tags=["Logging"]
    )
    def api_actions_clear():
        """Clear action log.

        Returns:
            dict: { "ok": True }
        """
        try:
            rti_fsp.clear_actions()
            return {"ok": True}
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": f"Unexpected error: {exc}"},
                status_code=500
            )

    @router.get(
        "/messages",
        summary="Get Message Log",
        description="Retrieves the logged protocol messages for debugging purposes.",
        response_description="List of logged protocol messages",
        responses={
            200: {"description": "List of messages returned successfully"},
            500: {"description": "Error retrieving messages"}
        },
        tags=["Logging"]
    )
    def api_messages():
        """Get logged protocol messages.

        Returns:
            dict: { "messages": list[dict] }
        """
        try:
            return {"messages": rti_fsp.get_messages()}
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": f"Unexpected error: {exc}"},
                status_code=500
            )

    @router.post(
        "/clear-messages",
        summary="Clear Message Log",
        description="Clears all logged protocol messages.",
        response_description="Message log clear confirmation",
        responses={
            200: {"description": "Messages cleared successfully"},
            500: {"description": "Error clearing messages"}
        },
        tags=["Logging"]
    )
    def api_messages_clear():
        """Clear message log.

        Returns:
            dict: { "ok": True }
        """
        try:
            rti_fsp.clear_messages()
            return {"ok": True}
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": f"Unexpected error: {exc}"},
                status_code=500
            )

    @router.post(
        "/readvalue",
        summary="Read Value",
        description="Reads a value from the server's IED model. Requires the server to be running.",
        response_description="Read value result",
        responses={
            200: {"description": "Value read successfully"},
            400: {"description": "Missing objRef parameter"},
            403: {"description": "Server is not running"},
            404: {"description": "Instance not available or read timeout"},
            500: {"description": "Error reading value"}
        },
        tags=["Data Access"]
    )
    def api_read_value(request: ReadvalueRequest):
        """Read a value from the server IED model.

        Request Body:
            ReadvalueRequest: {
                "objRef": str,  # Required - Object reference in ACSI format
                "fc": str        # Optional - Functional constraint
            }

        Returns:
            dict: {
                "ok": True,
                "success": True,
                "objRef": str,
                "fc": str,
                "values": list[dict]  # Each containing type and value
            }

        Raises:
            HTTPException 400: If objRef is missing
            HTTPException 403: If server is not running
            HTTPException 404: If instance not available or timeout
        """
        try:
            obj_ref = request.objRef  # Fixed typo from request,object
            fc = request.fc

            if not obj_ref:
                rti_fsp._log_action("Server readvalue rejected: missing objRef", "warn")
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400
                )

            if rti_fsp.runtime.server is None:
                rti_fsp._log_action(
                    "Server readvalue rejected: server not running",
                    "warn",
                    detail={"objRef": obj_ref, "fc": fc},
                )
                return JSONResponse(
                    content={"ok": False, "error": "Server is not running"},
                    status_code=503
                )

            try:
                result = rti_fsp.read_value(obj_ref)

                if result is None:
                    rti_fsp._log_action(
                        "Server readvalue failed: instanceNotAvailable",
                        "warn",
                        detail={"objRef": obj_ref, "fc": fc},
                    )
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404
                    )



                print(
                    f"[POST /ap/readvalue] SUCCESS objRef={obj_ref!r} "
                    f"fc={fc!r} type={result.get('type')!r} value={result.get('value')!r}"
                )

                rti_fsp._log_action(
                    "Server readvalue",
                    detail={
                        "objRef": obj_ref,
                        "fc": fc,
                        "type": result.get("type"),
                        "value": result.get("value"),
                    },
                )
                return {
                    "ok": True,
                    "success": True,
                    "objRef": obj_ref,
                    "fc": fc,
                    "values": result,
                }

            except FuturesTimeoutError:
                rti_fsp._log_action(
                    "Server readvalue timeout",
                    "warn",
                    detail={"objRef": obj_ref, "fc": fc},
                )
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"},
                    status_code=404
                )
            except ValueError as exc:
                rti_fsp._log_action(f"Server readvalue failed: {exc}", "warn")
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                rti_fsp._log_action(f"Server readvalue failed: {exc}", "error")
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=404
            )

    @router.post(
        "/writevalue",
        summary="Write Value",
        description="Writes a value to the server's IED model. Requires the server to be running.",
        response_description="Write value confirmation",
        responses={
            200: {"description": "Value written successfully"},
            400: {"description": "Missing parameters or invalid value"},
            403: {"description": "Server is not running"},
            404: {"description": "Write timeout"},
            500: {"description": "Error writing value"}
        },
        tags=["Data Access"]
    )
    async def api_write_value(request: WritevalueRequest):
        """Write a value in the server IED model.

        Request Body:
            WritevalueRequest: {
                "objRef": str,     # Required - Object reference
                "fc": str,        # Required - Functional constraint
                "value": str,     # Required - Value to write
                "dataType": str   # Optional - Data type for coercion
            }

        Returns:
            dict: {
                "ok": True,
                "success": True,
                "objRef": str,
                "fc": str,
                "value": any,
                "dataType": str
            }

        Raises:
            HTTPException 400: If objRef, fc, or value is missing
            HTTPException 403: If server is not running
            HTTPException 404: If write timeout occurs
        """
        try:
            obj_ref = request.objRef
            fc = request.fc
            value = request.value
            data_type = request.dataType

            if not obj_ref:
                rti_fsp._log_action("Server writevalue rejected: missing objRef", "warn")
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400
                )

            if value is None:
                rti_fsp._log_action(
                    "Server writevalue rejected: missing value",
                    "warn",
                    detail={"objRef": obj_ref, "fc": fc},
                )
                return JSONResponse(
                    content={"ok": False, "error": "value is required"},
                    status_code=400
                )

            if rti_fsp.runtime.server is None:
                rti_fsp._log_action(
                    "Server writevalue rejected: server not running",
                    "warn",
                    detail={"objRef": obj_ref, "fc": fc, "value": value},
                )
                return JSONResponse(
                    content={"ok": False, "error": "Server is not running"},
                    status_code=503
                )

            try:
                result = rti_fsp.write_value(obj_ref, value, data_type)

                if _use_io_plugin:
                    try:
                        # Get the existing IO router's client and mapping manager using dynamic loading
                        io_plugin = get_io_plugin_dynamic()
                        mapping_manager = get_mapping_manager_dynamic()
                        sync_to_io_device = get_sync_to_io_device_dynamic()
                        write_to_lcd = get_write_to_lcd_dynamic()
                        
                        if io_plugin is None or mapping_manager is None or sync_to_io_device is None or write_to_lcd is None:
                            logger.warning("Dynamic io_plugin loading failed, falling back to disabled state")
                            _use_io_plugin = False
                            return
                        logger.info(f"IO Plugin for sync: {io_plugin}")
                        if io_plugin:
                            # Fire-and-forget: don't wait for IO sync to complete
                            # Check health and sync in background
                            asyncio.create_task(
                                sync_to_io_device(io_plugin, obj_ref, value)
                            )

                            value_write = f"{obj_ref} : {value}"

                            asyncio.create_task(
                                write_to_lcd(io_plugin, "writeValue", value_write, mapping_manager=mapping_manager)
                            )
                        else:
                            logger.warning("IO Plugin is None - cannot sync to device. Call /api/io/connect first.")
                    except ImportError as e:
                        logger.error(f"ImportError - Cannot import IO Plugin: {e}")
                    except Exception as e:
                        logger.error(f"Exception in IO sync setup: {e}")
                
                
                return {
                    "ok": True,
                    "success": True,
                    "objRef": result["objRef"],
                    "fc": fc,
                    "value": result["value"],
                    "dataType": result["dataType"],
                }

            except FuturesTimeoutError:
                rti_fsp._log_action(
                    "Server writevalue timeout",
                    "warn",
                    detail={"objRef": obj_ref, "fc": fc},
                )
                return JSONResponse(
                    content={"ok": False, "error": "write timeout"},
                    status_code=504
                )
            except ValueError as exc:
                rti_fsp._log_action(f"Server writevalue failed: {exc}", "warn")
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                rti_fsp._log_action(f"Server writevalue failed: {exc}", "error")
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    # ==================== IO Plugin Connection Endpoints ====================

    @router.get(
        "/io-plugin",
        summary="Get IO Plugin Status",
        description="Returns whether io_plugin is enabled for device sync.",
        response_description="IO Plugin status",
        responses={
            200: {"description": "IO Plugin status returned successfully"}
        },
        tags=["IO Plugin"]
    )
    def api_get_io_plugin_status():
        """Get current io_plugin usage status.
        
        Returns:
            dict: {"enabled": bool}
        """
        return {"enabled": _use_io_plugin}

    @router.post(
        "/io-plugin",
        summary="Set IO Plugin Usage",
        description="Enable or disable io_plugin for syncing writes to physical IO devices.",
        response_description="IO Plugin configuration confirmation",
        responses={
            200: {"description": "IO Plugin configuration updated successfully"},
            500: {"description": "Error updating configuration"}
        },
        tags=["IO Plugin"]
    )
    def api_set_io_plugin(request: IoPluginConfigRequest):
        """Enable or disable io_plugin usage.
        
        When enabled, writes to the ACSI server will be synced to physical IO devices.
        When disabled, writes will only affect the ACSI server model.
        
        If enabling, will attempt to load modules if files are present.
        
        Request Body:
            IoPluginConfigRequest: {"enabled": bool}
        
        Returns:
            dict: {"ok": True, "enabled": bool, "message": str}
        """
        global _use_io_plugin
        _use_io_plugin = request.enabled

        if _use_io_plugin:
            try:
                # If enabling, try to load modules if files are present
                if check_required_io_plugin_files():
                    load_io_plugin_modules()
                    update_io_plugin_usage()
                else:
                    # Required files are missing, disable io_plugin
                    _use_io_plugin = False
                    logger.warning("Required IO plugin files are missing, disabling IO plugin")
            except Exception as e:
                logger.error(f"Error enabling IO Plugin: {e}")
                _use_io_plugin = False
                
        logger.info(f"IO Plugin usage set to: {_use_io_plugin}")
        return {
            "ok": True,
            "enabled": _use_io_plugin,
            "message": f"IO Plugin {'enabled' if _use_io_plugin else 'disabled'}"
        }

    @router.post(
        "/io-plugin/upload",
        summary="Upload IO Plugin File",
        description="Upload a file to the dynamic io_plugin directory. Multiple files can be uploaded to create a complete io_plugin implementation.",
        response_description="File upload confirmation",
        responses={
            200: {"description": "File uploaded successfully"},
            400: {"description": "Invalid request or file"},
            500: {"description": "Error uploading file"}
        },
        tags=["IO Plugin"]
    )
    async def api_upload_io_plugin_file(file: UploadFile = File(...), request: IoPluginFileUploadRequest = None):
        """Upload a file to the dynamic io_plugin directory.
        
        Files can be uploaded one at a time. After uploading all required files,
        call /api/io-plugin/reload to load the modules.
        
        Args:
            file: UploadFile - The file to upload
            request: IoPluginFileUploadRequest - Optional request body with file_path and overwrite
            
        Returns:
            dict: {"ok": True, "file_path": str, "size": int, "message": str}
        """
        try:
            # Read file content
            file_content = await file.read()
            
            # Determine file path
            if request and request.file_path:
                file_path = get_io_plugin_file_path(request.file_path)
            else:
                file_path = get_io_plugin_file_path(file.filename)
            
            # Check if file already exists
            if file_path.exists() and not (request and request.overwrite):
                return {
                    "ok": False,
                    "error": f"File already exists: {file_path.name}",
                    "message": "Use overwrite=true to replace existing files"
                }
            
            # Ensure directory exists
            ensure_io_plugin_dir()
            
            # Write file
            with open(file_path, 'wb') as f:
                f.write(file_content)
            
            logger.info(f"Uploaded io_plugin file: {file_path} ({len(file_content)} bytes)")
            
            # Check if we now have all required files
            if check_required_io_plugin_files():
                logger.info("All required io_plugin files are now present")
            
            return {
                "ok": True,
                "file_path": str(file_path.relative_to(io_plugin_dynamic_DIR)),
                "full_path": str(file_path),
                "size": len(file_content),
                "message": f"File uploaded successfully: {file.filename}",
                "files_present": check_required_io_plugin_files()
            }
            
        except Exception as e:
            logger.error(f"Error uploading io_plugin file: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get(
        "/io-plugin/files",
        summary="List IO Plugin Files",
        description="List all files currently in the dynamic io_plugin directory.",
        response_description="List of files",
        responses={
            200: {"description": "List of files returned successfully"},
            500: {"description": "Error listing files"}
        },
        tags=["IO Plugin"]
    )
    def api_list_io_plugin_files():
        """List all files in the dynamic io_plugin directory.
        
        Returns:
            dict: {"files": list, "required_files_present": bool, "missing_files": list}
        """
        try:
            ensure_io_plugin_dir()
            
            # Get all files in the directory
            all_files = []
            for item in io_plugin_dynamic_DIR.iterdir():
                if item.is_file():
                    all_files.append({
                        "name": item.name,
                        "path": str(item.relative_to(io_plugin_dynamic_DIR)),
                        "size": item.stat().st_size,
                        "modified": item.stat().st_mtime
                    })
            
            # Check which required files are missing
            required_files = ["io_router.py", "io_utils.py", "mapping_manager.py", "__init__.py"]
            present_files = [f.name for f in io_plugin_dynamic_DIR.iterdir() if f.is_file()]
            missing_files = [f for f in required_files if f not in present_files]
            
            return {
                "files": all_files,
                "required_files_present": len(missing_files) == 0,
                "missing_files": missing_files,
                "directory": str(io_plugin_dynamic_DIR)
            }
            
        except Exception as e:
            logger.error(f"Error listing io_plugin files: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post(
        "/io-plugin/reload",
        summary="Reload IO Plugin Modules",
        description="Reload the io_plugin modules from the dynamic directory. Use after uploading new files.",
        response_description="Reload confirmation",
        responses={
            200: {"description": "Modules reloaded successfully"},
            400: {"description": "Required files missing"},
            500: {"description": "Error reloading modules"}
        },
        tags=["IO Plugin"]
    )
    def api_reload_io_plugin_modules(request: IoClientReloadRequest = None):
        """Reload io_plugin modules from the dynamic directory.
        
        Args:
            request: IoClientReloadRequest - Optional request body with force flag
            
        Returns:
            dict: {"ok": True, "loaded": bool, "message": str, "modules": list}
        """
        try:
            force = request.force if request else False
            
            # Clear existing modules first
            clear_io_plugin_modules()
            
            # Check if required files exist
            if not check_required_io_plugin_files():
                return {
                    "ok": False,
                    "loaded": False,
                    "message": "Required files are missing",
                    "missing_files": [f for f in ["io_router.py", "io_utils.py", "mapping_manager.py", "__init__.py"] 
                                    if not get_io_plugin_file_path(f).exists()]
                }
            
            # Load modules
            success = load_io_plugin_modules()
            
            if success:
                # Update the usage flag
                update_io_plugin_usage()
                
                return {
                    "ok": True,
                    "loaded": True,
                    "message": "IO Plugin modules reloaded successfully",
                    "modules": ["io_router", "io_utils", "mapping_manager"],
                    "io_plugin_enabled": _use_io_plugin
                }
            else:
                return {
                    "ok": False,
                    "loaded": False,
                    "message": "Failed to load io_plugin modules"
                }
                
        except Exception as e:
            logger.error(f"Error reloading io_plugin modules: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete(
        "/io-plugin/files/{file_path:path}",
        summary="Delete IO Plugin File",
        description="Delete a file from the dynamic io_plugin directory.",
        response_description="Deletion confirmation",
        responses={
            200: {"description": "File deleted successfully"},
            404: {"description": "File not found"},
            500: {"description": "Error deleting file"}
        },
        tags=["IO Plugin"]
    )
    def api_delete_io_plugin_file(file_path: str):
        """Delete a file from the dynamic io_plugin directory.
        
        Args:
            file_path: str - Path to the file (relative to io_plugin directory)
            
        Returns:
            dict: {"ok": True, "deleted": str, "message": str}
        """
        try:
            file_to_delete = get_io_plugin_file_path(file_path)
            
            if not file_to_delete.exists():
                return {
                    "ok": False,
                    "deleted": False,
                    "message": f"File not found: {file_path}"
                }
            
            file_to_delete.unlink()
            logger.info(f"Deleted io_plugin file: {file_path}")
            
            return {
                "ok": True,
                "deleted": True,
                "file_path": file_path,
                "message": f"File deleted successfully: {file_path}"
            }
            
        except Exception as e:
            logger.error(f"Error deleting io_plugin file: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get(
        "/io-plugin/status",
        summary="Get IO Plugin Status",
        description="Get detailed status of io_plugin dynamic loading including file availability and module loading status.",
        response_description="Detailed status",
        responses={
            200: {"description": "Status returned successfully"}
        },
        tags=["IO Plugin"]
    )
    def api_get_io_plugin_detailed_status():
        """Get detailed status of io_plugin dynamic loading.
        
        Returns:
            dict: {"enabled": bool, "files_present": bool, "modules_loaded": bool, "details": dict}
        """
        try:
            files_present = check_required_io_plugin_files()
            modules_loaded = _io_plugin_module is not None and _mapping_manager_module is not None and _io_utils_module is not None
            
            return {
                "enabled": _use_io_plugin,
                "files_present": files_present,
                "modules_loaded": modules_loaded,
                "dynamic_directory": str(io_plugin_dynamic_DIR),
                "details": {
                    "io_router_loaded": _io_plugin_module is not None,
                    "io_utils_loaded": _io_utils_module is not None,
                    "mapping_manager_loaded": _mapping_manager_module is not None
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting io_plugin detailed status: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.post(
        "/io-plugin/connect",
        summary="Connect to IO Server",
        description="Connect to IO server and download io_plugin files for dynamic loading. This is an on-demand connection endpoint (no auto-fetch at startup).",
        response_description="Connection result with download and loading status",
        responses={
            200: {"description": "Connection and file download completed successfully"},
            400: {"description": "Invalid request or configuration"},
            500: {"description": "Error connecting to IO server or downloading files"}
        },
        tags=["IO Plugin Connection"]
    )
    async def api_io_plugin_connect(request: IoClientConnectRequest):
        """Connect to IO server and fetch io_plugin files.
        
        This endpoint implements on-demand connection to the IO server. It will:
        1. Check IO server health
        2. Download required files (or specified files)
        3. Load the modules if download is successful
        4. Enable io_plugin usage if requested
        
        Request Body:
            IoClientConnectRequest: {
                "server_url": str,           # IO server URL
                "files": list[str] | None,   # Files to fetch (None = all required)
                "timeout": float,             # Timeout in seconds
                "enable_io_plugin": bool    # Enable io_plugin after success
            }
        
        Returns:
            dict: {
                "ok": True/False,
                "connection_success": bool,
                "download_success": bool,
                "load_success": bool,
                "server_healthy": bool,
                "files_downloaded": list[str],
                "files_failed": list[str],
                "errors": dict,
                "status": str
            }
        """
        global _use_io_plugin
        
        try:
            # Record connection attempt
            io_plugin_connection_status.connect(request.server_url)
            
            # Set the server URL for future reference
            io_plugin_connection_status.io_server_url = request.server_url
            
            # Perform the connection and file download
            result = await fetch_and_load_io_plugin_files(request.server_url)
            
            # Update connection status
            io_plugin_connection_status.record_fetch(
                success=result.get("connection_success", False),
                error=result.get("errors", {}).get("general") or ", ".join(result.get("errors", {}).values()),
                files_fetched=len(result.get("files_downloaded", []))
            )
            
            # Enable io_plugin usage if requested and if connection was successful
            if request.enable_io_plugin and result.get("connection_success", False):
                _use_io_plugin = True
                update_io_plugin_usage()
            
            result["io_plugin_enabled"] = _use_io_plugin
            result["ok"] = result.get("connection_success", False)
            
            if result.get("connection_success", False):
                logger.info(f"IO Plugin connection successful: {request.server_url}")
                result["status"] = "connected"
            else:
                logger.warning(f"IO Plugin connection failed: {result.get('errors', {})}")
                result["status"] = "failed"
            
            return result
            
        except Exception as e:
            error_msg = str(e)
            io_plugin_connection_status.record_fetch(success=False, error=error_msg)
            logger.error(f"IO Plugin connection failed: {error_msg}")
            return {
                "ok": False,
                "connection_success": False,
                "error": error_msg,
                "status": "error"
            }

    @router.post(
        "/io-plugin/disconnect",
        summary="Disconnect from IO Server",
        description="Disconnect from IO server and optionally clear downloaded files and disable io_plugin usage.",
        response_description="Disconnection confirmation",
        responses={
            200: {"description": "Disconnected successfully"},
            500: {"description": "Error during disconnection"}
        },
        tags=["IO Plugin Connection"]
    )
    async def api_io_plugin_disconnect(request: IoClientDisconnectRequest):
        """Disconnect from IO server.
        
        This endpoint will:
        1. Mark connection as disconnected
        2. Optionally clear downloaded files
        3. Optionally disable io_plugin usage
        
        Request Body:
            IoClientDisconnectRequest: {
                "clear_files": bool,         # Clear downloaded files
                "disable_io_plugin": bool   # Disable io_plugin usage
            }
        
        Returns:
            dict: {
                "ok": True/False,
                "disconnected": bool,
                "files_cleared": bool,
                "io_plugin_disabled": bool,
                "message": str
            }
        """
        global _use_io_plugin
        
        try:
            # Record disconnection
            io_plugin_connection_status.disconnect()
            
            # Clear files if requested
            files_cleared = False
            if request.clear_files:
                try:
                    ensure_io_plugin_dir()
                    for filename in io_plugin_REQUIRED_FILES:
                        file_path = get_io_plugin_file_path(filename)
                        if file_path.exists():
                            file_path.unlink()
                    files_cleared = True
                    logger.info("IO Plugin files cleared")
                except Exception as e:
                    logger.error(f"Error clearing IO Plugin files: {e}")
            
            # Disable io_plugin usage if requested
            io_plugin_disabled = False
            if request.disable_io_plugin:
                _use_io_plugin = False
                io_plugin_disabled = True
                logger.info("IO Plugin usage disabled")
            
            return {
                "ok": True,
                "disconnected": True,
                "files_cleared": files_cleared,
                "io_plugin_disabled": io_plugin_disabled,
                "message": "Disconnected from IO server successfully"
            }
            
        except Exception as e:
            logger.error(f"Error during IO Plugin disconnection: {e}")
            return {
                "ok": False,
                "disconnected": False,
                "error": str(e),
                "message": "Failed to disconnect from IO server"
            }

    @router.get(
        "/io-plugin/connection-status",
        summary="Get IO Plugin Connection Status",
        description="Returns the current connection status to the IO server, including connection history and download statistics.",
        response_description="Connection status information",
        responses={
            200: {"description": "Connection status returned successfully"}
        },
        tags=["IO Plugin Connection"]
    )
    async def api_get_io_plugin_connection_status():
        """Get current IO Plugin connection status.
        
        Returns:
            IOPluginConnectionStatusResponse: {
                "connected": bool,
                "io_server_url": str | None,
                "last_connection_time": float | None,
                "last_disconnect_time": float | None,
                "last_fetch_time": float | None,
                "fetch_attempts": int,
                "successful_fetches": int,
                "last_error": str | None,
                "connection_duration": float | None,
                "status": str
            }
        """
        try:
            status = io_plugin_connection_status.get_status()
            return IOPluginConnectionStatusResponse(**status)
        except Exception as e:
            logger.error(f"Error getting IO Plugin connection status: {e}")
            return JSONResponse(
                content={"ok": False, "error": str(e)},
                status_code=500
            )

    @router.post(
        "/io-plugin/check-server",
        summary="Check IO Server Health",
        description="Check if the IO server is healthy and available without connecting.",
        response_description="Server health check result",
        responses={
            200: {"description": "Health check completed successfully"},
            500: {"description": "Error performing health check"}
        },
        tags=["IO Plugin Connection"]
    )
    async def api_check_io_server_health(request: IoClientConnectRequest):
        """Check IO server health.
        
        Request Body:
            IoClientConnectRequest: {
                "server_url": str   # IO server URL to check
            }
        
        Returns:
            dict: {
                "healthy": bool,
                "server_url": str,
                "status": str,
                "service": str,
                "version": str,
                "files_available": bool,
                "files_count": int
            }
        """
        try:
            result = await check_io_server_health(request.server_url)
            return result
        except Exception as e:
            logger.error(f"Error checking IO server health: {e}")
            return {
                "healthy": False,
                "server_url": request.server_url,
                "error": str(e),
                "status": "error"
            }

    return router, rti_fsp

def create_fastapi_app(factory_dir: Optional[Path] = None) -> FastAPI:

    """Create and configure the FastAPI application for ACSI server BFF."""
    app = FastAPI(
        title="ACSI Server WS Active",
        description="Backend for Frontend (BFF) endpoint providing REST API for ACSI Server control. "
                    "This service manages ACSI Server WebSocket Active lifecycle, IED models, data access, "
                    "and provides comprehensive monitoring capabilities.",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        openapi_tags=[
            {
                "name": "Server Control",
                "description": "Start, stop, and manage the ACSI Server WebSocket Active lifecycle"
            },
            {
                "name": "Model",
                "description": "Load, update, and manage IED models"
            },
            {
                "name": "Data Access",
                "description": "Read and write values to/from the IED model"
            },
            {
                "name": "Connections",
                "description": "View and manage active WebSocket connections"
            },
            {
                "name": "Logging",
                "description": "View and clear action and message logs"
            },
            {
                "name": "Health",
                "description": "Service health checks and status monitoring"
            },
            {
                "name": "Discovery",
                "description": "API introspection and endpoint discovery"
            },
            {
                "name": "IO Client",
                "description": "Enable/disable and check IO client sync with physical devices"
            }
        ]
    )

    resolved_factory_dir = os.getenv('MODELPATH') or factory_dir or Path(__file__).parent
    router, _server = create_bff_router(resolved_factory_dir)
    app.include_router(router)
    
    # Include IO router for device control via demo_IO
    # Add CORS middleware to allow requests from frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include IO router for control via dynamic loading only
    try:
        if check_required_io_plugin_files():
            # Load the modules and try to get the create_io_router function
            if load_io_plugin_modules():
                if _io_plugin_module and hasattr(_io_plugin_module, 'create_io_router'):
                    io_router = _io_plugin_module.create_io_router()
                    app.include_router(io_router)
                    logger.info("IO router included from dynamic loading")
            else:
                logger.debug("IO router not available - required files missing for dynamic loading")
                
    except Exception as e:
        logger.error(f"Failed to include IO router from dynamic loading: {e}")
       
    
    app.state.server = _server
    return app

if __name__ == "__main__":
    import argparse
    import uvicorn

    _LOG_CHOICES = ["critical", "error", "warning", "info", "debug", "trace"]

    parser = argparse.ArgumentParser(description="RTI Demo FSP (ACSI server) BFF endpoint")
    parser.add_argument(
        "--host",
        default=os.getenv("HOST", "0.0.0.0"),
        help="Host interface to bind (default: %(default)s, env: HOST)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", "5001")),
        help="Port to listen on (default: %(default)s, env: PORT)",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL", "info"),
        help="Log level: %s (default: %%(default)s, env: LOG_LEVEL)" % ", ".join(_LOG_CHOICES),
    )
    args = parser.parse_args()

    # Module scope already applied LOG_LEVEL from the environment at import
    # (covers the app + ws61850 + acsi_server loggers). Re-resolve here so an
    # explicit --log-level on the command line wins, and hand the same value to
    # uvicorn so its own 'uvicorn'/'uvicorn.error'/'uvicorn.access' loggers
    # follow suit.
    resolved = resolve_log_level(args.log_level)
    logging.getLogger().setLevel(resolved)
    uvicorn_log_level = args.log_level.lower()
    if uvicorn_log_level not in _LOG_CHOICES:
        uvicorn_log_level = logging.getLevelName(resolved).lower()

    logger.info(
        "Starting RTI Demo FSP BFF on %s:%d (log level %s)",
        args.host, args.port, logging.getLevelName(resolved),
    )

    factory_dir = Path(__file__).parent
    app = create_fastapi_app(factory_dir)
    uvicorn.run(app, host=args.host, port=args.port, log_level=uvicorn_log_level)
