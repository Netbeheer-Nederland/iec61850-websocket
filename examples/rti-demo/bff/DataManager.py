"""Data Management Module for RTI Demo BFF.

This module provides data read/write operations against connected RTI endpoints.
It abstracts the complexity of direct HTTP communication with backend services,
providing a clean interface for:
- Reading data values from ACSI endpoints
- Writing data values to ACSI endpoints
- Performing control operations (operate)
- Executing remote service calls

The DataManager uses ConnectionManager to resolve connection details and
BffClient for actual HTTP communication.
"""

from ConnectionManager import ConnectionManager
import requests
from typing import Any, Dict, List, Optional, Tuple


class DataManager:
    """Manages data operations against remote endpoints.
    
    Provides a high-level interface for interacting with RTI services
    (FSP, SO) to perform data operations without needing to know
    the underlying connection details.
    
    Attributes:
        conn_manager: ConnectionManager instance for connection resolution
        logger: Logger instance for data operation logging
    """

    def __init__(self, connection_manager: ConnectionManager, logger) -> None:
        self.conn_manager = connection_manager
        self.logger = logger

    def call_remote_service(self, connection: Dict, endpoint: str, method: str = 'GET', data: Optional[Dict] = None) -> \
    Optional[Dict]:
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
                self.logger.warning(f"Remote service error: {response.status_code}")
                return None
        except Exception as e:
            self.logger.error(f"Error calling remote service: {e}")
            return None

    def read_data(self, connection: Dict, obj_ref: str) -> Optional[Dict]:
        """Read data from a remote endpoint."""
        return self.call_remote_service(connection, f'/api/data/{obj_ref}', 'GET')

    def write_data(self, connection: Dict, obj_ref: str, value: str) -> Optional[Dict]:
        """Write data to a remote endpoint."""
        return self.call_remote_service(connection, f'/api/data/{obj_ref}', 'POST', {'value': value})

    def operate(self, connection: Dict, obj_ref: str, value: Any) -> Optional[Dict]:
        """Perform an operation on a remote endpoint."""
        return self.call_remote_service(connection, f'/api/operate/{obj_ref}', 'POST', {'value': value})
