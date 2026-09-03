"""Backend for Frontend (BFF) Server for RTI Demo.

This module provides a FastAPI-based REST API for managing RTI service discovery,
connections, data operations, and proxy requests to backend services.

Features:
- Service discovery (Docker and network-based)
- Connection management to remote endpoints
- Data read/write operations
- Dynamic API execution against registered targets
- Health checks and status monitoring
- Report generation and export
"""

from __future__ import annotations

from datetime import datetime
import json
import os
import logging
import sys
from typing import Any, Dict, List, Optional, Tuple
import requests
import threading
import time
from urllib.parse import urlparse

from fastapi import FastAPI, Request, HTTPException, status, Body
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from pydantic_models import *

from bffClient import BffClient

from ConnectionManager import ConnectionManager
from DataManager import DataManager

from concurrent.futures import ThreadPoolExecutor
import asyncio
import httpx

# Global state
_bff_clients: Dict[str, BffClient] = {}

# Configure logging
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
# bff/bff_server.py`, `uvicorn bff.bff_server:app`, a service wrapper, or
# pytest importing the module. Child loggers and the status-monitor / thread
# pool workers inherit this level.
logging.getLogger().setLevel(LOG_LEVEL)

logger = logging.getLogger(__name__)


class HealthCheckAccessFilter(logging.Filter):
    """Demote uvicorn access-log lines for health/status polls to DEBUG.

    The Docker healthcheck hits ``/api/health`` (and the HMI polls it plus
    ``/api/status``) every few seconds; logged at INFO they bury the real
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

# Try to import docker for auto-discovery
DOCKER_AVAILABLE = False
try:
    import docker
    from docker import DockerClient
    DOCKER_AVAILABLE = True
except ImportError:
    logger.warning("Docker Python SDK not available. Container auto-discovery disabled.")

# Determine base directory - check /app (Docker), then script dir, then parent dir
script_dir = os.path.dirname(os.path.abspath(__file__))
if os.path.exists('/app'):
    BASE_DIR = '/app'
elif os.path.exists(os.path.join(script_dir, 'connections.json')):
    BASE_DIR = script_dir
else:
    # Try parent directory
    parent_dir = os.path.dirname(script_dir)
    if os.path.exists(os.path.join(parent_dir, 'connections.json')):
        BASE_DIR = parent_dir
    else:
        BASE_DIR = script_dir

# Ensure base directory exists
os.makedirs(BASE_DIR, exist_ok=True)

CONNECTIONS_FILE = os.path.join(BASE_DIR, 'connections.json')
STATS_FILE = os.path.join(BASE_DIR, 'stats.json')


# Initialize managers
conn_manager = ConnectionManager(bff_clients=_bff_clients, connections_file=CONNECTIONS_FILE, logger=logger)
data_manager = DataManager(conn_manager, logger)


# ==================== FastAPI Application Setup ====================
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Installed here (not before uvicorn.run) so it survives uvicorn's own
    # logging dictConfig, which runs before app startup.
    logging.getLogger("uvicorn.access").addFilter(HealthCheckAccessFilter())

    asyncio.create_task(
        conn_manager.status_monitor(interval=10)
    )

    yield

    # Close the shared health-check client on shutdown.
    await conn_manager.aclose()


# Create FastAPI application
app = FastAPI(
    title="RTI Demo BFF Server",
    description="Backend for Frontend (BFF) server for RTI Demo. Provides service discovery, connection management, data operations, and proxy capabilities for RTI services.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    openapi_tags=[
        {
            "name": "Health",
            "description": "Health check and status monitoring endpoints"
        },
        {
            "name": "Endpoints",
            "description": "Service discovery and endpoint management"
        },
        {
            "name": "Connections",
            "description": "Manage connections to remote RTI endpoints"
        },
        {
            "name": "Data",
            "description": "Read and write data to ACSI endpoints"
        },
        {
            "name": "Reports",
            "description": "Generate and export reports"
        },
        {
            "name": "Stats",
            "description": "System statistics and metrics"
        },
        {
            "name": "Execution",
            "description": "Execute dynamic API calls against registered targets"
        }
    ]
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== API Endpoints ====================

# -------------------- Health & Status --------------------

async def _check_target(key: str, client: BffClient) -> Dict[str, str]:
    try:
        await asyncio.wait_for(
            asyncio.to_thread(client.request, "GET", "/api/health"),
            timeout=3.0
        )
        return {"target": key, "status": "reachable"}
    except Exception:
        return {"target": key, "status": "unreachable"}

@app.get(
    "/api/health",
    summary="Health Check",
    description="Health check endpoint for frontend: BFF status, discovered targets, and optional target reachability.",
    response_description="Health status information",
    responses={
        200: {"description": "Service is healthy"},
        500: {"description": "Health check failed"}
    },
    tags=["Health"]
)
async def health_check():
    try:
        bff_status = {"status": "ok", "service": "BFF"}

        targets = await asyncio.gather(
            *(_check_target(key, client) for key, client in _bff_clients.items())
        )

        return {
            "ok": True,
            "bff": bff_status,
            "targets": targets,
            "count": len(targets)
        }

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


def _fetch_endpoint_properties(endpoint: Dict) -> Dict:
    """Fetch endpoint properties from server/client properties APIs when available.

    Args:
        endpoint: Endpoint dictionary

    Returns:
        Dictionary with properties information or error.
    """
    host = endpoint.get('host')
    port = endpoint.get('port')
    endpoint_type = str(endpoint.get('type', '')).upper()

    if not host or not port:
        return {'available': False, 'error': 'missing host or port'}

    paths = ['/api/properties', '/api/properties']

    last_error = None
    for path in paths:
        url = f"http://{host}:{port}{path}"
        try:
            response = requests.get(url, timeout=2)
            if response.status_code >= 400:
                last_error = f"{path} returned {response.status_code}"
                continue

            payload = response.json()
            if isinstance(payload, dict):
                if 'properties' in payload:
                    return {
                        'available': True,
                        'source': path,
                        'properties': payload.get('properties')
                    }
                return {
                    'available': True,
                    'source': path,
                    'properties': payload
                }

            return {
                'available': True,
                'source': path,
                'properties': payload
            }
        except Exception as e:
            last_error = str(e)

    return {
        'available': False,
        'error': last_error or 'properties endpoint not reachable'
    }



# -------------------- Endpoints Management --------------------

@app.get(
    "/api/endpoints",
    summary="Get All Endpoints",
    description="Get all configured endpoints (including cached auto-discovered).",
    response_description="List of all endpoints with their properties",
    responses={
        200: {"description": "List of endpoints returned successfully"}
    },
    tags=["Endpoints"]
)
async def get_endpoints():
    """Retrieve all configured and discovered endpoints.
    
    This endpoint returns:
    - Manual connections from the connection manager
    - Auto-discovered services (from Docker and network scans)
    - Properties information for each endpoint when available
    
    Returns:
        JSON with endpoints list, counts, and discovery metadata.
    """
    # Keep Docker-discovery cache fresh when enabled.
    #if discovery.docker_enabled:
    #    discovery.discover_services()
    #    _register_bff_clients(discovery.discovered_services)

    # Use statuses already kept fresh by the background status_monitor instead
    # of blocking this request on a live health-check scan.
    endpoints = list(conn_manager.connections)
    #discovered = dict(discovery.discovered_services)

    # Add discovered services not already present in manual connections.
    #for service_info in discovered.values():
    #    exists = any(e['host'] == service_info['host'] and e['port'] == service_info['port'] for e in endpoints)
    #    if not exists:
    #        endpoints.append(service_info)

    # Enrich every endpoint with its properties payload in parallel, off the
    # event loop (the underlying call uses blocking `requests`).
    properties = await asyncio.gather(
        *(asyncio.to_thread(_fetch_endpoint_properties, endpoint) for endpoint in endpoints)
    )
    for endpoint, props in zip(endpoints, properties):
        endpoint['properties_info'] = props

    return {
        'endpoints': endpoints,
        'count': len(endpoints),
        #'discovered_count': len(discovered),
        #'last_discovery': discovery.last_discovery,
        #'docker_enabled': discovery.docker_enabled
    }

# -------------------- Connections Management --------------------

@app.get(
    "/api/connections",
    summary="Get All Connections",
    description="Get all configured connections to remote endpoints.",
    response_description="List of all connections",
    responses={
        200: {"description": "Connections retrieved successfully"}
    },
    tags=["Connections"]
)
async def get_connections():
    """Retrieve all configured connections.

    Returns:
        JSON with list of connections and their count.
    """
    # Ensure all connections have a status field
    connections_with_status = []
    for conn in conn_manager.connections:
        if 'status' not in conn:
            # Set default status based on type
            if conn.get('type') == 'IDP-Server':
                conn['status'] = 'connected'
            else:
                conn['status'] = 'disconnected'
        connections_with_status.append(conn)

    return {
        "connections": connections_with_status,
        "count": len(connections_with_status)
    }


@app.post(
    "/api/connections/tls-config",
    summary="update TLS Config for a specific connection",
    description="update TLS Config for a specific connectio",
    response_description="apply result",
    responses={
        201: {"description": "Connection with TLS config created successfully"},
        400: {"description": "Missing required fields"}
    },
    tags=["TLS"]
)
async def create_tls_connection(request: TLSConnectionCreateConfigRequest):
    """Create a new connection to a remote RTI endpoint.

    Request Body:
        ConnectionCreateRequest with name, host, port, type

    Returns:
        JSON with the created connection details.

    Raises:
        HTTPException 400: If required fields are missing.
    """
    print("server_key: ", request.server_key)
    print("server_cert: ", request.server_cert)

    ws_mode = request.ws_mode
    print("debug 1")
    
    # Validate required fields based on mode
    if ws_mode == "passive" or ws_mode == "Passive":
        if not request.server_key or not request.server_cert:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Missing required fields: server_key and server_cert for passive mode'
            )
    elif ws_mode == "active" or ws_mode == "Active":
        if not request.server_ca:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Missing required field: server_ca for active mode'
            )
    print("debug 2")

    connection = conn_manager.get_connection(request.connection_name)
    print("debug 3")

    if connection:
        if 'TLS' not in connection:
            connection['TLS'] = {}
        connection['TLS']['enable_tls'] = request.enable_tls
        connection['TLS']['tls_version'] = request.tls_version
        
        # Store certificates based on mode
        if ws_mode == "passive" or ws_mode == "Passive":
            connection['TLS']['server_key'] = request.server_key
            connection['TLS']['server_cert'] = request.server_cert
            connection['TLS']['server_ca'] = None
        elif ws_mode == "active" or ws_mode == "Active":
            connection['TLS']['server_key'] = None
            connection['TLS']['server_cert'] = None
            connection['TLS']['server_ca'] = request.server_ca
        
        conn_manager.save_connections()
        print("debug 4")

        return {
            "ok": True,
            "message": f"TLS config saved for {request.connection_name}"
        }

    print("debug 5")

    return {
        "ok": False,
        "message": "Connection not found"
    }


@app.get(
    "/api/connections/tls-config",
    summary="Get TLS Config for a specific connection",
    description="Retrieve the TLS configuration for a connection.",
    response_description="TLS configuration",
    responses={
        200: {"description": "TLS config returned successfully"},
        404: {"description": "Connection not found"}
    },
    tags=["TLS"]
)
async def get_tls_config(connection_name: str):
    """Get TLS configuration for a connection.

    Query Parameters:
        connection_name: Name of the connection to get TLS config for

    Returns:
        JSON with TLS configuration including enable_tls, tls_version,
        server_key, server_cert, server_ca.

    Raises:
        HTTPException 404: If connection is not found.
    """
    connection = conn_manager.get_connection(connection_name)

    if connection:
        tls_config = connection.get('TLS', {})
        return {
            "ok": True,
            "connection_name": connection_name,
            "enable_tls": tls_config.get('enable_tls', False),
            "tls_version": tls_config.get('tls_version'),
            "server_key": tls_config.get('server_key'),
            "server_cert": tls_config.get('server_cert'),
            "server_ca": tls_config.get('server_ca'),
            "ws_mode": connection.get('ws_mode')
        }

    return {
        "ok": False,
        "message": f"Connection '{connection_name}' not found"
    }


@app.post(
    "/api/connections/oauth-config",
    summary="Update OAuth Config for a specific connection",
    description="Update OAuth configuration for a connection.",
    response_description="Apply result",
    responses={
        200: {"description": "OAuth config updated successfully"},
        400: {"description": "Missing required fields"},
        404: {"description": "Connection not found"}
    },
    tags=["OAuth"]
)
async def create_oauth_connection(request: OAUTHConnectionCreateConfigRequest):
    """Update OAuth configuration for a connection.

    Request Body:
        OAUTHConnectionCreateConfigRequest with OAuth settings

    Returns:
        JSON with success status.

    Raises:
        HTTPException 400: If required fields are missing.
        HTTPException 404: If connection is not found.
    """
    connection = conn_manager.get_connection(request.connection_name)

    if connection:
        if 'OAuth' not in connection:
            connection['OAuth'] = {}
        
        connection['OAuth']['enable_oauth'] = request.enable_oauth
        
        # Store OAuth fields based on mode
        if request.ws_mode == "passive" or request.ws_mode == "Passive":
            # Server mode - store server OAuth config
            if request.certificate_endpoint_url:
                connection['OAuth']['certificate_endpoint'] = request.certificate_endpoint_url
            if request.token_issuer_url:
                connection['OAuth']['token_issuer'] = request.token_issuer_url
            if request.ca_certificate:
                connection['OAuth']['auth_server_ca'] = request.ca_certificate
            # Clear client-specific fields for server mode
            connection['OAuth'].pop('token_endpoint', None)
            connection['OAuth'].pop('client_id', None)
            connection['OAuth'].pop('client_secret', None)
            connection['OAuth'].pop('client_ca_cert', None)
        else:
            # Client mode - store client OAuth config
            if request.token_endpoint_url:
                connection['OAuth']['token_endpoint'] = request.token_endpoint_url
            if request.client_id:
                connection['OAuth']['client_id'] = request.client_id
            if request.client_secret:
                connection['OAuth']['client_secret'] = request.client_secret
            if request.ca_certificate:
                connection['OAuth']['auth_server_ca'] = request.ca_certificate
            if request.client_ca_cert:
                connection['OAuth']['client_ca_cert'] = request.client_ca_cert
            if request.enable_token_refresh is not None:
                connection['OAuth']['enable_token_refresh'] = request.enable_token_refresh
            # Clear server-specific fields for client mode
            connection['OAuth'].pop('certificate_endpoint', None)
            connection['OAuth'].pop('token_issuer', None)

        conn_manager.save_connections()

        return {
            "ok": True,
            "message": f"OAuth config saved for {request.connection_name}"
        }

    return {
        "ok": False,
        "message": "Connection not found"
    }


@app.get(
    "/api/connections/oauth-status",
    summary="Get OAuth Status for a specific connection",
    description="Retrieve the OAuth enable/disable status for a connection.",
    response_description="OAuth status",
    responses={
        200: {"description": "OAuth status returned successfully"},
        404: {"description": "Connection not found"}
    },
    tags=["OAuth"]
)
async def get_oauth_status(connection_name: str):
    """Get OAuth enable/disable status for a connection.

    Query Parameters:
        connection_name: Name of the connection to check

    Returns:
        JSON with enable_oauth status.

    Raises:
        HTTPException 404: If connection is not found.
    """
    connection = conn_manager.get_connection(connection_name)

    if connection:
        oauth_status = connection.get('OAuth', {}).get('enable_oauth', False)
        return {
            "ok": True,
            "connection_name": connection_name,
            "enable_oauth": oauth_status
        }

    return {
        "ok": False,
        "message": f"Connection '{connection_name}' not found"
    }


@app.get(
    "/api/connections/oauth-config",
    summary="Get OAuth Config for a specific connection",
    description="Retrieve the full OAuth configuration for a connection.",
    response_description="OAuth configuration",
    responses={
        200: {"description": "OAuth config returned successfully"},
        404: {"description": "Connection not found"}
    },
    tags=["OAuth"]
)
async def get_oauth_config(connection_name: str):
    """Get full OAuth configuration for a connection.

    Query Parameters:
        connection_name: Name of the connection to get config for

    Returns:
        JSON with full OAuth configuration including certificate_endpoint,
        token_issuer_url, client_id, client_secret, etc.

    Raises:
        HTTPException 404: If connection is not found.
    """
    connection = conn_manager.get_connection(connection_name)

    if connection:
        oauth_config = connection.get('OAuth', {})
        return {
            "ok": True,
            "connection_name": connection_name,
            "certificate_endpoint": oauth_config.get('certificate_endpoint'),
            "token_issuer_url": oauth_config.get('token_issuer'),
            "token_endpoint": oauth_config.get('token_endpoint'),
            "client_id": oauth_config.get('client_id'),
            "client_secret": oauth_config.get('client_secret'),
            "auth_server_ca": oauth_config.get('auth_server_ca'),
            "ca_certificate": oauth_config.get('ca_certificate'),
            "realm": oauth_config.get('realm'),
            "idp_server": oauth_config.get('idp_server'),
            "enable_oauth": oauth_config.get('enable_oauth', False),
            "enable_token_refresh": oauth_config.get('enable_token_refresh', False)
        }

    return {
        "ok": False,
        "message": f"Connection '{connection_name}' not found"
    }


@app.post(
    "/api/add-connection",
    summary="Create Connection",
    description="Create a new connection to a remote endpoint.",
    response_description="Created connection details",
    responses={
        201: {"description": "Connection created successfully"},
        400: {"description": "Missing required fields"}
    },
    tags=["Connections"]
)
async def create_connection(request: ConnectionCreateRequest):
    """Create a new connection to a remote RTI endpoint.
    
    Request Body:
        ConnectionCreateRequest with name, host, port, type
    
    Returns:
        JSON with the created connection details.
        
    Raises:
        HTTPException 400: If required fields are missing.
    """
    if not request.name or not request.type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Missing required fields: name, type'
        )
    
    # For IDP-Server, host and port are not required but endpoint is
    if request.type == 'IDP-Server':
        if not request.endpoint:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Missing required field: endpoint'
            )
    else:
        # For other types, host and port are required
        if not request.host or not request.port:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Missing required fields: host, port'
            )
    connection = conn_manager.add_connection(
        name=request.name,
        host=request.host,
        port=request.port,
        conn_type=request.type,
        acsi=request.acsi,
        ws_mode=request.ws_mode,
        endpoint=request.endpoint,
        certificate_endpoint=request.certificate_endpoint,
        auth_server_ca=request.auth_server_ca,
        realm=request.realm,
        token_endpoint=request.token_endpoint,
        client_id=request.client_id,
        client_secret=request.client_secret,
        enable_token_refresh=request.enable_token_refresh,
        idp_server=request.idp_server,
        auto_discovered=request.auto_discovered
    )
    conn_manager.save_connections()
    # Immediately probe the connection so its status is fresh right away instead
    # of showing "checking" until the background monitor runs.
    await conn_manager.check_connection(connection, conn_manager.get_client())

    return JSONResponse(content=connection, status_code=status.HTTP_201_CREATED)


@app.delete(
    "/api/delete-connection/{conn_name}",
    summary="Delete Connection",
    description="Delete an existing connection.",
    response_description="Deletion confirmation",
    responses={
        200: {"description": "Connection deleted successfully"},
        404: {"description": "Connection not found"}
    },
    tags=["Connections"]
)
async def delete_connection(conn_name: str):
    """Delete a connection by its ID.
    
    Path Parameters:
        conn_id: The ID of the connection to delete
    
    Returns:
        JSON with deletion status.
    """
    success = conn_manager.delete_connection(conn_name)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Connection not found'
        )
    return {'status': 'deleted'}


@app.put(
    "/api/edit-connection/{conn_name}",
    summary="Update Connection",
    description="Update an existing connection.",
    response_description="Updated connection details",
    responses={
        200: {"description": "Connection updated successfully"},
        404: {"description": "Connection not found"}
    },
    tags=["Connections"]
)
async def update_connection(conn_name: str, request: ConnectionUpdateRequest):
    """Update a connection by its ID.
    
    Path Parameters:
        conn_id: The ID of the connection to update
    
    Request Body:
        ConnectionUpdateRequest with fields to update
    
    Returns:
        JSON with the updated connection details.
        
    Raises:
        HTTPException 404: If connection is not found.
    """
    connection = conn_manager.get_connection(conn_name)
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Connection not found'
        )
    
    # Track old host:port for _bff_clients cleanup
    old_host = connection.get('host')
    old_port = connection.get('port')
    old_key = f"{old_host}:{old_port}" if old_host and old_port else None
    
    # Update fields from request
    if request.name is not None:
        connection['name'] = request.name
    if request.host is not None:
        connection['host'] = request.host
    if request.port is not None:
        connection['port'] = request.port
    if request.type is not None:
        connection['type'] = request.type
    if request.acsi is not None:
        connection['acsi'] = request.acsi
    if request.ws_mode is not None:
        connection['ws_mode'] = request.ws_mode
    if request.endpoint is not None:
        connection['endpoint'] = request.endpoint
    if request.status is not None:
        connection['status'] = request.status
    
    # Handle OAuth fields - nest them under OAuth object
    oauth_fields = {}
    if request.certificate_endpoint is not None:
        oauth_fields['certificate_endpoint'] = request.certificate_endpoint
    if request.token_issuer_url is not None:
        oauth_fields['token_issuer'] = request.token_issuer_url
    if request.auth_server_ca is not None:
        oauth_fields['auth_server_ca'] = request.auth_server_ca
    if request.realm is not None:
        oauth_fields['realm'] = request.realm
    if request.token_endpoint is not None:
        oauth_fields['token_endpoint'] = request.token_endpoint
    if request.client_id is not None:
        oauth_fields['client_id'] = request.client_id
    if request.client_secret is not None:
        oauth_fields['client_secret'] = request.client_secret
    if request.enable_token_refresh is not None:
        oauth_fields['enable_token_refresh'] = request.enable_token_refresh
    if request.idp_server is not None:
        oauth_fields['idp_server'] = request.idp_server
    
    # If we have OAuth fields, create/update the OAuth object
    if oauth_fields:
        if 'OAuth' not in connection:
            connection['OAuth'] = {}
        connection['OAuth'].update(oauth_fields)
    
    # Clean up any OAuth fields that were previously at top level
    top_level_oauth_fields = ['certificate_endpoint', 'auth_server_ca', 'realm', 
                               'token_endpoint', 'client_id', 'client_secret', 'enable_token_refresh', 'idp_server']
    for field in top_level_oauth_fields:
        if field in connection:
            del connection[field]
    
    # Update _bff_clients if host or port changed
    new_host = connection.get('host')
    new_port = connection.get('port')
    new_key = f"{new_host}:{new_port}" if new_host and new_port else None
    
    if old_key and new_key and old_key != new_key:
        # Remove old entry
        if old_key in _bff_clients:
            del _bff_clients[old_key]
        # Add new entry
        if new_key not in _bff_clients:
            _bff_clients[new_key] = BffClient(f"http://{new_host}:{new_port}")
    
    conn_manager.save_connections()
    
    return connection


# -------------------- Data Operations --------------------

@app.post(
    "/api/data/read",
    summary="Read Data",
    description="Read data from a connection.",
    response_description="Read value result",
    responses={
        200: {"description": "Data read successfully"},
        400: {"description": "Missing required fields or no connections configured"}
    },
    tags=["Data"]
)
async def read_data(request: DataReadRequest):
    """Read data from a remote endpoint.
    
    Request Body:
        DataReadRequest with objRef (object reference)
    
    Returns:
        JSON with objRef, value, type, and timestamp.
        If no connections are configured, returns mock data.
        
    Raises:
        HTTPException 400: If objRef is missing or no connections configured.
    """
    if not conn_manager.connections:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='No connections configured'
        )
    
    connection = conn_manager.connections[0]
    obj_ref = request.objRef
    
    # Call remote service
    result = data_manager.read_data(connection, obj_ref)
    
    if result:
        return {
            'objRef': obj_ref,
            'value': result.get('value'),
            'type': result.get('type'),
            'timestamp': datetime.now().isoformat()
        }
    else:
        # Return mock data for demonstration
        return {
            'objRef': obj_ref,
            'value': '42',
            'type': 'float',
            'timestamp': datetime.now().isoformat(),
            'source': 'mock'
        }


@app.post(
    "/api/data/write",
    summary="Write Data",
    description="Write data to a connection.",
    response_description="Write operation result",
    responses={
        200: {"description": "Data written successfully"},
        400: {"description": "Missing required fields or no connections configured"}
    },
    tags=["Data"]
)
async def write_data(request: DataWriteRequest):
    """Write data to a remote endpoint.
    
    Request Body:
        DataWriteRequest with objRef and value
    
    Returns:
        JSON with objRef, value, status, and timestamp.
        
    Raises:
        HTTPException 400: If objRef or value is missing, or no connections configured.
    """
    if not conn_manager.connections:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='No connections configured'
        )
    
    connection = conn_manager.connections[0]
    obj_ref = request.objRef
    value = request.value
    
    # Call remote service
    result = data_manager.write_data(connection, obj_ref, value)
    
    if result:
        return {
            'objRef': obj_ref,
            'value': value,
            'status': 'success',
            'timestamp': datetime.now().isoformat()
        }
    else:
        return {
            'objRef': obj_ref,
            'value': value,
            'status': 'success',
            'timestamp': datetime.now().isoformat(),
            'source': 'mock'
        }


# -------------------- Operate --------------------
@app.post(
    "/api/operate",
    summary="Operate on DO",
    description="Send Operate Command",
    response_description="Operate result",
    responses={
        200: {"description": "Command operated successfully"},
        400: {"description": "Missing required fields or no connections configured"}
    },
    tags=["Data"]
)
async def operate(request: DataWriteRequest):
    """Operate on a remote endpoint.

    Request Body:
        OperateRequest with objRef and value

    Returns:
        JSON with objRef, value, status, and timestamp.

    Raises:
        HTTPException 400: If objRef or value is missing, or no connections configured.
    """
    if not conn_manager.connections:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='No connections configured'
        )

    connection = conn_manager.connections[0]
    obj_ref = request.objRef
    value = request.value

    # Call remote service
    result = data_manager.operate(connection, obj_ref, value)

    if result:
        return {
            'objRef': obj_ref,
            'value': value,
            'status': 'success',
            'timestamp': datetime.now().isoformat()
        }
    else:
        return {
            'objRef': obj_ref,
            'value': value,
            'status': 'success',
            'timestamp': datetime.now().isoformat(),
            'source': 'mock'
        }


# -------------------- Dynamic API Execution --------------------

@app.post(
    "/api/execute",
    summary="Execute Dynamic API",
    description="Execute a dynamic API call against a registered target.",
    response_description="Execution result",
    responses={
        200: {"description": "API call executed successfully"},
        400: {"description": "Missing required parameters"},
        404: {"description": "Unknown target"},
        500: {"description": "API call failed"}
    },
    tags=["Execution"]
)
async def execute_dynamic_api(request: ExecuteRequest):
    """Execute a dynamic API call against a registered BFF target.
    
    This endpoint allows the frontend to dynamically call any API on a registered backend.
    
    Request Body:
        ExecuteRequest with target, path, method (default GET), and optional body
    
    Returns:
        JSON with execution result including target, method, path, and result.
        
    Raises:
        HTTPException 400: If target or path is missing.
        HTTPException 404: If target is not registered.
        HTTPException 500: If API call fails.
    """
    target = request.target
    method = request.method.upper()
    path = request.path
    body = request.body

    if not target or not path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="target and path are required"
        )

    # Special handling for OAuth reconfiguration
    # When HMI calls /reconfig-oauth, BFF needs to enrich the request with OAuth settings from connections.json
    if path == "/reconfig-oauth" and body and isinstance(body, dict):
        connection_name = body.get("connection_name")
        if connection_name:
            # Look up the connection
            connection = conn_manager.get_connection(connection_name)
            if connection:
                # Get OAuth config from connection
                oauth_config = connection.get("OAuth", {})
                
                # Extract cp from connection
                cp = connection.get("cp") or body.get("cp", "cp1")
                
                # Enrich the request body with OAuth fields from the connection
                # Only add fields that exist in the OAuth config and are not already in the body
                enriched_body = dict(body)
                
                # Add cp if not already present
                if "cp" not in enriched_body:
                    enriched_body["cp"] = cp
                
                # Add OAuth fields from connection if not already in body
                # Map connection field names to request field names
                oauth_fields = {
                    "token_endpoint_url": oauth_config.get("token_endpoint") or oauth_config.get("token_issuer"),
                    "certificate_endpoint_url": oauth_config.get("certificate_endpoint"),
                    "token_issuer_url": oauth_config.get("token_issuer"),
                    "client_id": oauth_config.get("client_id"),
                    "client_secret": oauth_config.get("client_secret"),
                    "ca_certificate": oauth_config.get("auth_server_ca"),
                    "enable_token_refresh": oauth_config.get("enable_token_refresh", False),
                }
                
                for field, value in oauth_fields.items():
                    # Only add if value exists and not already in body
                    if value is not None and field not in enriched_body:
                        enriched_body[field] = value
                
                body = enriched_body

    try:
        # Get client from registry
        client = _bff_clients.get(target)

        if not client:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Unknown target: {target}"
            )

        # Call API dynamically
        result = client.request(
            method=method,
            path=path,
            json=body
        )

        return {
            "ok": True,
            "target": target,
            "method": method,
            "path": path,
            "result": result
        }

    except Exception as e:

        print("failed to execute dynamic API call:", e)
        print("target:", target, "method:", method, "path:", path, "body:", body)
        logger.error(f"Dynamic API call failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# -------------------- Reports --------------------

@app.get(
    "/api/reports",
    summary="Get Reports",
    description="Get available reports.",
    response_description="List of available reports",
    responses={
        200: {"description": "Reports list returned successfully"}
    },
    tags=["Reports"]
)
async def get_reports():
    """Get a list of available reports.
    
    Returns:
        JSON with list of mock reports for demonstration.
    """
    mock_reports = [
        {
            'id': 1,
            'name': 'Connection Status Report',
            'description': 'Current status of all connections',
            'timestamp': datetime.now().isoformat()
        },
        {
            'id': 2,
            'name': 'Data Access Log',
            'description': 'Log of all data read/write operations',
            'timestamp': datetime.now().isoformat()
        },
        {
            'id': 3,
            'name': 'System Performance',
            'description': 'System metrics and performance data',
            'timestamp': datetime.now().isoformat()
        }
    ]
    
    return {'reports': mock_reports}


@app.post(
    "/api/reports/export",
    summary="Export Reports",
    description="Export reports data.",
    response_description="Exported reports data",
    responses={
        200: {"description": "Reports exported successfully"}
    },
    tags=["Reports"]
)
async def export_reports():
    """Export reports data including connections and summary.
    
    Returns:
        JSON with exported data including connections and reports.
    """
    export_data = {
        'exported_at': datetime.now().isoformat(),
        'connections': conn_manager.connections,
        'reports': [
            {
                'name': 'Export Summary',
                'timestamp': datetime.now().isoformat()
            }
        ]
    }
    
    return {'data': export_data, 'status': 'success'}


# -------------------- Statistics --------------------

@app.get(
    "/api/stats",
    summary="Get Statistics",
    description="Get system statistics.",
    response_description="System statistics",
    responses={
        200: {"description": "Statistics returned successfully"}
    },
    tags=["Stats"]
)
async def get_stats():
    """Get system statistics including report updates, BFF targets count, and uptime.
    
    Returns:
        JSON with system statistics.
    """
    return {
        'reportUpdates': 0,
        'bffTargets': len(conn_manager.connections),
        'totalRequests': 0,
        'uptime': '00:00:00'
    }


# ==================== Error Handling ====================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions and return JSON responses."""
    logger.error(f"HTTP error: {exc.status_code} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"ok": False, "error": exc.detail}
    )


@app.exception_handler(OSError)
async def storage_exception_handler(request: Request, exc: OSError):
    """Surface filesystem failures (e.g. a read-only connections.json) instead
    of collapsing them into a generic 500 with no detail. Covers
    PermissionError, read-only filesystem, and no-space-left errors raised
    while persisting connection changes."""
    logger.error(
        "Storage error on %s %s: %s", request.method, request.url.path, exc
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"ok": False, "error": f"Failed to persist data to disk: {exc}"},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    logger.error(f"Internal server error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"ok": False, "error": "Internal server error"}
    )


# ==================== Application Entry Point ====================

if __name__ == '__main__':
    import argparse
    import uvicorn

    _LOG_CHOICES = ["critical", "error", "warning", "info", "debug", "trace"]

    parser = argparse.ArgumentParser(description="RTI Demo BFF Server (FastAPI)")
    parser.add_argument(
        "--host",
        default=os.getenv("HOST", "0.0.0.0"),
        help="Host interface to bind (default: %(default)s, env: HOST)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", "5000")),
        help="Port to listen on (default: %(default)s, env: PORT)",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL", "info"),
        help="Log level: %s (default: %%(default)s, env: LOG_LEVEL)" % ", ".join(_LOG_CHOICES),
    )
    args = parser.parse_args()

    # Module scope already applied LOG_LEVEL from the environment at import.
    # Re-resolve here so an explicit --log-level on the command line wins, and
    # hand the same value to uvicorn so its own 'uvicorn'/'uvicorn.error'/
    # 'uvicorn.access' loggers follow suit.
    resolved = resolve_log_level(args.log_level)
    logging.getLogger().setLevel(resolved)
    uvicorn_log_level = args.log_level.lower()
    if uvicorn_log_level not in _LOG_CHOICES:
        uvicorn_log_level = logging.getLevelName(resolved).lower()

    logger.info(
        "Starting RTI Demo BFF Server (FastAPI) on %s:%d (log level %s)...",
        args.host, args.port, logging.getLevelName(resolved),
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level=uvicorn_log_level)
