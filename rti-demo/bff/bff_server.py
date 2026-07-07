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
from typing import Any, Dict, List, Optional, Tuple
import requests
import threading
import time
from urllib.parse import urlparse

from fastapi import FastAPI, Request, HTTPException, status, Body
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict

from bffClient import BffClient

# Global state
_bff_clients: Dict[str, BffClient] = {}

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Try to import docker for auto-discovery
DOCKER_AVAILABLE = False
try:
    import docker
    from docker import DockerClient
    DOCKER_AVAILABLE = True
except ImportError:
    logger.warning("Docker Python SDK not available. Container auto-discovery disabled.")

CONNECTIONS_FILE = '/app/connections.json'
STATS_FILE = 'stats.json'
DISCOVERED_FILE = 'discovered_endpoints.json'


# ==================== Pydantic Models ====================

class ConnectionCreateRequest(BaseModel):
    """Request body for creating a new connection."""
    name: str = Field(..., description="Human-readable name for the connection", json_schema_extra={"example": "RTI-FSP-01"})
    host: str = Field(..., description="Hostname or IP address of the endpoint", json_schema_extra={"example": "localhost"})
    port: int = Field(..., description="Port number of the endpoint", json_schema_extra={"example": 5000})
    type: str = Field(..., description="Type of the endpoint (e.g., RTI-FSP, RTI-SO)", json_schema_extra={"example": "RTI-FSP"})
    auto_discovered: bool = Field(default=False, description="Whether this connection was auto-discovered")


class ConnectionUpdateRequest(BaseModel):
    """Request body for updating an existing connection."""
    name: Optional[str] = Field(default=None, description="Human-readable name for the connection")
    host: Optional[str] = Field(default=None, description="Hostname or IP address of the endpoint")
    port: Optional[int] = Field(default=None, description="Port number of the endpoint")
    type: Optional[str] = Field(default=None, description="Type of the endpoint")
    status: Optional[str] = Field(default=None, description="Connection status")


class ExecuteRequest(BaseModel):
    """Request body for executing a dynamic API call."""
    target: str = Field(..., description="Target endpoint identifier (host:port)", json_schema_extra={"example": "localhost:5000"})
    method: str = Field(default="GET", description="HTTP method to use", json_schema_extra={"example": "GET"})
    path: str = Field(..., description="API path to call", json_schema_extra={"example": "/api/health"})
    body: Optional[Dict[str, Any]] = Field(default=None, description="Request body for POST/PUT requests")


class DataReadRequest(BaseModel):
    """Request body for reading data from an endpoint."""
    objRef: str = Field(..., description="Object reference in IEC61850 format", json_schema_extra={"example": "LD0/LLN0$ST$Mod"})


class DataWriteRequest(BaseModel):
    """Request body for writing data to an endpoint."""
    objRef: str = Field(..., description="Object reference in IEC61850 format", json_schema_extra={"example": "LD0/LLN0$ST$Mod"})
    value: str = Field(..., description="Value to write", json_schema_extra={"example": "ON"})


class DiscoveryRequest(BaseModel):
    """Request body for triggering service discovery."""
    host: Optional[str] = Field(default=None, description="Host to scan", json_schema_extra={"example": "localhost"})
    ports: Optional[List[int]] = Field(default=None, description="List of ports to scan")
    startPort: Optional[int] = Field(default=None, description="Start port for range scan", json_schema_extra={"example": 5000})
    endPort: Optional[int] = Field(default=None, description="End port for range scan", json_schema_extra={"example": 5010})


# ==================== Helper Functions ====================

def _register_bff_clients(discovered: Dict[str, Dict]) -> None:
    """Register BFF clients for discovered endpoints."""
    for ep in discovered.values():
        host = ep.get('host')
        port = ep.get('port')

        if not host or not port:
            continue

        key = f"{host}:{port}"
        base_url = f"http://{host}:{port}"

        if key not in _bff_clients:
            _bff_clients[key] = BffClient(base_url)


def get_bff_client_from_target(selector: str) -> Optional[BffClient]:
    """Get a BFF client by target selector."""
    return _bff_clients.get(selector)


def _endpoint_key(endpoint: Dict) -> Optional[str]:
    """Generate a unique key for an endpoint based on host and port."""
    host = endpoint.get('host')
    port = endpoint.get('port')
    if host is None or port is None:
        return None
    return f"{host}:{port}"


def load_discovered_endpoints() -> Dict[str, Dict]:
    """Load discovered endpoints from file."""
    if not os.path.exists(DISCOVERED_FILE):
        return {}

    try:
        with open(DISCOVERED_FILE, 'r') as f:
            data = json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load discovered endpoints: {e}")
        return {}

    if isinstance(data, dict):
        return data

    # Backward compatibility: accept list format and normalize to keyed dict.
    normalized: Dict[str, Dict] = {}
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                key = _endpoint_key(item)
                if key:
                    normalized[key] = item
    return normalized


def save_discovered_endpoints(discovered: Dict[str, Dict]) -> None:
    """Save discovered endpoints to file."""
    try:
        with open(DISCOVERED_FILE, 'w') as f:
            json.dump(discovered, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save discovered endpoints: {e}")


def _normalize_base_url(base_url: str) -> str:
    """Normalize a base URL by stripping trailing slashes."""
    return str(base_url or '').strip().rstrip('/')


def _base_url_to_host_port(base_url: str) -> Tuple[Optional[str], Optional[int]]:
    """Parse a base URL into host and port."""
    parsed = urlparse(base_url)
    if not parsed.scheme or not parsed.hostname:
        return None, None

    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == 'https' else 80
    return parsed.hostname, port


def _is_fsp_endpoint(endpoint: Dict) -> bool:
    """Check if an endpoint is an FSP (Front-end Server Platform) endpoint."""
    endpoint_type = str(endpoint.get('type', '')).upper()
    endpoint_name = str(endpoint.get('name', '')).upper()
    return (
        'FSP' in endpoint_type
        or 'SERVER' in endpoint_type
        or 'RTI-FSP' in endpoint_name
        or 'SERVER' in endpoint_name
    )


# ==================== Service Discovery ====================

class ServiceDiscovery:
    """Auto-discovers RTI services from Docker containers and network scanning."""
    
    def __init__(self) -> None:
        self.docker_enabled = os.getenv('RTI_DOCKER_ENABLED', 'false').lower() == 'true'
        self.client = None
        self.discovered_services: Dict[str, Dict] = load_discovered_endpoints()
        self.last_discovery: Optional[str] = None
        
        if self.docker_enabled and DOCKER_AVAILABLE:
            try:
                self.client = docker.from_env()
                logger.info("Docker client initialized for service discovery")
            except Exception as e:
                logger.warning(f"Failed to initialize Docker client: {e}")
                self.docker_enabled = False
    
    def discover_services(self) -> Dict[str, Dict]:
        """Discover RTI services from Docker containers.
        
        Returns:
            Dictionary of discovered services with their metadata.
        """
        if not self.docker_enabled or not self.client:
            return {}
        
        try:
            services: Dict[str, Dict] = {}
            containers = self.client.containers.list(filters={'status': 'running'})
            
            for container in containers:
                labels = container.labels or {}
                
                # Check if container has RTI service labels
                if 'rti.service' in labels:
                    service_name = labels['rti.service']
                    service_type = labels.get('rti.type', 'RTI-SO')
                    host = labels.get('rti.host', container.name)
                    port = int(labels.get('rti.port', 5000))
                    
                    # Check if service is healthy
                    status = 'disconnected'
                    try:
                        response = requests.get(
                            f"http://{host}:{port}/",
                            timeout=2
                        )
                        if response.status_code == 200:
                            status = 'connected'
                    except Exception:
                        status = 'disconnected'
                    
                    services[service_name] = {
                        'id': f"docker_{container.id[:12]}",
                        'name': service_name,
                        'type': service_type,
                        'host': host,
                        'port': port,
                        'status': status,
                        'docker_container': container.name,
                        'auto_discovered': True,
                        'created_at': datetime.now().isoformat()
                    }
            
            for service_info in services.values():
                key = _endpoint_key(service_info)
                if key:
                    self.discovered_services[key] = service_info

            self.last_discovery = datetime.now().isoformat()
            save_discovered_endpoints(self.discovered_services)
            logger.info(f"Discovered {len(services)} RTI services")
            return services
        
        except Exception as e:
            logger.error(f"Service discovery error: {e}")
            return {}
    
    def start_periodic_discovery(self, interval: int = 30) -> None:
        """Start periodic service discovery in background.
        
        Args:
            interval: Discovery interval in seconds.
        """
        if not self.docker_enabled:
            return
        
        def _discover() -> None:
            while True:
                try:
                    self.discover_services()
                    _register_bff_clients(self.discovered_services)
                except Exception as e:
                    logger.error(f"Periodic discovery error: {e}")
                time.sleep(interval)
        
        thread = threading.Thread(target=_discover, daemon=True)
        thread.start()
        logger.info(f"Service discovery started (interval: {interval}s)")


# Initialize service discovery
discovery = ServiceDiscovery()
discovery.discover_services()
_register_bff_clients(discovery.discovered_services)
discovery.start_periodic_discovery()


# ==================== Connection Management ====================

class ConnectionManager:
    """Manages connections to remote RTI endpoints."""
    
    def __init__(self) -> None:
        self.connections: List[Dict] = self.load_connections()
    
    def load_connections(self) -> List[Dict]:
        """Load connections from file."""
        if os.path.exists(CONNECTIONS_FILE):
            try:
                with open(CONNECTIONS_FILE, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading connections: {e}")
        return []
    
    def save_connections(self) -> None:
        """Save connections to file."""
        try:
            print("Writing connections:", self.connections)

            with open(CONNECTIONS_FILE, 'w') as f:
                json.dump(self.connections, f, indent=2)
            print("Finished writing")
        except Exception as e:
            logger.error(f"Error saving connections: {e}")
    
    def add_connection(self, name: str, host: str, port: int, conn_type: str, 
                      auto_discovered: bool = False) -> Dict:
        """Add a new connection.
        
        Args:
            name: Human-readable name for the connection
            host: Hostname or IP address
            port: Port number
            conn_type: Type of endpoint
            auto_discovered: Whether this connection was auto-discovered
            
        Returns:
            The created connection dictionary.
        """
        # Check if connection already exists
        existing = next((c for c in self.connections 
                        if c['host'] == host and c['port'] == port), None)
        if existing:
            logger.warning(f"Connection already exists: {host}:{port}")
            return existing
        
        connection = {
            'id': len(self.connections) + 1,
            'name': name,
            'host': host,
            'port': port,
            'type': conn_type,
            'status': 'disconnected',
            'auto_discovered': auto_discovered,
            'created_at': datetime.now().isoformat()
        }
        self.connections.append(connection)
        self.save_connections()
        logger.info(f"Connection added: {name} ({host}:{port})")
        return connection
    
    def delete_connection(self, conn_id: int) -> bool:
        """Delete a connection by ID.
        
        Args:
            conn_id: ID of the connection to delete
            
        Returns:
            True if connection was deleted, False otherwise.
        """
        original_count = len(self.connections)
        self.connections = [c for c in self.connections if c['id'] != conn_id]
        if len(self.connections) < original_count:
            self.save_connections()
            logger.info(f"Connection deleted: {conn_id}")
            return True
        return False
    
    def get_connection(self, conn_id: int) -> Optional[Dict]:
        """Get a specific connection by ID."""
        return next((c for c in self.connections if c['id'] == conn_id), None)
    
    def get_connection_by_host_port(self, host: str, port: int) -> Optional[Dict]:
        """Get connection by host and port."""
        return next((c for c in self.connections 
                    if c['host'] == host and c['port'] == port), None)
    
    def update_connection_status(self, conn_id: int, status: str) -> None:
        """Update connection status."""
        conn = self.get_connection(conn_id)
        if conn:
            conn['status'] = status
            self.save_connections()
    
    def auto_register_discovered(self, discovered: Dict[str, Dict]) -> int:
        """Auto-register discovered services as connections.
        
        Args:
            discovered: Dictionary of discovered services
            
        Returns:
            Number of services registered.
        """
        registered = 0
        for service_name, service_info in discovered.items():
            existing = self.get_connection_by_host_port(service_info['host'], 
                                                       service_info['port'])
            if not existing:
                self.add_connection(
                    name=service_info['name'],
                    host=service_info['host'],
                    port=service_info['port'],
                    conn_type=service_info['type'],
                    auto_discovered=True
                )
                registered += 1
        return registered


# ==================== Data Management ====================

class DataManager:
    """Manages data operations against remote endpoints."""
    
    def __init__(self, connection_manager: ConnectionManager) -> None:
        self.conn_manager = connection_manager
    
    def call_remote_service(self, connection: Dict, endpoint: str, method: str = 'GET', data: Optional[Dict] = None) -> Optional[Dict]:
        """Call a remote service endpoint.
        
        Args:
            connection: Connection dictionary
            endpoint: API endpoint path
            method: HTTP method
            data: Request body for POST requests
            
        Returns:
            Response JSON or None if error.
        """
        url = f"http://{connection['host']}:{connection['port']}{endpoint}"
        
        try:
            if method == 'GET':
                response = requests.get(url, timeout=20)
            elif method == 'POST':
                response = requests.post(url, json=data, timeout=20)
            else:
                return None
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"Remote service error: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Error calling remote service: {e}")
            return None
    
    def read_data(self, connection: Dict, obj_ref: str) -> Optional[Dict]:
        """Read data from a remote endpoint."""
        return self.call_remote_service(connection, f'/api/data/{obj_ref}', 'GET')
    
    def write_data(self, connection: Dict, obj_ref: str, value: str) -> Optional[Dict]:
        """Write data to a remote endpoint."""
        return self.call_remote_service(connection, f'/api/data/{obj_ref}', 'POST', {'value': value})


# Initialize managers
conn_manager = ConnectionManager()
data_manager = DataManager(conn_manager)


# ==================== Discovery Helper Functions ====================
def _discover_service_on_host_port(host: str, port: int) -> Optional[Dict]:
    """Probe a host:port and return endpoint metadata for ANY HTTP service."""
    base_url = f"http://{host}:{port}"

    # Try known RTI endpoints first (for proper typing)
    rti_paths = [
        ('/api/health', 'BFF'),
        ('/', 'RTI-SERVICE'),
    ]

    for path, default_type in rti_paths:
        try:
            response = requests.get(f"{base_url}{path}", timeout=1.0)
            if response.status_code < 400:
                # It's an RTI service - identify it
                service_type = default_type
                if path == '/api/health':
                    try:
                        data = response.json()
                        service = str(data.get('service', '')).upper()
                        if service in ('FSP', 'BFF', 'SO'):
                            service_type = f"RTI-{service}" if service != 'BFF' else 'BFF'
                    except (ValueError, TypeError):
                        pass
                return {
                    'id': f"scan_{host}_{port}",
                    'name': f"{service_type}-{host}:{port}",
                    'type': service_type,
                    'host': host,
                    'port': port,
                    'status': 'connected',
                    'auto_discovered': True,
                    'discovery_method': 'network_scan',
                    'health_path': path,
                    'created_at': datetime.now().isoformat(),
                }
        except Exception:
            continue

    # Fallback: Check for ANY HTTP service (even non-RTI)
    try:
        response = requests.get(base_url, timeout=1.0)
        if response.status_code < 500:  # Accept 404 as "service exists"
            return {
                'id': f"scan_{host}_{port}",
                'name': f"HTTP-{host}:{port}",
                'type': 'HTTP',
                'host': host,
                'port': port,
                'status': 'connected' if response.status_code < 400 else 'unknown',
                'auto_discovered': True,
                'discovery_method': 'network_scan',
                'health_path': '/',
                'created_at': datetime.now().isoformat(),
            }
    except Exception:
        pass

    return None

def discover_services_by_network(host: str, ports: List[int]) -> Dict[str, Dict]:
    """Discover reachable services on a specific host across selected ports.
    
    Args:
        host: Hostname or IP address to scan
        ports: List of ports to scan
        
    Returns:
        Dictionary of discovered services keyed by "host:port".
    """
    services: Dict[str, Dict] = {}
    for port in ports:
        service = _discover_service_on_host_port(host, port)
        if service:
            services[f"{host}:{port}"] = service
    return services


def _extract_scan_params(payload: Optional[Dict]) -> Tuple[str, List[int]]:
    """Extract scan parameters from request payload.
    
    Args:
        payload: Request body dictionary
        
    Returns:
        Tuple of (host, list of ports).
    """
    host = str((payload or {}).get('host', '')).strip()

    ports: List[int] = []
    provided_ports = (payload or {}).get('ports')
    if isinstance(provided_ports, list):
        for value in provided_ports:
            try:
                port = int(value)
                if 1 <= port <= 65535:
                    ports.append(port)
            except (TypeError, ValueError):
                continue
    else:
        start = (payload or {}).get('startPort')
        end = (payload or {}).get('endPort')
        if start is not None and end is not None:
            try:
                start_port = int(start)
                end_port = int(end)
                if start_port > end_port:
                    start_port, end_port = end_port, start_port
                if end_port - start_port <= 200:
                    ports = [p for p in range(start_port, end_port + 1) if 1 <= p <= 65535]
            except (TypeError, ValueError):
                ports = []

    return host, sorted(set(ports))


def _upsert_discovered_cache(discovered: Dict[str, Dict]) -> None:
    """Update the discovered endpoints cache."""
    for service_info in discovered.values():
        key = _endpoint_key(service_info)
        if key:
            discovery.discovered_services[key] = service_info
    save_discovered_endpoints(discovery.discovered_services)


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


# ==================== FastAPI Application Setup ====================

# Create FastAPI application
app = FastAPI(
    title="RTI Demo BFF Server",
    description="Backend for Frontend (BFF) server for RTI Demo. Provides service discovery, connection management, data operations, and proxy capabilities for RTI services.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
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
            "description": "Read and write data to IEC61850 endpoints"
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
    """Get the health status of the BFF server and its registered targets.
    
    Returns:
        JSON with BFF status, list of targets, and their reachability status.
    """
    try:
        # BFF self status
        bff_status = {
            "status": "ok",
            "service": "BFF",
        }

        # Known clients (registered)
        targets = []
        for key in _bff_clients.keys():
            status = "unknown"
            try:
                client = _bff_clients[key]
                client.request("GET", "/api/health")
                status = "reachable"
            except Exception:
                status = "unreachable"
            
            targets.append({
                "target": key,
                "status": status
            })

        return {
            "ok": True,
            "bff": bff_status,
            "targets": targets,
            "count": len(targets)
        }

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


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
    if discovery.docker_enabled:
        discovery.discover_services()
        _register_bff_clients(discovery.discovered_services)

    endpoints = list(conn_manager.connections)
    discovered = dict(discovery.discovered_services)

    # Add discovered services not already present in manual connections.
    for service_info in discovered.values():
        exists = any(e['host'] == service_info['host'] and e['port'] == service_info['port'] for e in endpoints)
        if not exists:
            endpoints.append(service_info)

    # Enrich every endpoint with its own server/client properties payload when reachable.
    for endpoint in endpoints:
        endpoint['properties_info'] = _fetch_endpoint_properties(endpoint)

    return {
        'endpoints': endpoints,
        'count': len(endpoints),
        'discovered_count': len(discovered),
        'last_discovery': discovery.last_discovery,
        'docker_enabled': discovery.docker_enabled
    }


@app.get(
    "/api/endpoints/discovered",
    summary="Get Discovered Endpoints",
    description="Get only cached auto-discovered endpoints.",
    response_description="List of auto-discovered endpoints",
    responses={
        200: {"description": "Discovered endpoints returned successfully"}
    },
    tags=["Endpoints"]
)
async def get_discovered_endpoints():
    """Retrieve only auto-discovered endpoints.
    
    Returns:
        JSON with discovered endpoints, count, and last discovery timestamp.
    """
    if discovery.docker_enabled:
        discovery.discover_services()
        _register_bff_clients(discovery.discovered_services)

    discovered = dict(discovery.discovered_services)
    return {
        'discovered': discovered,
        'count': len(discovered),
        'last_discovery': discovery.last_discovery
    }


@app.post(
    "/api/endpoints/discover",
    summary="Trigger Discovery",
    description="Manually trigger service discovery (Docker and/or network scan).",
    response_description="Discovery results",
    responses={
        200: {"description": "Discovery completed successfully"}
    },
    tags=["Endpoints"]
)
async def trigger_discovery(request: DiscoveryRequest):
    """Trigger service discovery using Docker and/or network scanning.
    
    The request body can specify host and ports for network scanning.
    If Docker is enabled, it will also scan for Docker containers.
    
    Request Body:
        DiscoveryRequest with optional host, ports, startPort, endPort
    
    Returns:
        JSON with discovery status, discovered services, and count.
    """
    payload = request.model_dump()
    discovered = discovery.discover_services()
    _register_bff_clients(discovery.discovered_services)

    # Optionally scan using host/ports provided by HMI payload.
    host, ports = _extract_scan_params(payload)
    if host and ports:
        network_discovered = discover_services_by_network(host, ports)
        discovered.update(network_discovered)

    if discovered:
        _upsert_discovered_cache(discovered)

    return {
        'status': 'success',
        'discovered': discovered,
        'count': len(discovered)
    }


@app.post(
    "/api/endpoints/discover-network",
    summary="Network Discovery",
    description="Discover endpoints on a given host and list/range of ports supplied by HMI.",
    response_description="Network discovery results",
    responses={
        200: {"description": "Network discovery completed successfully"},
        400: {"description": "Missing required parameters"}
    },
    tags=["Endpoints"]
)
async def trigger_network_discovery(request: DiscoveryRequest):
    """Discover endpoints on a specific host and port range.
    
    Request Body:
        DiscoveryRequest with host and either ports list or startPort/endPort range
    
    Returns:
        JSON with discovery results including found services.
        
    Raises:
        HTTPException 400: If host or ports are not provided.
    """
    payload = request.model_dump()
    host, ports = _extract_scan_params(payload)

    if not host:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='host is required.'
        )
    if not ports:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Provide ports or startPort/endPort.'
        )

    discovered = discover_services_by_network(host, ports)
    if discovered:
        _upsert_discovered_cache(discovered)
        _register_bff_clients(discovered)

    return {
        'ok': True,
        'status': 'success',
        'discovery_method': 'network_scan',
        'host': host,
        'ports': ports,
        'discovered': discovered,
        'count': len(discovered),
        'timestamp': datetime.now().isoformat(),
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
    return {
        'connections': conn_manager.connections,
        'count': len(conn_manager.connections)
    }

@app.post(
    "/api/connections",
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
    if not request.name or not request.host or not request.port or not request.type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Missing required fields: name, host, port, type'
        )
    connection = conn_manager.add_connection(
        name=request.name,
        host=request.host,
        port=request.port,
        conn_type=request.type,
        auto_discovered=request.auto_discovered
    )
    conn_manager.save_connections()
    print("Connection created:", connection)
    print("len connections:", len(conn_manager.connections))

    
    return JSONResponse(content=connection, status_code=status.HTTP_201_CREATED)


@app.delete(
    "/api/connections/{conn_id}",
    summary="Delete Connection",
    description="Delete an existing connection.",
    response_description="Deletion confirmation",
    responses={
        200: {"description": "Connection deleted successfully"},
        404: {"description": "Connection not found"}
    },
    tags=["Connections"]
)
async def delete_connection(conn_id: int):
    """Delete a connection by its ID.
    
    Path Parameters:
        conn_id: The ID of the connection to delete
    
    Returns:
        JSON with deletion status.
    """
    success = conn_manager.delete_connection(conn_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Connection not found'
        )
    return {'status': 'deleted'}


@app.put(
    "/api/connections/{conn_id}",
    summary="Update Connection",
    description="Update an existing connection.",
    response_description="Updated connection details",
    responses={
        200: {"description": "Connection updated successfully"},
        404: {"description": "Connection not found"}
    },
    tags=["Connections"]
)
async def update_connection(conn_id: int, request: ConnectionUpdateRequest):
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
    connection = conn_manager.get_connection(conn_id)
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Connection not found'
        )
    
    # Update fields from request
    if request.name is not None:
        connection['name'] = request.name
    if request.host is not None:
        connection['host'] = request.host
    if request.port is not None:
        connection['port'] = request.port
    if request.type is not None:
        connection['type'] = request.type
    if request.status is not None:
        connection['status'] = request.status
    
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
    import uvicorn
    logger.info("Starting RTI Demo BFF Server (FastAPI)...")
    uvicorn.run(app, host='0.0.0.0', port=5000)
