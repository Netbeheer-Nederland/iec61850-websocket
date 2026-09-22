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

from typing import Any

from pydantic import BaseModel, Field


class ConnectionCreateRequest(BaseModel):
    """Request body for creating a new connection."""

    name: str = Field(
        ...,
        description="Human-readable name for the connection",
        json_schema_extra={"example": "RTI-FSP-01"},
    )
    host: str | None = Field(
        default=None,
        description="Hostname or IP address of the endpoint's BFF server",
        json_schema_extra={"example": "localhost"},
    )
    port: int | None = Field(
        default=None,
        description="Port number of the endpoint's BFF server (used for all /api/execute proxying)",
        json_schema_extra={"example": 5000},
    )
    ws_port: int | None = Field(
        default=None,
        description="Port the RTI-SO instance's own WebSocket (Passive) endpoint listens on - distinct from the BFF server port above, and only meaningful for RTI-SO connections",
        json_schema_extra={"example": 8765},
    )
    type: str = Field(
        ...,
        description="Type of the endpoint (e.g., RTI-FSP, RTI-SO, IDP-Server)",
        json_schema_extra={"example": "RTI-FSP"},
    )
    acsi: str | None = Field(
        default=None,
        description="ACSI role (server/client)",
        json_schema_extra={"example": "server"},
    )
    ws_mode: str | None = Field(
        default=None, description="WebSocket mode", json_schema_extra={"example": ""}
    )
    endpoint: str | None = Field(
        default=None,
        description="Endpoint path for IDP-Server",
        json_schema_extra={"example": "/idp"},
    )
    certificate_endpoint: str | None = Field(
        default=None,
        description="Certificate endpoint for OAuth",
        json_schema_extra={"example": "https://localhost:8443/certs"},
    )
    auth_server_ca: str | None = Field(
        default=None,
        description="Auth server CA certificate",
        json_schema_extra={"example": "-----BEGIN CERTIFICATE-----..."},
    )
    realm: str | None = Field(
        default=None,
        description="OAuth realm for FSP",
        json_schema_extra={"example": "master"},
    )
    token_endpoint: str | None = Field(
        default=None,
        description="OAuth token endpoint for FSP",
        json_schema_extra={
            "example": "https://localhost:8443/auth/realms/master/protocol/openid-connect/token"
        },
    )
    client_id: str | None = Field(
        default=None,
        description="OAuth client ID for FSP",
        json_schema_extra={"example": "rti-fsp-client"},
    )
    client_secret: str | None = Field(
        default=None, description="OAuth client secret for FSP"
    )
    enable_token_refresh: bool | None = Field(
        default=None,
        description="Enable token refresh for FSP",
        json_schema_extra={"example": True},
    )
    idp_server: str | None = Field(
        default=None,
        description="IDP Server name for OAuth",
        json_schema_extra={"example": "IDP-Server-01"},
    )
    cp: str | None = Field(
        default=None,
        description="Connection point identifier this RTI-FSP registers under",
        json_schema_extra={"example": "cp1"},
    )
    auto_discovered: bool = Field(
        default=False, description="Whether this connection was auto-discovered"
    )


class TLSConnectionCreateConfigRequest(BaseModel):
    """Request body for creating a new connection."""

    connection_name: str = Field(
        ...,
        description="Human-readable name for the connection",
        json_schema_extra={"example": "RTI-FSP-01"},
    )
    enable_tls: bool = Field(
        default=False, description="enable TLS", json_schema_extra={"example": False}
    )
    tls_version: str = Field(
        default="1.2", description="TLS version", json_schema_extra={"example": "1.2"}
    )
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
    ws_mode: str = Field(
        default="passive",
        description="WebSocket mode (passive or active)",
        json_schema_extra={"example": "passive"},
    )


class OAUTHConnectionCreateConfigRequest(BaseModel):
    """Request body for OAuth configuration."""

    connection_name: str = Field(
        ...,
        description="Human-readable name for the connection",
        json_schema_extra={"example": "RTI-FSP-01"},
    )
    enable_oauth: bool = Field(
        default=False, description="Enable OAuth", json_schema_extra={"example": False}
    )
    ws_mode: str = Field(
        default="passive",
        description="WebSocket mode (passive or active)",
        json_schema_extra={"example": "passive"},
    )
    certificate_endpoint_url: str | None = Field(
        default=None,
        description="OAuth Certificate endpoint URL",
        json_schema_extra={"example": "https://auth.example.com/certs"},
    )
    token_issuer_url: str | None = Field(
        default=None,
        description="Token issuer URL",
        json_schema_extra={"example": "https://auth.example.com"},
    )
    ca_certificate: str | None = Field(
        default=None,
        description="Server CA certificate",
        json_schema_extra={"example": "-----BEGIN CERTIFICATE-----..."},
    )
    token_endpoint_url: str | None = Field(
        default=None,
        description="Token endpoint URL",
        json_schema_extra={"example": "https://auth.example.com/token"},
    )
    client_id: str | None = Field(
        default=None,
        description="Client ID",
        json_schema_extra={"example": "your-client-id"},
    )
    client_secret: str | None = Field(
        default=None,
        description="Client secret",
        json_schema_extra={"example": "your-client-secret"},
    )
    client_ca_cert: str | None = Field(
        default=None,
        description="Client CA certificate",
        json_schema_extra={"example": "-----BEGIN CERTIFICATE-----..."},
    )
    enable_token_refresh: bool | None = Field(
        default=None,
        description="Enable token refresh",
        json_schema_extra={"example": False},
    )


class ConnectionUpdateRequest(BaseModel):
    """Request body for updating an existing connection."""

    name: str | None = Field(
        default=None, description="Human-readable name for the connection"
    )
    host: str | None = Field(
        default=None, description="Hostname or IP address of the endpoint's BFF server"
    )
    port: int | None = Field(
        default=None, description="Port number of the endpoint's BFF server"
    )
    ws_port: int | None = Field(
        default=None,
        description="Port the RTI-SO instance's own WebSocket (Passive) endpoint listens on - distinct from the BFF server port above",
    )
    type: str | None = Field(default=None, description="Type of the endpoint")
    acsi: str | None = Field(default=None, description="ACSI role (server/client)")
    ws_mode: str | None = Field(default=None, description="WebSocket mode")
    endpoint: str | None = Field(
        default=None, description="Endpoint path for IDP-Server"
    )
    certificate_endpoint: str | None = Field(
        default=None, description="Certificate endpoint for OAuth"
    )
    auth_server_ca: str | None = Field(
        default=None, description="Auth server CA certificate"
    )
    realm: str | None = Field(default=None, description="OAuth realm for FSP")
    token_endpoint: str | None = Field(
        default=None, description="OAuth token endpoint for FSP"
    )
    token_issuer_url: str | None = Field(
        default=None, description="Token issuer URL for OAuth"
    )

    client_id: str | None = Field(default=None, description="OAuth client ID for FSP")
    client_secret: str | None = Field(
        default=None, description="OAuth client secret for FSP"
    )
    enable_token_refresh: bool | None = Field(
        default=None, description="Enable token refresh for FSP"
    )
    idp_server: str | None = Field(
        default=None, description="IDP Server name for OAuth"
    )
    cp: str | None = Field(
        default=None,
        description="Connection point identifier this RTI-FSP registers under",
    )
    status: str | None = Field(default=None, description="Connection status")


class ExecuteRequest(BaseModel):
    """Request body for executing a dynamic API call."""

    target: str = Field(
        ...,
        description="Target endpoint identifier (host:port)",
        json_schema_extra={"example": "localhost:5000"},
    )
    method: str = Field(
        default="GET",
        description="HTTP method to use",
        json_schema_extra={"example": "GET"},
    )
    path: str = Field(
        ...,
        description="API path to call",
        json_schema_extra={"example": "/api/health"},
    )
    body: dict[str, Any] | None = Field(
        default=None, description="Request body for POST/PUT requests"
    )


class DataReadRequest(BaseModel):
    """Request body for reading data from an endpoint."""

    objRef: str = Field(
        ...,
        description="Object reference in IEC61850 format",
        json_schema_extra={"example": "LD0/LLN0$ST$Mod"},
    )


class DataWriteRequest(BaseModel):
    """Request body for writing data to an endpoint."""

    objRef: str = Field(
        ...,
        description="Object reference in IEC61850 format",
        json_schema_extra={"example": "LD0/LLN0$ST$Mod"},
    )
    value: str = Field(
        ..., description="Value to write", json_schema_extra={"example": "ON"}
    )


class DiscoveryRequest(BaseModel):
    """Request body for triggering service discovery."""

    host: str | None = Field(
        default=None,
        description="Host to scan",
        json_schema_extra={"example": "localhost"},
    )
    ports: list[int] | None = Field(default=None, description="List of ports to scan")
    startPort: int | None = Field(
        default=None,
        description="Start port for range scan",
        json_schema_extra={"example": 5000},
    )
    endPort: int | None = Field(
        default=None,
        description="End port for range scan",
        json_schema_extra={"example": 5010},
    )
