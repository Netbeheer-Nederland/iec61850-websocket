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

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class AuthContext:
    """Opaque auth result returned after validating a server-side connection."""
    client_id: str | None = None
    token_expiry: float | None = None


@runtime_checkable
class AuthStrategy(Protocol):
    """
    Boundary between endpoint transport and authentication concerns.

    Outbound (client) side: provide HTTP headers for the WebSocket upgrade.
    Inbound (server) side: validate the upgrade request and return context.

    Implementations decide whether OAuth, mTLS, or no-auth is in use.
    endpoint.py sees only this Protocol — it never imports JWT or aiohttp.
    """

    async def client_headers(self) -> dict[str, str]:
        """Return HTTP headers to include in the outbound WebSocket upgrade request."""
        ...

    async def authenticate_server_connection(self, request) -> AuthContext:
        """Validate an inbound WebSocket upgrade request. Raise on failure."""
        ...


class NoAuthStrategy:
    """Pass-through strategy used when no authentication is required."""

    async def client_headers(self) -> dict[str, str]:
        return {}

    async def authenticate_server_connection(self, request) -> AuthContext:
        return AuthContext()


class BearerTokenStrategy:
    """
    Static bearer-token strategy: always uses the same token.
    For OAuth2 token acquisition with auto-refresh use OAuth2ClientCredentialsStrategy.
    """

    def __init__(self, token: str):
        self._token = token

    async def client_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    async def authenticate_server_connection(self, request) -> AuthContext:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise PermissionError("Missing or malformed Authorization header")
        return AuthContext()
