"""Backend for Frontend (BFF) endpoint providing REST API for ACSI client control.

This module exposes FastAPI endpoints that interact with the ACSI client,
handling connection management and value operations.
"""

from __future__ import annotations

import importlib
import logging
import os
import sys
import traceback
import asyncio
from concurrent.futures import TimeoutError as FuturesTimeoutError
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict

from acsi_client import ACSIClient

from ws61850.security.tls import TLSConfig
import ssl
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
# so/bff_endpoint.py`, `uvicorn so.bff_endpoint:app`, a service wrapper, or
# pytest importing create_fastapi_app. Child loggers (acsi_client, ws61850.*)
# and the ACSI client's background event-loop thread inherit this level.
logging.getLogger().setLevel(LOG_LEVEL)

logger = logging.getLogger(__name__)


class HealthCheckAccessFilter(logging.Filter):
    """Demote uvicorn access-log lines for health/status polls to DEBUG.

    The Docker healthcheck hits ``/api/status`` (and service discovery hits
    ``/api/health``) every few seconds; logged at INFO they bury the real
    request log. Matching records are relabelled DEBUG and only pass through
    when the ``uvicorn.access`` logger is actually at DEBUG.
    """

    QUIET_PATHS = ("/api/status", "/api/health")

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        # uvicorn access records: (client_addr, method, path, http_version, status)
        if not isinstance(args, tuple) or len(args) < 3:
            return True
        path = str(args[2]).split("?", 1)[0]
        if path not in self.QUIET_PATHS:
            return True
        record.levelno = logging.DEBUG
        record.levelname = "DEBUG"
        return logging.getLogger("uvicorn.access").isEnabledFor(logging.DEBUG)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # Installed here (not before uvicorn.run) so it survives uvicorn's own
    # logging dictConfig, which runs before app startup.
    logging.getLogger("uvicorn.access").addFilter(HealthCheckAccessFilter())
    yield


# Global flag to control io_client usage for writevalue sync
_use_io_client = True

# ==================== Dynamic IO Plugin Loading (ported from FSP) ====================

# Directory for dynamically loaded io_plugin files.
# Configurable via IO_PLUGIN_STORAGE environment variable.
# Default: /app/io_plugin_dynamic (good for Docker volumes)
IO_PLUGIN_STORAGE = os.getenv("IO_PLUGIN_STORAGE", "/app/io_plugin_dynamic")
io_plugin_dynamic_DIR = Path(IO_PLUGIN_STORAGE)

# Global reference to loaded io_plugin modules
_io_plugin_module = None
_mapping_manager_module = None
_io_utils_module = None

# Reference to the running FastAPI app instance, captured in
# create_fastapi_app(). Lets us register the IO router AFTER startup -
# e.g. right after a successful /api/io-plugin/connect call - without
# needing a process restart. FastAPI/Starlette supports adding routers
# at any time (it's just appending routes); it does not support removing
# them, so _io_router_included is a one-way latch.
_fastapi_app_ref: Optional["FastAPI"] = None
_io_router_included = False


def _try_include_io_router() -> bool:
    """Register the dynamically-loaded IO router on the running app, if not already done.

    Safe to call repeatedly - only registers once. This is what lets the
    IO control endpoints (LEDs, mappings, etc.) appear right after
    /api/io-plugin/connect or /api/io-plugin/reload succeed, with no
    process restart needed.
    """
    global _io_router_included
    if _io_router_included:
        return True
    if _fastapi_app_ref is None:
        logger.warning("Cannot include IO router - app reference not set yet")
        return False
    if _io_plugin_module is None or not hasattr(_io_plugin_module, 'create_io_router'):
        return False
    try:
        io_router = _io_plugin_module.create_io_router()
        _fastapi_app_ref.include_router(io_router)
        _io_router_included = True
        logger.info("IO router included dynamically")
        return True
    except Exception as e:
        logger.error(f"Failed to dynamically include IO router: {e}")
        return False


async def _bootstrap_io_client_after_connect(demo_io_server_url: str) -> Dict[str, Any]:
    """Chain the demo_IO device-proxy bootstrap sequence right after a
    successful /api/io-plugin/connect (files downloaded, modules loaded,
    IO router registered via _try_include_io_router()).

    Calls, in order:
        1. POST /api/io/connect               - point the IO router's proxy
           client at the demo_IO device service (the same host that just
           served the io-plugin files)
        2. POST /api/io/acsi/sync-to-server    - push current IEC61850
           mappings to that device service
        3. POST /api/io/acsi/enable-server-sync - enable it to write input
           device changes back to ACSI

    These three handlers are defined as private closures inside
    io_router.py's create_io_router() - they are wired to FastAPI via
    decorators but never exposed as importable module-level functions, so
    _io_plugin_module.api_connect_io(...) etc. do not exist to call
    directly. Going over loopback HTTP to our own just-registered routes
    reuses their existing logic/validation exactly as an external client
    would trigger it, without needing to modify io_router.py.

    Best-effort: any failure here is logged and reported in the returned
    dict, but never raised - a bootstrap hiccup should not turn an
    otherwise-successful /io-plugin/connect into a failure response.
    """
    self_port = os.getenv("PORT", "5003")
    base = f"http://127.0.0.1:{self_port}"
    steps: Dict[str, Any] = {}

    async def _call(step_name: str, method: str, path: str, **kwargs):
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.request(method, f"{base}{path}", **kwargs)
            try:
                body = resp.json()
            except Exception:
                body = resp.text
            steps[step_name] = {
                "ok": resp.status_code < 400,
                "status_code": resp.status_code,
                "body": body,
            }
            if resp.status_code >= 400:
                logger.warning(f"IO bootstrap step '{step_name}' returned HTTP {resp.status_code}: {body}")
        except Exception as e:
            logger.error(f"IO bootstrap step '{step_name}' failed: {e}")
            steps[step_name] = {"ok": False, "error": str(e)}

    # Explicitly pass the ACSI base URL rather than relying on io_router.py's
    # own fallback chain (request body -> ACSI_BASE_URL env var -> LAN-IP
    # auto-detect). That auto-detect runs socket.gethostname() INSIDE this
    # container, so it resolves to the Docker-bridge IP - unreachable from
    # a physical device like the demo_io Pi on the real LAN. Setting
    # ACSI_BASE_URL in this container's environment (e.g.
    # http://<host-LAN-IP>:5003) and passing it here explicitly avoids that
    # trap entirely.
    acsi_base_url = os.getenv("ACSI_BASE_URL")
    connect_body: Dict[str, Any] = {"base_url": demo_io_server_url}
    if acsi_base_url:
        connect_body["acsi_url"] = acsi_base_url
    else:
        logger.warning(
            "ACSI_BASE_URL is not set - /api/io/connect will fall back to "
            "io_router.py's auto-detected address, which is unreliable inside Docker."
        )

    await _call("io_connect", "POST", "/api/io/connect", json=connect_body)
    await _call("sync_to_server", "POST", "/api/io/acsi/sync-to-server")
    await _call("enable_server_sync", "POST", "/api/io/acsi/enable-server-sync")

    return steps


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

# Default files to fetch from IO server.
# NOTE: async_client_io.py is required because io_router.py imports
# AsyncDemoIOClient from it - without it, module loading fails with
# "No module named 'async_client_io'".
io_plugin_REQUIRED_FILES = [
    "io_router.py",
    "io_utils.py",
    "mapping_manager.py",
    "__init__.py",
    "async_client_io.py",
]


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
        "async_client_io.py",
    ]

    for file in required_files:
        file_path = get_io_plugin_file_path(file)
        if not file_path.exists():
            logger.debug(f"Required io_plugin file not found: {file_path}")
            return False

    return True


def _rebuild_pydantic_models(module) -> None:
    """Force-build any deferred Pydantic model schemas defined in a dynamically loaded module.

    Pydantic v2 sometimes defers a model's schema build until first use
    (e.g. when it can't immediately resolve every referenced type). That
    deferred build later resolves forward references via
    sys.modules[<model's __module__>].__dict__ - which only works if the
    module was registered in sys.modules (see load_io_plugin_modules).
    Calling model_rebuild() here forces the build to happen immediately,
    so a broken model fails loudly at connect/reload time instead of
    silently corrupting the next /openapi.json request.
    """
    try:
        from pydantic import BaseModel
    except ImportError:
        return

    for name, obj in vars(module).items():
        try:
            if isinstance(obj, type) and issubclass(obj, BaseModel) and obj is not BaseModel:
                obj.model_rebuild(force=True, _types_namespace=vars(module))
        except Exception as e:
            logger.warning(f"Could not rebuild Pydantic model '{name}' from {module.__name__}: {e}")


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

        # Load async_client_io module FIRST - io_router.py depends on it
        # (imports AsyncDemoIOClient from it). Registering it in sys.modules
        # lets io_router.py's own `import async_client_io` resolve.
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
        # IMPORTANT: register in sys.modules under its own name BEFORE
        # exec_module. Pydantic v2 may defer building a model's schema
        # (e.g. IOConnectionConfig) until first use, and when it does,
        # it resolves forward references via sys.modules[<module>].__dict__.
        # Without this registration, that lookup fails and FastAPI's
        # /openapi.json generation crashes with "is not fully defined".
        io_router_path = get_io_plugin_file_path("io_router.py")
        spec = importlib.util.spec_from_file_location("io_router", io_router_path)
        if spec and spec.loader:
            _io_plugin_module = importlib.util.module_from_spec(spec)
            sys.modules["io_router"] = _io_plugin_module
            spec.loader.exec_module(_io_plugin_module)
            # Force any deferred Pydantic model schemas in this module to
            # build now, while we can still report a clean load failure
            # here, rather than deferring the crash to whenever
            # /openapi.json happens to be requested next.
            _rebuild_pydantic_models(_io_plugin_module)
            logger.info(f"Successfully loaded io_router from {io_router_path}")
        else:
            logger.error(f"Failed to load io_router from {io_router_path}")
            return False

        # Load io_utils module
        io_utils_path = get_io_plugin_file_path("io_utils.py")
        spec = importlib.util.spec_from_file_location("io_utils", io_utils_path)
        if spec and spec.loader:
            _io_utils_module = importlib.util.module_from_spec(spec)
            sys.modules["io_utils"] = _io_utils_module
            spec.loader.exec_module(_io_utils_module)
            _rebuild_pydantic_models(_io_utils_module)
            logger.info(f"Successfully loaded io_utils from {io_utils_path}")
        else:
            logger.error(f"Failed to load io_utils from {io_utils_path}")
            return False

        # Load mapping_manager module
        mapping_manager_path = get_io_plugin_file_path("mapping_manager.py")
        spec = importlib.util.spec_from_file_location("mapping_manager", mapping_manager_path)
        if spec and spec.loader:
            _mapping_manager_module = importlib.util.module_from_spec(spec)
            sys.modules["mapping_manager"] = _mapping_manager_module
            spec.loader.exec_module(_mapping_manager_module)
            _rebuild_pydantic_models(_mapping_manager_module)
            logger.info(f"Successfully loaded mapping_manager from {mapping_manager_path}")
        else:
            logger.error(f"Failed to load mapping_manager from {mapping_manager_path}")
            return False

        return True

    except Exception as e:
        logger.error(f"Failed to load io_plugin modules: {e}")
        return False


def get_io_plugin_dynamic():
    """Get the io_client instance from dynamically loaded modules.

    NOTE: the loaded io_router.py module exposes this as get_io_client()
    (see io_router.py's `def get_io_client()`), not get_io_plugin() - the
    function name here is just this wrapper's own name.
    """
    if _io_plugin_module is None:
        if not load_io_plugin_modules():
            return None

    try:
        return _io_plugin_module.get_io_client()
    except AttributeError:
        logger.error("io_router module doesn't have get_io_client function")
        return None


def get_mapping_manager_dynamic():
    """Get the mapping_manager instance from dynamically loaded modules.

    NOTE: get_mapping_manager() lives on the loaded io_router module (it
    wraps IOMappingManager()), not on the mapping_manager module itself.
    """
    if _io_plugin_module is None:
        if not load_io_plugin_modules():
            return None

    try:
        return _io_plugin_module.get_mapping_manager()
    except AttributeError:
        logger.error("io_router module doesn't have get_mapping_manager function")
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
    """Update the _use_io_client flag based on file availability."""
    global _use_io_client
    _use_io_client = check_required_io_plugin_files() and load_io_plugin_modules()
    logger.info(f"IO client usage updated to: {_use_io_client}")


def clear_io_plugin_modules():
    """Clear all loaded io_plugin modules."""
    global _io_plugin_module, _mapping_manager_module, _io_utils_module
    _io_plugin_module = None
    _mapping_manager_module = None
    _io_utils_module = None
    # Remove dynamic directory from sys.path
    if str(io_plugin_dynamic_DIR) in sys.path:
        sys.path.remove(str(io_plugin_dynamic_DIR))
    # Remove all dynamically-registered modules from sys.modules so a
    # subsequent reload picks up freshly-downloaded copies instead of
    # stale cached modules (and stale Pydantic model classes/schemas).
    for _mod_name in ("async_client_io", "io_router", "io_utils", "mapping_manager"):
        if _mod_name in sys.modules:
            del sys.modules[_mod_name]


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
            results["modules_loaded"] = ["async_client_io", "io_router", "io_utils", "mapping_manager"]
            results["use_io_client_enabled"] = _use_io_client
        else:
            results["errors"]["load"] = "Failed to load modules"

        results["connection_success"] = True

        return results

    except Exception as e:
        logger.error(f"Error in fetch_and_load_io_plugin_files: {e}")
        results["errors"]["general"] = str(e)
        return results


# ==================== Pydantic Models ====================
class ConnectRequest(BaseModel):
    """Request body for connecting to an IEC61850 WebSocket server.

    Used by: POST /api/connect
    """
    host: str = Field(
        default="localhost",
        description="Server hostname or IP address to connect to",
        json_schema_extra={"example": "localhost"}
    )
    port: int = Field(
        default=8765,
        description="Server port number (1-65535)",
        ge=1,
        le=65535,
        json_schema_extra={"example": 8765}
    )

class ModelRequest(BaseModel):
    """Request body for connecting to an IEC61850 WebSocket server.

    Used by: POST /api/model
    """
    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"}
    )

    refresh: bool = Field(
        default=False,
        description="Force a fresh model rebuild instead of returning cached data",
        json_schema_extra={"example": False}
    )

class ServerDirectoryRequest(BaseModel):
    """Request body for getting server directory.

    Used by: POST /api/server-directory
    """
    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"}
    )

class LogicalDeviceRequest(BaseModel):
    """Request body for getting logical device directory.

    Used by: POST /api/logical-device
    """
    ld_inst: str = Field(
        ...,
        description="Logical Device instance name (e.g., 'LD0')",
        json_schema_extra={"example": "LD0"}
    )
    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"}
    )

class LogicalNodeRequest(BaseModel):
    """Request body for getting logical node tree.

    Used by: POST /api/logical-node
    """
    ld_inst: str = Field(
        ...,
        description="Logical Device instance name (e.g., 'LD0')",
        json_schema_extra={"example": "LD0"}
    )
    ln_inst: str = Field(
        ...,
        description="Logical Node instance name (e.g., 'LLN0')",
        json_schema_extra={"example": "LLN0"}
    )
    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"}
    )

class DataObjectRequest(BaseModel):
    """Request body for getting data object details.

    Used by: POST /api/data-object
    """
    ld_inst: str = Field(
        ...,
        description="Logical Device instance name (e.g., 'LD0')",
        json_schema_extra={"example": "LD0"}
    )
    ln_inst: str = Field(
        ...,
        description="Logical Node instance name (e.g., 'LLN0')",
        json_schema_extra={"example": "LLN0"}
    )
    do_name: str = Field(
        ...,
        description="Data Object name (e.g., 'Mod')",
        json_schema_extra={"example": "Mod"}
    )
    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"}
    )

class ReadvalueRequest(BaseModel):
    """Request body for reading a value from the connected server.

    Used by: POST /api/readvalue
    """
    objRef: str = Field(
        ...,
        description="Object reference in IEC61850 format (e.g., 'LD0/LLN0$ST$Mod')",
        json_schema_extra={"example": "LD0/LLN0$ST$Mod"}
    )
    fc: str = Field(
        default=None,
        description="Functional constraint (ST, MX, CO, etc.) - optional",
        json_schema_extra={"example": "ST"}
    )

    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"}
    )

class ReadRCBValueRequest(BaseModel):
    """Request body for reading a value from the connected server.

    Used by: POST /api/readvalue
    """
    objRef: str = Field(
        ...,
        description="Object reference in IEC61850 format (e.g., 'LD0/LLN0$ST$Mod')",
        json_schema_extra={"example": "LD0/LLN0$ST$Mod"}
    )

    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"}
    )

class WriteRCBValueRequest(BaseModel):
    """Request body for reading a value from the connected server.

    Used by: POST /api/readvalue
    """
    objRef: str = Field(
        ...,
        description="Object reference in IEC61850 format (e.g., 'LD0/LLN0$ST$Mod')",
        json_schema_extra={"example": "LD0/LLN0$ST$Mod"}
    )

    data: Any = Field(
        ...,
        description="Data to write (will be converted to appropriate type)",
    )

    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"}
    )

class GetDataDefinitionRequest(BaseModel):
    """Request body for reading a value from the connected server.

    Used by: POST /api/readvalue
    """
    ld_inst: str = Field(
        ...,
        description="LD name (e.g., 'LD0')",
        json_schema_extra={"example": "LD0"}
    )
    ln_inst: Optional[str] = Field(
        ...,
        description="LN name (e.g., 'LLN0')",
        json_schema_extra={"example": "LLN0"}
    )
    do_path: Optional[str] = Field(
        ...,
        description="Data Object path (e.g., 'Mod')",
        json_schema_extra={"example": "Mod"}
    )

    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"}
    )

class GetDataSetDirectory(BaseModel):
    """Request body for reading a value from the connected server.

    Used by: POST /api/readvalue
    """
    ld_inst: str = Field(
        ...,
        description="LD name (e.g., 'LD0')",
        json_schema_extra={"example": "LD0"}
    )
    ln_inst: str = Field(
        ...,
        description="LN name (e.g., 'LLN0')",
        json_schema_extra={"example": "LLN0"}
    )
    ds_inst: str = Field(
        ...,
        description="DataSet name (e.g., 'Event1')",
        json_schema_extra={"example": "Event1"}
    )

    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"}
    )


class OperateRequest(BaseModel):
    """Request body for writing a value to the connected server.

    Used by: POST /api/operate
    """
    objRef: str = Field(
        ...,
        description="Controllable DO Object reference in IEC61850 format",
        json_schema_extra={"example": "LD0/MMXU.WMaxSpt"}
    )
    value: Any = Field(
        ...,
        description="Value to write (will be converted to appropriate type)",
        json_schema_extra={"example": "12.4"}
    )
    value_type: Any = Field(
        ...,
        description="Value type hint for coercion (BOOLEAN, INT32, FLOAT32, etc.)",
        json_schema_extra={"example": "float32"}
    )

    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"}
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "objRef": "LD0/MMXU.WMaxSpt",
            "value": "2.11",
            "value_type": "float32",
            "cp": "cp1",
        }
    })


class IoClientConfigRequest(BaseModel):
    """Request body for enabling/disabling io_client usage for writevalue sync."""
    enabled: bool = Field(
        ...,
        description="Whether to enable io_client for device sync in writevalue",
        json_schema_extra={"example": True}
    )

class TLSConnectionCreateConfigRequest(BaseModel):
    """Request body for creating a new connection."""
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
    connection_name: Optional[str] = Field(default=None, description="Connection name (optional, auto-detected)", json_schema_extra={"example": "RTI-SO-01"})
    enable_oauth: bool = Field(default=False, description="Enable OAuth authentication", json_schema_extra={"example": False})
    ws_mode: str = Field(default="passive", description="WebSocket mode (passive or active)", json_schema_extra={"example": "passive"})
    # OAuth settings for SO (passive mode)
    certificate_endpoint_url: Optional[str] = Field(default=None, description="OAuth Certificate endpoint URL", json_schema_extra={"example": "https://auth.example.com/certs"})
    token_issuer_url: Optional[str] = Field(default=None, description="token issuer url", json_schema_extra={"example": "https://auth.example.com"})
    ca_certificate: Optional[str] = Field(default=None, description="Server CA certificate", json_schema_extra={"example": "-----BEGIN CERTIFICATE-----..."})


class WriteValueRequest(BaseModel):
    """Request body for writing a value to the connected server.

    Used by: POST /api/writevalue
    """
    objRef: str = Field(
        ...,
        description="Object reference in IEC61850 format",
        json_schema_extra={"example": "LD0/LLN0$ST$Mod"}
    )
    fc: str = Field(
        ...,
        description="Functional constraint (ST, MX, CO, etc.)",
        json_schema_extra={"example": "ST"}
    )
    value: Any = Field(
        ...,
        description="Value to write (will be converted to appropriate type)",
        json_schema_extra={"example": "ON"}
    )
    dataType: Optional[str] = Field(
        default=None,
        description="Optional value type hint for coercion",
        json_schema_extra={"example": "BOOLEAN"}
    )

    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"}
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "objRef": "LD0/LLN0$ST$Mod",
            "fc": "ST",
            "value": "ON",
            "value_type": "BOOLEAN",
            "cp": "cp1"
        }
    })


# ==================== IO Plugin Connection Models (ported from FSP) ====================

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
        json_schema_extra={"example": ["io_router.py", "io_utils.py", "mapping_manager.py", "__init__.py", "async_client_io.py"]}
    )
    timeout: float = Field(
        default=10.0,
        description="Timeout in seconds for file downloads",
        json_schema_extra={"example": 10.0}
    )
    enable_io_plugin: bool = Field(
        default=True,
        description="Whether to enable io_client usage after successful connection",
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
        description="Whether to disable io_client usage after disconnection",
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


def create_fastapi_app(factory_dir: Optional[Path] = None) -> FastAPI:
    """Create and configure the FastAPI application for Acsi-Client BFF."""
    global _fastapi_app_ref
    app = FastAPI(
        lifespan=_lifespan,
        title="ACSI Client WS Passive",
        description="Backend for Frontend (BFF) endpoint providing REST API for ACSI client control. "
                    "This service manages IEC61850 WebSocket client connections, data access, "
                    "model retrieval, and provides comprehensive monitoring capabilities.",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        openapi_tags=[
            {"name": "Client Status", "description": "Get client status, connections, and properties"},
            {"name": "Connection Management", "description": "Connect to and disconnect from Acsi-Servers"},
            {"name": "Model Access", "description": "Retrieve and explore IED models from connected servers"},
            {"name": "Data Access", "description": "Read and write values to/from connected servers"},
            {"name": "Logging", "description": "View and clear action and message logs"},
            {"name": "Health", "description": "Service health checks and status monitoring"},
            {"name": "Discovery", "description": "API introspection and endpoint discovery"},
            {"name": "Diagnostics", "description": "Internal diagnostic endpoints"},
            {"name": "IO Client", "description": "Enable/disable and check IO client sync with physical devices"},
            {"name": "IO Plugin Connection", "description": "On-demand connect/disconnect to the IO server for dynamic IO module loading"},
        ]
    )

    resolved_factory_dir = os.getenv('MODELPATH') or factory_dir or Path(__file__).parent
    router, _client = create_bff_router(resolved_factory_dir)
    app.include_router(router)
    app.state.client = _client

    # Capture the app reference so the IO router can be registered later
    # (e.g. right after /api/io-plugin/connect succeeds), without needing
    # a process restart.
    _fastapi_app_ref = app

    # Initialize dynamic io_plugin loading system (mirrors FSP behaviour:
    # if files already exist under IO_PLUGIN_STORAGE from a previous run,
    # try to load them at startup; otherwise stays disabled until
    # /api/io-plugin/connect is called).
    ensure_io_plugin_dir()
    update_io_plugin_usage()

    # Include IO router for device control via dynamic loading only.
    # If the files aren't present yet at startup, this is a no-op - the
    # router gets registered later, on-demand, by _try_include_io_router()
    # once /api/io-plugin/connect or /api/io-plugin/reload succeed.
    try:
        if check_required_io_plugin_files():
            if load_io_plugin_modules():
                update_io_plugin_usage()
                _try_include_io_router()
            else:
                logger.debug("IO router not available - failed to load dynamic modules")
        else:
            logger.debug("IO router not available - required files missing for dynamic loading")
    except Exception as e:
        logger.error(f"Failed to include IO router from dynamic loading: {e}")

    # Add CORS middleware to allow requests from frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return app

def create_bff_router(app: FastAPI) -> tuple[APIRouter, ACSIClient]:
    """Create a FastAPI router for the ACSI client BFF API.

    Returns:
        Tuple of (APIRouter, ACSIClient instance)
    """
    router = APIRouter(
        prefix="/api",
        tags=["acsi-client"],
        responses={404: {"description": "Not found"}, 500: {"description": "Internal server error"}}
    )
    rti_so = ACSIClient()

    def on_write_callback(obj_ref, value, fc, data_type, result):
        logger.info(f"[WRITE] {obj_ref}={value} fc={fc} type={data_type} result={result}")
        # Sync with mapped device if io_client is enabled (fire-and-forget)
        if _use_io_client and result:
            try:
                io_client = get_io_plugin_dynamic()
                sync_to_io_device = get_sync_to_io_device_dynamic()

                if io_client is None or sync_to_io_device is None:
                    logger.warning("Dynamic io_plugin loading failed, falling back to disabled state")
                    return
                logger.info(f"IO client for sync: {io_client}")
                if io_client:
                    # This callback runs on an AnyIO worker thread (it's a
                    # plain sync def, not async), not on the asyncio event
                    # loop itself - asyncio.create_task() would raise
                    # "no running event loop" here. Schedule onto the
                    # actual runtime event loop instead.
                    loop = rti_so.runtime.loop
                    if loop is None or not loop.is_running():
                        logger.warning("Cannot schedule IO sync - runtime loop not available")
                        return
                    asyncio.run_coroutine_threadsafe(
                        sync_to_io_device(io_client, obj_ref, value), loop
                    )
                else:
                    logger.warning("IO client is None - cannot sync to device. Call /api/io-plugin/connect first.")
            except ImportError as e:
                logger.error(f"ImportError - Cannot import IO client: {e}")
            except Exception as e:
                logger.error(f"Exception in IO sync setup: {e}")


    rti_so.install_write_callback(on_write_callback)

    def on_report_callback(rptID, dataSet, data):
        """Callback for received report messages."""
        logger.info(f"[REPORT] rptID={rptID} dataSet={dataSet} dataCount={len(data)}")
        for item in data:
            logger.info(f"  {item.get('dataRef')} = {item.get('value')}")

        if _use_io_client:
            try:
                io_client = get_io_plugin_dynamic()
                mapping_manager = get_mapping_manager_dynamic()
                blink_led_task = get_blink_led_task_dynamic()
                write_to_lcd = get_write_to_lcd_dynamic()

                if io_client is None or mapping_manager is None or blink_led_task is None or write_to_lcd is None:
                    logger.warning("Dynamic io_plugin loading failed, falling back to disabled state")
                    return
                logger.info(f"IO client for sync: {io_client}")
                if io_client:
                    # Runs on an AnyIO worker thread - see on_write_callback
                    # for why asyncio.create_task() would fail here.
                    loop = rti_so.runtime.loop
                    if loop is None or not loop.is_running():
                        logger.warning("Cannot schedule IO sync - runtime loop not available")
                        return

                    asyncio.run_coroutine_threadsafe(
                        blink_led_task(io_client, "rc_rcv", interval=0.2, count=1, mapping_manager=mapping_manager), loop
                    )

                    value = f"rptID={rptID} dataSet={dataSet}"

                    asyncio.run_coroutine_threadsafe(
                        write_to_lcd(io_client, "rc_rcv", value, mapping_manager=mapping_manager), loop
                    )

                else:
                    logger.warning("IO client is None - cannot sync to device. Call /api/io-plugin/connect first.")
            except ImportError as e:
                logger.error(f"ImportError - Cannot import IO client: {e}")
            except Exception as e:
                logger.error(f"Exception in IO sync setup: {e}")


    rti_so.install_report_callback(on_report_callback)

    def on_connected_callback(associate_response):
        """Callback for received associateResponse messages."""
        logger.info(f"[CONNECTED] associateResponse: {associate_response}")
        # A build that failed or hung while disconnected can leave model_status
        # stuck at 'error' (or 'building'). Clear it here so the next fetch
        # after reconnect rebuilds against the live connection instead of
        # immediately returning a stale pre-reconnect error.
        cp = associate_response.get("associateId")
        if cp:
            model_info = rti_so.get_model_info(cp)
            with rti_so.runtime.lock:
                if model_info.model_status in ('error', 'building'):
                    model_info.model_status = 'idle'
                    model_info.model_data = None
                    model_info.model_error = None
                    model_info.model_ready_event.clear()

        if _use_io_client:
            try:
                io_client = get_io_plugin_dynamic()
                mapping_manager = get_mapping_manager_dynamic()
                blink_led_task = get_blink_led_task_dynamic()
                write_to_lcd = get_write_to_lcd_dynamic()

                if io_client is None or mapping_manager is None or blink_led_task is None or write_to_lcd is None:
                    logger.warning("Dynamic io_plugin loading failed, falling back to disabled state")
                    return
                logger.info(f"IO client for connected: {io_client}")
                if io_client:
                    # Runs on an AnyIO worker thread - see on_write_callback
                    # for why asyncio.create_task() would fail here.
                    loop = rti_so.runtime.loop
                    if loop is None or not loop.is_running():
                        logger.warning("Cannot schedule IO sync - runtime loop not available")
                        return

                    # Use associateId as identifier, or a default
                    associate_id = associate_response.get("associateId", "connected")
                    # Blink LED to indicate connection
                    asyncio.run_coroutine_threadsafe(
                        blink_led_task(io_client, "connected", interval=0.5, count=2, mapping_manager=mapping_manager), loop
                    )

                    # Write connection info to LCD
                    value = f"Connected: {associate_id}"
                    asyncio.run_coroutine_threadsafe(
                        write_to_lcd(io_client, "connected", value, mapping_manager=mapping_manager), loop
                    )
                else:
                    logger.warning("IO client is None - cannot turn on LED. Call /api/io-plugin/connect first.")
            except ImportError as e:
                logger.error(f"ImportError - Cannot import IO client: {e}")
            except Exception as e:
                logger.error(f"Exception in IO connected callback: {e}")

    rti_so.install_connected_callback(on_connected_callback)

    # ==================== Helper Functions ====================

    def _check_websocket_connection():
        """Verify that an active WebSocket connection exists.

        Raises:
            HTTPException 503: If no WebSocket connection is established
        """
        endpoint = rti_so.runtime.endpoint
        if endpoint is None or len(endpoint.websocket_info_list) == 0:
            raise HTTPException(status_code=503, detail="no-active-websocket-connection")

    def _convert_bytes_to_hex(obj: Any) -> Any:
        """Recursively convert bytes objects to hex strings for JSON serialization."""
        if isinstance(obj, bytes):
            return obj.hex()
        elif isinstance(obj, dict):
            return {k: _convert_bytes_to_hex(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [_convert_bytes_to_hex(item) for item in obj]
        elif isinstance(obj, tuple):
            return tuple(_convert_bytes_to_hex(item) for item in obj)
        else:
            return obj

    async def _aget_ln_details(ld_inst: str, ln_inst: str, acsi_client: Any, ws_info) -> Dict[str, Any]:
        """Async variant used internally for concurrent model assembly."""
        async def _safe(coro):
            try:
                return await coro
            except Exception:
                return None

        do_items =  await _invoke_ln_directory_async(acsi_client, ws_info, ld_inst, ln_inst, 'dataObject')
        brcb_items =  await _invoke_ln_directory_async(acsi_client, ws_info, ld_inst, ln_inst, 'brcb')
        urcb_items =  await _invoke_ln_directory_async(acsi_client, ws_info, ld_inst, ln_inst, 'urcb')
        dataset_items =  await _invoke_ln_directory_async(acsi_client, ws_info, ld_inst, ln_inst, 'dataset')

        data_objects = []
        data_attributes = []

        do_list = []
        if isinstance(do_items, dict):
            do_list = do_items.get('dataObjects', do_items.get('instanceNames', [])) or []
            data_attributes = do_items.get('dataAttributes', []) or []
        elif isinstance(do_items, list):
            do_list = do_items
        if do_list:
            lock = rti_so.runtime.invoke_lock
            for do_name in do_list:
                defn = None
                try:
                    obj_ref = f"{ld_inst}/{ln_inst}.{do_name}"
                    if lock is None:
                        defn = await acsi_client.get_data_definition(obj_ref, ws_info, None, None)
                    else:
                        async with lock:
                            defn = await acsi_client.get_data_definition(obj_ref, ws_info, None, None)

                    cdc = None
                    if isinstance(defn, dict):
                        cdc = defn.get('cdc')
                    data_objects.append({'name': do_name, 'cdc': cdc})
                except Exception:
                    data_objects.append({'name': do_name, 'cdc': None})

        def _extract_rcb(entries, kind):
            out = []
            if isinstance(entries, list):
                out = entries
            elif isinstance(entries, dict):
                out = entries.get('instanceNames') or entries.get('reportControlBlocks') or []
            return [{'name': ref, 'type': kind} for ref in out]

        rcbs = []
        lock = rti_so.runtime.invoke_lock

        brcb_list = _extract_rcb(brcb_items, 'BRCB')
        for rcb_info in brcb_list:
            rcb_name = rcb_info['name']
            rcb_ref = f"{ld_inst}/{ln_inst}.{rcb_name}"
            rcb_values = None
            try:
                if lock is None:
                    rcb_values = await acsi_client.get_BRCB_values(rcb_ref, ws_info, None, None)
                else:
                    async with lock:
                        rcb_values = await acsi_client.get_BRCB_values(rcb_ref, ws_info, None, None)
                rpt_ena = False
                if isinstance(rcb_values, dict):
                    rpt_ena = rcb_values.get('RptEna', False)
                    rcb_values = _convert_bytes_to_hex(rcb_values)
                rcbs.append({'name': rcb_name, 'type': 'BRCB', 'values': rcb_values, 'enabled': rpt_ena})
            except Exception:
                rcbs.append({'name': rcb_name, 'type': 'BRCB', 'values': None, 'enabled': False})

        urcb_list = _extract_rcb(urcb_items, 'URCB')
        for rcb_info in urcb_list:
            rcb_name = rcb_info['name']
            rcb_ref = f"{ld_inst}/{ln_inst}.{rcb_name}"
            rcb_values = None
            try:
                if lock is None:
                    rcb_values = await acsi_client.get_URCB_values(rcb_ref, ws_info, None, None)
                else:
                    async with lock:
                        rcb_values = await acsi_client.get_URCB_values(rcb_ref, ws_info, None, None)
                rpt_ena = False
                if isinstance(rcb_values, dict):
                    rpt_ena = rcb_values.get('RptEna', False)
                    rcb_values = _convert_bytes_to_hex(rcb_values)
                rcbs.append({'name': rcb_name, 'type': 'URCB', 'values': rcb_values, 'enabled': rpt_ena})
            except Exception:
                rcbs.append({'name': rcb_name, 'type': 'URCB', 'values': None, 'enabled': False})

        datasets = []
        if isinstance(dataset_items, list):
            datasets = dataset_items
        elif isinstance(dataset_items, dict):
            datasets = dataset_items.get('instanceNames') or dataset_items.get('dataSets') or []

        return {
            'dataObjects': data_objects,
            'dataAttributes': data_attributes,
            'reportControlBlocks': rcbs,
            'dataSets': datasets,
        }

    def _invoke_ln_directory(acsi_client, ws_info, ld_inst, ln_inst, mode):
        """Return coroutine that performs directory call under a lock."""
        async def _coro():
            lock = rti_so.runtime.invoke_lock
            if lock is None:
                items = await acsi_client.get_logical_node_directory(ld_inst, ln_inst, mode, ws_info, None, None)
                return items
            async with lock:
                items = await acsi_client.get_logical_node_directory(ld_inst, ln_inst, mode, ws_info, None, None)
                return items
        return _coro()

    async def _invoke_ln_directory_async(acsi_client, ws_info, ld_inst, ln_inst, mode):
        return await _invoke_ln_directory(acsi_client, ws_info, ld_inst, ln_inst, mode)

    # ================ Background Model Build ================
    async def _abuild_full_model(cp) -> None:
        """Build full model with PARALLEL websocket calls for better performance."""
        endpoint = rti_so.runtime.endpoint
        loop = rti_so.runtime.loop
        acsi_client = rti_so.get_iec61850_client(cp)

        if acsi_client is None:
            raise HTTPException(status_code=404, detail=f"Client with cp={cp} not found")
        else:
            logger.info("client found with cp: ", cp)

        if not rti_so or not endpoint or not loop or not acsi_client.is_connected:
            raise RuntimeError('not-connected')
        try:
            ws_info = endpoint.get_websocket_info(acsi_client)
        except Exception as e:
            print(f"CRASHED in get_websocket_info: {type(e).__name__}: {e}")
            raise

        if ws_info is None:
            raise RuntimeError('no-websocket-info')

        model_info = rti_so.get_model_info(cp)

        def _init_progress(ld_list):
            with rti_so.runtime.lock:
                model_info.model_progress = {
                    'lds_total': len(ld_list), 'lds_done': 0,
                    'lns_total': 0, 'lns_done': 0,
                    'current_ld': None, 'current_ln': None
                }

        def _set_current_ld(ld):
            with rti_so.runtime.lock:
                if model_info.model_progress:
                    model_info.model_progress['current_ld'] = ld

        def _add_lns_total(n):
            if n:
                with rti_so.runtime.lock:
                    if model_info.model_progress:
                        model_info.model_progress['lns_total'] += n

        def _set_current_ln(ln):
            with rti_so.runtime.lock:
                if model_info.model_progress:
                    model_info.model_progress['current_ln'] = ln

        def _inc_ln_done():
            with rti_so.runtime.lock:
                if model_info.model_progress:
                    model_info.model_progress['lns_done'] += 1

        def _finish_ld():
            with rti_so.runtime.lock:
                if model_info.model_progress:
                    model_info.model_progress['lds_done'] += 1
                    model_info.model_progress['current_ln'] = None

        try:
            # Step 1: Get all LDs
            ld_list = await acsi_client.get_server_directory(ws_info, None, None)
            if not isinstance(ld_list, list):
                raise RuntimeError('unexpected-server-directory')

            _init_progress(ld_list)

            # Step 2: Fetch all LD directories in PARALLEL
            async def fetch_ld_directory(ld):
                try:
                    ln_list = None
                    _set_current_ld(ld)
                    lock = rti_so.runtime.invoke_lock
                    if lock is None:
                        ln_list = await acsi_client.get_logical_device_directory(ld, ws_info, None, None)
                    else:
                        async with lock:
                            ln_list = await acsi_client.get_logical_device_directory(ld, ws_info, None, None)
                    if not isinstance(ln_list, list):
                        raise RuntimeError('unexpected-ln-list')
                    return {'ld': ld, 'ln_list': ln_list, 'status': 'ok'}
                except Exception as e:
                    logger.error(f"Failed to get directory for {ld}: {e}")
                    return {'ld': ld, 'ln_list': [], 'status': 'error'}
                finally:
                    _finish_ld()

            ld_coros = [fetch_ld_directory(ld) for ld in ld_list]
            ld_results = await asyncio.gather(*ld_coros)

            # Build maps from results
            logical_device_map = {}
            logical_device_status = {}
            all_ln_tasks = []  # List of (ld, ln_inst) tuples

            for result in ld_results:
                ld = result['ld']
                ln_list = result['ln_list']
                logical_device_map[ld] = ln_list
                logical_device_status[ld] = result['status']
                _add_lns_total(len(ln_list))

                # Collect all LNs for parallel fetching
                for ln_full in ln_list:
                    if '/' in ln_full:
                        ln_inst = ln_full.split('/')[-1]
                    elif ':' in ln_full:
                        ln_inst = ln_full.split(':')[-1]
                    else:
                        ln_inst = ln_full
                    all_ln_tasks.append((ld, ln_inst))

            # Step 3: Fetch all LN details in PARALLEL
            async def fetch_ln_details(task):
                ld, ln_inst = task
                try:
                    _set_current_ln(ln_inst)
                    details = await _aget_ln_details(ld, ln_inst, acsi_client, ws_info)
                    _inc_ln_done()
                    return {'ld': ld, 'ln_inst': ln_inst, 'details': details}
                except Exception as e:
                    print(f"Failed to get details for {ld}/{ln_inst}: {e}")
                    _inc_ln_done()
                    return {'ld': ld, 'ln_inst': ln_inst, 'details': None}

            ln_coros = [fetch_ln_details(task) for task in all_ln_tasks]
            ln_results = await asyncio.gather(*ln_coros)

            # Build logical_node_details
            logical_node_details = {}
            for result in ln_results:
                if result['details']:
                    logical_node_details[f"{result['ld']}/{result['ln_inst']}"] = result['details']

            model = {
                'server': {'logicalDevices': ld_list},
                'logicalDeviceMap': logical_device_map,
                'logicalDeviceStatus': logical_device_status,
                'logicalNodeDetails': logical_node_details,
                'source': 'live'
            }
            with rti_so.runtime.lock:
                model_info.model_data = model
                model_info.model_error = None
                model_info.model_status = 'ready'
                model_info.model_ready_event.set()

        except Exception as e:
            with rti_so.runtime.lock:
                model_info.model_status = 'error'
                model_info.model_error = str(e)
                model_info.model_ready_event.set()
            raise

    def _start_model_build_if_needed(cp):
        """Schedule background model build if idle or error."""
        model_info = rti_so.get_model_info(cp)

        with rti_so.runtime.lock:
            model_status = model_info.model_status
            if model_status in ('ready', 'building'):
                return model_status
            model_info.model_data = None
            model_info.model_error = None
            model_info.model_status = 'building'

        loop = rti_so.runtime.loop
        if not loop:
            with rti_so.runtime.lock:
                model_info.model_status = 'error'
                model_info.model_error = 'no-loop'
            return 'error'

        try:
            #client._log_action("Scheduling model build", "info")
            fut = asyncio.run_coroutine_threadsafe(_abuild_full_model(cp), loop)
            #client._log_action("Model build scheduled", "info")
        except Exception as e:
            with rti_so.runtime.lock:
                model_info.model_status = 'error'
                model_info.model_error = str(e)
            #client._log_action(f"Failed to schedule model build: {e}", "error")
            return 'error'

        with rti_so.runtime.lock:
            model_info.model_task = fut

        def _on_model_task_done(future):
            model_info = rti_so.get_model_info(cp)
            try:
                exc = future.exception()
            except Exception:
                exc = None
            with rti_so.runtime.lock:
                try:
                    model_info.model_task = None
                except Exception:
                    pass
                if exc is not None:
                    model_info.model_status = 'error'
                    model_info.model_error = str(exc)
                    #client._log_action(f"Model build failed: {exc}", "error")
                else:
                    if model_info.model_status != 'ready':
                        model_info.model_status = 'ready'
                        model_info.model_error = None
                    #client._log_action("Model build completed", "info")

        try:
            fut.add_done_callback(_on_model_task_done)
        except Exception as e:
            print(f"Failed to attach model task callback: {e}")
           # client._log_action(f"Failed to attach model task callback: {e}", "warn")

        return 'building'

    # ==================== Helper Methods ====================

    # ==================== Route Handlers ====================
    @router.get(
        "/status",
        summary="Get Client Status",
        description="Returns the current operational status of the Acsi-Client.",
        response_description="Client status information",
        responses={
            200: {"description": "Client status returned successfully"},
            500: {"description": "Error retrieving client status"}
        },
        tags=["Client Status"]
    )
    def api_status():
        """Get current client status.

        Returns:
            dict: Client status information including:
                - status: Connection status
                - host: Connected host (if connected)
                - port: Connected port (if connected)
                - error: Any error message
        """
        try:
            return rti_so.get_status()
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.post(
        "/connections",
        summary="Get Connection Info",
        description="Returns detailed information about the current WebSocket connection, including peer address, port, and connection status.",
        response_description="Connection details",
        responses={
            200: {"description": "Connection information returned successfully"},
            500: {"description": "Error retrieving connection info"}
        },
        tags=["Client Status"]
    )
    def api_connections(request:ModelRequest):
        """Get connection information.

        Returns:
            dict: {
                "ok": True,
                "status": str,
                "connected": bool,
                "server_role": "ACSI-Client",
                "ws_mode": "passive",
                "connection": {
                    "peer_address": str | None,
                    "peer_port": int | None,
                    "local_role": "ACSI-Client",
                    "ws_mode": "passive",
                    "remote_role": "ACSI_Server",
                    "cp": str
                } | None
            }
        """
        try:
            cp = request.cp
            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500
                )

            endpoint = rti_so.runtime.endpoint
            connection_info = {
                "ok": True,
                "status": rti_so.runtime.status,
                "connected": rti_so.runtime.status == "connected",
                "server_role": "ACSI-Client",
                "ws_mode": "passive",
                "connection": None,
            }

            if endpoint is not None and acsi_client is not None:
                ws_info = endpoint.get_websocket_info(acsi_client)
                if ws_info is not None:
                    peer_address = None
                    peer_port = None
                    try:
                        if hasattr(ws_info, "remote_address"):
                            addr_tuple = ws_info.remote_address
                            if isinstance(addr_tuple, tuple) and len(addr_tuple) >= 2:
                                peer_address = addr_tuple[0]
                                peer_port = addr_tuple[1]
                        elif hasattr(ws_info, "peername"):
                            addr_tuple = ws_info.peername()
                            if isinstance(addr_tuple, tuple) and len(addr_tuple) >= 2:
                                peer_address = addr_tuple[0]
                                peer_port = addr_tuple[1]
                    except Exception:
                        pass

                    connection_info["connection"] = {
                        "peer_address": peer_address,
                        "peer_port": peer_port,
                        "local_role": "ACSI-Client",
                        "ws_mode": "passive",
                        "remote_role": "ACSI_Server",
                        "cp": rti_so.runtime.cp,
                    }

            return connection_info
        except Exception as exc:
            rti_so._log_action(f"Get connections failed: {exc}", "error")
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

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
            rti_so._log_action(f"Reconfig connection request: connection={request.connection_name}, enable_tls={request.enable_tls}", "info")
            # Normalize tls_version to handle "1.2", "1.3", "TLSv1_2", "TLSv1_3" formats
            tls_version_str = (request.tls_version or "1.3").lower()
            if "1.2" in tls_version_str or "1_2" in tls_version_str:
                tls_version = ssl.TLSVersion.TLSv1_2
            else:
                tls_version = ssl.TLSVersion.TLSv1_3
            rti_so._log_action(f"TLS version determined: {tls_version} from request: {request.tls_version}", "info")
            print("Reconfiguring connection with TLS version: ", tls_version, "(from request:", request.tls_version, ")")
            if request.ws_mode.lower() == "passive":
                rti_so._log_action("Reconfiguring passive endpoint with TLS", "info")
                print("Reconfiguring passive endpoint with TLS: ", request.enable_tls)
                # Only create TLSConfig if TLS is enabled
                tls_config = None
                if request.enable_tls:
                    rti_so._log_action("Creating TLS config for server mode", "info")
                    tls_config = TLSConfig(
                        mode="server",
                        certfile=request.server_cert,
                        keyfile=request.server_key,
                        min_version=tls_version,
                        max_version=tls_version,
                        keylog_file=os.path.join("/app/so", "tlskeys.log"),
                    )
                else:
                    rti_so._log_action("TLS disabled, no TLS config needed", "info")
                print("TLS Config: ", tls_config)

                # Explicitly clear the endpoint's TLS config if TLS is being disabled
                endpoint = rti_so.runtime.endpoint
                if endpoint is not None and not request.enable_tls:
                    if hasattr(endpoint, '_tls_config'):
                        endpoint._tls_config = None
                    rti_so._log_action("Cleared endpoint TLS config", "info")
                    print("Cleared endpoint TLS config")

                # Cancel existing connection task before reconnecting
                if endpoint is not None and hasattr(endpoint, '_connect_task'):
                    connect_task = endpoint._connect_task
                    if connect_task and not connect_task.done():
                        rti_so._log_action("Cancelling existing connection task", "info")
                        print("Cancelling endpoint's _connect_task")
                        connect_task.cancel()

                # Run on the loop that actually owns the endpoint (runtime.loop),
                # not uvicorn's own loop — matches the pattern used by
                # read_value/write_value/operate elsewhere in this router.
                rti_so._log_action("Invoking reconfigure_endpoint on runtime loop", "info")
                rti_so.invoke_on_runtime_loop(
                    rti_so.runtime.endpoint.reconfigure_endpoint(request.enable_tls,
                                                                 tls_config=tls_config,
                                                                 oauth_enable=rti_so.runtime.endpoint._oauth_enable),
                    timeout=30,  # stop_passive + restart can take a few seconds
                )

                #if request.enable_tls:
                rti_so._log_action("Waiting for endpoint to be running", "info")
                rti_so.invoke_on_runtime_loop(
                    rti_so.runtime.endpoint._endpoint_running_event.wait(),
                    timeout=20,
                )

                if not rti_so.runtime.endpoint._is_endpoint_running:
                    last_err = getattr(rti_so.runtime.endpoint, "_last_start_error", None)
                    rti_so._log_action(f"Endpoint failed to start: {last_err}", "error")
                    return JSONResponse(
                        content={"ok": False, "error": f"endpoint failed to start: {last_err}"},
                        status_code=500,
                    )

                rti_so._log_action(f"Endpoint status: {rti_so.runtime.endpoint._is_endpoint_running}", "info")
                print("endpoint status is: ", rti_so.runtime.endpoint._is_endpoint_running)

                rti_so._log_action(f"Connection reconfigured: enable_tls={request.enable_tls}", "info")
                return JSONResponse(
                    content={"ok": True, "status": "reconfigured", "ws_mode": request.ws_mode,
                             "enable_tls": request.enable_tls},
                    status_code=200,
                )
            else:
                rti_so._log_action("Rejected: Only passive mode is supported for TLS reconfiguration", "warn")
                return JSONResponse(
                    content={"ok": False, "error": "Only passive mode is supported for reconfiguration."},
                    status_code=400,
                )
        except Exception as exc:
            import traceback
            print("reconfig error:", repr(exc))
            traceback.print_exc()
            rti_so._log_action(f"Reconfig connection failed: {exc}", "error")
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
            endpoint = rti_so.runtime.endpoint
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
            ws_mode = "passive"
            if hasattr(endpoint, 'ws_mode'):
                ws_mode = endpoint.ws_mode
            elif hasattr(rti_so.runtime, 'ws_mode'):
                ws_mode = rti_so.runtime.ws_mode

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
            rti_so._log_action(f"Reconfig OAuth request: enable={request.enable_oauth}, connection={request.connection_name or 'unknown'}", "info")
            # Get OAuth settings from request (BFF should provide these from connections.json)
            certificate_endpoint = getattr(request, 'certificate_endpoint_url', None) or getattr(request, 'certificate_endpoint', None)
            token_issuer_url = getattr(request, 'token_issuer_url', None) or getattr(request, 'token_issuer', None)
            # If we have token_endpoint but not token_issuer, extract issuer from endpoint URL
            token_endpoint_from_req = getattr(request, 'token_endpoint', None) or getattr(request, 'token_endpoint_url', None)
            if token_endpoint_from_req and not token_issuer_url:
                # token_endpoint is like: https://localhost:8443/realms/iec61850-websocket/protocol/openid-connect/token
                # token_issuer should be: https://localhost:8443/realms/iec61850-websocket
                token_issuer_url = token_endpoint_from_req.replace('/protocol/openid-connect/token', '')
                rti_so._log_action("Extracted token_issuer from token_endpoint URL", "info")
            ca_certificate = getattr(request, 'ca_certificate', None)

            # Validate that required OAuth settings are provided
            connection_name = request.connection_name or "unknown"
            if request.enable_oauth and (not certificate_endpoint or not token_issuer_url):
                error_msg = f"certificate_endpoint and token_issuer_url are required for OAuth but were not provided in request for connection: {connection_name}"
                rti_so._log_action(error_msg, "error")
                raise ValueError(error_msg)

            # When disabling OAuth, pass None to signal that OAuth should be disabled
            # The underlying library should handle None properly
            if not request.enable_oauth:
                rti_so._log_action("Disabling OAuth for connection", "info")
                certificate_endpoint = None
                token_issuer_url = None
                ca_certificate = None

            if request.ws_mode.lower() == "passive":
                rti_so._log_action("Reconfiguring OAuth for passive mode", "info")
                loop = rti_so.runtime.loop
                if loop is None or not loop.is_running():
                    rti_so._log_action("Client not connected", "error")
                    raise HTTPException(status_code=503, detail="client-not-connected")

                rti_so._log_action("Invoking reconfigure_oauth on runtime loop", "info")
                fut = asyncio.run_coroutine_threadsafe(
                    rti_so.runtime.endpoint.reconfigure_oauth(
                        request.enable_oauth,
                        certificate_endpoint=certificate_endpoint,
                        token_issuer=token_issuer_url,
                        kc_cert=ca_certificate,
                    ),
                    loop,
                )
                await asyncio.wrap_future(fut)

                if request.enable_oauth:
                    rti_so._log_action("Waiting for OAuth endpoint to be running", "info")
                    wait_fut = asyncio.run_coroutine_threadsafe(
                        rti_so.runtime.endpoint._endpoint_running_event.wait(), loop
                    )
                    await asyncio.wrap_future(wait_fut)
                    rti_so._log_action(f"OAuth endpoint status: {rti_so.runtime.endpoint._is_endpoint_running}", "info")
                    print("endpoint status is: ", rti_so.runtime.endpoint._is_endpoint_running)

                rti_so._log_action(f"OAuth reconfigured: enable={request.enable_oauth}", "info")
                return JSONResponse(
                    content={"ok": True, "status": "reconfigured", "ws_mode": "passive",
                             "enable_oauth": request.enable_oauth},
                    status_code=200,
                )
            else:
                rti_so._log_action("Rejected: Only passive mode is supported for OAuth reconfiguration", "warn")
                return JSONResponse(
                    content={"ok": False, "error": "Only passive mode is supported for OAuth reconfiguration."},
                    status_code=400,
                )
        except Exception as exc:
            import traceback
            print("reconfig oauth error:", exc)
            print("Traceback:", traceback.format_exc())
            rti_so._log_action(f"Reconfig OAuth failed: {exc}", "error")
            return JSONResponse(content={"ok": False, "error": str(exc)}, status_code=500)

    @router.get(
        "/oauth-status",
        summary="Get OAuth Status",
        description="Returns whether OAuth is currently enabled or disabled for this SO client.",
        response_description="OAuth enable status",
        responses={
            200: {"description": "OAuth status returned successfully"},
            500: {"description": "Error retrieving OAuth status"}
        },
        tags=["OAuth"]
    )
    def api_get_oauth_status():
        """Get current OAuth enable/disable status from the SO server.

        Returns:
            dict: {
                "ok": True,
                "enable_oauth": bool  # Current OAuth status
            }
        """
        try:
            # Check the runtime endpoint's OAuth enable status
            if hasattr(rti_so.runtime, 'endpoint') and hasattr(rti_so.runtime.endpoint, '_oauth_enable'):
                enable_oauth = rti_so.runtime.endpoint._oauth_enable
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
        "/properties",
        summary="Get Client Properties",
        description="Returns the static properties and configuration of the ACSI client.",
        response_description="Client properties",
        tags=["Client Status"]
    )
    def api_properties():
        """Get connection information.

        Returns:
            dict: {
                "ok": True,
                "acsi_role": "ACSI-Client",
                "ws_mode": "passive"
            }
        """
        return {
            "ok": True,
            "acsi_role": "ACSI-Client",
            "ws_mode": "passive",
            "acsi_client_list": rti_so.get_cp_list(),
        }

    @router.post(
        "/connect",
        summary="Connect to Server",
        description="Start an Active WS instance.",
        response_description="Connection confirmation",
        responses={
            200: {"description": "Connection initiated successfully"},
            400: {"description": "Invalid parameters (port must be integer)"},
            500: {"description": "Connection failed"}
        },
        tags=["Connection Management"]
    )
    async def api_connect(request: ConnectRequest):
        """Start a WS Passive Endpoint.

        Request Body:
            ConnectRequest: {
                "host": str,  # Server hostname/IP
                "port": int,  # Server port (1-65535)
                "cp": str      # Communication point
            }

        Returns:
            dict: {
                "ok": True,
                "status": "connecting",
                "host": str,
                "port": int,
                "cp": str
            }

        Raises:
            HTTPException 400: If port is not a valid integer
            HTTPException 500: If connection fails
        """
        try:
            host = request.host
            port = request.port

            rti_so._log_action(f"Connect request: host={host}, port={port}", "info")

            try:
                rti_so.connect(host, port)
                rti_so._log_action(f"Connecting to: host={host}, port={port}", "info")
                return {"ok": True, "status": "connecting", "host": host, "port": port}
            except (ValueError, RuntimeError) as exc:
                rti_so._log_action(f"Connect rejected: {exc}", "warn")
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
        except Exception as exc:
            rti_so._log_action(f"Connect failed: {exc}", "error")
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.post(
        "/disconnect",
        summary="Disconnect from Server",
        description="Stops the passive websocket endpoint.",
        response_description="Disconnection confirmation",
        responses={
            200: {"description": "Disconnection status"},
            500: {"description": "Error during disconnection"}
        },
        tags=["Connection Management"]
    )
    async def api_disconnect(request: Request):
        """Disconnect from the IEC 61850 WebSocket server."""
        try:
            rti_so._log_action("Disconnect request", "info")
            status = rti_so.runtime.status
            if status in (None, "disconnected"):
                rti_so._log_action("Already disconnected", "info")
                return {"ok": True, "status": "disconnected"}

            try:
                rti_so.disconnect()
                rti_so._log_action("Disconnecting...", "info")
                current = rti_so.runtime.status
                if current in ("disconnecting", "connected"):
                    return {"ok": True, "status": "disconnecting"}
                rti_so._log_action("Disconnected", "info")
                return {"ok": True, "status": "disconnected"}
            except Exception as exc:
                current = rti_so.runtime.status
                if current in ("disconnecting", "disconnected"):
                    return {"ok": True, "status": current}
                rti_so._log_action(f"Disconnect failed: {exc}", "error")
                raise HTTPException(status_code=500, detail=str(exc))
        except Exception as exc:
            rti_so._log_action(f"Disconnect error: {exc}", "error")
            raise HTTPException(status_code=500, detail=str(exc))

    @router.post(
        "/model/tree",
        summary="Get IED Model Tree",
        description="Retrieves the complete IED model tree from the connected server. This includes logical devices, logical nodes, data objects, and data attributes.",
        response_description="Complete IED model hierarchy",
        responses={
            200: {"description": "Model tree returned successfully"},
            503: {"description": "Client not connected"},
            500: {"description": "Error retrieving model"}
        },
        tags=["Model Access"]
    )
    async def api_model(request: ModelRequest):
        """Get the IED model tree from the connected server."""

        cp = request.cp
        model_info = rti_so.get_model_info(cp)
        refresh = request.refresh

        print("the refresh value: ", refresh)

        if refresh:
                with rti_so.runtime.lock:
                    model_info.model_status = 'idle'
                    model_info.model_data = None
                    model_info.model_error = None
                    model_info.model_ready_event.clear()

        try:
            loop = rti_so.runtime.loop
            if loop is None or not getattr(loop, "is_running", lambda: False)():
                print("Client not connected, raising HTTPException")
                raise HTTPException(status_code=503, detail="client-not-connected")

            _check_websocket_connection()

            with rti_so.runtime.lock:
                model_status = model_info.model_status
                data = model_info.model_data
                error = model_info.model_error
            if model_status == 'ready' and data:
                return {'status': 'ready', 'model': data}
            if model_status == 'error':
                raise HTTPException(status_code=500, detail=error)
            if model_status == 'idle':
                start_result = _start_model_build_if_needed(cp)
                if start_result == 'error':
                    rti_so._log_action('Model build scheduling failed', 'error')
                    print("the error is: ", rti_so.runtime.model_error)

                    raise HTTPException(status_code=503, detail=rti_so.runtime.model_error)
                else:
                    try:
                        await asyncio.wait_for(model_info.model_ready_event.wait(), timeout=12)
                    except asyncio.TimeoutError:
                        raise HTTPException(status_code=504, detail="model-build-timeout")
                    data = model_info.model_data
                    return {"status": "ready", "model": data}

            return {'status': 'error', 'model': None}
        except HTTPException as e:
            print("HTTPException raised in api_model, re-raising: ", e)
            raise
        except Exception as exc:
            rti_so._log_action(f"Get model failed (outer): {exc}", "error")
            print("Unhandled outer exception in api_model:", exc)
            logger.exception("Unhandled outer exception in api_model")
            raise HTTPException(
                status_code=500,
                detail={"error": str(exc), "traceback": traceback.format_exc()}
            )

    @router.post(
        "/server-directory",
        summary="Get Server Directory",
        description="Retrieves the list of all Logical Devices from the connected IEC61850 server. This is a modular endpoint for incremental model building.",
        response_description="Server directory with list of logical devices",
        responses={
            200: {"description": "Server directory returned successfully"},
            503: {"description": "Client not connected"},
            500: {"description": "Error retrieving server directory"}
        },
        tags=["Model Access"]
    )
    async def api_server_directory(request: ServerDirectoryRequest):
        """Get the server directory (list of Logical Devices) from the connected server."""
        try:
            _check_websocket_connection()

            cp = request.cp
            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500
                )

            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.get_server_directory_tree(cp), timeout=10
                )

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404
                    )

                return {
                    "ok": True,
                    "success": True,
                    "serverDirectory": result,
                }

            except FuturesTimeoutError:
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"},
                    status_code=504
                )
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
        except HTTPException:
            raise
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.post(
        "/logical-device",
        summary="Get Logical Device Directory",
        description="Retrieves the list of all Logical Nodes for a specific Logical Device from the connected IEC61850 server. This is a modular endpoint for incremental model building.",
        response_description="Logical Device directory with list of logical nodes",
        responses={
            200: {"description": "Logical Device directory returned successfully"},
            400: {"description": "Missing ld_inst parameter"},
            503: {"description": "Client not connected"},
            500: {"description": "Error retrieving logical device directory"}
        },
        tags=["Model Access"]
    )
    async def api_logical_device(request: LogicalDeviceRequest):
        """Get the Logical Node list for a specific Logical Device from the connected server."""
        try:
            _check_websocket_connection()

            ld_inst = request.ld_inst
            cp = request.cp
            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500
                )

            if not ld_inst:
                return JSONResponse(
                    content={"ok": False, "error": "ld_inst is required"},
                    status_code=400
                )

            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.get_logical_device_tree(ld_inst, cp), timeout=10
                )

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404
                    )

                return {
                    "ok": True,
                    "success": True,
                    "logicalDevice": result,
                }

            except FuturesTimeoutError:
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"},
                    status_code=504
                )
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
        except HTTPException:
            raise
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.post(
        "/logical-node",
        summary="Get Logical Node Tree",
        description="Retrieves the complete tree (Data Objects, Data Attributes, RCBs, DataSets) for a specific Logical Node from the connected IEC61850 server. This is a modular endpoint for incremental model building.",
        response_description="Logical Node tree with all child elements",
        responses={
            200: {"description": "Logical Node tree returned successfully"},
            400: {"description": "Missing ld_inst or ln_inst parameter"},
            503: {"description": "Client not connected"},
            500: {"description": "Error retrieving logical node tree"}
        },
        tags=["Model Access"]
    )
    async def api_logical_node(request: LogicalNodeRequest):
        """Get the complete tree for a specific Logical Node from the connected server."""
        try:
            _check_websocket_connection()

            ld_inst = request.ld_inst
            ln_inst = request.ln_inst
            cp = request.cp
            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500
                )

            if not ld_inst:
                return JSONResponse(
                    content={"ok": False, "error": "ld_inst is required"},
                    status_code=400
                )

            if not ln_inst:
                return JSONResponse(
                    content={"ok": False, "error": "ln_inst is required"},
                    status_code=400
                )

            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.get_logical_node_tree(ld_inst, ln_inst, cp), timeout=10
                )

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404
                    )

                return {
                    "ok": True,
                    "success": True,
                    "logicalNode": result,
                }

            except FuturesTimeoutError:
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"},
                    status_code=504
                )
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
        except HTTPException:
            raise
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.post(
        "/data-object",
        summary="Get Data Object Details",
        description="Retrieves complete details for a specific Data Object including its definition and data attributes from the connected IEC61850 server. This is a modular endpoint for incremental model building.",
        response_description="Data Object details with definition and data attributes",
        responses={
            200: {"description": "Data Object details returned successfully"},
            400: {"description": "Missing ld_inst, ln_inst, or do_name parameter"},
            503: {"description": "Client not connected"},
            500: {"description": "Error retrieving data object details"}
        },
        tags=["Model Access"]
    )
    async def api_data_object(request: DataObjectRequest):
        """Get the complete details for a specific Data Object from the connected server."""
        try:
            _check_websocket_connection()

            ld_inst = request.ld_inst
            ln_inst = request.ln_inst
            do_name = request.do_name
            cp = request.cp
            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500
                )

            if not ld_inst:
                return JSONResponse(
                    content={"ok": False, "error": "ld_inst is required"},
                    status_code=400
                )

            if not ln_inst:
                return JSONResponse(
                    content={"ok": False, "error": "ln_inst is required"},
                    status_code=400
                )

            if not do_name:
                return JSONResponse(
                    content={"ok": False, "error": "do_name is required"},
                    status_code=400
                )

            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.get_data_object_details(ld_inst, ln_inst, do_name, cp), timeout=10
                )

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404
                    )

                return {
                    "ok": True,
                    "success": True,
                    "dataObject": result,
                }

            except FuturesTimeoutError:
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"},
                    status_code=504
                )
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
        except HTTPException:
            raise
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.get(
        "/actions-logs",
        summary="Get Action Log",
        description="Retrieves the logged client actions for debugging and auditing. Actions include connection events, model builds, and data operations.",
        response_description="List of logged actions",
        responses={
            200: {"description": "Action log returned successfully"},
            500: {"description": "Error retrieving actions"}
        },
        tags=["Logging"]
    )
    async def api_actions(request: Request):
        """Get logged client actions."""
        try:
            return {"actions": rti_so.get_actions()}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.post(
        "/clear-logs",
        summary="Clear Action Log",
        description="Clears all logged client actions.",
        response_description="Clear confirmation",
        responses={
            200: {"description": "Actions cleared successfully"},
            500: {"description": "Error clearing actions"}
        },
        tags=["Logging"]
    )
    async def api_actions_clear(request: Request):
        """Clear action log."""
        try:
            rti_so.clear_actions()
            return {"ok": True}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.get(
        "/messages",
        summary="Get Message Log",
        description="Retrieves the logged protocol messages for debugging. Messages include raw WebSocket communication and protocol-level events.",
        response_description="List of logged messages",
        responses={
            200: {"description": "Message log returned successfully"},
            500: {"description": "Error retrieving messages"}
        },
        tags=["Logging"]
    )
    async def api_messages(request: Request):
        """Get logged protocol messages."""
        try:
            return {"messages": rti_so.get_messages()}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.post(
        "/clear-messages",
        summary="Clear Message Log",
        description="Clears all logged protocol messages.",
        response_description="Clear confirmation",
        responses={
            200: {"description": "Messages cleared successfully"},
            500: {"description": "Error clearing messages"}
        },
        tags=["Logging"]
    )
    async def api_messages_clear(request: Request):
        """Clear message log."""
        try:
            rti_so.clear_messages()
            return {"ok": True}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.post(
        "/readvalue",
        summary="Read Value",
        description="Reads a value from the connected Acsi-Server. The client must be connected before calling this endpoint.",
        response_description="Read value result",
        responses={
            200: {"description": "Value read successfully"},
            400: {"description": "Missing objRef parameter"},
            403: {"description": "Client is not connected"},
            404: {"description": "Instance not available or read timeout"},
            500: {"description": "Error reading value"}
        },
        tags=["Data Access"]
    )
    async def api_read_value(request: ReadvalueRequest):
        """Read a value from the connected server.

        Request Body:
            ReadvalueRequest: {
                "objRef": str,  # Required - Object reference in IEC61850 format
                "fc": str       # Optional - Functional constraint
            }

        Returns:
            dict: {
                "ok": True,
                "success": True,
                "objRef": str,
                "value": any  # The read value
            }

        Raises:
            HTTPException 400: If objRef is missing
            HTTPException 403: If client is not connected
            HTTPException 404: If instance not available or timeout
        """
        try:
            # ✅ Check WebSocket connection before attempting to read
            _check_websocket_connection()

            obj_ref = request.objRef
            fc = request.fc

            cp = request.cp
            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500
                )

            if not obj_ref:
                rti_so._log_action("Client readvalue rejected: missing objRef", "warn")
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400
                )

            rti_so._log_action(f"Readvalue request: objRef={obj_ref}, fc={fc}", "info")

            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.read_value(obj_ref, fc, cp), timeout=10
                )

                if _use_io_client:
                    try:
                        io_client = get_io_plugin_dynamic()
                        mapping_manager = get_mapping_manager_dynamic()
                        sync_to_io_device = get_sync_to_io_device_dynamic()
                        write_to_lcd = get_write_to_lcd_dynamic()
                        blink_led_task = get_blink_led_task_dynamic()

                        if io_client is None or mapping_manager is None or write_to_lcd is None or blink_led_task is None:
                            logger.warning("[SO] Dynamic io_plugin loading failed, falling back to disabled state")
                        else:
                            logger.info(f"[SO] IO client for sync: {io_client}")
                            if io_client:
                                # Fire-and-forget: don't wait for IO sync to complete
                                # Check health and sync in background
                                lcdValue = f"Read - {obj_ref}"

                                if result is None:
                                        lcdValue = f"Readvalue failed - {obj_ref} fail"
                                else:
                                    lcdValue = f"{obj_ref} : {result.get('value')}"

                                asyncio.create_task(
                                    blink_led_task(io_client, "read", interval=0.2, count=1, mapping_manager=mapping_manager)
                                )

                                asyncio.create_task(
                                    write_to_lcd(io_client, "read", lcdValue, mapping_manager=mapping_manager)
                                )

                            else:
                                logger.warning("[SO] IO client is None - cannot sync to device. Call /api/io-plugin/connect first.")
                    except ImportError as e:
                        logger.error(f"[SO] ImportError - Cannot import IO client: {e}")
                    except Exception as e:
                        logger.error(f"[SO] Exception in IO sync setup: {e}")


                if result is None:
                    rti_so._log_action(
                        "Client readvalue failed: instanceNotAvailable",
                        "warn",
                        detail={"objRef": obj_ref, "fc": fc}
                    )
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404
                    )

                rti_so._log_action(
                    "Client readvalue",
                    detail={
                        "objRef": obj_ref,
                        "value": result.get("value"),
                    },
                )
                return {
                    "ok": True,
                    "success": True,
                    "objRef": obj_ref,
                    "value": result.get("value"),
                }

            except FuturesTimeoutError:
                rti_so._log_action(
                    "Client readvalue timeout",
                    "warn",
                    detail={"objRef": obj_ref, "fc": fc},
                )
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"},
                    status_code=504
                )
            except ValueError as exc:
                rti_so._log_action(f"Client readvalue failed: {exc}", "warn")
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                rti_so._log_action(f"Client readvalue failed: {exc}", "error")
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
        except HTTPException:
            raise
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.post(
        "/getDataDefinition",
        summary="Get Data Definition",
        description="Retrieves the data definition for a specified object reference from the connected IEC61850 server. The client must be connected before calling this endpoint.",
        response_description="Data definition result",
        responses={
            200: {"description": "Data definition retrieved successfully"},
            400: {"description": "Missing objRef parameter"},
            403: {"description": "Client is not connected"},
            404: {"description": "Instance not available or retrieval timeout"},
            500: {"description": "Error retrieving data definition"}
        },
        tags=["Data Access"]
    )
    async def api_get_data_definition(request: GetDataDefinitionRequest):
        """Read a value from the connected server.

        Request Body:
            ReadvalueRequest: {
                "objRef": str,  # Required - Object reference in IEC61850 format
                "fc": str       # Optional - Functional constraint
            }

        Returns:
            dict: {
                "ok": True,
                "success": True,
                "objRef": str,
                "value": any  # The read value
            }

        Raises:
            HTTPException 400: If objRef is missing
            HTTPException 403: If client is not connected
            HTTPException 404: If instance not available or timeout
        """
        try:
            # ✅ Check WebSocket connection before attempting to get data definition
            _check_websocket_connection()

            ld_inst = request.ld_inst
            ln_inst = request.ln_inst
            do_path = request.do_path

            cp = request.cp
            print("the cp value in getDataDefinition: ", cp)
            print("the ld_inst value in getDataDefinition: ", ld_inst)
            print("the ln_inst value in getDataDefinition: ", ln_inst)
            print("the do_path value in getDataDefinition: ", do_path)

            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500
                )
            if acsi_client:
                print("the acsi_client value in getDataDefinition: ", acsi_client)
            else:
                print("the acsi_client is None in getDataDefinition")
            obj_ref = f"{ld_inst}/{ln_inst}.{do_path}" if do_path else f"{ld_inst}/{ln_inst}"

            if not obj_ref:
                #client._log_action("Client readvalue rejected: missing objRef", "warn")
                print("missing objRef in getDataDefinition")
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400
                )

            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.get_data_definition(obj_ref, cp), timeout=10
                )

                print("result in getDataDefinition: ", result)

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404
                    )

                return {
                    "ok": True,
                    "success": True,
                    "objRef": obj_ref,
                    "value": result.get("dataDefinition"),
                }

            except FuturesTimeoutError:
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"},
                    status_code=504
                )
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                print("Exception in getDataDefinition: ", exc)
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
        except Exception as exc:
            print("Unhandled exception in getDataDefinition: ", exc)
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.post(
        "/brcb-read",
        summary="Get brcb values",
        description="Retrieves BRCB values for a specified object reference from the connected IEC61850 server. The client must be connected before calling this endpoint.",
        response_description="Data definition result",
        responses={
            200: {"description": "BRCB values successfully"},
            400: {"description": "Missing objRef parameter"},
            403: {"description": "Client is not connected"},
            404: {"description": "Instance not available or retrieval timeout"},
            500: {"description": "Error retrieving data definition"}
        },
        tags=["Data Access"]
    )

    async def api_get_brcb_values(request: ReadRCBValueRequest):
        """Read BRCB values from the connected server."""
        try:
            # ✅ Check WebSocket connection before attempting to read BRCB
            _check_websocket_connection()

            obj_ref = request.objRef

            cp = request.cp
            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500
                )

            if not obj_ref:
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400
                )

            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.get_brcb_definition(obj_ref, cp), timeout=10
                )

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404
                    )

                return {
                    "ok": True,
                    "success": True,
                    "objRef": obj_ref,
                    "value": result.get("brcbDefinition"),
                }

            except FuturesTimeoutError:
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"},
                    status_code=504
                )
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
        except HTTPException:
            raise
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.post(
        "/brcb-write",
        summary="Writes brcb values",
        description="Writes BRCB values for a specified object reference from the connected IEC61850 server. The client must be connected before calling this endpoint.",
        response_description="Data definition result",
        responses={
            200: {"description": "BRCB values written successfully"},
            400: {"description": "Missing objRef parameter"},
            403: {"description": "Client is not connected"},
            404: {"description": "Instance not available or retrieval timeout"},
            500: {"description": "Error retrieving data definition"}
        },
        tags=["Data Access"]
    )
    async def api_set_brcb_values(request: WriteRCBValueRequest):
        """Read BRCB values from the connected server."""
        try:
            # ✅ Check WebSocket connection before attempting to write BRCB
            _check_websocket_connection()

            obj_ref = request.objRef

            cp = request.cp
            data = request.data
            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500
                )

            if not obj_ref:
                # client._log_action("Client readvalue rejected: missing objRef", "warn")
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400
                )
            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.set_brcb_values(cp, data), timeout=10
                )

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404
                    )

                return {
                    "ok": True,
                    "success": True,
                    "objRef": obj_ref,
                    "value": result.get("result"),
                }

            except FuturesTimeoutError:
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"},
                    status_code=504
                )
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.post(
        "/urcb-read",
        summary="Get brcb values",
        description="Retrieves BRCB values for a specified object reference from the connected IEC61850 server. The client must be connected before calling this endpoint.",
        response_description="Data definition result",
        responses={
            200: {"description": "BRCB values successfully"},
            400: {"description": "Missing objRef parameter"},
            403: {"description": "Client is not connected"},
            404: {"description": "Instance not available or retrieval timeout"},
            500: {"description": "Error retrieving data definition"}
        },
        tags=["Data Access"]
    )

    async def api_get_urcb_values(request: ReadRCBValueRequest):
        """Read BRCB values from the connected server."""
        try:
            # ✅ Check WebSocket connection before attempting to read URCB
            _check_websocket_connection()

            obj_ref = request.objRef

            cp = request.cp
            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500
                )

            if not obj_ref:
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400
                )

            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.get_urcb_definition(obj_ref, cp), timeout=10
                )

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404
                    )

                return {
                    "ok": True,
                    "success": True,
                    "objRef": obj_ref,
                    "value": result.get("urcbDefinition"),
                }

            except FuturesTimeoutError:
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"},
                    status_code=504
                )
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
        except HTTPException:
            raise
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.post(
        "/urcb-write",
        summary="Writes urcb values",
        description="Writes URCB values for a specified object reference from the connected IEC61850 server. The client must be connected before calling this endpoint.",
        response_description="Data definition result",
        responses={
            200: {"description": "URCB values written successfully"},
            400: {"description": "Missing objRef parameter"},
            403: {"description": "Client is not connected"},
            404: {"description": "Instance not available or retrieval timeout"},
            500: {"description": "Error retrieving data definition"}
        },
        tags=["Data Access"]
    )
    async def api_set_urcb_values(request: WriteRCBValueRequest):
        """Read BRCB values from the connected server."""
        try:
            # ✅ Check WebSocket connection before attempting to write URCB
            _check_websocket_connection()

            obj_ref = request.objRef

            cp = request.cp
            data = request.data

            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500
                )

            if not obj_ref:
                # client._log_action("Client readvalue rejected: missing objRef", "warn")
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400
                )
            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.set_urcb_values(cp, data), timeout=10
                )

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404
                    )

                return {
                    "ok": True,
                    "success": True,
                    "objRef": obj_ref,
                    "value": result.get("result"),
                }

            except FuturesTimeoutError:
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"},
                    status_code=504
                )
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.post(
        "/getDataSetDirectory",
        summary="Get Data Set directory",
        description="Retrieves the data definition for a specified object reference from the connected IEC61850 server. The client must be connected before calling this endpoint.",
        response_description="Data set directory",
        responses={
            200: {"description": "Data definition retrieved successfully"},
            400: {"description": "Missing objRef parameter"},
            403: {"description": "Client is not connected"},
            404: {"description": "Instance not available or retrieval timeout"},
            500: {"description": "Error retrieving data definition"}
        },
        tags=["Data Access"]
    )
    async def api_get_dataset_directory(request: GetDataSetDirectory):

        try:
            # ✅ Check WebSocket connection before attempting to get dataset directory
            _check_websocket_connection()

            ld_inst = request.ld_inst
            ln_inst = request.ln_inst
            ds_inst = request.ds_inst

            obj_ref = f"{ld_inst}/{ln_inst}.{ds_inst}"

            cp = request.cp
            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500
                )

            if not obj_ref:
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400
                )

            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.get_dataset_directory(ld_inst, ln_inst, ds_inst, cp), timeout=10
                )

                print("get ds result: ", result)

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404
                    )

                return {
                    "ok": True,
                    "success": True,
                    "objRef": obj_ref,
                    "value": result.get("value"),
                }

            except FuturesTimeoutError:
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"},
                    status_code=504
                )
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
        except HTTPException:
            raise
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.get(
        "/apis",
        summary="List All API Endpoints",
        description="Returns a comprehensive list of all available API endpoints with their HTTP methods, request body schemas, and response formats.",
        response_description="List of all endpoints with their metadata",
        tags=["Discovery"]
    )
    async def api_list_all_endpoints(request: Request):
        """List all API endpoints."""
        routes = []
        for rule in app.url_map.iter_rules():
            path = str(rule)
            if path.startswith("/api/iec61850client/"):
                methods = [m for m in rule.methods if m not in ("HEAD", "OPTIONS")]
                routes.append({"path": path, "methods": methods, "endpoint": rule.endpoint})
        return {"ok": True, "count": len(routes), "endpoints": sorted(routes, key=lambda x: x["path"])}

    @router.get(
        "/health",
        summary="Health Check",
        description="Generic health endpoint used by external discovery systems (e.g., BFF network scan).",
        response_description="Health status",
        responses={
            200: {"description": "Service is healthy"},
            500: {"description": "Service is unhealthy"}
        },
        tags=["Health"]
    )
    async def api_health(request: Request):
        """Generic health endpoint used by external discovery."""
        try:
            return {
                "status": "ok",
                "service": "SO",
                "server": {"status": "ok", "host": "localhost", "port": 8080},
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.post(
        "/writevalue",
        summary="Write Value",
        description="Writes a value to the connected Acsi-Server. The client must be connected before calling this endpoint.",
        response_description="Write value confirmation",
        responses={
            200: {"description": "Value written successfully"},
            400: {"description": "Missing parameters (objRef, fc, or value)"},
            403: {"description": "Client is not connected"},
            500: {"description": "Error writing value"}
        },
        tags=["Data Access"]
    )
    async def api_write_value(request: WriteValueRequest):
        """Write a value to the connected server.

                Request Body:
                    WriteValueRequest: {
                        "objRef": str,     # Required - Object reference
                        "fc": str,        # Required - Functional constraint
                        "value": any,     # Required - Value to write
                        "value_type": str # Optional - Value type hint
                    }

                Returns:
                    dict: {
                        "ok": True,
                        "success": True,
                        "objRef": str,
                        "fc": str,
                        "value": any  # The written value
                    }

                Raises:
                    HTTPException 400: If objRef, fc, or value is missing
                    HTTPException 403: If client is not connected
                    HTTPException 500: If write operation fails
                """
        try:
            # ✅ Check WebSocket connection before attempting to write value
            _check_websocket_connection()

            obj_ref = request.objRef
            fc = request.fc
            value = request.value
            value_type = request.dataType

            cp = request.cp
            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500
                )

            if not obj_ref:
                rti_so._log_action("Writevalue request rejected: missing objRef", "warn")
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400
                )

            if not fc:
                rti_so._log_action("Writevalue request rejected: missing fc", "warn")
                return JSONResponse(
                    content={"ok": False, "error": "fc is required"},
                    status_code=400
                )

            if value is None:
                rti_so._log_action(f"Writevalue request rejected: missing value for objRef={obj_ref}", "warn")
                return JSONResponse(
                    content={"ok": False, "error": "value is required"},
                    status_code=400
                )

            rti_so._log_action(f"Writevalue request: objRef={obj_ref}, fc={fc}, value={value}", "info")

            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.write_value(obj_ref, value, fc, value_type, cp), timeout=10
                )

                # Sync with mapped device if io_client is enabled (fire-and-forget)
                if _use_io_client:
                    try:
                        io_client = get_io_plugin_dynamic()
                        mapping_manager = get_mapping_manager_dynamic()
                        write_to_lcd = get_write_to_lcd_dynamic()
                        blink_led_task = get_blink_led_task_dynamic()

                        if io_client is None or mapping_manager is None or write_to_lcd is None or blink_led_task is None:
                            logger.warning("[SO] Dynamic io_plugin loading failed, falling back to disabled state")
                        else:
                            logger.info(f"[SO] IO client for sync: {io_client}")
                            if io_client:
                                # Fire-and-forget: don't wait for IO sync to complete
                                # Check health and sync in background
                                ledValue = True
                                lcdValue = f"Write - {obj_ref} Value: {value}"

                                if result is None:
                                        ledValue = False
                                        lcdValue = f"Write - {obj_ref} fail"
                                else:
                                    if result.get("error") is not None:
                                        ledValue = False
                                        lcdValue = f"Write - {obj_ref} fail"


                                asyncio.create_task(
                                    blink_led_task(io_client, "setpoint", interval=0.2, count=1, mapping_manager=mapping_manager)
                                )

                                asyncio.create_task(
                                    write_to_lcd(io_client, "setpoint", lcdValue, mapping_manager=mapping_manager)
                                )

                            else:
                                logger.warning("[SO] IO client is None - cannot sync to device. Call /api/io-plugin/connect first.")
                    except ImportError as e:
                        logger.error(f"[SO] ImportError - Cannot import IO client: {e}")
                    except Exception as e:
                        logger.error(f"[SO] Exception in IO sync setup: {e}")

                print("write value result in so: ", result)

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404
                    )
                else:
                    print(f"the write result for {obj_ref}: {result} ")
                    if result.get("error") is None:
                        return {
                            "ok": True,
                            "success": True,
                            "objRef": obj_ref,
                            "fc": fc,
                            "value": result.get("value"),
                        }
                    else:
                        return JSONResponse(
                            content={"ok": False, "error": result.get("error")},
                            status_code=500
                        )

            except FuturesTimeoutError:
                rti_so._log_action("WriteValue timeout", "error")
                return JSONResponse(
                    content={"ok": False, "error": "write timeout"},
                    status_code=504
                )
            except ValueError as exc:
                rti_so._log_action(f"WriteValue value error: {exc}", "error")
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                rti_so._log_action(f"WriteValue error: {exc}", "error")
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
        except Exception as exc:
            rti_so._log_action(f"WriteValue error: {exc}", "error")

            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.post(
        "/operate",
        summary="Operate",
        description="Sends an operate command to the connected Acsi-Server. The client must be connected before calling this endpoint.",
        response_description="Operate command",
        responses={
            200: {"description": "Operate command sent successfully"},
            400: {"description": "Missing parameters (objRef or value)"},
            403: {"description": "Client is not connected"},
            500: {"description": "Error writing value"}
        },
        tags=["Data Access"]
    )
    async def api_operate(request: OperateRequest):
        """Send an Operate command to the connected server.

                Request Body:
                    WriteValueRequest: {
                        "objRef": str,     # Required - Object reference
                        "value": any,     # Required - Value to write
                        "value_type": str # Optional - Value type hint
                    }

                Returns:
                    dict: {
                        "ok": True,
                        "success": True,
                        "objRef": str,
                        "value": any  # The written value
                    }

                Raises:
                    HTTPException 400: If objRef or value is missing
                    HTTPException 403: If client is not connected
                    HTTPException 500: If write operation fails
                """
        try:
            # ✅ Check WebSocket connection before attempting to operate
            _check_websocket_connection()

            obj_ref = request.objRef
            value = request.value
            value_type = request.value_type

            cp = request.cp
            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500
                )

            if not obj_ref:
                rti_so._log_action("Operate request rejected: missing objRef", "warn")
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400
                )
            if value is None:
                rti_so._log_action("Operate request rejected: missing value", "warn")
                return JSONResponse(
                    content={"ok": False, "error": "value is required"},
                    status_code=400
                )

            rti_so._log_action(f"Operate request: objRef={obj_ref}, value={value}", "info")

            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.operate(obj_ref, value, value_type, cp), timeout=10
                )

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404
                    )
                else:

                    if _use_io_client:
                        try:
                            io_client = get_io_plugin_dynamic()
                            mapping_manager = get_mapping_manager_dynamic()
                            blink_led_task = get_blink_led_task_dynamic()
                            write_to_lcd = get_write_to_lcd_dynamic()

                            if io_client is None or mapping_manager is None or blink_led_task is None or write_to_lcd is None:
                                logger.warning("Dynamic io_plugin loading failed, falling back to disabled state")
                            else:
                                logger.info(f"IO client for sync: {io_client}")
                                if io_client:
                                    # Fire-and-forget: don't wait for LED blink to complete
                                    # Check health and blink LED in background
                                    asyncio.create_task(
                                        blink_led_task(io_client, "operate", interval=0.2, count=1, mapping_manager=mapping_manager)
                                    )

                                    lcd_value = f"Oper {obj_ref}={value}"

                                    asyncio.create_task(
                                        write_to_lcd(io_client, "operate", lcd_value, mapping_manager=mapping_manager)
                                    )

                                else:
                                    logger.warning("IO client is None - cannot sync to device. Call /api/io-plugin/connect first.")
                        except ImportError as e:
                            logger.error(f"ImportError - Cannot import IO client: {e}")
                        except Exception as e:
                            logger.error(f"Exception in IO sync setup: {e}")

                    print("operate result in so: ", result)
                    #operate_result = result.get('result', {})
                    success = result.get('result', False)
                    error = result.get('serviceError', "")
                    return {
                        "ok": success,
                        "error": error,
                    }
            except FuturesTimeoutError:
                return JSONResponse(
                    content={"ok": False, "error": "Operate timeout"},
                    status_code=504
                )
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                print("entered here 1")
                print(f"Exception in api_operate: {exc}")
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
        except HTTPException:
            raise
        except Exception as exc:
            print("entered here 2")
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    # ==================== IO Client Endpoints ====================

    @router.get(
        "/io-client",
        summary="Get IO Client Status",
        description="Returns whether io_client is enabled for device sync in writevalue.",
        response_description="IO client status",
        responses={
            200: {"description": "IO client status returned successfully"}
        },
        tags=["IO Client"]
    )
    def api_get_io_client_status():
        """Get current io_client usage status for writevalue sync.

        Returns:
            dict: {"enabled": bool}
        """
        return {"enabled": _use_io_client}

    @router.post(
        "/io-client",
        summary="Set IO Client Usage",
        description="Enable or disable io_client for syncing writes to physical IO devices in writevalue endpoint. If enabling, will attempt to load modules if files are present.",
        response_description="IO client configuration confirmation",
        responses={
            200: {"description": "IO client configuration updated successfully"},
            500: {"description": "Error updating configuration"}
        },
        tags=["IO Client"]
    )
    def api_set_io_client(request: IoClientConfigRequest):
        """Enable or disable io_client usage for writevalue sync.

        When enabled, writes to the ACSI server via /writevalue will be synced
        to physical IO devices. When disabled, writes will only affect the ACSI
        server model.

        Request Body:
            IoClientConfigRequest: {"enabled": bool}

        Returns:
            dict: {"ok": True, "enabled": bool, "message": str}
        """
        global _use_io_client
        _use_io_client = request.enabled

        if _use_io_client:
            try:
                if check_required_io_plugin_files():
                    load_io_plugin_modules()
                    update_io_plugin_usage()
                    _try_include_io_router()
                else:
                    _use_io_client = False
                    logger.warning("Required IO plugin files are missing, disabling IO client")
            except Exception as e:
                logger.error(f"Error enabling IO client: {e}")
                _use_io_client = False

        logger.info(f"IO client usage set to: {_use_io_client}")
        return {
            "ok": True,
            "enabled": _use_io_client,
            "message": f"IO client {'enabled' if _use_io_client else 'disabled'} for writevalue sync"
        }

    # ==================== IO Plugin Connection Endpoints (ported from FSP) ====================

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
        4. Enable io_client usage if requested

        Request Body:
            IoClientConnectRequest: {
                "server_url": str,           # IO server URL
                "files": list[str] | None,   # Files to fetch (None = all required)
                "timeout": float,             # Timeout in seconds
                "enable_io_plugin": bool    # Enable io_client after success
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
        global _use_io_client

        try:
            io_plugin_connection_status.connect(request.server_url)
            io_plugin_connection_status.io_server_url = request.server_url

            result = await fetch_and_load_io_plugin_files(request.server_url)

            io_plugin_connection_status.record_fetch(
                success=result.get("connection_success", False),
                error=result.get("errors", {}).get("general") or ", ".join(result.get("errors", {}).values()),
                files_fetched=len(result.get("files_downloaded", []))
            )

            if request.enable_io_plugin and result.get("connection_success", False):
                _use_io_client = True
                update_io_plugin_usage()
                # Register the IO router on the running app (no restart needed)
                _try_include_io_router()

                # Chain the demo_IO bootstrap sequence now that /api/io/*
                # is live: point the proxy client at the same host we just
                # downloaded files from, then sync mappings and enable
                # server-side ACSI sync. Best-effort - failures here are
                # reported but don't fail this endpoint's response.
                if _io_router_included:
                    result["io_bootstrap"] = await _bootstrap_io_client_after_connect(request.server_url)

            result["io_plugin_enabled"] = _use_io_client
            result["io_router_included"] = _io_router_included
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
        description="Disconnect from IO server and optionally clear downloaded files and disable io_client usage.",
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
        3. Optionally disable io_client usage

        Request Body:
            IoClientDisconnectRequest: {
                "clear_files": bool,         # Clear downloaded files
                "disable_io_plugin": bool   # Disable io_client usage
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
        global _use_io_client

        try:
            io_plugin_connection_status.disconnect()

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

            io_plugin_disabled = False
            if request.disable_io_plugin:
                _use_io_client = False
                io_plugin_disabled = True
                logger.info("IO client usage disabled")

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

    @router.get(
        "/io-plugin/files",
        summary="List IO Plugin Files",
        description="List all files currently in the dynamic io_plugin directory.",
        response_description="List of files",
        responses={
            200: {"description": "List of files returned successfully"},
            500: {"description": "Error listing files"}
        },
        tags=["IO Plugin Connection"]
    )
    def api_list_io_plugin_files():
        """List all files in the dynamic io_plugin directory.

        Returns:
            dict: {"files": list, "required_files_present": bool, "missing_files": list}
        """
        try:
            ensure_io_plugin_dir()

            all_files = []
            for item in io_plugin_dynamic_DIR.iterdir():
                if item.is_file():
                    all_files.append({
                        "name": item.name,
                        "path": str(item.relative_to(io_plugin_dynamic_DIR)),
                        "size": item.stat().st_size,
                        "modified": item.stat().st_mtime
                    })

            required_files = ["io_router.py", "io_utils.py", "mapping_manager.py", "__init__.py", "async_client_io.py"]
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
        description="Reload the io_plugin modules from the dynamic directory. Use after uploading or re-downloading files.",
        response_description="Reload confirmation",
        responses={
            200: {"description": "Modules reloaded successfully"},
            400: {"description": "Required files missing"},
            500: {"description": "Error reloading modules"}
        },
        tags=["IO Plugin Connection"]
    )
    def api_reload_io_plugin_modules():
        """Reload io_plugin modules from the dynamic directory.

        Returns:
            dict: {"ok": True, "loaded": bool, "message": str, "modules": list}
        """
        try:
            clear_io_plugin_modules()

            if not check_required_io_plugin_files():
                required_files = ["io_router.py", "io_utils.py", "mapping_manager.py", "__init__.py", "async_client_io.py"]
                return {
                    "ok": False,
                    "loaded": False,
                    "message": "Required files are missing",
                    "missing_files": [f for f in required_files if not get_io_plugin_file_path(f).exists()]
                }

            success = load_io_plugin_modules()

            if success:
                update_io_plugin_usage()
                # Register the IO router on the running app if this is the
                # first successful load - no restart needed.
                _try_include_io_router()
                return {
                    "ok": True,
                    "loaded": True,
                    "message": "IO Plugin modules reloaded successfully",
                    "modules": ["async_client_io", "io_router", "io_utils", "mapping_manager"],
                    "io_plugin_enabled": _use_io_client,
                    "io_router_included": _io_router_included
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

    return router, rti_so

if __name__ == "__main__":
    import argparse
    import uvicorn

    _LOG_CHOICES = ["critical", "error", "warning", "info", "debug", "trace"]

    parser = argparse.ArgumentParser(description="RTI Demo SO (ACSI client) BFF endpoint")
    parser.add_argument(
        "--host",
        default=os.getenv("HOST", "0.0.0.0"),
        help="Host interface to bind (default: %(default)s, env: HOST)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", "5003")),
        help="Port to listen on (default: %(default)s, env: PORT)",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL", "info"),
        help="Log level: %s (default: %%(default)s, env: LOG_LEVEL)" % ", ".join(_LOG_CHOICES),
    )
    args = parser.parse_args()

    # Module scope already applied LOG_LEVEL from the environment at import
    # (covers the app + ws61850 + acsi_client loggers). Re-resolve here so an
    # explicit --log-level on the command line wins, and hand the same value to
    # uvicorn so its own 'uvicorn'/'uvicorn.error'/'uvicorn.access' loggers
    # follow suit.
    resolved = resolve_log_level(args.log_level)
    logging.getLogger().setLevel(resolved)
    uvicorn_log_level = args.log_level.lower()
    if uvicorn_log_level not in _LOG_CHOICES:
        uvicorn_log_level = logging.getLevelName(resolved).lower()

    logger.info(
        "Starting RTI Demo SO BFF on %s:%d (log level %s)",
        args.host, args.port, logging.getLevelName(resolved),
    )

    factory_dir = Path(__file__).parent
    app = create_fastapi_app(factory_dir)
    uvicorn.run(app, host=args.host, port=args.port, log_level=uvicorn_log_level)
