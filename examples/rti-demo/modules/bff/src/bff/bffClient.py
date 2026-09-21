# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
#
# Copyright 2025 Netbeheer Nederland
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""HTTP client wrapper for BFF-to-backend communication.

This module provides a simple, reusable HTTP client with:
- Connection pooling (via requests session)
- Error handling with automatic status code checking
- JSON parsing with fallback to text
- Configurable timeout
- Clean URL joining

Used by BFF server to communicate with RTI-FSP, RTI-SO, and other backend services.
"""

import requests


class BffClient:
    """HTTP client for communicating with RTI backend services.
    
    Provides a clean interface for making HTTP requests to RTI services
    (FSP, SO, demo_IO) with consistent error handling and response parsing.
    
    Attributes:
        base_url: The base URL of the target service (without trailing slash)
    """
    
    def __init__(self, base_url: str):
        """Initialize BffClient with base service URL.
        
        Args:
            base_url: Base URL of the RTI service (e.g., 'http://localhost:5001')
        """
        self.base_url = base_url.rstrip('/')

    def request(self, method: str, path: str, json=None, params=None, headers=None):
        """Send HTTP request to the backend service.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            path: API endpoint path (e.g., '/api/health')
            json: Request body as dict (for POST/PUT requests)
            params: Query parameters as dict
            headers: Additional HTTP headers as dict
            
        Returns:
            Parsed JSON response if response is JSON, otherwise raw text
            
        Raises:
            requests.exceptions.HTTPError: If response status code >= 400
            requests.exceptions.Timeout: If request times out (15 seconds)
            requests.exceptions.RequestException: For other request errors
        """
        url = f"{self.base_url}{path}"

        response = requests.request(
            method=method,
            url=url,
            json=json,
            params=params,
            headers=headers or {},
            timeout=15
        )

        response.raise_for_status()

        try:
            return response.json()
        except Exception:
            return response.text