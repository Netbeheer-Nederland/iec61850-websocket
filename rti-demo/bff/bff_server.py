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
from bffClient import BffClient

_bff_clients: Dict[str, BffClient] = {}

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

def _register_bff_clients(discovered: Dict[str, Dict]):
    for ep in discovered.values():
        host = ep.get('host')
        port = ep.get('port')

        if not host or not port:
            continue

        key = f"{host}:{port}"
        base_url = f"http://{host}:{port}"

        if key not in _bff_clients:
            _bff_clients[key] = BffClient(base_url)

def get_bff_client_from_target(selector: str) -> BffClient:
    return _bff_clients.get(selector)

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

## =============================================
## Health & Status Endpoints
## =============================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """
    Health check endpoint for frontend:
    - BFF status
    - discovered targets
    - optional target reachability
    """
    try:
        # ✅ BFF self status
        bff_status = {
            "status": "ok",
            "service": "BFF",
        }

        # ✅ known clients (registered)
        targets = []
        for key in _bff_clients.keys():
            targets.append({
                "target": key,
                "status": "unknown"  # optional (see below)
            })
            try:
                client = _bff_clients[key]
                client.request("GET", "/api/health")
                status = "reachable"
            except Exception:
                    status = "unreachable"


        return jsonify({
            "ok": True,
            "bff": bff_status,
            "targets": targets,
            "count": len(targets)
        })

    except Exception as e:
        logger.error(f"Health check failed: {e}")

        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500

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

@app.route('/api/execute', methods=['POST'])
def execute_dynamic_api():
    data = request.get_json(silent=True) or {}

    target = data.get('target')
    method = data.get('method', 'GET').upper()
    path = data.get('path')
    body = data.get('body')

    if not target or not path:
        return jsonify({
            "ok": False,
            "error": "target and path are required"
        }), 400

    try:
        # ✅ get client from registry
        client = _bff_clients.get(target)

        if not client:
            return jsonify({
                "ok": False,
                "error": f"Unknown target: {target}"
            }), 404

        # ✅ call API dynamically
        result = client.request(
            method=method,
            path=path,
            json=body
        )

        return jsonify({
            "ok": True,
            "target": target,
            "method": method,
            "path": path,
            "result": result
        })

    except Exception as e:
        logger.error(f"Dynamic API call failed: {e}")

        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500

@app.route('/api/endpoints', methods=['GET'])
def get_endpoints():
    """Get all configured endpoints (including cached auto-discovered)."""
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
        _register_bff_clients(discovery.discovered_services)


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
    _register_bff_clients(discovery.discovered_services)

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

# =============================================
# Connections Management
# =============================================

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


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get system statistics"""
    return jsonify({
        'reportUpdates': 0,
        'bffTargets': len(conn_manager.connections),
        'totalRequests': 0,
        'uptime': '00:00:00'
    })

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
    logger.info("  POST   /api/connect")
    logger.info("  DELETE /api/connections/<id>")
    logger.info("  POST   /api/data/read")
    logger.info("  POST   /api/data/write")
    logger.info("  GET    /api/model/tree")
    logger.info("  GET    /api/reports")
    logger.info("  POST   /api/reports/export")
    
    app.run(host='0.0.0.0', port=5000, debug=True)
