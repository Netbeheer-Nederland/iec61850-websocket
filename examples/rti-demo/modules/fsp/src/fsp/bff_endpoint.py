# SPDX-FileCopyrightText: 2025-2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
#
# Copyright 2025-2026 Netbeheer Nederland
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

"""Backend for Frontend (BFF) endpoint providing REST API for ACSI server control.

This module exposes REST API endpoints that interact with the ACSI server,
handling model management, server lifecycle, and value operations.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
import ssl
import sys
import tempfile
from concurrent.futures import TimeoutError as FuturesTimeoutError
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from acsi_plugins import (
    Associated,
    OperateReceived,
    OperateResponse,
    PluginHost,
    ServerStopped,
    ValueWritten,
)
from acsi_plugins.web import PluginService
from acsi_plugins.web import attach as attach_plugins
from fastapi import APIRouter, FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from fsp.acsi_server import RUNNING, ACSIServer
from ws61850.iec61850.data_model.ied_model import DataAttribute, DataObject, IedModel
from ws61850.security.tls import TLSConfig


def resolve_log_level(value: str | None, default: int = logging.INFO) -> int:
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
    format="%(asctime)s - %(name)s - %(threadName)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)  # Force stdout for Docker
    ],
    force=True,  # Override any existing config
)

# Apply the severity to the root logger here at import time, not only in the
# __main__ block, so every entry point honours LOG_LEVEL: `python
# fsp/bff_endpoint.py`, `uvicorn fsp.bff_endpoint:app`, a service wrapper, or
# pytest importing create_fastapi_app. Child loggers (acsi_server, ws61850.*)
# and any background event-loop thread inherit this level.
logging.getLogger().setLevel(LOG_LEVEL)

logger = logging.getLogger(__name__)


class HealthCheckAccessFilter(logging.Filter):
    """Demote uvicorn access-log lines for health/status polls to DEBUG.

    The Docker healthcheck hits ``/api/status`` (and service discovery hits
    ``/api/health``, and the HMI's message monitor polls ``/api/messages``)
    every few seconds; logged at INFO they bury the real request log.
    Matching records are relabelled DEBUG and only pass through when the
    ``uvicorn.access`` logger is actually at DEBUG.
    """

    QUIET_PATHS = (
        "/api/status",
        "/api/health",
        "/api/messages",
        "/api/actions-logs",
        "/api/tls-config",
        "/api/oauth-status",
    )

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


def _off(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in ("0", "false", "no", "off")


def _autostart(server) -> None:
    """Start the ACSI server with the service (decision 0033).

    FSP_AUTOSTART (default true) starts it "ready": it serves its model,
    runs its reports and takes writes, without a connection to the SO; the
    HMI's Connect (POST /api/iec61850server/start) then only dials out.
    FSP_AUTOCONNECT (default false) also dials out to FSP_SO_HOST (default
    localhost) and FSP_SO_PORT (default 8765), trying again every few
    seconds while the SO isn't there. A failure is logged, not raised - the
    REST API still starts.
    """
    if _off("FSP_AUTOSTART", "true"):
        return
    try:
        if _off("FSP_AUTOCONNECT", "false"):
            server.start_server()
            server._log_action("Autostart: server ready", "info", kind="system")
            return
        host = os.getenv("FSP_SO_HOST", "localhost")
        port = int(os.getenv("FSP_SO_PORT", "8765"))
        server.start_server(host, port)
        server._log_action(
            f"Autostart: dialing the SO at host={host}, port={port}",
            "info",
            kind="system",
        )
    except (ValueError, RuntimeError, OSError) as exc:
        server._log_action(f"Autostart failed: {exc}", "warn", kind="system")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Installed here (not before uvicorn.run), so it survives uvicorn's own
    # logging dictConfig, which runs before app startup.
    logging.getLogger("uvicorn.access").addFilter(HealthCheckAccessFilter())
    # Looked up here, not bound at import, so tests can replace it.
    async with plugin_service.lifespan():
        # After the plugins, so they see the association.
        server = getattr(app.state, "server", None)
        if server is not None:
            _autostart(server)
        yield


# ==================== Plugins ====================
# The plugins this FSP hosts (decisions 0021, 0029): HTTP services it
# connects to. The host passes ACSI events to them and asks the owner of an
# objRef to answer an Operate on it; the service connects the configured ones
# at startup and adds, reloads and removes them (/api/plugins). Settings from
# PLUGINS_FILE, PLUGINS, PLUGIN_HOST_URL, PLUGIN_ALLOWED_SOURCES and
# PLUGIN_RETRY_SECONDS.
plugin_host = PluginHost(role="fsp")
plugin_service = PluginService.from_env(plugin_host)


# ==================== Pydantic Models ====================
class WritevalueRequest(BaseModel):
    """Request body for writing a value to the ACSI server model."""

    obj_ref: str = Field(
        ...,
        alias="objRef",
        description="Object reference in ACSI format (e.g., 'LD0/LLN0$ST$Mod')",
        json_schema_extra={"example": "LD0/LLN0$ST$Mod"},
    )
    fc: str = Field(
        ...,
        description="Functional constraint (ST, MX, CO, etc.)",
        json_schema_extra={"example": "ST"},
    )
    value: str = Field(
        ...,
        description="Value to write as string representation",
        json_schema_extra={"example": "ON"},
    )
    data_type: str = Field(
        default="",
        alias="dataType",
        description="Optional data type for value coercion",
        json_schema_extra={"example": "BOOLEAN"},
    )


class UpdateIedmodelRequest(BaseModel):
    """Request body for updating the IED model file."""

    model_source: str = Field(
        ...,
        alias="modelPy",
        description="Complete Python code for model.py file",
        json_schema_extra={
            "example": "from ws61850... import IedModel\nmodel = IedModel(...)"
        },
    )


class StartRequest(BaseModel):
    """Request body for starting the ACSI WebSocket Passive."""

    host: str = Field(
        default="0.0.0.0",
        description="Hostname or IP address to bind to",
        json_schema_extra={"example": "0.0.0.0"},
    )
    port: str = Field(
        default="8765",
        description="Port number to listen on",
        json_schema_extra={"example": "8765"},
    )
    mode: str = Field(
        default="server",
        description="Operating mode (only 'server' supported)",
        json_schema_extra={"example": "server"},
    )
    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"},
    )
    # Optional stored TLS config - added by the BFF's /api/execute from
    # connections.json, since TLS is otherwise lost when this FSP restarts.
    # Omitted entirely, the endpoint's current TLS config is left as-is.
    enable_tls: bool | None = Field(
        default=None,
        description="Dial out over WSS (omit to keep the current TLS setting)",
        json_schema_extra={"example": True},
    )
    tls_version: str | None = Field(
        default=None,
        description="TLS version",
        json_schema_extra={"example": "TLSv1_3"},
    )
    server_ca: str | None = Field(
        default=None,
        description="CA certificate (PEM) to validate the SO against",
        json_schema_extra={"example": "-----BEGIN CERTIFICATE-----..."},
    )
    # Optional stored OAuth config - added by the BFF's /api/execute from
    # connections.json, so the token is fetched before dialing out instead of
    # by a /reconfig-oauth after a first, token-less attempt the SO refuses.
    # Omitted entirely, the current OAuth setup is left as-is.
    enable_oauth: bool | None = Field(
        default=None,
        description="Present an OAuth token (omit to keep the current OAuth setting)",
    )
    token_endpoint_url: str | None = Field(
        default=None, description="IDP token endpoint"
    )
    client_id: str | None = Field(default=None, description="OAuth client id")
    client_secret: str | None = Field(default=None, description="OAuth client secret")
    ca_certificate: str | None = Field(
        default=None, description="CA certificate (PEM) for the IDP's HTTPS"
    )
    enable_token_refresh: bool | None = Field(
        default=None, description="Fetch a fresh token on every (re)connect"
    )


def _client_tls_config(tls_version: str | None, server_ca: str | None) -> TLSConfig:
    """Client-mode TLSConfig for the FSP's active dial-out."""
    # Normalize tls_version to handle "1.2", "1.3", "TLSv1_2", "TLSv1_3" formats
    tls_version_str = (tls_version or "1.3").lower()
    if "1.2" in tls_version_str or "1_2" in tls_version_str:
        version = ssl.TLSVersion.TLSv1_2
    else:
        version = ssl.TLSVersion.TLSv1_3
    keylog_file = tempfile.NamedTemporaryFile(
        mode="w",
        prefix="tlskeys",
        suffix=".log",
        delete=True,
    )
    return TLSConfig(
        mode="client",
        cafile=server_ca,
        min_version=version,
        max_version=version,
        keylog_file=keylog_file.name,
    )


class ReadvalueRequest(BaseModel):
    """Request body for reading a value from the ACSI server model."""

    obj_ref: str = Field(
        ...,
        alias="objRef",
        description="Object reference in ACSI format",
        json_schema_extra={"example": "LD0/MMXU1$MX$volA"},
    )
    fc: str = Field(
        default="",
        description="Functional constraint (optional)",
        json_schema_extra={"example": "MX"},
    )


class TLSConnectionCreateConfigRequest(BaseModel):
    """Request body for creating a new connection."""

    host: str = Field(
        default="0.0.0.0",
        description="Hostname or IP address to bind to",
        json_schema_extra={"example": "0.0.0.0"},
    )
    port: str = Field(
        default="8765",
        description="Port number to listen on",
        json_schema_extra={"example": "8765"},
    )

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


class OAUTHCreateConfigRequest(BaseModel):
    """Request body for OAuth reconfiguration."""

    connection_name: str | None = Field(
        default=None,
        description="Connection name (optional, auto-detected)",
        json_schema_extra={"example": "RTI-FSP-01"},
    )
    enable_oauth: bool = Field(
        default=False,
        description="Enable OAuth authentication",
        json_schema_extra={"example": False},
    )
    host: str = Field(
        default="127.0.0.1",
        description="ws host",
        json_schema_extra={"example": "127.0.0.1"},
    )
    port: str = Field(
        default="8765", description="ws port", json_schema_extra={"example": "8765"}
    )
    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"},
    )
    ws_mode: str = Field(
        default="active",
        description="WebSocket mode (passive or active)",
        json_schema_extra={"example": "active"},
    )
    # OAuth settings for FSP (active mode)
    token_endpoint_url: str | None = Field(
        default=None,
        description="OAuth Token endpoint URL",
        json_schema_extra={"example": "https://auth.example.com/token"},
    )
    client_id: str | None = Field(
        default=None,
        description="OAuth Client ID",
        json_schema_extra={"example": "my-client-id"},
    )
    client_secret: str | None = Field(
        default=None,
        description="OAuth Client Secret",
        json_schema_extra={"example": "my-client-secret"},
    )
    ca_certificate: str | None = Field(
        default=None,
        description="Server CA certificate",
        json_schema_extra={"example": "-----BEGIN CERTIFICATE-----..."},
    )
    enable_token_refresh: bool = Field(
        default=False,
        description="Enable token refresh",
        json_schema_extra={"example": False},
    )


def create_bff_router(factory_dir) -> tuple[APIRouter, ACSIServer]:
    """Create a FastAPI router for the ACSI server BFF API.

    Args:
        factory_dir: Path to the fsp directory containing model.py

    Returns:
        Tuple of (APIRouter, ACSIServer instance)
    """

    router = APIRouter(
        prefix="/api",
        tags=["ACSI-Server"],
        responses={
            404: {"description": "Not found"},
            500: {"description": "Internal server error"},
        },
    )

    rti_fsp = ACSIServer(factory_dir)

    def on_connected_callback(associate_response):
        """An associateResponse was sent."""
        logger.info(f"[FSP CONNECTED] associateResponse: {associate_response}")
        plugin_host.emit(
            Associated(associate_response.get("associateId", "fsp_connected"))
        )

    def on_operate_received_callback(operate_data):
        """An Operate request was received."""
        logger.info(f"[FSP OPERATE RECEIVED] operate request: {operate_data}")
        plugin_host.emit(OperateReceived(operate_data))

    def on_operate_response_callback(operate_response):
        """An Operate response was sent."""
        logger.info(f"[FSP OPERATE RESPONSE] operate response: {operate_response}")
        plugin_host.emit(
            OperateResponse(
                success=bool(operate_response.get("success", False)),
                add_cause=operate_response.get("addCause") or None,
                data=operate_response,
            )
        )

    # The plugin that owns an objRef answers an Operate on it. Looked up per
    # call, so the module's plugin_host can be replaced (tests).
    rti_fsp.install_control_hook(
        lambda obj_ref, ctl_val: plugin_host.handle_control(obj_ref, ctl_val)
    )
    rti_fsp.install_connected_callback(on_connected_callback)
    rti_fsp.install_operate_received_callback(on_operate_received_callback)
    rti_fsp.install_operate_response_callback(on_operate_response_callback)

    # ==================== Helper Functions ====================
    def serialize_data_attribute(da: DataAttribute) -> dict[str, Any]:
        """Serialize a DataAttribute to JSON-compatible dict."""
        return {
            "kind": "DA",
            "type": "DA",
            "name": da.name,
            "fc": da.fc.name if da.fc is not None else None,
            "bType": da.type.name if da.type is not None else None,
            "children": [
                serialize_data_attribute(child) for child in (da.data_attributes or [])
            ],
        }

    def serialize_data_object(do: DataObject) -> dict[str, Any]:
        """Serialize a DataObject to JSON-compatible dict."""
        children: list[dict[str, Any]] = []
        for item in do.do_or_da or []:
            if isinstance(item, DataObject):
                children.append(serialize_data_object(item))
            elif isinstance(item, DataAttribute):
                children.append(serialize_data_attribute(item))

        return {
            "kind": "DO",
            "type": "DO",
            "name": do.name,
            "cdc": do.cdc,
            "children": children,
        }

    def serialize_ied_tree(ied: IedModel) -> dict[str, Any]:
        """Serialize an IED model tree to JSON-compatible dict."""
        return {
            "kind": "IED",
            "type": "IED",
            "name": ied.name,
            "children": [
                {
                    "kind": "LD",
                    "type": "LDevice",
                    "name": ld.name,
                    "ldName": ld.ldName,
                    "children": [
                        {
                            "kind": "LN",
                            "type": "LogicalNode",
                            "name": ln.name,
                            "children": (
                                [
                                    {
                                        "kind": "Group",
                                        "type": "Group",
                                        "name": "DataSets",
                                        "children": [
                                            {
                                                "kind": "DataSet",
                                                "type": "DataSet",
                                                "name": ds.name,
                                                "ref": f"{ld.name}/{ln.name}.{ds.name}",
                                            }
                                            for ds in (ln.data_sets or [])
                                        ],
                                    }
                                ]
                                if (ln.data_sets or [])
                                else []
                            )
                            + (
                                [
                                    {
                                        "kind": "Group",
                                        "type": "Group",
                                        "name": "ReportControls",
                                        "children": [
                                            {
                                                "kind": "BRCB"
                                                if rcb.buffered
                                                else "URCB",
                                                "type": "ReportControl",
                                                "name": rcb.name,
                                                "ref": f"{ld.name}/{ln.name}.{rcb.name}",
                                            }
                                            for rcb in (ln.rcbs or [])
                                        ],
                                    }
                                ]
                                if (ln.rcbs or [])
                                else []
                            )
                            + [
                                serialize_data_object(do)
                                for do in (ln.data_objects or [])
                            ],
                        }
                        for ln in (ld.logical_nodes or [])
                    ],
                }
                for ld in (ied.logical_devices or [])
            ],
        }

    def collect_da_paths_from_do(data_object: DataObject, prefix: str) -> list[tuple]:
        """Collect flattened (path, fc_name) tuples under a DO path."""
        results: list[tuple] = []
        for item in data_object.do_or_da or []:
            if isinstance(item, DataAttribute):
                da_path = f"{prefix}.{item.name}"
                fc_name = item.fc.name if item.fc is not None else None
                results.append((da_path, fc_name))
                results.extend(collect_da_paths_from_da(item, da_path))
            elif isinstance(item, DataObject):
                sub_prefix = f"{prefix}.{item.name}"
                results.extend(collect_da_paths_from_do(item, sub_prefix))
        return results

    def collect_da_paths_from_da(
        data_attribute: DataAttribute, prefix: str
    ) -> list[tuple]:
        """Collect flattened (path, fc_name) tuples for nested DA paths."""
        results: list[tuple] = []
        for child in data_attribute.data_attributes or []:
            child_path = f"{prefix}.{child.name}"
            fc_name = child.fc.name if child.fc is not None else None
            results.append((child_path, fc_name))
            results.extend(collect_da_paths_from_da(child, child_path))
        return results

    def build_logical_node_details(
        ied_model: IedModel | None,
    ) -> dict[str, dict[str, Any]]:
        """Build UI-friendly logical node details."""
        details: dict[str, dict[str, Any]] = {}
        if ied_model is None:
            return details

        for ld in ied_model.logical_devices or []:
            for ln in ld.logical_nodes or []:
                data_objects: list[dict[str, Any]] = []
                data_attributes: list[str] = []
                da_fc_map: dict[str, str] = {}
                report_control_blocks: list[dict[str, Any]] = []
                datasets: list[dict[str, Any]] = []
                ln_prefix = f"{ld.name}/{ln.name}."

                for data_object in ln.data_objects or []:
                    cdc = (data_object.cdc or "").lower()
                    obj_info = {"name": data_object.name, "cdc": data_object.cdc}

                    # Collect DataSets (from DataObjects with cdc="dataset")
                    if cdc == "dataset":
                        datasets.append(obj_info)
                    # Collect Report Control Blocks (RCB, BRCB, URCB) from DataObjects
                    elif cdc in ("rcb", "brcb", "urcb"):
                        report_control_blocks.append(obj_info)

                    data_objects.append(obj_info)
                    for da_path, fc_name in collect_da_paths_from_do(
                        data_object, data_object.name
                    ):
                        data_attributes.append(da_path)
                        if fc_name:
                            da_fc_map[f"{ln_prefix}{da_path}"] = fc_name

                # Also collect DataSets from ln.data_sets
                for ds in ln.data_sets or []:
                    datasets.append({"name": ds.name, "cdc": "dataset"})

                # Also collect ReportControls from ln.rcbs
                for rcb in ln.rcbs or []:
                    report_control_blocks.append({"name": rcb.name, "cdc": "rcb"})

                ln_key = f"{ld.name}/{ln.name}"
                details[ln_key] = {
                    "dataObjects": data_objects,
                    "dataAttributes": sorted(set(data_attributes)),
                    "dataAttributeFcs": da_fc_map,
                    "reportControlBlocks": report_control_blocks,
                    "dataSets": datasets,
                }

        return details

    def extract_tpa_info(websocket_info: Any) -> dict[str, Any]:
        """Extract TPA (Three Part Address) and connection info from websocket_info."""
        info = {
            "peer_address": None,
            "peer_port": None,
            "role": "ACSI-Server",
            "ws_mode": "active",
            "remote_role": None,
            "tpa": None,
            "status": "active",
        }

        try:
            if hasattr(websocket_info, "remote_address"):
                addr_tuple = websocket_info.remote_address
                if isinstance(addr_tuple, tuple) and len(addr_tuple) >= 2:
                    info["peer_address"] = addr_tuple[0]
                    info["peer_port"] = addr_tuple[1]
            elif hasattr(websocket_info, "peername"):
                addr_tuple = websocket_info.peername()
                if isinstance(addr_tuple, tuple) and len(addr_tuple) >= 2:
                    info["peer_address"] = addr_tuple[0]
                    info["peer_port"] = addr_tuple[1]

            if hasattr(websocket_info, "tpa"):
                info["tpa"] = str(websocket_info.tpa)
            elif hasattr(websocket_info, "request") and hasattr(
                websocket_info.request, "headers"
            ):
                headers = websocket_info.request.headers
                if "X-TPA" in headers:
                    info["tpa"] = headers["X-TPA"]

            if hasattr(websocket_info, "connected") and not websocket_info.connected:
                info["status"] = "disconnected"
            elif hasattr(websocket_info, "is_open") and not websocket_info.is_open():
                info["status"] = "disconnected"
        except Exception:
            pass

        return info

    # ==================== Route Handlers ====================

    @router.get(
        "/apis",
        summary="List All API Endpoints",
        description="Returns a comprehensive list of all available API endpoints with their HTTP methods, request body schemas, and response formats.",
        response_description="List of all endpoints with their metadata",
        tags=["Discovery"],
    )
    async def api_list_all_endpoints():
        """List all API endpoints with their schemas and metadata.

        This endpoint provides introspection capabilities, returning:
        - All available routes under /api/
        - HTTP methods supported by each endpoint
        - Request body schemas (when applicable)
        - Endpoint names for programmatic access

        Returns:
            dict: {
                "ok": True,
                "count": int,
                "endpoints": [
                    {
                        "path": str,
                        "methods": list[str],
                        "endpoint": str,
                        "body_schema": dict | None
                    }
                ]
            }
        """
        from pydantic import TypeAdapter

        routes = []
        for route in router.routes:
            # route.path on a route added through a prefixed APIRouter (here,
            # prefix="/api") is already the full path, e.g. "/api/status" -
            # prepending "/api" again doubled it to "/api/api/status".
            path = route.path
            methods = list(route.methods)

            body_schema = None
            if hasattr(route, "body_field") and route.body_field:
                try:
                    model = route.body_field.annotation
                    if model is not Any:
                        adapter = TypeAdapter(model)
                        body_schema = adapter.json_schema()
                except Exception:
                    body_schema = None

            routes.append(
                {
                    "path": path,
                    "methods": methods,
                    "endpoint": route.name,
                    "body_schema": body_schema,
                }
            )

        return {
            "ok": True,
            "count": len(routes),
            "endpoints": sorted(routes, key=lambda x: x["path"]),
        }

    @router.get(
        "/status",
        summary="Get Server Status",
        description="Retrieves the current operational status of the ACSI WebSocket.",
        response_description="Server status information",
        responses={
            200: {"description": "Server status returned successfully"},
            500: {"description": "Error retrieving server status"},
        },
        tags=["Server Control"],
    )
    def api_status():
        """Get current server status.

        Returns:
            JSONResponse: {
                "ok": True,
                "status": str  # One of: "stopped", "starting", "ready", "listening", "stopping", "error"
            }
        """
        try:
            return JSONResponse(
                # A JSON object, not str(dict) - see
                # test_status_error_with_quotes_survives_as_json.
                content={"ok": True, "status": rti_fsp.get_status()},
                status_code=200,
            )
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)}, status_code=500
            )

    @router.get(
        "/health",
        summary="Health Check",
        description="Health check endpoint for service discovery and monitoring. Returns the service status and connection information.",
        response_description="Health status and service information",
        responses={
            200: {"description": "Service is healthy and running"},
            500: {"description": "Service is unhealthy"},
        },
        tags=["Health"],
    )
    def api_health():
        """Generic health endpoint used by external discovery (e.g., BFF network scan).

        Returns:
            dict: {
                "status": "ok",
                "service": "ACSI-Server",
                "server": {
                    "status": str | None,
                    "host": str | None,
                    "port": int | None
                }
            }
        """
        try:
            status = rti_fsp.get_status()
            return {
                "status": "ok",
                "service": "ACSI-Server",
                "server": {
                    "status": status.get("status"),
                    "host": status.get("host"),
                    "port": status.get("port"),
                },
            }
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)}, status_code=500
            )

    @router.get(
        "/connections",
        summary="List Active Connections",
        description="Returns information about all currently connected active WebSockets, including peer addresses and connection status.",
        response_description="List of active WebSocket connections",
        responses={
            200: {"description": "List of connections returned successfully"},
            500: {"description": "Error retrieving connections"},
        },
        tags=["Connections"],
    )
    def api_connections():
        """Get TPA information for all connected servers.

        Returns:
            dict: {
                "ok": True,
                "role": "ACSI-Server",
                "ws_mode": "active",
                "connected_servers": int,
                "connections": list[dict]  # Each containing peer_address, peer_port, tpa, status
            }
        """
        try:
            endpoint = rti_fsp.runtime.endpoint
            connections = []

            if endpoint is not None and hasattr(endpoint, "websocket_info_list"):
                for ws_info in endpoint.websocket_info_list:
                    tpa_data = extract_tpa_info(ws_info)
                    connections.append(tpa_data)

            return {
                "ok": True,
                "role": "ACSI-Server",
                "ws_mode": "active",
                "connected_servers": len(connections),
                "connections": connections,
            }
        except Exception as exc:
            rti_fsp._log_action(
                f"Get connections failed: {exc}", "error", kind="system"
            )
            return JSONResponse(
                content={"ok": False, "error": str(exc)}, status_code=500
            )

    @router.get(
        "/properties",
        summary="Get Server Properties",
        description="Returns the static properties and capabilities of the ACSI server.",
        response_description="Server role and mode properties",
        tags=["Server Control"],
    )
    def api_roles():
        """Get property information for the server.

        Returns:
            dict: {
                "ok": True,
                "acsi_role": "ACSI-Server",
                "ws_mode": "Active"
            }
        """
        return {
            "ok": True,
            "acsi_role": "ACSI-Server",
            "ws_mode": "Active",
        }

    @router.get(
        "/model",
        summary="Get IED Model",
        description="Returns the current loaded IED model descriptor for UI rendering, including the complete hierarchy of logical devices, logical nodes, data objects, and data attributes.",
        response_description="Complete IED model tree structure",
        responses={
            200: {"description": "IED model data returned successfully"},
            500: {"description": "Error retrieving model"},
        },
        tags=["Model"],
    )
    def api_model():
        """Return current loaded model descriptor for UI rendering.

        The response includes:
        - Server information and access points
        - Complete IED model tree
        - Logical device map
        - Detailed logical node information with data objects and attributes

        Returns:
            dict: {
                "status": "ready",
                "accessPoints": list[str],
                "model": {
                    "server": {...},
                    "tree": {...},
                    "source": str,
                    "iedName": str,
                    "logicalDeviceMap": dict,
                    "logicalNodeDetails": dict
                }
            }
        """
        try:
            ied_model: IedModel | None = rti_fsp.runtime.ied_model
            source = rti_fsp.runtime.model_source
            selected_ied = rti_fsp.runtime.model_ied_name
            access_points = [rti_fsp.runtime.cp or "cp1"]

            logical_devices: list[str] = []
            if ied_model is not None:
                logical_devices = [ld.name for ld in (ied_model.logical_devices or [])]

            tree_data = serialize_ied_tree(ied_model) if ied_model is not None else None
            logical_node_details = build_logical_node_details(ied_model)

            result = {
                "status": "ready",
                "accessPoints": access_points,
                "model": {
                    "server": {
                        "name": "ACSI Server WS Active",
                        "mode": "active",
                        "logicalDevices": logical_devices,
                        "iedName": selected_ied,
                        "iedNames": [selected_ied] if selected_ied else [],
                    },
                    "tree": tree_data,
                    "source": source,
                    "iedName": selected_ied,
                    "logicalDeviceMap": {
                        ld.name: [ln.name for ln in (ld.logical_nodes or [])]
                        for ld in (ied_model.logical_devices or [])
                    }
                    if ied_model is not None
                    else {"-": ["No model loaded. Upload an .scl/.scd file."]},
                    "logicalNodeDetails": logical_node_details,
                },
            }
            has_tree = tree_data is not None
            logger.info(
                f"[GET /ap/model] "
                f"ied_model={ied_model is not None} "
                f"has_tree={has_tree} "
                f"source={source!r} "
                f"iedName={selected_ied!r} "
                f"logicalDevices={logical_devices}"
            )
            return result
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)}, status_code=500
            )

    @router.post(
        "/update-iedmodel",
        summary="Update IED Model",
        description="Updates the model.py file in the ACSI-Server directory and reloads the IED model. Supports dynamic hot-swap while server is running.",
        response_description="Model update confirmation",
        responses={
            200: {"description": "Model updated successfully"},
            202: {"description": "Model update accepted, hot-swap in progress"},
            400: {"description": "Invalid request"},
            500: {"description": "Error updating model"},
        },
        tags=["Model"],
    )
    def api_update_iedmodel(request: UpdateIedmodelRequest):
        """Update model.py in fsp directory and reload IED model.

        Supports dynamic model updates while the server is running (hot-swap).
        The new model will be applied immediately if the server is running,
        or loaded when the server starts.

        Request Body:
            UpdateIedmodelRequest: { "modelPy": str }

        Returns:
            dict: {
                "ok": True,
                "source": str,  # Path to the updated model file
                "ied": str,     # Name of the IED model
                "modelVersion": int,  # New model version number
                "dynamicReload": bool, # Whether hot-swap was performed
                "status": str   # "loaded" or "reloading"
            }
        """
        try:
            model_py = request.model_source

            if not isinstance(model_py, str) or not model_py.strip():
                return JSONResponse(
                    content={
                        "ok": False,
                        "error": "modelPy is required and must be a non-empty string.",
                    },
                    status_code=400,
                )

            # Check server status
            server_status = rti_fsp.get_status()
            is_running = server_status.get("status") in RUNNING

            # Always apply dynamically if server is running
            ied_model = rti_fsp.update_model_file(model_py, apply_dynamically=True)

            rti_fsp._log_action(
                "IED model updated",
                detail={
                    "source": str(rti_fsp.model_file),
                    "ied": ied_model.name,
                    "dynamic": is_running,
                    "version": rti_fsp.runtime.model_version,
                },
                kind="system",
            )

            # Check if hot-swap is in progress
            if is_running and rti_fsp.runtime.model_reload_in_progress:
                return JSONResponse(
                    content={
                        "ok": True,
                        "source": str(rti_fsp.model_file),
                        "ied": ied_model.name,
                        "modelVersion": rti_fsp.runtime.model_version,
                        "dynamicReload": True,
                        "status": "reloading",
                    },
                    status_code=202,  # Accepted - hot-swap in progress
                )
            else:
                return {
                    "ok": True,
                    "source": str(rti_fsp.model_file),
                    "ied": ied_model.name,
                    "modelVersion": rti_fsp.runtime.model_version,
                    "dynamicReload": is_running,
                    "status": "loaded",
                }

        except Exception as exc:
            rti_fsp._log_action(
                f"IED model update failed: {exc}", "error", kind="system"
            )
            return JSONResponse(
                content={"ok": False, "error": str(exc)}, status_code=400
            )

    @router.post(
        "/update-iedmodel-file",
        summary="Update IED Model from File",
        description="Upload a model.py file directly. Supports dynamic hot-swap while server is running.",
        response_description="Model update confirmation",
        responses={
            200: {"description": "Model updated successfully"},
            202: {"description": "Model update accepted, hot-swap in progress"},
            400: {"description": "Invalid request"},
            500: {"description": "Error updating model"},
        },
        tags=["Model"],
    )
    async def api_update_iedmodel_file(file: UploadFile = File(...)):
        """Upload model.py file directly for update.

        Accepts multipart/form-data with a 'file' field containing the model.py content.
        Supports the same hot-swap behavior as the JSON endpoint.

        Args:
            file: UploadFile - The model.py file to upload

        Returns:
            dict: {
                "ok": True,
                "source": str,  # Path to the updated model file
                "ied": str,     # Name of the IED model
                "modelVersion": int,  # New model version number
                "dynamicReload": bool, # Whether hot-swap was performed
                "status": str   # "loaded" or "reloading"
            }
        """
        try:
            # Read file content as string
            model_py = await file.read()
            model_py = model_py.decode("utf-8")

            if not model_py.strip():
                return JSONResponse(
                    content={"ok": False, "error": "Uploaded file is empty."},
                    status_code=400,
                )

            # Reuse existing logic
            server_status = rti_fsp.get_status()
            is_running = server_status.get("status") in RUNNING

            ied_model = rti_fsp.update_model_file(model_py, apply_dynamically=True)

            rti_fsp._log_action(
                "IED model updated from file",
                detail={
                    "source": str(rti_fsp.model_file),
                    "ied": ied_model.name,
                    "dynamic": is_running,
                    "version": rti_fsp.runtime.model_version,
                    "filename": file.filename,
                },
                kind="system",
            )

            # Check if hot-swap is in progress
            if is_running and rti_fsp.runtime.model_reload_in_progress:
                return JSONResponse(
                    content={
                        "ok": True,
                        "source": str(rti_fsp.model_file),
                        "ied": ied_model.name,
                        "modelVersion": rti_fsp.runtime.model_version,
                        "dynamicReload": True,
                        "status": "reloading",
                    },
                    status_code=202,  # Accepted - hot-swap in progress
                )
            else:
                return {
                    "ok": True,
                    "source": str(rti_fsp.model_file),
                    "ied": ied_model.name,
                    "modelVersion": rti_fsp.runtime.model_version,
                    "dynamicReload": is_running,
                    "status": "loaded",
                }

        except Exception as exc:
            rti_fsp._log_action(
                f"IED model file update failed: {exc}", "error", kind="system"
            )
            return JSONResponse(
                content={"ok": False, "error": str(exc)}, status_code=400
            )

    @router.post(
        "/start",
        summary="Start Server",
        description="Starts the ACSI server - Active WebSocket on the specified host and port. Only 'server' mode is supported.",
        response_description="Server start confirmation",
        responses={
            200: {"description": "Server started successfully"},
            400: {"description": "Invalid parameters or server error"},
        },
        tags=["Server Control"],
    )
    def api_start(request: StartRequest):
        """Start the ACSI WebSocket server.

        Request Body:
            StartRequest: {
                "host": str,    # Hostname/IP to bind to
                "port": str,    # Port number to listen on
                "mode": str,    # Only 'server' mode supported
                "cp": str       # Communication point identifier
            }

        Returns:
            dict: {
                "ok": True,
                "status": "listening",
                "host": str,
                "port": int
            }

        Raises:
            HTTPException 400: If mode is not 'server' or port is invalid
            HTTPException 400: If server fails to start
        """
        try:
            host = request.host
            raw_port = request.port
            mode = request.mode
            cp = request.cp

            if mode != "active":
                rti_fsp._log_action(
                    "Only 'active' mode is supported in this app",
                    "error",
                    kind="system",
                )
                return JSONResponse(
                    content={
                        "ok": False,
                        "error": "Only 'active' mode is supported in this app.",
                    },
                    status_code=400,
                )
            try:
                port = int(raw_port)
            except (TypeError, ValueError):
                return JSONResponse(
                    content={"ok": False, "error": f"Invalid port value: {raw_port!r}"},
                    status_code=400,
                )

            if cp:
                try:
                    rti_fsp._set_runtime_state(cp=cp)
                except Exception as exc:
                    return JSONResponse(
                        content={
                            "ok": False,
                            "error": f"Failed to set runtime state: {exc}",
                        },
                        status_code=400,
                    )

            if request.enable_tls is not None:
                rti_fsp.runtime.endpoint._tls_config = (
                    _client_tls_config(request.tls_version, request.server_ca)
                    if request.enable_tls
                    else None
                )
                rti_fsp._log_action(
                    f"Applied TLS config on start: enable_tls={request.enable_tls}",
                    "debug",
                    kind="system",
                )

            if request.enable_oauth is not None:
                if request.enable_oauth and not request.token_endpoint_url:
                    return JSONResponse(
                        content={
                            "ok": False,
                            "error": "OAuth is enabled but no token_endpoint_url was given",
                        },
                        status_code=400,
                    )
                endpoint = rti_fsp.runtime.endpoint
                if request.enable_oauth:
                    rti_fsp.runtime.start_oauth = {
                        "token_endpoint": request.token_endpoint_url,
                        "client_id": request.client_id,
                        "client_secret": request.client_secret,
                        "kc_cert": request.ca_certificate,
                        "enable_token_refresh": bool(request.enable_token_refresh),
                    }
                else:
                    rti_fsp.runtime.start_oauth = None
                    if endpoint is not None:
                        endpoint._oauth_enable = False
                        endpoint._access_token = None
                        endpoint._credentials_provider = None
                        endpoint._assoc_handler._token_endpoint = None
                        endpoint._assoc_handler._kc_cert = None
                rti_fsp._log_action(
                    f"Applied OAuth config on start: enable_oauth={request.enable_oauth}",
                    "debug",
                    kind="system",
                )

            try:
                # A ready server (FSP_AUTOSTART) only dials out.
                rti_fsp.connect(host, port)
            except Exception as exc:
                return JSONResponse(
                    content={"ok": False, "error": f"Failed to start server: {exc}"},
                    status_code=400,
                )

            return {"ok": True, "status": "listening", "host": host, "port": port}
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": f"Unexpected error: {exc}"},
                status_code=400,
            )

    @router.post(
        "/stop",
        summary="Disconnect",
        description="Drops the connection to the SO; the ACSI server keeps running, ready (decision 0033).",
        response_description="Server stop confirmation",
        responses={
            200: {"description": "Server stopped or stopping"},
            500: {"description": "Error stopping server"},
        },
        tags=["Server Control"],
    )
    def api_stop():
        """Drop the connection to the SO (the HMI's Disconnect).

        The ACSI server keeps running, "ready": it serves its model, runs its
        reports and takes writes, and /start connects it again. A server that
        isn't running or connected is left as it is, except one that is
        starting or failed, which is stopped.

        Returns:
            dict: {
                "ok": True,
                "status": str  # "ready", "stopped" or "stopping"
            }

        Raises:
            HTTPException 500: If error occurs during stop
        """
        try:
            status = rti_fsp.runtime.status
            logger.info(f"[FSP STOP] current status={status!r}")
            if status in (None, "stopped"):
                logger.info("[FSP STOP] early-return: already stopped")
                return {"ok": True, "status": "stopped"}
            if status in ("ready", "reloading"):
                logger.info("[FSP STOP] early-return: not connected")
                return {"ok": True, "status": status}

            try:
                # Tell the plugins first, and wait for them (up to 5 s): the IO
                # plugin turns its "connected" LED off. ServerStopped: the
                # connection ends; the server keeps running. This handler runs on
                # a worker thread, not the plugin loop, so waiting is safe.
                done, pending = concurrent.futures.wait(
                    plugin_host.emit(ServerStopped()), timeout=5
                )
                if pending:
                    logger.warning(
                        f"[FSP STOP] {len(pending)} plugin(s) still busy after 5 s"
                    )

                if status == "listening":
                    rti_fsp.disconnect()
                    return {"ok": True, "status": rti_fsp.runtime.status}
                rti_fsp.stop_server()
                current = rti_fsp.runtime.status
                if current in ("stopping", "starting"):
                    return {"ok": True, "status": "stopping"}
                return {"ok": True, "status": "stopped"}
            except Exception as exc:
                current = rti_fsp.runtime.status
                if current in ("stopping", "stopped"):
                    return {"ok": True, "status": current}
                rti_fsp._log_action(f"Stop failed: {exc}", "error", kind="system")
                return JSONResponse(
                    content={"ok": False, "error": f"Unexpected error: {exc}"},
                    status_code=500,
                )
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": f"Unexpected error: {exc}"},
                status_code=500,
            )

    @router.post(
        "/reconfig-connection",
        summary="Get Connection Info",
        description="Returns detailed information about the current WebSocket connection, including peer address, port, and connection status.",
        response_description="Connection details",
        responses={
            200: {"description": "Connection information returned successfully"},
            500: {"description": "Error retrieving connection info"},
        },
        tags=["Client Status"],
    )
    async def api_reconfig_connection(request: TLSConnectionCreateConfigRequest):
        """Reconfigure the connection with a new communication point."""
        try:
            rti_fsp._log_action(
                f"Starting connection reconfiguration for host: {request.host}, port: {request.port}",
                "debug",
                kind="system",
            )
            # Normalize tls_version to handle "1.2", "1.3", "TLSv1_2", "TLSv1_3" formats
            tls_version_str = (request.tls_version or "1.3").lower()
            if "1.2" in tls_version_str or "1_2" in tls_version_str:
                tls_version = ssl.TLSVersion.TLSv1_2
            else:
                tls_version = ssl.TLSVersion.TLSv1_3
            logger.info(
                f"tls_version in reconfig connection: {tls_version} from request: {request.tls_version}"
            )
            rti_fsp._log_action(
                f"tls_version in reconfig connection: {tls_version} from request: {request.tls_version}",
                "debug",
                kind="system",
            )
            host = request.host
            request_port = request.port
            if request.ws_mode.lower() == "active":
                # Only create TLSConfig if TLS is enabled
                tls_config = None
                if request.enable_tls:
                    tls_config = _client_tls_config(
                        request.tls_version, request.server_ca
                    )
                cp = os.getenv("CP", "cp1")

                endpoint = rti_fsp.runtime.endpoint
                if endpoint is None:
                    return JSONResponse(
                        content={"ok": False, "error": "Endpoint not initialized"},
                        status_code=500,
                    )

                # Disconnected: just keep the setting for the next Connect.
                # Starting the dial-out from here used to reconnect an FSP the
                # user had deliberately disconnected.
                loop = rti_fsp.runtime.loop
                if loop is None or not loop.is_running():
                    endpoint._tls_config = tls_config
                    rti_fsp._log_action(
                        f"TLS config saved (enable_tls={request.enable_tls}), "
                        "applies on next Connect",
                        "info",
                        kind="system",
                    )
                    return JSONResponse(
                        content={
                            "ok": True,
                            "status": "saved",
                            "ws_mode": request.ws_mode,
                            "enable_tls": request.enable_tls,
                        },
                        status_code=200,
                    )

                # Call reconfigure_connection on the endpoint's event loop
                # The library handles TLS config and task restart internally
                rti_fsp._log_action(
                    f"Calling reconfigure_connection for host: {host}, port: {request_port}, TLS: {request.enable_tls}",
                    "debug",
                    kind="system",
                )
                fut = asyncio.run_coroutine_threadsafe(
                    endpoint.reconfigure_connection(
                        host,
                        request_port,
                        cp,
                        request.enable_tls,
                        tls_config=tls_config,
                    ),
                    loop,
                )
                # Wait for the reconfiguration to complete
                try:
                    await asyncio.wrap_future(fut)
                    rti_fsp._log_action(
                        "Connection reconfigured successfully", "info", kind="system"
                    )
                except Exception as e:
                    rti_fsp._log_action(
                        f"Error during reconfigure_connection: {e}",
                        "error",
                        kind="system",
                    )
                    logger.info(f"Error during reconfigure_connection: {e}")

                rti_fsp.runtime.tasks["ws"] = endpoint._connect_task

                logger.info(
                    f"Reconfigured connection with TLS enabled: {request.enable_tls}"
                )
                return JSONResponse(
                    content={
                        "ok": True,
                        "status": "reconfigured",
                        "ws_mode": request.ws_mode,
                        "enable_tls": request.enable_tls,
                    },
                    status_code=200,
                )
            else:
                return JSONResponse(
                    content={
                        "ok": False,
                        "error": "Only active mode is supported for reconfiguration.",
                    },
                    status_code=400,
                )
        except Exception as exc:
            rti_fsp._log_action(
                f"api_reconfig_connection failed: {exc}", "error", kind="system"
            )
            return JSONResponse(
                content={"ok": False, "error": str(exc)}, status_code=500
            )

    @router.get(
        "/tls-config",
        summary="Get TLS Configuration",
        description="Returns the current TLS configuration from runtime variables.",
        response_description="TLS configuration from runtime",
        responses={
            200: {"description": "TLS configuration returned successfully"},
            500: {"description": "Error retrieving TLS configuration"},
        },
        tags=["TLS"],
    )
    def api_get_tls_config():
        """Get current TLS configuration from runtime.

        Returns: TLS configuration from the endpoint's runtime state including:
        - enable_tls: Whether TLS is enabled
        - tls_version: TLS version (1.2 or 1.3)
        - server_key: Server private key (for server mode)
        - server_cert: Server certificate (for server mode)
        - server_ca: CA certificate (for client mode)
        - ws_mode: WebSocket mode (active or passive)
        """
        try:
            endpoint = rti_fsp.runtime.endpoint
            if endpoint is None:
                return JSONResponse(
                    content={"ok": False, "error": "Endpoint not available"},
                    status_code=500,
                )

            # Get TLS config from runtime
            enable_tls = False
            tls_version = "1.2"
            server_key = None
            server_cert = None
            server_ca = None

            if hasattr(endpoint, "_tls_config") and endpoint._tls_config is not None:
                tls_config = endpoint._tls_config
                enable_tls = True
                # Extract TLS version from config
                if hasattr(tls_config, "min_version"):
                    if tls_config.min_version == ssl.TLSVersion.TLSv1_3:
                        tls_version = "1.3"
                    elif tls_config.min_version == ssl.TLSVersion.TLSv1_2:
                        tls_version = "1.2"
                if hasattr(tls_config, "cafile"):
                    server_ca = tls_config.cafile
                if hasattr(tls_config, "certfile"):
                    server_cert = tls_config.certfile
                if hasattr(tls_config, "keyfile"):
                    server_key = tls_config.keyfile

            # Get ws_mode
            ws_mode = "active"
            if hasattr(endpoint, "ws_mode"):
                ws_mode = endpoint.ws_mode
            elif hasattr(rti_fsp.runtime, "ws_mode"):
                ws_mode = rti_fsp.runtime.ws_mode

            return {
                "ok": True,
                "enable_tls": enable_tls,
                "tls_version": tls_version,
                "server_key": server_key,
                "server_cert": server_cert,
                "server_ca": server_ca,
                "ws_mode": ws_mode,
            }
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)}, status_code=500
            )

    @router.post(
        "/reconfig-oauth",
        summary="Get Connection Info",
        description="Returns detailed information about the current WebSocket connection, including peer address, port, and connection status.",
        response_description="Connection details",
        responses={
            200: {"description": "Connection information returned successfully"},
            500: {"description": "Error retrieving connection info"},
        },
        tags=["Client Status"],
    )
    async def api_reconfig_oauth(request: OAUTHCreateConfigRequest):
        """Reconfigure OAuth settings. OAuth config should be provided in the request by BFF."""
        try:
            rti_fsp._log_action(
                f"Starting OAuth reconfiguration for connection: {request.connection_name or 'unknown'}",
                "debug",
                kind="system",
            )
            cp = request.cp or os.getenv("CP", "cp1")
            host = request.host
            oauth_port = request.port

            # Get OAuth settings from request (BFF should provide these from connections.json)
            token_endpoint = getattr(request, "token_endpoint_url", None) or getattr(
                request, "token_endpoint", None
            )
            client_id = getattr(request, "client_id", None)
            client_secret = getattr(request, "client_secret", None)
            ca_certificate = getattr(request, "ca_certificate", None)
            enable_token_refresh = getattr(request, "enable_token_refresh", False)

            connection_name = request.connection_name or "unknown"
            rti_fsp._log_action(
                f"OAuth configuration - enable: {request.enable_oauth}, connection: {connection_name}",
                "debug",
                kind="system",
            )

            # Validate that required OAuth settings are provided
            if request.enable_oauth and not token_endpoint:
                error_msg = f"token_endpoint is required for OAuth but was not provided in request for connection: {connection_name}"
                rti_fsp._log_action(error_msg, "error", kind="system")
                raise ValueError(error_msg)

            if not request.enable_oauth:
                rti_fsp._log_action(
                    "Disabling OAuth for connection", "debug", kind="system"
                )
                token_endpoint = None
                client_id = None
                client_secret = None
                ca_certificate = None

            logger.info(f"Reconfiguring OAuth with connection: {connection_name}")
            logger.info(
                f"OAuth enable: {request.enable_oauth}, token_endpoint: {token_endpoint}"
            )

            # The next /start without OAuth fields dials out the same way.
            rti_fsp.runtime.start_oauth = (
                {
                    "token_endpoint": token_endpoint,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "kc_cert": ca_certificate,
                    "enable_token_refresh": bool(enable_token_refresh),
                }
                if request.enable_oauth
                else None
            )

            # Disconnected: don't dial out from here (that used to reconnect an
            # FSP the user had deliberately disconnected). Turning OAuth off
            # takes effect now - clearing the in-memory state, so
            # /oauth-status stops reporting it on - while turning it on is
            # applied by the HMI's Connect, which fetches the token then.
            loop = rti_fsp.runtime.loop
            if loop is None or not loop.is_running():
                endpoint = rti_fsp.runtime.endpoint
                if not request.enable_oauth and endpoint is not None:
                    endpoint._oauth_enable = False
                    endpoint._access_token = None
                    endpoint._credentials_provider = None
                    endpoint._assoc_handler._token_endpoint = None
                    endpoint._assoc_handler._kc_cert = None
                rti_fsp._log_action(
                    f"OAuth config saved (enable_oauth={request.enable_oauth}), "
                    "applies on next Connect",
                    "info",
                    kind="system",
                )
                return JSONResponse(
                    content={
                        "ok": True,
                        "status": "saved",
                        "ws_mode": "active",
                        "enable_oauth": request.enable_oauth,
                    },
                    status_code=200,
                )

            # When disabling OAuth, stop the endpoint first to avoid issues with ClientCredentialsProvider
            if not request.enable_oauth:
                rti_fsp._log_action(
                    "Disabling OAuth - stopping endpoint first",
                    "debug",
                    kind="system",
                )
                logger.info("Disabling OAuth - stopping endpoint first")
                # Stop the current connection if it exists
                if (
                    hasattr(rti_fsp.runtime.endpoint, "_connect_task")
                    and rti_fsp.runtime.endpoint._connect_task is not None
                ):
                    stop_fut = asyncio.run_coroutine_threadsafe(
                        rti_fsp.runtime.endpoint._cancel_task(
                            rti_fsp.runtime.endpoint._connect_task
                        ),
                        loop,
                    )
                    await asyncio.wrap_future(stop_fut)
                rti_fsp._log_action(
                    "Endpoint stopped, now reconfiguring with OAuth disabled",
                    "debug",
                    kind="system",
                )
                logger.info("Endpoint stopped, now reconfiguring with OAuth disabled")

            # Call reconfigure_oauth with settings from connection
            rti_fsp._log_action(
                f"Calling reconfigure_oauth for host: {host}, port: {oauth_port}, OAuth: {request.enable_oauth}",
                "debug",
                kind="system",
            )
            fut = asyncio.run_coroutine_threadsafe(
                rti_fsp.runtime.endpoint.reconfigure_oauth(
                    host=host,
                    port=str(oauth_port),
                    cp=cp,
                    oauth_enable=request.enable_oauth,
                    token_endpoint=token_endpoint,
                    client_id=client_id,
                    client_secret=client_secret,
                    kc_cert=ca_certificate,
                    enable_token_refresh=enable_token_refresh,
                ),
                loop,
            )
            await asyncio.wrap_future(fut)
            rti_fsp._log_action(
                "OAuth reconfigured successfully", "info", kind="system"
            )
            rti_fsp.runtime.tasks["ws"] = rti_fsp.runtime.endpoint._connect_task

            return JSONResponse(
                content={
                    "ok": True,
                    "status": "reconfigured",
                    "ws_mode": "active",
                    "enable_oauth": request.enable_oauth,
                },
                status_code=200,
            )
        except Exception as exc:
            logger.info(f"Reconfig OAuth error: {exc}")
            rti_fsp._log_action(
                f"api_reconfig_oauth failed: {exc}", "error", kind="system"
            )
            return JSONResponse(
                content={"ok": False, "error": str(exc)}, status_code=500
            )

    @router.get(
        "/oauth-status",
        summary="Get OAuth Status",
        description="Returns whether OAuth is currently enabled or disabled for this FSP server.",
        response_description="OAuth enable status",
        responses={
            200: {"description": "OAuth status returned successfully"},
            500: {"description": "Error retrieving OAuth status"},
        },
        tags=["OAuth"],
    )
    def api_get_oauth_status():
        """Get current OAuth enable/disable status from the FSP server.

        Returns:
            dict: {
                "ok": True,
                "enable_oauth": bool  # Current OAuth status
            }
        """
        try:
            # Check the runtime endpoint's OAuth enable status
            if hasattr(rti_fsp.runtime, "endpoint") and hasattr(
                rti_fsp.runtime.endpoint, "_oauth_enable"
            ):
                enable_oauth = rti_fsp.runtime.endpoint._oauth_enable
                return {"ok": True, "enable_oauth": enable_oauth}
            else:
                # If endpoint not available or attribute not found, check if OAuth is configured
                return {"ok": True, "enable_oauth": False}
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)}, status_code=500
            )

    @router.get(
        "/actions-logs",
        summary="Get Action Log",
        description="Retrieves the logged server actions for debugging and auditing purposes.",
        response_description="List of logged actions",
        responses={
            200: {"description": "List of actions returned successfully"},
            500: {"description": "Error retrieving actions"},
        },
        tags=["Logging"],
    )
    def api_actions():
        """Get logged server actions.

        Returns:
            dict: { "actions": list[dict] }
        """
        try:
            return {"actions": rti_fsp.get_actions()}
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": f"Unexpected error: {exc}"},
                status_code=500,
            )

    @router.post(
        "/clear-logs",
        summary="Clear Action Log",
        description="Clears all logged server actions.",
        response_description="Action log clear confirmation",
        responses={
            200: {"description": "Actions cleared successfully"},
            500: {"description": "Error clearing actions"},
        },
        tags=["Logging"],
    )
    def api_actions_clear():
        """Clear action log.

        Returns:
            dict: { "ok": True }
        """
        try:
            rti_fsp.clear_actions()
            return {"ok": True}
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": f"Unexpected error: {exc}"},
                status_code=500,
            )

    @router.get(
        "/messages",
        summary="Get Message Log",
        description="Retrieves the logged protocol messages for debugging purposes.",
        response_description="List of logged protocol messages",
        responses={
            200: {"description": "List of messages returned successfully"},
            500: {"description": "Error retrieving messages"},
        },
        tags=["Logging"],
    )
    def api_messages():
        """Get logged protocol messages.

        Returns:
            dict: { "messages": list[dict] }
        """
        try:
            return {"messages": rti_fsp.get_messages()}
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": f"Unexpected error: {exc}"},
                status_code=500,
            )

    @router.post(
        "/clear-messages",
        summary="Clear Message Log",
        description="Clears all logged protocol messages.",
        response_description="Message log clear confirmation",
        responses={
            200: {"description": "Messages cleared successfully"},
            500: {"description": "Error clearing messages"},
        },
        tags=["Logging"],
    )
    def api_messages_clear():
        """Clear message log.

        Returns:
            dict: { "ok": True }
        """
        try:
            rti_fsp.clear_messages()
            return {"ok": True}
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": f"Unexpected error: {exc}"},
                status_code=500,
            )

    @router.post(
        "/readvalue",
        summary="Read Value",
        description="Reads a value from the server's IED model. Requires the server to be running.",
        response_description="Read value result",
        responses={
            200: {"description": "Value read successfully"},
            400: {"description": "Missing objRef parameter"},
            403: {"description": "Server is not running"},
            404: {"description": "Instance not available or read timeout"},
            500: {"description": "Error reading value"},
        },
        tags=["Data Access"],
    )
    def api_read_value(request: ReadvalueRequest):
        """Read a value from the server IED model.

        Request Body:
            ReadvalueRequest: {
                "objRef": str,  # Required - Object reference in ACSI format
                "fc": str        # Optional - Functional constraint
            }

        Returns:
            dict: {
                "ok": True,
                "success": True,
                "objRef": str,
                "fc": str,
                "values": list[dict]  # Each containing type and value
            }

        Raises:
            HTTPException 400: If objRef is missing
            HTTPException 403: If server is not running
            HTTPException 404: If instance not available or timeout
        """
        try:
            obj_ref = request.obj_ref
            fc = request.fc

            if not obj_ref:
                rti_fsp._log_action(
                    "Server readvalue rejected: missing objRef", "warn", kind="acsi"
                )
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400,
                )

            if rti_fsp.runtime.server is None:
                rti_fsp._log_action(
                    "Server readvalue rejected: server not running",
                    "warn",
                    detail={"objRef": obj_ref, "fc": fc},
                    kind="acsi",
                )
                return JSONResponse(
                    content={"ok": False, "error": "Server is not running"},
                    status_code=503,
                )

            try:
                result = rti_fsp.read_value(obj_ref)

                if result is None:
                    rti_fsp._log_action(
                        "Server readvalue failed: instanceNotAvailable",
                        "warn",
                        detail={"objRef": obj_ref, "fc": fc},
                        kind="acsi",
                    )
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404,
                    )

                logger.info(
                    f"[POST /ap/readvalue] SUCCESS objRef={obj_ref!r} "
                    f"fc={fc!r} type={result.get('type')!r} value={result.get('value')!r}"
                )

                rti_fsp._log_action(
                    "Server readvalue",
                    service="getDataValues",
                    detail={
                        "objRef": obj_ref,
                        "fc": fc,
                        "type": result.get("type"),
                        "value": result.get("value"),
                    },
                    kind="acsi",
                )
                return {
                    "ok": True,
                    "success": True,
                    "objRef": obj_ref,
                    "fc": fc,
                    "values": result,
                }

            except FuturesTimeoutError:
                rti_fsp._log_action(
                    "Server readvalue timeout",
                    "warn",
                    detail={"objRef": obj_ref, "fc": fc},
                    kind="acsi",
                )
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"}, status_code=404
                )
            except ValueError as exc:
                rti_fsp._log_action(
                    f"Server readvalue failed: {exc}", "warn", kind="acsi"
                )
                return JSONResponse(
                    content={"ok": False, "error": str(exc)}, status_code=404
                )
            except Exception as exc:
                rti_fsp._log_action(
                    f"Server readvalue failed: {exc}", "error", kind="acsi"
                )
                return JSONResponse(
                    content={"ok": False, "error": str(exc)}, status_code=500
                )
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)}, status_code=404
            )

    @router.post(
        "/writevalue",
        summary="Write Value",
        description="Writes a value to the server's IED model. Requires the server to be running.",
        response_description="Write value confirmation",
        responses={
            200: {"description": "Value written successfully"},
            400: {"description": "Missing parameters or invalid value"},
            403: {"description": "Server is not running"},
            404: {"description": "Write timeout"},
            500: {"description": "Error writing value"},
        },
        tags=["Data Access"],
    )
    async def api_write_value(request: WritevalueRequest):
        """Write a value in the server IED model.

        Request Body:
            WritevalueRequest: {
                "objRef": str,     # Required - Object reference
                "fc": str,        # Required - Functional constraint
                "value": str,     # Required - Value to write
                "dataType": str   # Optional - Data type for coercion
            }

        Returns:
            dict: {
                "ok": True,
                "success": True,
                "objRef": str,
                "fc": str,
                "value": any,
                "dataType": str
            }

        Raises:
            HTTPException 400: If objRef, fc, or value is missing
            HTTPException 403: If server is not running
            HTTPException 404: If write timeout occurs
        """
        try:
            obj_ref = request.obj_ref
            fc = request.fc
            value = request.value
            data_type = request.data_type

            if not obj_ref:
                rti_fsp._log_action(
                    "Server writevalue rejected: missing objRef",
                    "warn",
                    kind="acsi",
                )
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400,
                )

            if value is None:
                rti_fsp._log_action(
                    "Server writevalue rejected: missing value",
                    "warn",
                    detail={"objRef": obj_ref, "fc": fc},
                    kind="acsi",
                )
                return JSONResponse(
                    content={"ok": False, "error": "value is required"}, status_code=400
                )

            if rti_fsp.runtime.server is None:
                rti_fsp._log_action(
                    "Server writevalue rejected: server not running",
                    "warn",
                    detail={"objRef": obj_ref, "fc": fc, "value": value},
                    kind="acsi",
                )
                return JSONResponse(
                    content={"ok": False, "error": "Server is not running"},
                    status_code=503,
                )

            try:
                result = rti_fsp.write_value(obj_ref, value, data_type)
                # Success counterpart of "Server readvalue" - without it a
                # local write only ever showed up in the log if it failed.
                rti_fsp._log_action(
                    "Server writevalue",
                    detail={
                        "objRef": obj_ref,
                        "fc": fc,
                        "value": result.get("value"),
                        "dataType": result.get("dataType"),
                    },
                    kind="acsi",
                    service="setDataValues",
                )

                plugin_host.emit(ValueWritten(obj_ref, result.get("value")))

                return {
                    "ok": True,
                    "success": True,
                    "objRef": result["objRef"],
                    "fc": fc,
                    "value": result["value"],
                    "dataType": result["dataType"],
                }

            except FuturesTimeoutError:
                rti_fsp._log_action(
                    "Server writevalue timeout",
                    "warn",
                    detail={"objRef": obj_ref, "fc": fc},
                    kind="acsi",
                )
                return JSONResponse(
                    content={"ok": False, "error": "write timeout"}, status_code=504
                )
            except ValueError as exc:
                rti_fsp._log_action(
                    f"Server writevalue failed: {exc}", "warn", kind="acsi"
                )
                return JSONResponse(
                    content={"ok": False, "error": str(exc)}, status_code=404
                )
            except Exception as exc:
                rti_fsp._log_action(
                    f"Server writevalue failed: {exc}", "error", kind="acsi"
                )
                return JSONResponse(
                    content={"ok": False, "error": str(exc)}, status_code=500
                )
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)}, status_code=500
            )

    return router, rti_fsp


def create_fastapi_app(factory_dir: Path | None = None) -> FastAPI:
    """Create and configure the FastAPI application for ACSI server BFF."""
    app = FastAPI(
        title="ACSI Server WS Active",
        description="Backend for Frontend (BFF) endpoint providing REST API for ACSI Server control. "
        "This service manages ACSI Server WebSocket Active lifecycle, IED models, data access, "
        "and provides comprehensive monitoring capabilities.",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=_lifespan,
        openapi_tags=[
            {
                "name": "Server Control",
                "description": "Start, stop, and manage the ACSI Server WebSocket Active lifecycle",
            },
            {"name": "Model", "description": "Load, update, and manage IED models"},
            {
                "name": "Data Access",
                "description": "Read and write values to/from the IED model",
            },
            {
                "name": "Connections",
                "description": "View and manage active WebSocket connections",
            },
            {
                "name": "Logging",
                "description": "View and clear action and message logs",
            },
            {
                "name": "Health",
                "description": "Service health checks and status monitoring",
            },
            {
                "name": "Discovery",
                "description": "API introspection and endpoint discovery",
            },
            {
                "name": "Plugins",
                "description": "Connect, add, reload and remove plugins (HTTP services, decision 0029); their routes are under /api/plugins/<name>/",
            },
        ],
    )

    resolved_factory_dir = (
        os.getenv("MODELPATH") or factory_dir or Path(__file__).parent
    )
    router, _server = create_bff_router(resolved_factory_dir)
    app.include_router(router)
    # /api/plugins; the plugins themselves are loaded by _lifespan.
    attach_plugins(app, plugin_service)

    # Add CORS middleware to allow requests from frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.server = _server
    return app


if __name__ == "__main__":
    import argparse

    import uvicorn

    _LOG_CHOICES = ["critical", "error", "warning", "info", "debug", "trace"]

    parser = argparse.ArgumentParser(
        description="RTI Demo FSP (ACSI server) BFF endpoint"
    )
    parser.add_argument(
        "--host",
        default=os.getenv("HOST", "0.0.0.0"),
        help="Host interface to bind (default: %(default)s, env: HOST)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", "5001")),
        help="Port to listen on (default: %(default)s, env: PORT)",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL", "info"),
        help="Log level: {} (default: %(default)s, env: LOG_LEVEL)".format(
            ", ".join(_LOG_CHOICES)
        ),
    )
    args = parser.parse_args()

    # Module scope already applied LOG_LEVEL from the environment at import
    # (covers the app + ws61850 + acsi_server loggers). Re-resolve here so an
    # explicit --log-level on the command line wins, and hand the same value to
    # uvicorn so its own 'uvicorn'/'uvicorn.error'/'uvicorn.access' loggers
    # follow suit.
    resolved = resolve_log_level(args.log_level)
    logging.getLogger().setLevel(resolved)
    uvicorn_log_level = args.log_level.lower()
    if uvicorn_log_level not in _LOG_CHOICES:
        uvicorn_log_level = logging.getLevelName(resolved).lower()

    logger.info(
        "Starting RTI Demo FSP BFF on %s:%d (log level %s)",
        args.host,
        args.port,
        logging.getLevelName(resolved),
    )

    factory_dir = Path(__file__).parent
    app = create_fastapi_app(factory_dir)
    # log_config=None: don't let uvicorn apply its own logging dictConfig
    # (separate formatter/handlers for the uvicorn/uvicorn.access/
    # uvicorn.error loggers) - let those records propagate to the root
    # logger instead, so they use the same timestamped format as the
    # app's own logger.info(...) calls above.
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level=uvicorn_log_level,
        log_config=None,
    )
