"""Connection Management Module for RTI Demo BFF.

This module provides centralized management of connections to RTI services (FSP, SO, demo_IO, IDP-Server).
It handles:
- Connection CRUD operations (Create, Read, Update, Delete)
- Persistent storage to connections.json file
- Health monitoring of all registered connections
- Auto-discovery of services (Docker containers, network scanning)
- OAuth and TLS configuration per connection
- BFF client instantiation for each connection

The ConnectionManager is a core component of the BFF server, enabling it to:
1. Maintain a registry of all backend service endpoints
2. Monitor service health and availability
3. Proxy requests to the appropriate backend service
4. Manage authentication (OAuth) and encryption (TLS) settings
"""

from typing import Any, Dict, List, Optional, Tuple
from bffClient import BffClient
from concurrent.futures import ThreadPoolExecutor
import asyncio
import httpx
import os
import json
from datetime import datetime


class ConnectionManager:
    """Manages connections to remote RTI endpoints.
    
    This class is responsible for:
    - Maintaining a list of all configured connections
    - Loading/saving connections from/to connections.json
    - Creating BffClient instances for each connection
    - Monitoring connection health status
    - Auto-registering discovered services
    - Providing connection lookup by name or host:port
    
    Attributes:
        connections_file: Path to the JSON file for persistent storage
        _bff_clients: Dictionary of BffClient instances keyed by "host:port"
        connections: List of connection dictionaries
        logger: Logger instance for connection-related messages
    """

    def __init__(self, bff_clients, connections_file, logger ) -> None:
        self.connections_file = connections_file
        self._bff_clients = bff_clients
        self.logger = logger

        self.connections: List[Dict] = self.load_connections()
        self.status_task = None
        # Reusable HTTP client (connection pooling + keep-alive) for health checks.
        self._client: Optional[httpx.AsyncClient] = None
        # Give every connection an initial status so the UI can render instantly.
        for con in self.connections:
            con.setdefault("status", "checking")

        self._register_connections_as_clients()

    def _register_connections_as_clients(self) -> None:
        """Register BFF clients for all current connections."""
        for con in self.connections:
            host = con.get('host')
            port = con.get('port')
            if host and port:
                key = f"{host}:{port}"
                if key not in self._bff_clients:
                    self._bff_clients[key] = BffClient(f"http://{host}:{port}")

    def get_client(self) -> httpx.AsyncClient:
        """Return a shared AsyncClient, creating it lazily.
        
        Creates a single httpx.AsyncClient instance with 2-second timeout
        that is reused for all health check requests to avoid connection overhead.
        
        Returns:
            Shared httpx.AsyncClient instance
        """
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=2.0)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def status_monitor(self, interval=10):
        # Run an immediate check so cards populate on startup instead of
        # waiting for the first interval to elapse.
        await self.get_all_connections_with_status()
        while True:
            await asyncio.sleep(interval)
            await self.get_all_connections_with_status()

    def load_connections(self) -> List[Dict]:
        """Load connections from file."""
        if os.path.exists(self.connections_file):
            try:
                with open(self.connections_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"Error loading connections: {e}")
        return []

    def save_connections(self) -> None:
        """Save connections to file."""
        try:
            with open(self.connections_file, 'w') as f:
                json.dump(self.connections, f, indent=2)
        except Exception as e:
            self.logger.error(f"Error saving connections: {e}")

    def add_connection(self, name: str, host: Optional[str] = None, port: Optional[int] = None, conn_type: str = "",
                       acsi: Optional[str] = None, ws_mode: Optional[str] = None, endpoint: Optional[str] = None,
                       certificate_endpoint: Optional[str] = None, auth_server_ca: Optional[str] = None,
                       realm: Optional[str] = None, token_endpoint: Optional[str] = None,
                       client_id: Optional[str] = None, client_secret: Optional[str] = None,
                       enable_token_refresh: Optional[bool] = None, idp_server: Optional[str] = None,
                       auto_discovered: bool = False) -> Dict:
        """Add a new connection.

        Args:
            name: Human-readable name for the connection
            host: Hostname or IP address
            port: Port number
            conn_type: Type of endpoint
            acsi: ACSI role (server/client)
            ws_mode: WebSocket mode
            auto_discovered: Whether this connection was auto-discovered

        Returns:
            The created connection dictionary.
        """
        # Check if connection already exists (for non-IDP-Server types)
        if conn_type != 'IDP-Server' and host and port:
            existing = next((c for c in self.connections
                             if c.get('host') == host and c.get('port') == port and c['name'] == name), None)
            if existing:
                self.logger.warning(f"Connection already exists: {host}:{port}")
                return existing

        connection_in_file = next((c for c in self.connections
                                   if c['name'] == name), None)
        if connection_in_file:
            # Track old host:port for _bff_clients cleanup (for non-IDP-Server types)
            old_key = f"{connection_in_file.get('host')}:{connection_in_file.get('port')}" if connection_in_file.get(
                'host') and connection_in_file.get('port') else None

            if conn_type == 'IDP-Server':
                connection_in_file['type'] = conn_type
                if endpoint is not None:
                    connection_in_file['endpoint'] = endpoint

                # For IDP-Server, also update OAuth fields
                # Create OAuth object if any OAuth fields are provided
                oauth_fields = {}
                if certificate_endpoint is not None:
                    oauth_fields['certificate_endpoint'] = certificate_endpoint
                if auth_server_ca is not None:
                    oauth_fields['auth_server_ca'] = auth_server_ca
                if realm is not None:
                    oauth_fields['realm'] = realm
                if token_endpoint is not None:
                    oauth_fields['token_endpoint'] = token_endpoint
                if client_id is not None:
                    oauth_fields['client_id'] = client_id
                if client_secret is not None:
                    oauth_fields['client_secret'] = client_secret
                if enable_token_refresh is not None:
                    oauth_fields['enable_token_refresh'] = enable_token_refresh
                if idp_server is not None:
                    oauth_fields['idp_server'] = idp_server

                if oauth_fields:
                    if 'OAuth' not in connection_in_file:
                        connection_in_file['OAuth'] = {}
                    connection_in_file['OAuth'].update(oauth_fields)

                # Clean up any OAuth fields that were previously at top level
                top_level_oauth_fields = ['certificate_endpoint', 'auth_server_ca', 'realm',
                                          'token_endpoint', 'client_id', 'client_secret', 'enable_token_refresh',
                                          'idp_server']
                for field in top_level_oauth_fields:
                    if field in connection_in_file:
                        del connection_in_file[field]
            else:
                connection_in_file['host'] = host
                connection_in_file['port'] = port
                connection_in_file['type'] = conn_type
                connection_in_file['acsi'] = acsi
                connection_in_file['ws_mode'] = ws_mode

                # Update OAuth fields for non-IDP-Server types
                oauth_fields = {}
                if certificate_endpoint is not None:
                    oauth_fields['certificate_endpoint'] = certificate_endpoint
                if auth_server_ca is not None:
                    oauth_fields['auth_server_ca'] = auth_server_ca
                if realm is not None:
                    oauth_fields['realm'] = realm
                if token_endpoint is not None:
                    oauth_fields['token_endpoint'] = token_endpoint
                if client_id is not None:
                    oauth_fields['client_id'] = client_id
                if client_secret is not None:
                    oauth_fields['client_secret'] = client_secret
                if enable_token_refresh is not None:
                    oauth_fields['enable_token_refresh'] = enable_token_refresh
                if idp_server is not None:
                    oauth_fields['idp_server'] = idp_server

                if oauth_fields:
                    if 'OAuth' not in connection_in_file:
                        connection_in_file['OAuth'] = {}
                    connection_in_file['OAuth'].update(oauth_fields)

                # Clean up any OAuth fields that were previously at top level
                top_level_oauth_fields = ['certificate_endpoint', 'auth_server_ca', 'realm',
                                          'token_endpoint', 'client_id', 'client_secret', 'enable_token_refresh',
                                          'idp_server']
                for field in top_level_oauth_fields:
                    if field in connection_in_file:
                        del connection_in_file[field]

                # Update _bff_clients if host or port changed
                new_key = f"{host}:{port}"
                if old_key != new_key:
                    if old_key in self._bff_clients:
                        del self._bff_clients[old_key]
                    if new_key not in self._bff_clients:
                        self._bff_clients[new_key] = BffClient(f"http://{host}:{port}")

            self.save_connections()
            return connection_in_file

        connection = {
            'id': len(self.connections) + 1,
            'name': name,
            'host': host,
            'port': port,
            'type': conn_type,
            'acsi': acsi,
            'ws_mode': ws_mode,
            'auto_discovered': auto_discovered,
            'created_at': datetime.now().isoformat()
        }

        # Add endpoint for IDP-Server
        if conn_type == 'IDP-Server' and endpoint is not None:
            connection['endpoint'] = endpoint

        # Create OAuth object if any OAuth fields are provided
        oauth_fields = {}
        if certificate_endpoint is not None:
            oauth_fields['certificate_endpoint'] = certificate_endpoint
        if auth_server_ca is not None:
            oauth_fields['auth_server_ca'] = auth_server_ca
        if realm is not None:
            oauth_fields['realm'] = realm
        if token_endpoint is not None:
            oauth_fields['token_endpoint'] = token_endpoint
        if client_id is not None:
            oauth_fields['client_id'] = client_id
        if client_secret is not None:
            oauth_fields['client_secret'] = client_secret
        if enable_token_refresh is not None:
            oauth_fields['enable_token_refresh'] = enable_token_refresh
        if idp_server is not None:
            oauth_fields['idp_server'] = idp_server

        if oauth_fields:
            connection['OAuth'] = oauth_fields

        self.connections.append(connection)
        self.save_connections()

        # Only create BFF client for non-IDP-Server types with host and port
        if conn_type != 'IDP-Server' and host and port:
            key = f"{host}:{port}"
            if key not in self._bff_clients:
                self._bff_clients[key] = BffClient(f"http://{host}:{port}")

        self.logger.info(f"Connection added: {name} ({host}:{port})")
        return connection

    def delete_connection(self, conn_name) -> bool:
        """Delete a connection by name.

        Removes the connection from the connections list and deletes the associated
        BffClient instance. Also saves the updated connections to disk.

        Args:
            conn_name: Name of the connection to delete

        Returns:
            bool: True if connection was found and deleted, False otherwise
        """
        # Find the connection to get its host:port before deleting
        connection = self.get_connection(conn_name)

        original_count = len(self.connections)
        self.connections = [c for c in self.connections if c['name'] != conn_name]
        if len(self.connections) < original_count:
            self.save_connections()

            # Remove from _bff_clients if it exists
            if connection and connection.get('host') and connection.get('port'):
                old_key = f"{connection['host']}:{connection['port']}"
                if old_key in self._bff_clients:
                    del self._bff_clients[old_key]

            self.logger.info(f"Connection deleted: {conn_name}")
            return True
        return False

    def get_connection(self, conn_name: str) -> Optional[Dict]:
        """Get a specific connection by name.
        
        Args:
            conn_name: Name of the connection to retrieve
            
        Returns:
            Connection dictionary if found, None otherwise
        """
        return next((c for c in self.connections if c['name'] == conn_name), None)

    def get_connection_by_host_port(self, host: str, port: int) -> Optional[Dict]:
        """Get connection by host and port.
        
        Useful for looking up connections when you have network coordinates
        but not the connection name.
        
        Args:
            host: Hostname or IP address
            port: Port number
            
        Returns:
            Connection dictionary if found, None otherwise
        """
        return next((c for c in self.connections
                     if c['host'] == host and c['port'] == port), None)

    def update_connection_status(self, conn_name: str, status: str) -> None:
        """Update connection status and save to disk.
        
        Args:
            conn_name: Name of the connection to update
            status: New status value (e.g., 'connected', 'disconnected', 'error')
        """
        conn = self.get_connection(conn_name)
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

    async def check_connection(self, con, client):
        # For IDP-Server, check via endpoint or host:port
        if con.get('type') == 'IDP-Server':
            # Create a client that doesn't verify SSL for IDP servers
            # (Keycloak often uses self-signed certs)
            idp_client = httpx.AsyncClient(timeout=2.0, verify=False)
            
            try:
                # Try to use host:port first if available (for local IDP servers)
                host = con.get('host')
                port = con.get('port')
                endpoint = con.get('endpoint')
                
                if host and port:
                    # Use host:port if both are defined
                    url = f"http://{host}:{port}"
                elif endpoint:
                    # Otherwise, use the endpoint
                    if endpoint.startswith('http://') or endpoint.startswith('https://'):
                        url = endpoint
                    else:
                        # If it's just a path, try localhost with common IDP ports
                        # Try HTTPS first (common for Keycloak)
                        url = f"https://localhost{endpoint if endpoint.startswith('/') else '/' + endpoint}"
                else:
                    # No endpoint or host/port defined, mark as disconnected
                    con["status"] = "disconnected"
                    return
                
                response = await idp_client.get(url)
                con["status"] = "connected" if response.status_code < 500 else "disconnected"
            except httpx.RequestError as e:
                # Try HTTP if HTTPS failed
                if endpoint and not endpoint.startswith('http://') and not endpoint.startswith('https://'):
                    try:
                        url = f"http://localhost{endpoint if endpoint.startswith('/') else '/' + endpoint}"
                        response = await idp_client.get(url)
                        con["status"] = "connected" if response.status_code < 500 else "disconnected"
                        await idp_client.aclose()
                        return
                    except httpx.RequestError as e2:
                        self.logger.debug(f"IDP-Server connection check failed for {con.get('name')}: {e2}")
                        con["status"] = "disconnected"
                else:
                    self.logger.debug(f"IDP-Server connection check failed for {con.get('name')}: {e}")
                    con["status"] = "disconnected"
            finally:
                await idp_client.aclose()
            return

        # For other types, check connectivity via host:port
        if not con.get('host') or not con.get('port'):
            con["status"] = "disconnected"
            return

        try:
            response = await client.get(
                f"http://{con['host']}:{con['port']}",
            )
            con["status"] = (
                "connected"
                if response.status_code < 500
                else "disconnected"
            )
        except httpx.RequestError:
            con["status"] = "disconnected"

    async def get_all_connections_with_status(self):
        client = self.get_client()
        await asyncio.gather(
            *(self.check_connection(con, client) for con in self.connections)
        )
        return self.connections