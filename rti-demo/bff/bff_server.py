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

from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from datetime import datetime
import json
import os
import logging
from typing import Dict, List, Optional
import requests
import threading
import time
from fspClient import FspClient

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

# Initialize FSP client (point to the RTI server container)
FSP_BASE_URL = os.environ.get('FSP_BASE_URL', 'http://rti-server:5001')
fsp_client = FspClient(FSP_BASE_URL)

# Service discovery
class ServiceDiscovery:
    """Auto-discovers RTI services from Docker containers"""
    
    def __init__(self):
        self.docker_enabled = os.getenv('RTI_DOCKER_ENABLED', 'false').lower() == 'true'
        self.client = None
        self.discovered_services = {}
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
            
            self.discovered_services = services
            self.last_discovery = datetime.now().isoformat()
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
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0'
    })

# =============================================
# Endpoints Management
# =============================================

@app.route('/api/endpoints', methods=['GET'])
def get_endpoints():
    """Get all configured endpoints (including auto-discovered)"""
    # Get user-configured connections
    endpoints = list(conn_manager.connections)
    
    # Add auto-discovered services
    discovered = discovery.discover_services()
    
    # Check if discovered service already in connections
    for service_name, service_info in discovered.items():
        exists = any(e['host'] == service_info['host'] and e['port'] == service_info['port'] 
                    for e in endpoints)
        if not exists:
            endpoints.append(service_info)
    
    return jsonify({
        'endpoints': endpoints,
        'count': len(endpoints),
        'discovered_count': len(discovered),
        'last_discovery': discovery.last_discovery,
        'docker_enabled': discovery.docker_enabled
    })

@app.route('/api/endpoints/discovered', methods=['GET'])
def get_discovered_endpoints():
    """Get only auto-discovered endpoints"""
    discovered = discovery.discover_services()
    return jsonify({
        'discovered': discovered,
        'count': len(discovered),
        'last_discovery': discovery.last_discovery
    })

@app.route('/api/endpoints/discover', methods=['POST'])
def trigger_discovery():
    """Manually trigger service discovery"""
    discovered = discovery.discover_services()
    return jsonify({
        'status': 'success',
        'discovered': discovered,
        'count': len(discovered)
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

RTI_CLIENT_URL = os.environ.get('RTI_CLIENT_URL', 'http://rti-client:5000')
RTI_SERVER_URL = os.environ.get('RTI_SERVER_URL', 'http://rti-server:5001')


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
    return _proxy_request(RTI_CLIENT_URL, '/api/iec61850client/', path)


@app.route('/api/iec61850server/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def proxy_iec61850server(path):
    """Forward /api/iec61850server/* requests directly to the RTI server container."""
    return _proxy_request(RTI_SERVER_URL, '/api/iec61850server/', path)


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
