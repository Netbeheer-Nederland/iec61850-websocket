"""
RTI Demo BFF (Backend For Frontend) Server
==========================================
This server acts as a middleware between the frontend UI and backend services.
It provides endpoints for the frontend to:
- Manage connections to remote IEC 61850 endpoints
- Read/write data
- Get device information
- Handle reports
- Auto-discover Docker containers with RTI services
"""

from flask import Flask, request, jsonify, Response, has_request_context
from flask_cors import CORS
from datetime import datetime
import json
import os
import logging
from typing import Dict, List, Optional, Tuple
import requests
import threading
import time
from urllib.parse import urlparse
from fspClient import FspClient
from soClient import SOClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Try to import docker for auto-discovery
DOCKER_AVAILABLE = False
docker_client = None
try:
    import docker
    from docker import DockerClient
    DOCKER_AVAILABLE = True
except ImportError:
    logger.warning("Docker Python SDK not available. Container auto-discovery disabled.")

app = Flask(__name__)
CORS(app)

# Data storage (in production, use a database)
CONNECTIONS_FILE = 'connections.json'
STATS_FILE = 'stats.json'
DISCOVERED_FILE = 'discovered_endpoints.json'


def _endpoint_key(endpoint: Dict) -> Optional[str]:
    host = endpoint.get('host')
    port = endpoint.get('port')
    if host is None or port is None:
        return None
    return f"{host}:{port}"


def load_discovered_endpoints() -> Dict[str, Dict]:
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


def save_discovered_endpoints(discovered: Dict[str, Dict]):
    try:
        with open(DISCOVERED_FILE, 'w') as f:
            json.dump(discovered, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save discovered endpoints: {e}")


# Initialize FSP client (point to the RTI server container)
FSP_BASE_URL = os.environ.get('FSP_BASE_URL', 'http://rti-server:5001')
_fsp_client_cache: Dict[str, FspClient] = {}


def _normalize_base_url(base_url: str) -> str:
    return str(base_url or '').strip().rstrip('/')


def _base_url_to_host_port(base_url: str) -> Tuple[Optional[str], Optional[int]]:
    parsed = urlparse(base_url)
    if not parsed.scheme or not parsed.hostname:
        return None, None

    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == 'https' else 80
    return parsed.hostname, port


def _is_fsp_endpoint(endpoint: Dict) -> bool:
    endpoint_type = str(endpoint.get('type', '')).upper()
    endpoint_name = str(endpoint.get('name', '')).upper()
    return (
        'FSP' in endpoint_type
        or 'SERVER' in endpoint_type
        or 'RTI-FSP' in endpoint_name
        or 'SERVER' in endpoint_name
    )


def _collect_fsp_targets() -> List[Dict]:
    targets: Dict[str, Dict] = {}

    default_base = _normalize_base_url(FSP_BASE_URL)
    default_host, default_port = _base_url_to_host_port(default_base)
    if default_host is not None and default_port is not None:
        key = f"{default_host}:{default_port}"
        targets[key] = {
            'id': key,
            'name': f"Default FSP ({key})",
            'host': default_host,
            'port': default_port,
            'base_url': default_base,
            'source': 'env',
        }

    conn_manager_instance = globals().get('conn_manager')
    if conn_manager_instance is not None:
        for endpoint in getattr(conn_manager_instance, 'connections', []):
            if not isinstance(endpoint, dict) or not _is_fsp_endpoint(endpoint):
                continue

            host = endpoint.get('host')
            port = endpoint.get('port')
            if host is None or port is None:
                continue

            key = f"{host}:{port}"
            targets[key] = {
                'id': key,
                'name': endpoint.get('name') or f"FSP ({key})",
                'host': host,
                'port': int(port),
                'base_url': f"http://{host}:{int(port)}",
                'source': 'connections',
                'type': endpoint.get('type'),
                'status': endpoint.get('status'),
            }

    discovery_instance = globals().get('discovery')
    if discovery_instance is not None:
        for endpoint in getattr(discovery_instance, 'discovered_services', {}).values():
            if not isinstance(endpoint, dict) or not _is_fsp_endpoint(endpoint):
                continue

            host = endpoint.get('host')
            port = endpoint.get('port')
            if host is None or port is None:
                continue

            key = f"{host}:{port}"
            existing = targets.get(key, {})
            targets[key] = {
                'id': key,
                'name': endpoint.get('name') or existing.get('name') or f"FSP ({key})",
                'host': host,
                'port': int(port),
                'base_url': f"http://{host}:{int(port)}",
                'source': existing.get('source', 'discovery'),
                'type': endpoint.get('type', existing.get('type')),
                'status': endpoint.get('status', existing.get('status')),
            }

    return list(targets.values())


def _extract_fsp_selector() -> Optional[str]:
    if not has_request_context():
        return None

    selector = request.args.get('fspTarget') or request.headers.get('X-FSP-Target')
    if selector:
        return str(selector).strip()

    payload = request.get_json(silent=True) or {}
    if isinstance(payload, dict) and payload.get('fspTarget'):
        return str(payload.get('fspTarget')).strip()

    return None


def _resolve_fsp_target(selector: Optional[str]) -> Dict:
    targets = _collect_fsp_targets()
    if not targets:
        return {
            'id': 'default',
            'name': 'Default FSP',
            'base_url': _normalize_base_url(FSP_BASE_URL),
            'source': 'env',
        }

    if not selector:
        return targets[0]

    selector_norm = selector.strip().lower()
    for target in targets:
        if selector_norm in {
            str(target.get('id', '')).lower(),
            str(target.get('base_url', '')).lower(),
            f"{target.get('host')}:{target.get('port')}".lower(),
        }:
            return target

    return targets[0]


def _get_fsp_client_for_target(base_url: str) -> FspClient:
    normalized = _normalize_base_url(base_url)
    cached = _fsp_client_cache.get(normalized)
    if cached is None:
        cached = FspClient(normalized)
        _fsp_client_cache[normalized] = cached
    return cached


class RequestScopedFspClient:
    """Dispatches FSP calls to a selected target from request context when provided."""

    def selected_target(self) -> Dict:
        selector = _extract_fsp_selector()
        return _resolve_fsp_target(selector)

    def selected_base_url(self) -> str:
        target = self.selected_target()
        return str(target.get('base_url') or _normalize_base_url(FSP_BASE_URL))

    def _selected_client(self) -> FspClient:
        return _get_fsp_client_for_target(self.selected_base_url())

    def __getattr__(self, item):
        return getattr(self._selected_client(), item)


fsp_client = RequestScopedFspClient()

SO_BASE_URL = os.environ.get('SO_BASE_URL', 'http://rti-client:5002')
so_client = SOClient(SO_BASE_URL)

# Service discovery
class ServiceDiscovery:
    """Auto-discovers RTI services from Docker containers"""
    
    def __init__(self):
        self.docker_enabled = os.getenv('RTI_DOCKER_ENABLED', 'false').lower() == 'true'
        self.client = None
        self.discovered_services = load_discovered_endpoints()
        self.last_discovery = None
        
        if self.docker_enabled and DOCKER_AVAILABLE:
            try:
                self.client = docker.from_env()
                logger.info("Docker client initialized for service discovery")
            except Exception as e:
                logger.warning(f"Failed to initialize Docker client: {e}")
                self.docker_enabled = False
    
    def discover_services(self) -> Dict[str, Dict]:
        """Discover RTI services from Docker containers"""
        if not self.docker_enabled or not self.client:
            return {}
        
        try:
            services = {}
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
                    except:
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
    
    def start_periodic_discovery(self, interval: int = 30):
        """Start periodic service discovery in background"""
        if not self.docker_enabled:
            return
        
        def _discover():
            while True:
                try:
                    self.discover_services()
                except Exception as e:
                    logger.error(f"Periodic discovery error: {e}")
                time.sleep(interval)
        
        thread = threading.Thread(target=_discover, daemon=True)
        thread.start()
        logger.info(f"Service discovery started (interval: {interval}s)")

# Initialize service discovery
discovery = ServiceDiscovery()
discovery.discover_services()
discovery.start_periodic_discovery()

class ConnectionManager:
    """Manages connections to remote endpoints"""
    
    def __init__(self):
        self.connections = self.load_connections()
    
    def load_connections(self) -> List[Dict]:
        """Load connections from file"""
        if os.path.exists(CONNECTIONS_FILE):
            try:
                with open(CONNECTIONS_FILE, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading connections: {e}")
        return []
    
    def save_connections(self):
        """Save connections to file"""
        try:
            with open(CONNECTIONS_FILE, 'w') as f:
                json.dump(self.connections, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving connections: {e}")
    
    def add_connection(self, name: str, host: str, port: int, conn_type: str, 
                      auto_discovered: bool = False) -> Dict:
        """Add a new connection"""
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
        """Delete a connection"""
        original_count = len(self.connections)
        self.connections = [c for c in self.connections if c['id'] != conn_id]
        if len(self.connections) < original_count:
            self.save_connections()
            logger.info(f"Connection deleted: {conn_id}")
            return True
        return False
    
    def get_connection(self, conn_id: int) -> Optional[Dict]:
        """Get a specific connection"""
        return next((c for c in self.connections if c['id'] == conn_id), None)
    
    def get_connection_by_host_port(self, host: str, port: int) -> Optional[Dict]:
        """Get connection by host and port"""
        return next((c for c in self.connections 
                    if c['host'] == host and c['port'] == port), None)
    
    def update_connection_status(self, conn_id: int, status: str):
        """Update connection status"""
        conn = self.get_connection(conn_id)
        if conn:
            conn['status'] = status
            self.save_connections()
    
    def auto_register_discovered(self, discovered: Dict[str, Dict]) -> int:
        """Auto-register discovered services as connections"""
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

class DataManager:
    """Manages data operations"""
    
    def __init__(self, connection_manager: ConnectionManager):
        self.conn_manager = connection_manager
    
    def call_remote_service(self, connection: Dict, endpoint: str, method: str = 'GET', data: Dict = None) -> Optional[Dict]:
        """Call a remote service"""
        url = f"http://{connection['host']}:{connection['port']}{endpoint}"
        
        try:
            if method == 'GET':
                response = requests.get(url, timeout=5)
            elif method == 'POST':
                response = requests.post(url, json=data, timeout=5)
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
        """Read data from a remote endpoint"""
        return self.call_remote_service(connection, f'/api/data/{obj_ref}', 'GET')
    
    def write_data(self, connection: Dict, obj_ref: str, value: str) -> Optional[Dict]:
        """Write data to a remote endpoint"""
        return self.call_remote_service(connection, f'/api/data/{obj_ref}', 'POST', {'value': value})

# Initialize managers
conn_manager = ConnectionManager()
data_manager = DataManager(conn_manager)

# =============================================
# Health & Status Endpoints
# =============================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint that also reports downstream FSP health when available."""
    fsp_reachable = False
    fsp_details = None
    fsp_error = None

    try:
        fsp_details = fsp_client.health()
        fsp_reachable = True
    except requests.exceptions.RequestException as e:
        fsp_error = str(e)

    return jsonify({
        'status': 'ok',
        'bff': {
            'status': 'ok',
            'connected': True,
            'version': '1.0.0'
        },
        'fsp': {
            'reachable': fsp_reachable,
            'details': fsp_details,
            'error': fsp_error,
        },
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0'
    })

# =============================================
# Endpoints Management
# =============================================

def _discover_service_on_host_port(host: str, port: int) -> Optional[Dict]:
    """Probe a host:port using known health endpoints and return endpoint metadata if reachable."""
    candidates = [
        ('/api/health', 'BFF'),
        ('/', 'RTI-SERVICE'),
    ]

    for path, service_type in candidates:
        url = f"http://{host}:{port}{path}"
        try:
            response = requests.get(url, timeout=1.0)
            if response.status_code >= 400:
                continue

            detected_type = service_type
            if path == '/api/health':
                try:
                    payload = response.json()
                    declared_service = str(payload.get('service', '')).upper()
                    if declared_service == 'FSP':
                        detected_type = 'RTI-FSP'
                    elif declared_service == 'BFF':
                        detected_type = 'BFF'
                except ValueError:
                    pass

            return {
                'id': f"scan_{host}_{port}",
                'name': f"{detected_type}-{host}:{port}",
                'type': detected_type,
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

    return None


def discover_services_by_network(host: str, ports: List[int]) -> Dict[str, Dict]:
    """Discover reachable services on a specific host across selected ports."""
    services: Dict[str, Dict] = {}
    for port in ports:
        service = _discover_service_on_host_port(host, port)
        if service:
            services[f"{host}:{port}"] = service
    return services


def _extract_scan_params(payload: Dict) -> tuple[str, List[int]]:
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


def _upsert_discovered_cache(discovered: Dict[str, Dict]):
    for service_info in discovered.values():
        key = _endpoint_key(service_info)
        if key:
            discovery.discovered_services[key] = service_info
    save_discovered_endpoints(discovery.discovered_services)


def _fetch_endpoint_properties(endpoint: Dict) -> Dict:
    """Fetch endpoint properties from server/client properties APIs when available."""
    host = endpoint.get('host')
    port = endpoint.get('port')
    endpoint_type = str(endpoint.get('type', '')).upper()

    if not host or not port:
        return {'available': False, 'error': 'missing host or port'}

    # Prefer a probe order based on type, but try both paths for compatibility.
    if 'SO' in endpoint_type or 'CLIENT' in endpoint_type:
        paths = ['/api/iec61850client/properties', '/api/iec61850server/properties']
    elif 'FSP' in endpoint_type or 'SERVER' in endpoint_type:
        paths = ['/api/iec61850server/properties', '/api/iec61850client/properties']
    else:
        paths = ['/api/iec61850server/properties', '/api/iec61850client/properties']

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

@app.route('/api/endpoints', methods=['GET'])
def get_endpoints():
    """Get all configured endpoints (including cached auto-discovered)."""
    # Keep Docker-discovery cache fresh when enabled.
    if discovery.docker_enabled:
        discovery.discover_services()

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

    return jsonify({
        'endpoints': endpoints,
        'count': len(endpoints),
        'discovered_count': len(discovered),
        'last_discovery': discovery.last_discovery,
        'docker_enabled': discovery.docker_enabled
    })

@app.route('/api/endpoints/discovered', methods=['GET'])
def get_discovered_endpoints():
    """Get only cached auto-discovered endpoints."""
    if discovery.docker_enabled:
        discovery.discover_services()

    discovered = dict(discovery.discovered_services)
    return jsonify({
        'discovered': discovered,
        'count': len(discovered),
        'last_discovery': discovery.last_discovery
    })

@app.route('/api/endpoints/discover', methods=['POST'])
def trigger_discovery():
    """Manually trigger service discovery (Docker and/or network scan)."""
    payload = request.get_json(silent=True) or {}
    discovered = discovery.discover_services()

    # Optionally scan using host/ports provided by HMI payload.
    host, ports = _extract_scan_params(payload)
    if host and ports:
        network_discovered = discover_services_by_network(host, ports)
        discovered.update(network_discovered)

    if discovered:
        _upsert_discovered_cache(discovered)

    return jsonify({
        'status': 'success',
        'discovered': discovered,
        'count': len(discovered)
    })


@app.route('/api/endpoints/discover-network', methods=['POST'])
def trigger_network_discovery():
    """Discover endpoints on a given host and list/range of ports supplied by HMI."""
    payload = request.get_json(silent=True) or {}
    host, ports = _extract_scan_params(payload)

    if not host:
        return jsonify({'ok': False, 'error': 'host is required.'}), 400
    if not ports:
        return jsonify({'ok': False, 'error': 'Provide ports or startPort/endPort.'}), 400

    discovered = discover_services_by_network(host, ports)
    if discovered:
        _upsert_discovered_cache(discovered)

    return jsonify({
        'ok': True,
        'status': 'success',
        'discovery_method': 'network_scan',
        'host': host,
        'ports': ports,
        'discovered': discovered,
        'count': len(discovered),
        'timestamp': datetime.now().isoformat(),
    })


@app.route('/api/fsp/targets', methods=['GET'])
def list_fsp_targets():
    """List available FSP targets and which one is currently selected for this request."""
    targets = _collect_fsp_targets()
    selected = _resolve_fsp_target(_extract_fsp_selector())
    return jsonify({
        'ok': True,
        'targets': targets,
        'count': len(targets),
        'selected': selected,
    })

# =============================================
# Connections Management
# =============================================

@app.route('/api/connections', methods=['GET'])
def get_connections():
    """Get all connections"""
    try:
        fsp_payload = fsp_client.connections()

        # FSP returned an error envelope
        if not fsp_payload.get('ok', False):
            return jsonify({
                'ok': False,
                'error': fsp_payload.get('error', 'unknown FSP error'),
                'local_connections': conn_manager.connections,
            }), 502

        # Success: forward FSP fields + add BFF-local connections
        return jsonify({
            'ok': True,
            'server_role': fsp_payload.get('server_role'),
            'ws_mode': fsp_payload.get('ws_mode'),
            'connected_clients': fsp_payload.get('connected_clients', 0),
            'connections': fsp_payload.get('connections', []),
            'local_connections': conn_manager.connections,
            'timestamp': datetime.now().isoformat(),
        }), 200

    except requests.exceptions.RequestException as e:
        logger.warning(f"FSP get connections failed: {e}")
        return jsonify({
            'ok': False,
            'error': f'FSP unreachable: {e}',
            'local_connections': conn_manager.connections,
        }), 502

@app.route('/api/connections', methods=['POST'])
def create_connection():
    """Create a new connection"""
    data = request.get_json()
    
    required_fields = ['name', 'host', 'port', 'type']
    if not all(field in data for field in required_fields):
        return jsonify({'error': 'Missing required fields'}), 400
    
    connection = conn_manager.add_connection(
        name=data['name'],
        host=data['host'],
        port=int(data['port']),
        conn_type=data['type']
    )
    
    return jsonify(connection), 201

@app.route('/api/connections/<int:conn_id>', methods=['DELETE'])
def delete_connection(conn_id):
    """Delete a connection"""
    conn_manager.delete_connection(conn_id)
    return jsonify({'status': 'deleted'}), 200

@app.route('/api/connections/<int:conn_id>', methods=['PUT'])
def update_connection(conn_id):
    """Update a connection"""
    connection = conn_manager.get_connection(conn_id)
    if not connection:
        return jsonify({'error': 'Connection not found'}), 404
    
    data = request.get_json()
    connection.update(data)
    conn_manager.save_connections()
    
    return jsonify(connection), 200

# =============================================
# Data Operations
# =============================================

@app.route('/api/data/read', methods=['POST'])
def read_data():
    """Read data from a connection"""
    data = request.get_json()
    
    if 'objRef' not in data:
        return jsonify({'error': 'objRef is required'}), 400
    
    # Use first connected endpoint (in production, allow specifying which connection)
    if not conn_manager.connections:
        return jsonify({'error': 'No connections configured'}), 400
    
    connection = conn_manager.connections[0]
    obj_ref = data['objRef']
    
    # Call remote service
    result = data_manager.read_data(connection, obj_ref)
    
    if result:
        return jsonify({
            'objRef': obj_ref,
            'value': result.get('value'),
            'type': result.get('type'),
            'timestamp': datetime.now().isoformat()
        })
    else:
        # Return mock data for demonstration
        return jsonify({
            'objRef': obj_ref,
            'value': '42',
            'type': 'float',
            'timestamp': datetime.now().isoformat(),
            'source': 'mock'
        })

@app.route('/api/data/write', methods=['POST'])
def write_data():
    """Write data to a connection"""
    data = request.get_json()
    
    required = ['objRef', 'value']
    if not all(field in data for field in required):
        return jsonify({'error': 'objRef and value are required'}), 400
    
    if not conn_manager.connections:
        return jsonify({'error': 'No connections configured'}), 400
    
    connection = conn_manager.connections[0]
    obj_ref = data['objRef']
    value = data['value']
    
    # Call remote service
    result = data_manager.write_data(connection, obj_ref, value)
    
    if result:
        return jsonify({
            'objRef': obj_ref,
            'value': value,
            'status': 'success',
            'timestamp': datetime.now().isoformat()
        })
    else:
        return jsonify({
            'objRef': obj_ref,
            'value': value,
            'status': 'success',
            'timestamp': datetime.now().isoformat(),
            'source': 'mock'
        })

# =============================================
# Model Management
# =============================================

@app.route('/api/model/tree', methods=['GET'])
def get_model_tree():
    """Get IEC 61850 model tree"""
    # Mock model tree - replace with actual model from server
    # mock_tree = {
    #     'children': [
    #         {
    #             'name': 'LD0',
    #             'icon': 'folder',
    #             'children': [
    #                 {
    #                     'name': 'LLN0',
    #                     'icon': 'folder',
    #                     'children': [
    #                         {'name': 'Mod', 'icon': 'cube'},
    #                         {'name': 'Beh', 'icon': 'cube'},
    #                         {'name': 'Health', 'icon': 'cube'}
    #                     ]
    #                 },
    #                 {
    #                     'name': 'DWMX1',
    #                     'icon': 'folder',
    #                     'children': [
    #                         {'name': 'WMaxSpt', 'icon': 'cube'},
    #                         {'name': 'WMinSpt', 'icon': 'cube'}
    #                     ]
    #                 }
    #             ]
    #         }
    #     ]
    # }
    #
    # return jsonify({'tree': mock_tree})

    try:
        tree = fsp_client.model()
        return jsonify({'tree': tree, 'source': 'fsp'})
    except requests.exceptions.RequestException as e:
        logger.warning(f"FSP unreachable, returning mock: {e}")
        #return jsonify({'tree': MOCK_TREE, 'source': 'mock'}), 200

#read value
@app.route('/api/model/readvalue', methods=['POST'])
def read_model_value():
    """Read a value from the model on the FSP (ACSI server)."""
    data = request.get_json(silent=True) or {}

    if 'objRef' not in data:
        return jsonify({'ok': False, 'error': 'objRef is required'}), 400

    obj_ref = data['objRef']
    fc = data.get('fc')

    try:
        fsp_response = fsp_client.read_value(obj_ref, fc)

        if not fsp_response.get('ok', True):
            return jsonify({
                'ok': False,
                'error': fsp_response.get('error', 'FSP read failed'),
                'fsp': fsp_response,
            }), 502

        return jsonify({
            'ok': True,
            'value': fsp_response.get('value'),
            'type': fsp_response.get('type'),
            'timestamp': datetime.now().isoformat(),
            'fsp': fsp_response,
        }), 200

    except requests.exceptions.RequestException as e:
        logger.error(f"FSP read_value failed: {e}")
        return jsonify({
            'ok': False,
            'error': f'FSP unreachable: {e}',
        }), 502

#write value
@app.route('/api/model/writevalue', methods=['POST'])
def write_model_value():
    """Write a value to the model on the FSP (ACSI server)."""
    data = request.get_json(silent=True) or {}

    required_fields = ['objRef', 'value']
    if not all(field in data for field in required_fields):
        return jsonify({'ok': False, 'error': 'objRef and value are required'}), 400

    obj_ref = data['objRef']
    value = data['value']

    try:
        fsp_response = fsp_client.write(obj_ref, value)

        if not fsp_response.get('ok', True):
            return jsonify({
                'ok': False,
                'error': fsp_response.get('error', 'FSP write failed'),
                'fsp': fsp_response,
            }), 502

        return jsonify({
            'ok': True,
            'status': 'success',
            'timestamp': datetime.now().isoformat(),
            'fsp': fsp_response,
        }), 200

    except requests.exceptions.RequestException as e:
        logger.error(f"FSP write failed: {e}")
        return jsonify({
            'ok': False,
            'error': f'FSP unreachable: {e}',
        }), 502


#update model
@app.route('/api/model/update', methods=['POST'])
def update_model():
    """Update the IED model on the FSP (ACSI server)."""
    data = request.get_json(silent=True) or {}

    if 'modelPy' not in data:
        return jsonify({'ok': False, 'error': 'modelPy is required'}), 400

    model_py = data['modelPy']
    if not isinstance(model_py, str) or not model_py.strip():
        return jsonify({'ok': False, 'error': 'modelPy must be a non-empty string'}), 400

    try:
        fsp_response = fsp_client.update_model(model_py)

        if not fsp_response.get('ok', True):
            return jsonify({
                'ok': False,
                'error': fsp_response.get('error', 'FSP rejected the model'),
                'fsp': fsp_response,
            }), 502

        return jsonify({
            'ok': True,
            'status': 'success',
            'fsp': fsp_response,
            'timestamp': datetime.now().isoformat(),
        }), 200

    except requests.exceptions.RequestException as e:
        logger.error(f"FSP update-iedmodel failed: {e}")
        return jsonify({
            'ok': False,
            'error': f'FSP unreachable: {e}',
        }), 502



# overal status
@app.route('/api/status', methods=['GET'])
def get_overall_status():
    """BFF-level status: combines BFF + FSP health for the UI."""
    fsp_status = None
    fsp_ok = False
    try:
        fsp_status = fsp_client.status()
        fsp_ok = True
    except requests.exceptions.RequestException as e:
        logger.warning(f"FSP status check failed: {e}")

    return jsonify({
        'bff': {'status': 'ok', 'version': '1.0.0'},
        'fsp': {'reachable': fsp_ok, 'details': fsp_status},
        'timestamp': datetime.now().isoformat(),
    })

@app.route('/api/iec61850server/start', methods=['POST'])
def start_acsi_server():
    """Start the ACSI server on the FSP with given parameters."""
    data = request.get_json(silent=True) or {}
    host = None
    port = None
    mode = None
    cp = None

    if('host' in data):
        host = data['host']
    if('port' in data):
        port = data['port']
    if('mode' in data):
        mode = data['mode']
    if('cp' in data):
        cp = data['cp']

    try:
        result = fsp_client.start_acsi_server(host, port, mode, cp)
        return jsonify({'ok': True, 'result': result})
    except requests.exceptions.RequestException as e:
        logger.error(f"FSP update-iedmodel failed: {e}")
        return jsonify({
            'ok': False,
            'error': f'FSP unreachable: {e}',
        }), 502

@app.route('/api/iec61850server/stop', methods=['POST'])
def stop_acsi_server():
    """Stop the ACSI server on the FSP."""
    try:
        result = fsp_client.stop_acsi_server()
        return jsonify({'ok': True, 'result': result})
    except requests.exceptions.RequestException as e:
        logger.error(f"FSP stop_acsi_server failed: {e}")
        return jsonify({
            'ok': False,
            'error': f'FSP unreachable: {e}',
        }), 502

@app.route('/api/iec61850server/actions', methods=['GET'])
def get_server_actions():
    """Get available actions for the ACSI server."""
    try:
        result = fsp_client.actions()
        return jsonify({'ok': True, 'actions': result})
    except requests.exceptions.RequestException as e:
        logger.error(f"FSP get_server_actions failed: {e}")
        return jsonify({
            'ok': False,
            'error': f'FSP unreachable: {e}',
        }), 502

@app.route('/api/iec61850server/properties', methods=['GET'])
def get_server_properties():
    """Get available actions for the ACSI server."""
    try:
        result = fsp_client.properties()
        return jsonify({'ok': True, 'properties': result})
    except requests.exceptions.RequestException as e:
        logger.error(f"FSP get_server_properties failed: {e}")
        return jsonify({
            'ok': False,
            'error': f'FSP unreachable: {e}',
        }), 502

@app.route('/api/iec61850server/actions/clear', methods=['POST'])
def clear_server_actions():
    """Clear actions on the ACSI server."""
    try:
        # Assuming there's an endpoint to clear actions - this is a placeholder
        result = fsp_client.clear_actions()
        return jsonify({'ok': True, 'result': result})
    except requests.exceptions.RequestException as e:
        logger.error(f"FSP clear_server_actions failed: {e}")
        return jsonify({
            'ok': False,
            'error': f'FSP unreachable: {e}',
        }), 502

@app.route('/api/iec61850server/messages', methods=['GET'])
def get_protocol_messages():
    """Get protocol messages from the ACSI server."""
    try:
        result = fsp_client.protocol_messages()
        return jsonify({'ok': True, 'messages': result})
    except requests.exceptions.RequestException as e:
        logger.error(f"FSP get_protocol_messages failed: {e}")
        return jsonify({
            'ok': False,
            'error': f'FSP unreachable: {e}',
        }), 502

@app.route('/api/iec61850server/messages/clear', methods=['POST'])
def clear_protocol_messages():
    """Clear protocol messages on the ACSI server."""
    try:
        # Assuming there's an endpoint to clear messages - this is a placeholder
        result = fsp_client.clear_protocol_messages()
        return jsonify({'ok': True, 'result': result})
    except requests.exceptions.RequestException as e:
        logger.error(f"FSP clear_protocol_messages failed: {e}")
        return jsonify({
            'ok': False,
            'error': f'FSP unreachable: {e}',
        }), 502

# =============================================
# Reports
# =============================================

@app.route('/api/reports', methods=['GET'])
def get_reports():
    """Get available reports"""
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
    
    return jsonify({'reports': mock_reports})

@app.route('/api/reports/export', methods=['POST'])
def export_reports():
    """Export reports"""
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
    
    return jsonify({'data': export_data, 'status': 'success'})

# =============================================
# Statistics
# =============================================

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get system statistics"""
    return jsonify({
        'reportUpdates': 0,
        'bffTargets': len(conn_manager.connections),
        'totalRequests': 0,
        'uptime': '00:00:00'
    })

@app.route('/api/acsiserver/status', methods=['GET'])
def get_status():
    """Get system statistics"""


# =============================================
# Error Handling
# =============================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404
# =============================================
# Passthrough proxy to RTI backends
# =============================================

def _proxy_request(base_url: str, prefix: str, path: str):
    target = f"{base_url}{prefix}{path}"
    try:
        resp = requests.request(
            method=request.method,
            url=target,
            headers={k: v for k, v in request.headers if k.lower() != 'host'},
            data=request.get_data(),
            params=request.args,
            timeout=10,
            allow_redirects=False,
        )
        return Response(
            resp.content,
            status=resp.status_code,
            content_type=resp.headers.get('Content-Type', 'application/json'),
        )
    except requests.exceptions.RequestException as e:
        logger.error(f"Proxy error for {target}: {e}")
        return jsonify({'error': 'backend unreachable', 'detail': str(e)}), 502


@app.route('/api/iec61850client/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def proxy_iec61850client(path):
    """Forward /api/iec61850client/* requests directly to the RTI client container."""
    return _proxy_request(SO_BASE_URL, '/api/iec61850client/', path)


@app.route('/api/iec61850server/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def proxy_iec61850server(path):
    """Forward /api/iec61850server/* requests directly to the RTI server container."""
    return _proxy_request(fsp_client.selected_base_url(), '/api/iec61850server/', path)

@app.route('/api/iec61850client/status', methods=['GET'])
def get_asci_client_status():
    """Get status of the IEC 61850 client (SO)."""
    try:
        status = so_client.status()
        return jsonify({'ok': True, 'status': status})
    except requests.exceptions.RequestException as e:
        logger.error(f"SO client status failed: {e}")
        return jsonify({'ok': False, 'error': f'SO client unreachable: {e}'}), 502

@app.route('/api/iec61850client/connections', methods=['GET'])
def get_asci_client_connections():
    """Get connections of the IEC 61850 client (SO)."""
    try:
        connections = so_client.connections()
        return jsonify({'ok': True, 'connections': connections})
    except requests.exceptions.RequestException as e:
        logger.error(f"SO client connections failed: {e}")
        return jsonify({'ok': False, 'error': f'SO client unreachable: {e}'}), 502

@app.route('/api/iec61850client/connect', methods=['post'])
def connect_asci_client():
    """Connect the IEC 61850 client (SO) to a server."""
    data = request.get_json(silent=True) or {}
    host = data.get('host')
    port = data.get('port')
    cp = data.get('cp')

    try:
        result = so_client.connect(host, port, cp)
        return jsonify({'ok': True, 'result': result})
    except requests.exceptions.RequestException as e:
        logger.error(f"SO client connect failed: {e}")
        return jsonify({'ok': False, 'error': f'SO client unreachable: {e}'}), 502

@app.route('/api/iec61850client/disconnect', methods=['post'])
def disconnect_asci_client():
    """Disconnect the IEC 61850 client (SO) from the server."""
    try:
        result = so_client.disconnect()
        return jsonify({'ok': True, 'result': result})
    except requests.exceptions.RequestException as e:
        logger.error(f"SO client disconnect failed: {e}")
        return jsonify({'ok': False, 'error': f'SO client unreachable: {e}'}), 502


@app.route('/api/iec61850client/actions', methods=['GET'])
def get_asci_client_actions():
    """Get actions from the IEC 61850 client (SO)."""
    try:
        actions = so_client.actions()
        return jsonify({'ok': True, 'actions': actions})
    except requests.exceptions.RequestException as e:
        logger.error(f"SO client actions failed: {e}")
        return jsonify({'ok': False, 'error': f'SO client unreachable: {e}'}), 502

@app.route('/api/iec61850client/model/tree', methods=['GET'])
def get_tree_from_acsi_client():
    """Get actions from the IEC 61850 client (SO)."""
    try:
        model = so_client.model()
        return jsonify({'ok': True, 'model': model})
    except requests.exceptions.RequestException as e:
        logger.error(f"SO client actions failed: {e}")
        return jsonify({'ok': False, 'error': f'SO client unreachable: {e}'}), 502

@app.route('/api/iec61850client/properties', methods=['GET'])
def get_client_properties():
    """Get available actions for the ACSI server."""
    try:
        result = so_client.properties()
        return jsonify({'ok': True, 'properties': result})
    except requests.exceptions.RequestException as e:
        logger.error(f"FSP get_client_properties failed: {e}")
        return jsonify({
            'ok': False,
            'error': f'SO unreachable: {e}',
        }), 502

@app.route('/api/iec61850client/actions/clear', methods=['POST'])
def clear_asci_client_actions():
    """Clear actions on the IEC 61850 client (SO)."""
    try:
        result = so_client.clear_actions()
        return jsonify({'ok': True, 'result': result})
    except requests.exceptions.RequestException as e:
        logger.error(f"SO client clear actions failed: {e}")
        return jsonify({'ok': False, 'error': f'SO client unreachable: {e}'}), 502

@app.route('/api/iec61850client/messages', methods=['GET'])
def get_asci_client_messages():
    """Get protocol messages from the IEC 61850 client (SO)."""
    try:
        messages = so_client.protocol_messages()
        return jsonify({'ok': True, 'messages': messages})
    except requests.exceptions.RequestException as e:
        logger.error(f"SO client protocol messages failed: {e}")
        return jsonify({'ok': False, 'error': f'SO client unreachable: {e}'}), 502

@app.route('/api/iec61850client/messages/clear', methods=['POST'])
def clear_asci_client_messages():
    """Clear protocol messages on the IEC 61850 client (SO)."""
    try:
        result = so_client.clear_protocol_messages()
        return jsonify({'ok': True, 'result': result})
    except requests.exceptions.RequestException as e:
        logger.error(f"SO client clear protocol messages failed: {e}")
        return jsonify({'ok': False, 'error': f'SO client unreachable: {e}'}), 502

@app.route('/api/iec61850client/readvalue', methods=['post'])
def read_asci_client_value():
    """Read a value using the IEC 61850 client (SO)."""
    data = request.get_json(silent=True) or {}
    obj_ref = data.get('objRef')
    fc = data.get('fc')

    if not obj_ref:
        return jsonify({'ok': False, 'error': 'objRef is required'}), 400

    try:
        result = so_client.read_value(obj_ref, fc)
        return jsonify({'ok': True, 'result': result})
    except requests.exceptions.RequestException as e:
        logger.error(f"SO client read value failed: {e}")
        return jsonify({'ok': False, 'error': f'SO client unreachable: {e}'}), 502

@app.route('/api/iec61850client/writevalue', methods=['post'])
def write_asci_client_value():
    """Write a value using the IEC 61850 client (SO)."""
    data = request.get_json(silent=True) or {}
    obj_ref = data.get('objRef')
    value = data.get('value')
    fc = data.get('fc')
    da_type = data.get('dataType')

    if not obj_ref or value is None:
        return jsonify({'ok': False, 'error': 'objRef and value are required'}), 400

    try:
        result = so_client.write_value(obj_ref, value, fc, da_type)
        return jsonify({'ok': True, 'result': result})
    except requests.exceptions.HTTPError as e:
        # Forward the SO's actual error body so it's not hidden behind a generic 502.
        upstream_status = e.response.status_code if e.response is not None else 502
        try:
            upstream_body = e.response.json() if e.response is not None else {'error': str(e)}
        except Exception:
            upstream_body = {'error': e.response.text if e.response is not None else str(e)}
        logger.error(f"SO client write value failed: upstream={upstream_status} body={upstream_body}")
        return jsonify({
            'ok': False,
            'error': f'SO write failed (upstream {upstream_status})',
            'upstream_status': upstream_status,
            'upstream': upstream_body,
            'sent_payload': {'objRef': obj_ref, 'value': value, 'fc': fc, 'dataType': da_type},
        }), 502
    except requests.exceptions.RequestException as e:
        logger.error(f"SO client write value failed: {e}")
        return jsonify({'ok': False, 'error': f'SO client unreachable: {e}'}), 502

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({'error': 'Internal server error'}), 500

# =============================================
# Application Entry Point
# =============================================

if __name__ == '__main__':
    logger.info("Starting RTI Demo BFF Server...")
    logger.info("Available endpoints:")
    logger.info("  GET    /api/health")
    logger.info("  GET    /api/endpoints")
    logger.info("  GET    /api/connections")
    logger.info("  POST   /api/connections")
    logger.info("  DELETE /api/connections/<id>")
    logger.info("  POST   /api/data/read")
    logger.info("  POST   /api/data/write")
    logger.info("  GET    /api/model/tree")
    logger.info("  GET    /api/reports")
    logger.info("  POST   /api/reports/export")
    
    app.run(host='0.0.0.0', port=5000, debug=True)
