# SPDX-FileCopyrightText: 2025-2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
#
# Copyright 2025-2026 Netbeheer Nederland
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Backend for Frontend (BFF) endpoint providing REST API for ACSI client control.

This module exposes FastAPI endpoints that interact with the ACSI client,
handling connection management and value operations.
"""

from __future__ import annotations

import asyncio
import logging
import os
import ssl
import sys
import tempfile
import traceback
from concurrent.futures import TimeoutError as FuturesTimeoutError
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from acsi_plugins import (
    Associated,
    OperateResponse,
    PluginHost,
    ReportReceived,
    ValueRead,
    ValueWritten,
)
from acsi_plugins.web import PluginService
from acsi_plugins.web import attach as attach_plugins
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from so.acsi_client import ACSIClient, originator
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
# __main__ block, so every entry point honors LOG_LEVEL: `python
# so/bff_endpoint.py`, `uvicorn so.bff_endpoint:app`, a service wrapper, or
# pytest importing create_fastapi_app. Child loggers (acsi_client, ws61850.*)
# and the ACSI client's background event-loop thread inherit this level.
logging.getLogger().setLevel(LOG_LEVEL)

logger = logging.getLogger(__name__)


class HealthCheckAccessFilter(logging.Filter):
    """Demote uvicorn access-log lines for health/status polls to DEBUG.

    The Docker healthcheck hits ``/api/status`` (and service discovery hits
    ``/api/health``), and the HMI's message monitor polls ``/api/messages``,
    every few seconds; logged at INFO they bury the real request log.
    Matching records are relabelled DEBUG and only pass through when the
    ``uvicorn.access`` logger is actually at DEBUG.
    """

    QUIET_PATHS = (
        "/api/status",
        "/api/health",
        "/api/messages",
        "/api/properties",
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


def _listen_on_start(client) -> None:
    """Start the SO's WebSocket server (passive endpoint) with the service.

    The FSPs dial in to it, so it listens from the start instead of waiting
    for a POST /api/connect: on SO_WS_HOST (default 0.0.0.0) and SO_WS_PORT
    (default 8765). SO_LISTEN_ON_START=false leaves it to /api/connect, as
    before. A failure is logged, not raised - the REST API still starts.
    """
    if os.getenv("SO_LISTEN_ON_START", "true").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return
    host = os.getenv("SO_WS_HOST", "0.0.0.0")
    port = int(os.getenv("SO_WS_PORT", "8765"))
    try:
        client.connect(host, port)
        client._log_action(
            f"Listening on start: host={host}, port={port}", "info", kind="system"
        )
    except (ValueError, RuntimeError) as exc:
        client._log_action(f"Listen on start failed: {exc}", "warn", kind="system")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Installed here (not before uvicorn.run) so it survives uvicorn's own
    # logging dictConfig, which runs before app startup.
    logging.getLogger("uvicorn.access").addFilter(HealthCheckAccessFilter())
    client = getattr(app.state, "client", None)
    if client is not None:
        _listen_on_start(client)
    # Looked up here, not bound at import, so tests can replace it.
    async with plugin_service.lifespan():
        yield


# ==================== Plugins ====================
# The plugins this SO hosts (decision 0021). The host passes ACSI events to
# them; the service installs, reloads and removes them (/api/plugins).
# Settings from PLUGIN_STORAGE, PLUGIN_ALLOWED_SOURCES and PLUGINS.
plugin_host = PluginHost(role="so")
plugin_service = PluginService.from_env(plugin_host)


# ==================== Pydantic Models ====================
class ConnectRequest(BaseModel):
    """Request body for connecting to an IEC61850 WebSocket server.

    Used by: POST /api/connect
    """

    host: str = Field(
        default="localhost",
        description="Server hostname or IP address to connect to",
        json_schema_extra={"example": "localhost"},
    )
    port: int = Field(
        default=8765,
        description="Server port number (1-65535)",
        ge=1,
        le=65535,
        json_schema_extra={"example": 8765},
    )


class ModelRequest(BaseModel):
    """Request body for connecting to an IEC61850 WebSocket server.

    Used by: POST /api/model
    """

    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"},
    )

    refresh: bool = Field(
        default=False,
        description="Force a fresh model rebuild instead of returning cached data",
        json_schema_extra={"example": False},
    )


class ServerDirectoryRequest(BaseModel):
    """Request body for getting server directory.

    Used by: POST /api/server-directory
    """

    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"},
    )


class LogicalDeviceRequest(BaseModel):
    """Request body for getting logical device directory.

    Used by: POST /api/logical-device
    """

    ld_inst: str = Field(
        ...,
        description="Logical Device instance name (e.g., 'LD0')",
        json_schema_extra={"example": "LD0"},
    )
    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"},
    )


class LogicalNodeRequest(BaseModel):
    """Request body for getting logical node tree.

    Used by: POST /api/logical-node
    """

    ld_inst: str = Field(
        ...,
        description="Logical Device instance name (e.g., 'LD0')",
        json_schema_extra={"example": "LD0"},
    )
    ln_inst: str = Field(
        ...,
        description="Logical Node instance name (e.g., 'LLN0')",
        json_schema_extra={"example": "LLN0"},
    )
    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"},
    )


class DataObjectRequest(BaseModel):
    """Request body for getting data object details.

    Used by: POST /api/data-object
    """

    ld_inst: str = Field(
        ...,
        description="Logical Device instance name (e.g., 'LD0')",
        json_schema_extra={"example": "LD0"},
    )
    ln_inst: str = Field(
        ...,
        description="Logical Node instance name (e.g., 'LLN0')",
        json_schema_extra={"example": "LLN0"},
    )
    do_name: str = Field(
        ...,
        description="Data Object name (e.g., 'Mod')",
        json_schema_extra={"example": "Mod"},
    )
    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"},
    )


class ReadvalueRequest(BaseModel):
    """Request body for reading a value from the connected server.

    Used by: POST /api/readvalue
    """

    obj_ref: str = Field(
        ...,
        alias="objRef",
        description="Object reference in IEC61850 format (e.g., 'LD0/LLN0$ST$Mod')",
        json_schema_extra={"example": "LD0/LLN0$ST$Mod"},
    )
    fc: str = Field(
        default=None,
        description="Functional constraint (ST, MX, CO, etc.) - optional",
        json_schema_extra={"example": "ST"},
    )

    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"},
    )


class ReadRCBValueRequest(BaseModel):
    """Request body for reading a value from the connected server.

    Used by: POST /api/readvalue
    """

    obj_ref: str = Field(
        ...,
        alias="objRef",
        description="Object reference in IEC61850 format (e.g., 'LD0/LLN0$ST$Mod')",
        json_schema_extra={"example": "LD0/LLN0$ST$Mod"},
    )

    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"},
    )


class WriteRCBValueRequest(BaseModel):
    """Request body for reading a value from the connected server.

    Used by: POST /api/readvalue
    """

    obj_ref: str = Field(
        ...,
        alias="objRef",
        description="Object reference in IEC61850 format (e.g., 'LD0/LLN0$ST$Mod')",
        json_schema_extra={"example": "LD0/LLN0$ST$Mod"},
    )

    data: Any = Field(
        ...,
        description="Data to write (will be converted to appropriate type)",
    )

    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"},
    )


class GetDataDefinitionRequest(BaseModel):
    """Request body for reading a value from the connected server.

    Used by: POST /api/readvalue
    """

    ld_inst: str = Field(
        ..., description="LD name (e.g., 'LD0')", json_schema_extra={"example": "LD0"}
    )
    ln_inst: str | None = Field(
        ..., description="LN name (e.g., 'LLN0')", json_schema_extra={"example": "LLN0"}
    )
    do_path: str | None = Field(
        ...,
        description="Data Object path (e.g., 'Mod')",
        json_schema_extra={"example": "Mod"},
    )

    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"},
    )


class GetDataSetDirectory(BaseModel):
    """Request body for reading a value from the connected server.

    Used by: POST /api/readvalue
    """

    ld_inst: str = Field(
        ..., description="LD name (e.g., 'LD0')", json_schema_extra={"example": "LD0"}
    )
    ln_inst: str = Field(
        ..., description="LN name (e.g., 'LLN0')", json_schema_extra={"example": "LLN0"}
    )
    ds_inst: str = Field(
        ...,
        description="DataSet name (e.g., 'Event1')",
        json_schema_extra={"example": "Event1"},
    )

    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"},
    )


class SelectRequest(BaseModel):
    """Request body for selecting a controllable DO (select-before-operate).

    Used by: POST /api/select
    """

    obj_ref: str = Field(
        ...,
        alias="objRef",
        description="Controllable DO Object reference in IEC61850 format",
        json_schema_extra={"example": "LD0/CSWI1.Pos"},
    )

    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"},
    )


def control_answer(result: Any) -> dict[str, Any]:
    """{ok, error} for a select / operate the FSP answered with `result`.

    The ACSI client returns True when the server carried it out, the
    serviceError's name when it refused, None when it didn't answer. Only
    True is ok - the operate route used to hand the serviceError's name
    back as `ok` (a non-empty string, so truthy) with an empty error.
    """
    if result is True:
        return {"ok": True, "error": ""}
    if result is None:
        return {"ok": False, "error": "no response"}
    if isinstance(result, str) and result:
        return {"ok": False, "error": result}
    return {"ok": False, "error": "refused"}


class OperateRequest(BaseModel):
    """Request body for writing a value to the connected server.

    Used by: POST /api/operate
    """

    obj_ref: str = Field(
        ...,
        alias="objRef",
        description="Controllable DO Object reference in IEC61850 format",
        json_schema_extra={"example": "LD0/MMXU.WMaxSpt"},
    )
    value: Any = Field(
        ...,
        description="Value to write (will be converted to appropriate type)",
        json_schema_extra={"example": "12.4"},
    )
    value_type: Any = Field(
        ...,
        description="Value type hint for coercion (BOOLEAN, INT32, FLOAT32, etc.)",
        json_schema_extra={"example": "float32"},
    )

    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"},
    )

    ctl_num: int = Field(
        default=0,
        alias="ctlNum",
        description="Control sequence number (0..255)",
    )

    origin: dict[str, Any] | None = Field(
        default=None,
        description="Originator: orCat (OriginatorCategoryKind number or name) and orIdent; "
        "omitted, the SO's own fixed origin is used",
        json_schema_extra={"example": {"orCat": 2, "orIdent": "HMI"}},
    )

    test: bool = Field(
        default=False,
        description="Operate in test mode - the server is not to act on it",
    )

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "objRef": "LD0/MMXU.WMaxSpt",
                "value": "2.11",
                "value_type": "float32",
                "cp": "cp1",
            }
        },
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


class OAUTHCreateConfigRequest(BaseModel):
    """Request body for OAuth reconfiguration."""

    connection_name: str | None = Field(
        default=None,
        description="Connection name (optional, auto-detected)",
        json_schema_extra={"example": "RTI-SO-01"},
    )
    enable_oauth: bool = Field(
        default=False,
        description="Enable OAuth authentication",
        json_schema_extra={"example": False},
    )
    ws_mode: str = Field(
        default="passive",
        description="WebSocket mode (passive or active)",
        json_schema_extra={"example": "passive"},
    )
    # OAuth settings for SO (passive mode)
    certificate_endpoint_url: str | None = Field(
        default=None,
        description="OAuth Certificate endpoint URL",
        json_schema_extra={"example": "https://auth.example.com/certs"},
    )
    token_issuer_url: str | None = Field(
        default=None,
        description="token issuer url",
        json_schema_extra={"example": "https://auth.example.com"},
    )
    ca_certificate: str | None = Field(
        default=None,
        description="Server CA certificate",
        json_schema_extra={"example": "-----BEGIN CERTIFICATE-----..."},
    )


class WriteValueRequest(BaseModel):
    """Request body for writing a value to the connected server.

    Used by: POST /api/writevalue
    """

    obj_ref: str = Field(
        ...,
        alias="objRef",
        description="Object reference in IEC61850 format",
        json_schema_extra={"example": "LD0/LLN0$ST$Mod"},
    )
    fc: str = Field(
        ...,
        description="Functional constraint (ST, MX, CO, etc.)",
        json_schema_extra={"example": "ST"},
    )
    value: Any = Field(
        ...,
        description="Value to write (will be converted to appropriate type)",
        json_schema_extra={"example": "ON"},
    )
    data_type: str | None = Field(
        default=None,
        alias="dataType",
        description="Optional value type hint for coercion",
        json_schema_extra={"example": "BOOLEAN"},
    )

    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"},
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "objRef": "LD0/LLN0$ST$Mod",
                "fc": "ST",
                "value": "ON",
                "value_type": "BOOLEAN",
                "cp": "cp1",
            }
        }
    )


# ==================== IO Plugin Connection Models (ported from FSP) ====================


def create_fastapi_app(factory_dir: Path | None = None) -> FastAPI:
    """Create and configure the FastAPI application for Acsi-Client BFF."""
    app = FastAPI(
        lifespan=_lifespan,
        title="ACSI Client WS Passive",
        description="Backend for Frontend (BFF) endpoint providing REST API for ACSI client control. "
        "This service manages IEC61850 WebSocket client connections, data access, "
        "model retrieval, and provides comprehensive monitoring capabilities.",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        openapi_tags=[
            {
                "name": "Client Status",
                "description": "Get client status, connections, and properties",
            },
            {
                "name": "Connection Management",
                "description": "Connect to and disconnect from Acsi-Servers",
            },
            {
                "name": "Model Access",
                "description": "Retrieve and explore IED models from connected servers",
            },
            {
                "name": "Data Access",
                "description": "Read and write values to/from connected servers",
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
            {"name": "Diagnostics", "description": "Internal diagnostic endpoints"},
            {
                "name": "Plugins",
                "description": "Install, reload and remove plugins; their routes are under /api/plugins/<name>/",
            },
        ],
    )

    resolved_factory_dir = (
        os.getenv("MODELPATH") or factory_dir or Path(__file__).parent
    )
    router, _client = create_bff_router(resolved_factory_dir)
    app.include_router(router)
    app.state.client = _client

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

    return app


def create_bff_router(app: FastAPI) -> tuple[APIRouter, ACSIClient]:
    """Create a FastAPI router for the ACSI client BFF API.

    Returns:
        Tuple of (APIRouter, ACSIClient instance)
    """
    router = APIRouter(
        prefix="/api",
        tags=["acsi-client"],
        responses={
            404: {"description": "Not found"},
            500: {"description": "Internal server error"},
        },
    )
    rti_so = ACSIClient()

    def on_write_callback(obj_ref, value, fc, data_type, result):
        logger.info(
            f"[WRITE] {obj_ref}={value} fc={fc} type={data_type} result={result}"
        )

    rti_so.install_write_callback(on_write_callback)

    def on_report_callback(rpt_id, data_set, data):
        """Callback for received report messages."""
        logger.info(f"[REPORT] rptID={rpt_id} dataSet={data_set} dataCount={len(data)}")
        for item in data:
            logger.info(f"  {item.get('dataRef')} = {item.get('value')}")

        plugin_host.emit(ReportReceived(rpt_id, data_set, list(data)))

    rti_so.install_report_callback(on_report_callback)

    def on_connected_callback(associate_response):
        """Callback for received associateResponse messages."""
        logger.info(f"[CONNECTED] associateResponse: {associate_response}")
        # A build that failed or hung while disconnected can leave model_status
        # stuck at 'error' (or 'building'). Clear it here so the next fetch
        # after reconnect rebuilds against the live connection instead of
        # immediately returning a stale pre-reconnect error.
        cp = associate_response.get("associateId")
        if cp:
            model_info = rti_so.get_model_info(cp)
            with rti_so.runtime.lock:
                if model_info.model_status in ("error", "building"):
                    model_info.model_status = "idle"
                    model_info.model_data = None
                    model_info.model_error = None
                    model_info.model_ready_event.clear()

        plugin_host.emit(Associated(associate_response.get("associateId", "connected")))

    rti_so.install_connected_callback(on_connected_callback)

    # ==================== Helper Functions ====================

    def _check_websocket_connection():
        """Verify that an active WebSocket connection exists.

        Raises:
            HTTPException 503: If no WebSocket connection is established
        """
        endpoint = rti_so.runtime.endpoint
        if endpoint is None or len(endpoint.websocket_info_list) == 0:
            raise HTTPException(
                status_code=503, detail="no-active-websocket-connection"
            )

    def _convert_bytes_to_hex(obj: Any) -> Any:
        """Recursively convert bytes objects to hex strings for JSON serialization."""
        if isinstance(obj, bytes):
            return obj.hex()
        elif isinstance(obj, dict):
            return {k: _convert_bytes_to_hex(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [_convert_bytes_to_hex(item) for item in obj]
        elif isinstance(obj, tuple):
            return tuple(_convert_bytes_to_hex(item) for item in obj)
        else:
            return obj

    async def _aget_ln_details(
        ld_inst: str, ln_inst: str, acsi_client: Any, ws_info
    ) -> dict[str, Any]:
        """Async variant used internally for concurrent model assembly."""

        async def _safe(coro):
            try:
                return await coro
            except Exception:
                return None

        do_items = await _invoke_ln_directory_async(
            acsi_client, ws_info, ld_inst, ln_inst, "dataObject"
        )
        brcb_items = await _invoke_ln_directory_async(
            acsi_client, ws_info, ld_inst, ln_inst, "brcb"
        )
        urcb_items = await _invoke_ln_directory_async(
            acsi_client, ws_info, ld_inst, ln_inst, "urcb"
        )
        dataset_items = await _invoke_ln_directory_async(
            acsi_client, ws_info, ld_inst, ln_inst, "dataset"
        )

        data_objects = []
        data_attributes = []

        do_list = []
        if isinstance(do_items, dict):
            do_list = (
                do_items.get("dataObjects", do_items.get("instanceNames", [])) or []
            )
            data_attributes = do_items.get("dataAttributes", []) or []
        elif isinstance(do_items, list):
            do_list = do_items
        if do_list:
            lock = rti_so.runtime.invoke_lock
            for do_name in do_list:
                defn = None
                try:
                    obj_ref = f"{ld_inst}/{ln_inst}.{do_name}"
                    if lock is None:
                        defn = await acsi_client.get_data_definition(
                            obj_ref, ws_info, None, None
                        )
                    else:
                        async with lock:
                            defn = await acsi_client.get_data_definition(
                                obj_ref, ws_info, None, None
                            )

                    cdc = None
                    if isinstance(defn, dict):
                        cdc = defn.get("cdc")
                    data_objects.append({"name": do_name, "cdc": cdc})
                except Exception:
                    data_objects.append({"name": do_name, "cdc": None})

        def _extract_rcb(entries, kind):
            out = []
            if isinstance(entries, list):
                out = entries
            elif isinstance(entries, dict):
                out = (
                    entries.get("instanceNames")
                    or entries.get("reportControlBlocks")
                    or []
                )
            return [{"name": ref, "type": kind} for ref in out]

        rcbs = []
        lock = rti_so.runtime.invoke_lock

        brcb_list = _extract_rcb(brcb_items, "BRCB")
        for rcb_info in brcb_list:
            rcb_name = rcb_info["name"]
            rcb_ref = f"{ld_inst}/{ln_inst}.{rcb_name}"
            rcb_values = None
            try:
                if lock is None:
                    rcb_values = await acsi_client.get_BRCB_values(
                        rcb_ref, ws_info, None, None
                    )
                else:
                    async with lock:
                        rcb_values = await acsi_client.get_BRCB_values(
                            rcb_ref, ws_info, None, None
                        )
                rpt_ena = False
                if isinstance(rcb_values, dict):
                    rpt_ena = rcb_values.get("RptEna", False)
                    rcb_values = _convert_bytes_to_hex(rcb_values)
                rcbs.append(
                    {
                        "name": rcb_name,
                        "type": "BRCB",
                        "values": rcb_values,
                        "enabled": rpt_ena,
                    }
                )
            except Exception:
                rcbs.append(
                    {"name": rcb_name, "type": "BRCB", "values": None, "enabled": False}
                )

        urcb_list = _extract_rcb(urcb_items, "URCB")
        for rcb_info in urcb_list:
            rcb_name = rcb_info["name"]
            rcb_ref = f"{ld_inst}/{ln_inst}.{rcb_name}"
            rcb_values = None
            try:
                if lock is None:
                    rcb_values = await acsi_client.get_URCB_values(
                        rcb_ref, ws_info, None, None
                    )
                else:
                    async with lock:
                        rcb_values = await acsi_client.get_URCB_values(
                            rcb_ref, ws_info, None, None
                        )
                rpt_ena = False
                if isinstance(rcb_values, dict):
                    rpt_ena = rcb_values.get("RptEna", False)
                    rcb_values = _convert_bytes_to_hex(rcb_values)
                rcbs.append(
                    {
                        "name": rcb_name,
                        "type": "URCB",
                        "values": rcb_values,
                        "enabled": rpt_ena,
                    }
                )
            except Exception:
                rcbs.append(
                    {"name": rcb_name, "type": "URCB", "values": None, "enabled": False}
                )

        datasets = []
        if isinstance(dataset_items, list):
            datasets = dataset_items
        elif isinstance(dataset_items, dict):
            datasets = (
                dataset_items.get("instanceNames")
                or dataset_items.get("dataSets")
                or []
            )

        return {
            "dataObjects": data_objects,
            "dataAttributes": data_attributes,
            "reportControlBlocks": rcbs,
            "dataSets": datasets,
        }

    def _invoke_ln_directory(acsi_client, ws_info, ld_inst, ln_inst, mode):
        """Return coroutine that performs directory call under a lock."""

        async def _coro():
            lock = rti_so.runtime.invoke_lock
            if lock is None:
                items = await acsi_client.get_logical_node_directory(
                    ld_inst, ln_inst, mode, ws_info, None, None
                )
                return items
            async with lock:
                items = await acsi_client.get_logical_node_directory(
                    ld_inst, ln_inst, mode, ws_info, None, None
                )
                return items

        return _coro()

    async def _invoke_ln_directory_async(acsi_client, ws_info, ld_inst, ln_inst, mode):
        return await _invoke_ln_directory(acsi_client, ws_info, ld_inst, ln_inst, mode)

    # ================ Background Model Build ================
    async def _abuild_full_model(cp) -> None:
        """Build full model with PARALLEL websocket calls for better performance."""
        endpoint = rti_so.runtime.endpoint
        loop = rti_so.runtime.loop
        acsi_client = rti_so.get_iec61850_client(cp)

        if acsi_client is None:
            raise HTTPException(
                status_code=404, detail=f"Client with cp={cp} not found"
            )
        else:
            logger.info(f"client found with cp: {cp}")

        if not rti_so or not endpoint or not loop or not acsi_client.is_connected:
            raise RuntimeError("not-connected")
        try:
            ws_info = endpoint.get_websocket_info(acsi_client)
        except Exception as e:
            logger.info(f"CRASHED in get_websocket_info: {type(e).__name__}: {e}")
            raise

        if ws_info is None:
            raise RuntimeError("no-websocket-info")

        model_info = rti_so.get_model_info(cp)

        def _init_progress(ld_list):
            with rti_so.runtime.lock:
                model_info.model_progress = {
                    "lds_total": len(ld_list),
                    "lds_done": 0,
                    "lns_total": 0,
                    "lns_done": 0,
                    "current_ld": None,
                    "current_ln": None,
                }

        def _set_current_ld(ld):
            with rti_so.runtime.lock:
                if model_info.model_progress:
                    model_info.model_progress["current_ld"] = ld

        def _add_lns_total(n):
            if n:
                with rti_so.runtime.lock:
                    if model_info.model_progress:
                        model_info.model_progress["lns_total"] += n

        def _set_current_ln(ln):
            with rti_so.runtime.lock:
                if model_info.model_progress:
                    model_info.model_progress["current_ln"] = ln

        def _inc_ln_done():
            with rti_so.runtime.lock:
                if model_info.model_progress:
                    model_info.model_progress["lns_done"] += 1

        def _finish_ld():
            with rti_so.runtime.lock:
                if model_info.model_progress:
                    model_info.model_progress["lds_done"] += 1
                    model_info.model_progress["current_ln"] = None

        try:
            # Step 1: Get all LDs
            ld_list = await acsi_client.get_server_directory(ws_info, None, None)
            if not isinstance(ld_list, list):
                raise RuntimeError("unexpected-server-directory")

            _init_progress(ld_list)

            # Step 2: Fetch all LD directories in PARALLEL
            async def fetch_ld_directory(ld):
                try:
                    ln_list = None
                    _set_current_ld(ld)
                    lock = rti_so.runtime.invoke_lock
                    if lock is None:
                        ln_list = await acsi_client.get_logical_device_directory(
                            ld, ws_info, None, None
                        )
                    else:
                        async with lock:
                            ln_list = await acsi_client.get_logical_device_directory(
                                ld, ws_info, None, None
                            )
                    if not isinstance(ln_list, list):
                        raise RuntimeError("unexpected-ln-list")
                    return {"ld": ld, "ln_list": ln_list, "status": "ok"}
                except Exception as e:
                    logger.error(f"Failed to get directory for {ld}: {e}")
                    return {"ld": ld, "ln_list": [], "status": "error"}
                finally:
                    _finish_ld()

            ld_coros = [fetch_ld_directory(ld) for ld in ld_list]
            ld_results = await asyncio.gather(*ld_coros)

            # Build maps from results
            logical_device_map = {}
            logical_device_status = {}
            all_ln_tasks = []

            for result in ld_results:
                ld = result["ld"]
                ln_list = result["ln_list"]
                logical_device_map[ld] = ln_list
                logical_device_status[ld] = result["status"]
                _add_lns_total(len(ln_list))

                # Collect all LNs for parallel fetching
                for ln_full in ln_list:
                    if "/" in ln_full:
                        ln_inst = ln_full.split("/")[-1]
                    elif ":" in ln_full:
                        ln_inst = ln_full.split(":")[-1]
                    else:
                        ln_inst = ln_full
                    all_ln_tasks.append((ld, ln_inst))

            # Step 3: Fetch all LN details in PARALLEL
            async def fetch_ln_details(task):
                ld, ln_inst = task
                try:
                    _set_current_ln(ln_inst)
                    details = await _aget_ln_details(ld, ln_inst, acsi_client, ws_info)
                    _inc_ln_done()
                    return {"ld": ld, "ln_inst": ln_inst, "details": details}
                except Exception as e:
                    logger.info(f"Failed to get details for {ld}/{ln_inst}: {e}")
                    _inc_ln_done()
                    return {"ld": ld, "ln_inst": ln_inst, "details": None}

            ln_coros = [fetch_ln_details(task) for task in all_ln_tasks]
            ln_results = await asyncio.gather(*ln_coros)

            # Build logical_node_details
            logical_node_details = {}
            for result in ln_results:
                if result["details"]:
                    logical_node_details[f"{result['ld']}/{result['ln_inst']}"] = (
                        result["details"]
                    )

            model = {
                "server": {"logicalDevices": ld_list},
                "logicalDeviceMap": logical_device_map,
                "logicalDeviceStatus": logical_device_status,
                "logicalNodeDetails": logical_node_details,
                "source": "live",
            }
            with rti_so.runtime.lock:
                model_info.model_data = model
                model_info.model_error = None
                model_info.model_status = "ready"
                model_info.model_ready_event.set()

        except Exception as e:
            with rti_so.runtime.lock:
                model_info.model_status = "error"
                model_info.model_error = str(e)
                model_info.model_ready_event.set()
            raise

    def _start_model_build_if_needed(cp):
        """Schedule background model build if idle or error."""
        model_info = rti_so.get_model_info(cp)

        with rti_so.runtime.lock:
            model_status = model_info.model_status
            if model_status in ("ready", "building"):
                return model_status
            model_info.model_data = None
            model_info.model_error = None
            model_info.model_status = "building"

        loop = rti_so.runtime.loop
        if not loop:
            with rti_so.runtime.lock:
                model_info.model_status = "error"
                model_info.model_error = "no-loop"
            return "error"

        try:
            rti_so._log_action("Scheduling model build", "debug", kind="system")
            fut = asyncio.run_coroutine_threadsafe(_abuild_full_model(cp), loop)
            rti_so._log_action("Model build scheduled", "debug", kind="system")
        except Exception as e:
            with rti_so.runtime.lock:
                model_info.model_status = "error"
                model_info.model_error = str(e)
            rti_so._log_action(
                f"Failed to schedule model build: {e}", "error", kind="system"
            )
            return "error"

        with rti_so.runtime.lock:
            model_info.model_task = fut

        def _on_model_task_done(future):
            model_info = rti_so.get_model_info(cp)
            try:
                exc = future.exception()
            except Exception:
                exc = None
            with rti_so.runtime.lock:
                try:
                    model_info.model_task = None
                except Exception:
                    pass
                if exc is not None:
                    model_info.model_status = "error"
                    model_info.model_error = str(exc)
                    logger.error(f"Model build failed: {exc}")
                else:
                    if model_info.model_status != "ready":
                        model_info.model_status = "ready"
                        model_info.model_error = None
                    logger.info("Model build completed")

        try:
            fut.add_done_callback(_on_model_task_done)
        except Exception as e:
            logger.info(f"Failed to attach model task callback: {e}")

        return "building"

    # ==================== Helper Methods ====================

    # ==================== Route Handlers ====================
    @router.get(
        "/status",
        summary="Get Client Status",
        description="Returns the current operational status of the Acsi-Client.",
        response_description="Client status information",
        responses={
            200: {"description": "Client status returned successfully"},
            500: {"description": "Error retrieving client status"},
        },
        tags=["Client Status"],
    )
    def api_status():
        """Get current client status.

        Returns:
            dict: Client status information including:
                - status: Connection status
                - host: Connected host (if connected)
                - port: Connected port (if connected)
                - error: Any error message
        """
        try:
            return rti_so.get_status()
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)}, status_code=500
            )

    @router.post(
        "/connections",
        summary="Get Connection Info",
        description="Returns detailed information about the current WebSocket connection, including peer address, port, and connection status.",
        response_description="Connection details",
        responses={
            200: {"description": "Connection information returned successfully"},
            500: {"description": "Error retrieving connection info"},
        },
        tags=["Client Status"],
    )
    def api_connections(request: ModelRequest):
        """Get connection information.

        Returns:
            dict: {
                "ok": True,
                "status": str,
                "connected": bool,
                "server_role": "ACSI-Client",
                "ws_mode": "passive",
                "connection": {
                    "peer_address": str | None,
                    "peer_port": int | None,
                    "local_role": "ACSI-Client",
                    "ws_mode": "passive",
                    "remote_role": "ACSI_Server",
                    "cp": str
                } | None
            }
        """
        try:
            cp = request.cp
            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500,
                )

            endpoint = rti_so.runtime.endpoint
            connection_info = {
                "ok": True,
                "status": rti_so.runtime.status,
                "connected": rti_so.runtime.status == "connected",
                "server_role": "ACSI-Client",
                "ws_mode": "passive",
                "connection": None,
            }

            if endpoint is not None and acsi_client is not None:
                ws_info = endpoint.get_websocket_info(acsi_client)
                if ws_info is not None:
                    peer_address = None
                    peer_port = None
                    try:
                        if hasattr(ws_info, "remote_address"):
                            addr_tuple = ws_info.remote_address
                            if isinstance(addr_tuple, tuple) and len(addr_tuple) >= 2:
                                peer_address = addr_tuple[0]
                                peer_port = addr_tuple[1]
                        elif hasattr(ws_info, "peername"):
                            addr_tuple = ws_info.peername()
                            if isinstance(addr_tuple, tuple) and len(addr_tuple) >= 2:
                                peer_address = addr_tuple[0]
                                peer_port = addr_tuple[1]
                    except Exception:
                        pass

                    connection_info["connection"] = {
                        "peer_address": peer_address,
                        "peer_port": peer_port,
                        "local_role": "ACSI-Client",
                        "ws_mode": "passive",
                        "remote_role": "ACSI_Server",
                        "cp": acsi_client.cp,
                    }

            return connection_info
        except Exception as exc:
            rti_so._log_action(f"Get connections failed: {exc}", "error", kind="system")
            return JSONResponse(
                content={"ok": False, "error": str(exc)}, status_code=500
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
            rti_so._log_action(
                f"Reconfig connection request: connection={request.connection_name}, enable_tls={request.enable_tls}",
                "debug",
                kind="system",
            )
            # Normalize tls_version to handle "1.2", "1.3", "TLSv1_2", "TLSv1_3" formats
            tls_version_str = (request.tls_version or "1.3").lower()
            if "1.2" in tls_version_str or "1_2" in tls_version_str:
                tls_version = ssl.TLSVersion.TLSv1_2
            else:
                tls_version = ssl.TLSVersion.TLSv1_3
            rti_so._log_action(
                f"TLS version determined: {tls_version} from request: {request.tls_version}",
                "debug",
                kind="system",
            )
            rti_so._log_action(
                f"Reconfiguring connection with TLS version: {tls_version} from request: {request.tls_version}",
                "debug",
                kind="system",
            )
            if request.ws_mode.lower() == "passive":
                rti_so._log_action(
                    "Reconfiguring passive endpoint with TLS", "debug", kind="system"
                )
                rti_so._log_action(
                    f"Reconfiguring passive endpoint with TLS: {request.enable_tls}",
                    "debug",
                    kind="system",
                )
                # Only create TLSConfig if TLS is enabled
                tls_config = None
                if request.enable_tls:
                    rti_so._log_action(
                        "Creating TLS config for server mode", "debug", kind="system"
                    )
                    keylog_file = tempfile.NamedTemporaryFile(
                        mode="w",
                        prefix="tlskeys",
                        suffix=".log",
                        delete=True,
                    )
                    tls_config = TLSConfig(
                        mode="server",
                        certfile=request.server_cert,
                        keyfile=request.server_key,
                        min_version=tls_version,
                        max_version=tls_version,
                        keylog_file=keylog_file.name,
                    )
                else:
                    rti_so._log_action(
                        "TLS disabled, no TLS config needed", "debug", kind="system"
                    )

                # Explicitly clear the endpoint's TLS config if TLS is being disabled
                endpoint = rti_so.runtime.endpoint
                if endpoint is not None and not request.enable_tls:
                    if hasattr(endpoint, "_tls_config"):
                        endpoint._tls_config = None
                    rti_so._log_action(
                        "Cleared endpoint TLS config", "debug", kind="system"
                    )

                # Cancel existing connection task before reconnecting
                if endpoint is not None and hasattr(endpoint, "_connect_task"):
                    connect_task = endpoint._connect_task
                    if connect_task and not connect_task.done():
                        rti_so._log_action(
                            "Cancelling existing connection task",
                            "debug",
                            kind="system",
                        )
                        connect_task.cancel()

                # Run on the loop that actually owns the endpoint (runtime.loop),
                # not uvicorn's own loop — matches the pattern used by
                # read_value/write_value/operate elsewhere in this router.
                rti_so._log_action(
                    "Invoking reconfigure_endpoint on runtime loop",
                    "debug",
                    kind="system",
                )
                rti_so.invoke_on_runtime_loop(
                    rti_so.runtime.endpoint.reconfigure_endpoint(
                        request.enable_tls,
                        tls_config=tls_config,
                        oauth_enable=rti_so.runtime.endpoint._oauth_enable,
                    ),
                    timeout=30,  # stop_passive + restart can take a few seconds
                )

                # if request.enable_tls:
                rti_so._log_action(
                    "Waiting for endpoint to be running", "debug", kind="system"
                )
                rti_so.invoke_on_runtime_loop(
                    rti_so.runtime.endpoint._endpoint_running_event.wait(),
                    timeout=20,
                )

                if not rti_so.runtime.endpoint._is_endpoint_running:
                    last_err = getattr(
                        rti_so.runtime.endpoint, "_last_start_error", None
                    )
                    rti_so._log_action(
                        f"Endpoint failed to start: {last_err}", "error", kind="system"
                    )
                    return JSONResponse(
                        content={
                            "ok": False,
                            "error": f"endpoint failed to start: {last_err}",
                        },
                        status_code=500,
                    )

                rti_so._log_action(
                    f"Endpoint status: {rti_so.runtime.endpoint._is_endpoint_running}",
                    "debug",
                    kind="system",
                )

                rti_so._log_action(
                    f"Connection reconfigured: enable_tls={request.enable_tls}",
                    "info",
                    kind="system",
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
                rti_so._log_action(
                    "Rejected: Only passive mode is supported for TLS reconfiguration",
                    "warn",
                    kind="system",
                )
                return JSONResponse(
                    content={
                        "ok": False,
                        "error": "Only passive mode is supported for reconfiguration.",
                    },
                    status_code=400,
                )
        except Exception as exc:
            rti_so._log_action(
                f"Reconfig connection failed: {exc}", "error", kind="system"
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
            endpoint = rti_so.runtime.endpoint
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
            ws_mode = "passive"
            if hasattr(endpoint, "ws_mode"):
                ws_mode = endpoint.ws_mode
            elif hasattr(rti_so.runtime, "ws_mode"):
                ws_mode = rti_so.runtime.ws_mode

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
            rti_so._log_action(
                f"Reconfig OAuth request: enable={request.enable_oauth}, connection={request.connection_name or 'unknown'}",
                "debug",
                kind="system",
            )
            # Get OAuth settings from request (BFF should provide these from connections.json)
            certificate_endpoint = getattr(
                request, "certificate_endpoint_url", None
            ) or getattr(request, "certificate_endpoint", None)
            token_issuer_url = getattr(request, "token_issuer_url", None) or getattr(
                request, "token_issuer", None
            )
            # If we have token_endpoint but not token_issuer, extract issuer from endpoint URL
            token_endpoint_from_req = getattr(
                request, "token_endpoint", None
            ) or getattr(request, "token_endpoint_url", None)
            if token_endpoint_from_req and not token_issuer_url:
                # token_endpoint is like: https://localhost:8443/realms/iec61850-websocket/protocol/openid-connect/token
                # token_issuer should be: https://localhost:8443/realms/iec61850-websocket
                token_issuer_url = token_endpoint_from_req.replace(
                    "/protocol/openid-connect/token", ""
                )
                rti_so._log_action(
                    "Extracted token_issuer from token_endpoint URL",
                    "debug",
                    kind="system",
                )
            ca_certificate = getattr(request, "ca_certificate", None)

            # Validate that required OAuth settings are provided
            connection_name = request.connection_name or "unknown"
            if request.enable_oauth and (
                not certificate_endpoint or not token_issuer_url
            ):
                error_msg = f"certificate_endpoint and token_issuer_url are required for OAuth but were not provided in request for connection: {connection_name}"
                rti_so._log_action(error_msg, "error", kind="system")
                raise ValueError(error_msg)

            if not request.enable_oauth:
                rti_so._log_action(
                    "Disabling OAuth for connection", "debug", kind="system"
                )
                certificate_endpoint = None
                token_issuer_url = None
                ca_certificate = None

            if request.ws_mode.lower() == "passive":
                rti_so._log_action(
                    "Reconfiguring OAuth for passive mode", "debug", kind="system"
                )
                loop = rti_so.runtime.loop
                if loop is None or not loop.is_running():
                    rti_so._log_action("Client not connected", "error", kind="system")
                    raise HTTPException(status_code=503, detail="client-not-connected")

                rti_so._log_action(
                    "Invoking reconfigure_oauth on runtime loop",
                    "debug",
                    kind="system",
                )
                fut = asyncio.run_coroutine_threadsafe(
                    rti_so.runtime.endpoint.reconfigure_oauth(
                        request.enable_oauth,
                        certificate_endpoint=certificate_endpoint,
                        token_issuer=token_issuer_url,
                        kc_cert=ca_certificate,
                    ),
                    loop,
                )
                await asyncio.wrap_future(fut)

                if request.enable_oauth:
                    rti_so._log_action(
                        "Waiting for OAuth endpoint to be running",
                        "debug",
                        kind="system",
                    )
                    wait_fut = asyncio.run_coroutine_threadsafe(
                        rti_so.runtime.endpoint._endpoint_running_event.wait(), loop
                    )
                    await asyncio.wrap_future(wait_fut)
                    rti_so._log_action(
                        f"OAuth endpoint status: {rti_so.runtime.endpoint._is_endpoint_running}",
                        "debug",
                        kind="system",
                    )

                rti_so._log_action(
                    f"OAuth reconfigured: enable={request.enable_oauth}",
                    "info",
                    kind="system",
                )
                return JSONResponse(
                    content={
                        "ok": True,
                        "status": "reconfigured",
                        "ws_mode": "passive",
                        "enable_oauth": request.enable_oauth,
                    },
                    status_code=200,
                )
            else:
                rti_so._log_action(
                    "Rejected: Only passive mode is supported for OAuth reconfiguration",
                    "warn",
                    kind="system",
                )
                return JSONResponse(
                    content={
                        "ok": False,
                        "error": "Only passive mode is supported for OAuth reconfiguration.",
                    },
                    status_code=400,
                )
        except Exception as exc:
            rti_so._log_action(f"Reconfig OAuth failed: {exc}", "error", kind="system")
            return JSONResponse(
                content={"ok": False, "error": str(exc)}, status_code=500
            )

    @router.get(
        "/oauth-status",
        summary="Get OAuth Status",
        description="Returns whether OAuth is currently enabled or disabled for this SO client.",
        response_description="OAuth enable status",
        responses={
            200: {"description": "OAuth status returned successfully"},
            500: {"description": "Error retrieving OAuth status"},
        },
        tags=["OAuth"],
    )
    def api_get_oauth_status():
        """Get current OAuth enable/disable status from the SO server.

        Returns:
            dict: {
                "ok": True,
                "enable_oauth": bool  # Current OAuth status
            }
        """
        try:
            if hasattr(rti_so.runtime, "endpoint") and hasattr(
                rti_so.runtime.endpoint, "_oauth_enable"
            ):
                enable_oauth = rti_so.runtime.endpoint._oauth_enable
                return {"ok": True, "enable_oauth": enable_oauth}
            else:
                return {"ok": True, "enable_oauth": False}
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)}, status_code=500
            )

    @router.get(
        "/properties",
        summary="Get Client Properties",
        description="Returns the static properties and configuration of the ACSI client.",
        response_description="Client properties",
        tags=["Client Status"],
    )
    def api_properties():
        """Get connection information.

        Returns:
            dict: {
                "ok": True,
                "acsi_role": "ACSI-Client",
                "ws_mode": "passive"
            }
        """
        return {
            "ok": True,
            "acsi_role": "ACSI-Client",
            "ws_mode": "passive",
            "acsi_client_list": rti_so.get_cp_list(),
        }

    @router.post(
        "/connect",
        summary="Connect to Server",
        description="Start an Active WS instance.",
        response_description="Connection confirmation",
        responses={
            200: {"description": "Connection initiated successfully"},
            400: {"description": "Invalid parameters (port must be integer)"},
            500: {"description": "Connection failed"},
        },
        tags=["Connection Management"],
    )
    async def api_connect(request: ConnectRequest):
        """Start a WS Passive Endpoint.

        Request Body:
            ConnectRequest: {
                "host": str,  # Server hostname/IP
                "port": int,  # Server port (1-65535)
                "cp": str      # Communication point
            }

        Returns:
            dict: {
                "ok": True,
                "status": "connecting",
                "host": str,
                "port": int,
                "cp": str
            }

        Raises:
            HTTPException 400: If port is not a valid integer
            HTTPException 500: If connection fails
        """
        try:
            host = request.host
            port = request.port

            # The genuine "connected" event is logged by acsi_client.py's
            # own _connect_async once the connection actually completes -
            # these are just the REST-handler-layer request/dispatch trace.
            rti_so._log_action(
                f"Connect request: host={host}, port={port}", "debug", kind="system"
            )

            try:
                rti_so.connect(host, port)
                rti_so._log_action(
                    f"Connecting to: host={host}, port={port}", "debug", kind="system"
                )
                return {"ok": True, "status": "connecting", "host": host, "port": port}
            except (ValueError, RuntimeError) as exc:
                rti_so._log_action(f"Connect rejected: {exc}", "warn", kind="system")
                return JSONResponse(
                    content={"ok": False, "error": str(exc)}, status_code=500
                )
        except Exception as exc:
            rti_so._log_action(f"Connect failed: {exc}", "error", kind="system")
            return JSONResponse(
                content={"ok": False, "error": str(exc)}, status_code=500
            )

    @router.post(
        "/disconnect",
        summary="Disconnect from Server",
        description="Stops the passive websocket endpoint.",
        response_description="Disconnection confirmation",
        responses={
            200: {"description": "Disconnection status"},
            500: {"description": "Error during disconnection"},
        },
        tags=["Connection Management"],
    )
    async def api_disconnect(request: Request):
        """Disconnect from the IEC 61850 WebSocket server."""
        try:
            # The genuine "disconnected" event is logged by acsi_client.py's
            # own _disconnect_async - these are just the REST-handler-layer
            # request/dispatch trace.
            rti_so._log_action("Disconnect request", "debug", kind="system")
            status = rti_so.runtime.status
            if status in (None, "disconnected"):
                rti_so._log_action("Already disconnected", "debug", kind="system")
                return {"ok": True, "status": "disconnected"}

            try:
                rti_so.disconnect()
                rti_so._log_action("Disconnecting...", "debug", kind="system")
                current = rti_so.runtime.status
                if current in ("disconnecting", "connected"):
                    return {"ok": True, "status": "disconnecting"}
                rti_so._log_action("Disconnected", "debug", kind="system")
                return {"ok": True, "status": "disconnected"}
            except Exception as exc:
                current = rti_so.runtime.status
                if current in ("disconnecting", "disconnected"):
                    return {"ok": True, "status": current}
                rti_so._log_action(f"Disconnect failed: {exc}", "error", kind="system")
                raise HTTPException(status_code=500, detail=str(exc))
        except Exception as exc:
            rti_so._log_action(f"Disconnect error: {exc}", "error", kind="system")
            raise HTTPException(status_code=500, detail=str(exc))

    @router.post(
        "/model/tree",
        summary="Get IED Model Tree",
        description="Retrieves the complete IED model tree from the connected server. This includes logical devices, logical nodes, data objects, and data attributes.",
        response_description="Complete IED model hierarchy",
        responses={
            200: {"description": "Model tree returned successfully"},
            503: {"description": "Client not connected"},
            500: {"description": "Error retrieving model"},
        },
        tags=["Model Access"],
    )
    async def api_model(request: ModelRequest):
        """Get the IED model tree from the connected server."""

        cp = request.cp
        model_info = rti_so.get_model_info(cp)
        refresh = request.refresh

        if refresh:
            with rti_so.runtime.lock:
                model_info.model_status = "idle"
                model_info.model_data = None
                model_info.model_error = None
                model_info.model_ready_event.clear()

        try:
            loop = rti_so.runtime.loop
            if loop is None or not getattr(loop, "is_running", lambda: False)():
                rti_so._log_action(
                    "Client not connected, raising HTTPException",
                    "error",
                    kind="system",
                )
                raise HTTPException(status_code=503, detail="client-not-connected")

            _check_websocket_connection()

            with rti_so.runtime.lock:
                model_status = model_info.model_status
                data = model_info.model_data
                error = model_info.model_error
            if model_status == "ready" and data:
                return {"status": "ready", "model": data}
            if model_status == "error":
                raise HTTPException(status_code=500, detail=error)
            if model_status == "idle":
                start_result = _start_model_build_if_needed(cp)
                if start_result == "error":
                    rti_so._log_action(
                        "Model build scheduling failed", "error", kind="system"
                    )
                    raise HTTPException(
                        status_code=503, detail=rti_so.runtime.model_error
                    )
                else:
                    try:
                        await asyncio.wait_for(
                            model_info.model_ready_event.wait(), timeout=12
                        )
                    except TimeoutError:
                        raise HTTPException(
                            status_code=504, detail="model-build-timeout"
                        )
                    data = model_info.model_data
                    return {"status": "ready", "model": data}

            return {"status": "error", "model": None}
        except HTTPException as e:
            rti_so._log_action(
                f"HTTPException raised in api_model, re-raising: {e}",
                "debug",
                kind="system",
            )
            raise
        except Exception as exc:
            rti_so._log_action(
                f"Get model failed (outer): {exc}", "error", kind="system"
            )
            logger.exception("Unhandled outer exception in api_model")
            raise HTTPException(
                status_code=500,
                detail={"error": str(exc), "traceback": traceback.format_exc()},
            )

    @router.post(
        "/server-directory",
        summary="Get Server Directory",
        description="Retrieves the list of all Logical Devices from the connected IEC61850 server. This is a modular endpoint for incremental model building.",
        response_description="Server directory with list of logical devices",
        responses={
            200: {"description": "Server directory returned successfully"},
            503: {"description": "Client not connected"},
            500: {"description": "Error retrieving server directory"},
        },
        tags=["Model Access"],
    )
    async def api_server_directory(request: ServerDirectoryRequest):
        """Get the server directory (list of Logical Devices) from the connected server."""
        try:
            _check_websocket_connection()

            cp = request.cp
            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500,
                )

            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.get_server_directory_tree(cp), timeout=10
                )

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404,
                    )

                return {
                    "ok": True,
                    "success": True,
                    "serverDirectory": result,
                }

            except FuturesTimeoutError:
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"}, status_code=504
                )
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)}, status_code=404
                )
            except Exception as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)}, status_code=500
                )
        except HTTPException:
            raise
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)}, status_code=500
            )

    @router.post(
        "/logical-device",
        summary="Get Logical Device Directory",
        description="Retrieves the list of all Logical Nodes for a specific Logical Device from the connected IEC61850 server. This is a modular endpoint for incremental model building.",
        response_description="Logical Device directory with list of logical nodes",
        responses={
            200: {"description": "Logical Device directory returned successfully"},
            400: {"description": "Missing ld_inst parameter"},
            503: {"description": "Client not connected"},
            500: {"description": "Error retrieving logical device directory"},
        },
        tags=["Model Access"],
    )
    async def api_logical_device(request: LogicalDeviceRequest):
        """Get the Logical Node list for a specific Logical Device from the connected server."""
        try:
            _check_websocket_connection()

            ld_inst = request.ld_inst
            cp = request.cp
            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500,
                )

            if not ld_inst:
                return JSONResponse(
                    content={"ok": False, "error": "ld_inst is required"},
                    status_code=400,
                )

            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.get_logical_device_tree(ld_inst, cp), timeout=10
                )

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404,
                    )

                return {
                    "ok": True,
                    "success": True,
                    "logicalDevice": result,
                }

            except FuturesTimeoutError:
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"}, status_code=504
                )
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)}, status_code=404
                )
            except Exception as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)}, status_code=500
                )
        except HTTPException:
            raise
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)}, status_code=500
            )

    @router.post(
        "/logical-node",
        summary="Get Logical Node Tree",
        description="Retrieves the complete tree (Data Objects, Data Attributes, RCBs, DataSets) for a specific Logical Node from the connected IEC61850 server. This is a modular endpoint for incremental model building.",
        response_description="Logical Node tree with all child elements",
        responses={
            200: {"description": "Logical Node tree returned successfully"},
            400: {"description": "Missing ld_inst or ln_inst parameter"},
            503: {"description": "Client not connected"},
            500: {"description": "Error retrieving logical node tree"},
        },
        tags=["Model Access"],
    )
    async def api_logical_node(request: LogicalNodeRequest):
        """Get the complete tree for a specific Logical Node from the connected server."""
        try:
            _check_websocket_connection()

            ld_inst = request.ld_inst
            ln_inst = request.ln_inst
            cp = request.cp
            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500,
                )

            if not ld_inst:
                return JSONResponse(
                    content={"ok": False, "error": "ld_inst is required"},
                    status_code=400,
                )

            if not ln_inst:
                return JSONResponse(
                    content={"ok": False, "error": "ln_inst is required"},
                    status_code=400,
                )

            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.get_logical_node_tree(ld_inst, ln_inst, cp), timeout=10
                )

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404,
                    )

                return {
                    "ok": True,
                    "success": True,
                    "logicalNode": result,
                }

            except FuturesTimeoutError:
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"}, status_code=504
                )
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)}, status_code=404
                )
            except Exception as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)}, status_code=500
                )
        except HTTPException:
            raise
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)}, status_code=500
            )

    @router.post(
        "/data-object",
        summary="Get Data Object Details",
        description="Retrieves complete details for a specific Data Object including its definition and data attributes from the connected IEC61850 server. This is a modular endpoint for incremental model building.",
        response_description="Data Object details with definition and data attributes",
        responses={
            200: {"description": "Data Object details returned successfully"},
            400: {"description": "Missing ld_inst, ln_inst, or do_name parameter"},
            503: {"description": "Client not connected"},
            500: {"description": "Error retrieving data object details"},
        },
        tags=["Model Access"],
    )
    async def api_data_object(request: DataObjectRequest):
        """Get the complete details for a specific Data Object from the connected server."""
        try:
            _check_websocket_connection()

            ld_inst = request.ld_inst
            ln_inst = request.ln_inst
            do_name = request.do_name
            cp = request.cp
            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500,
                )

            if not ld_inst:
                return JSONResponse(
                    content={"ok": False, "error": "ld_inst is required"},
                    status_code=400,
                )

            if not ln_inst:
                return JSONResponse(
                    content={"ok": False, "error": "ln_inst is required"},
                    status_code=400,
                )

            if not do_name:
                return JSONResponse(
                    content={"ok": False, "error": "do_name is required"},
                    status_code=400,
                )

            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.get_data_object_details(ld_inst, ln_inst, do_name, cp),
                    timeout=10,
                )

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404,
                    )

                return {
                    "ok": True,
                    "success": True,
                    "dataObject": result,
                }

            except FuturesTimeoutError:
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"}, status_code=504
                )
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)}, status_code=404
                )
            except Exception as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)}, status_code=500
                )
        except HTTPException:
            raise
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)}, status_code=500
            )

    @router.get(
        "/actions-logs",
        summary="Get Action Log",
        description="Retrieves the logged client actions for debugging and auditing. Actions include connection events, model builds, and data operations.",
        response_description="List of logged actions",
        responses={
            200: {"description": "Action log returned successfully"},
            500: {"description": "Error retrieving actions"},
        },
        tags=["Logging"],
    )
    async def api_actions(request: Request):
        """Get logged client actions."""
        try:
            return {"actions": rti_so.get_actions()}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.post(
        "/clear-logs",
        summary="Clear Action Log",
        description="Clears all logged client actions.",
        response_description="Clear confirmation",
        responses={
            200: {"description": "Actions cleared successfully"},
            500: {"description": "Error clearing actions"},
        },
        tags=["Logging"],
    )
    async def api_actions_clear(request: Request):
        """Clear action log."""
        try:
            rti_so.clear_actions()
            return {"ok": True}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.get(
        "/messages",
        summary="Get Message Log",
        description="Retrieves the logged protocol messages for debugging. Messages include raw WebSocket communication and protocol-level events.",
        response_description="List of logged messages",
        responses={
            200: {"description": "Message log returned successfully"},
            500: {"description": "Error retrieving messages"},
        },
        tags=["Logging"],
    )
    async def api_messages(request: Request):
        """Get logged protocol messages."""
        try:
            return {"messages": rti_so.get_messages()}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.post(
        "/clear-messages",
        summary="Clear Message Log",
        description="Clears all logged protocol messages.",
        response_description="Clear confirmation",
        responses={
            200: {"description": "Messages cleared successfully"},
            500: {"description": "Error clearing messages"},
        },
        tags=["Logging"],
    )
    async def api_messages_clear(request: Request):
        """Clear message log."""
        try:
            rti_so.clear_messages()
            return {"ok": True}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.post(
        "/readvalue",
        summary="Read Value",
        description="Reads a value from the connected Acsi-Server. The client must be connected before calling this endpoint.",
        response_description="Read value result",
        responses={
            200: {"description": "Value read successfully"},
            400: {"description": "Missing objRef parameter"},
            403: {"description": "Client is not connected"},
            404: {"description": "Instance not available or read timeout"},
            500: {"description": "Error reading value"},
        },
        tags=["Data Access"],
    )
    async def api_read_value(request: ReadvalueRequest):
        """Read a value from the connected server.

        Request Body:
            ReadvalueRequest: {
                "objRef": str,  # Required - Object reference in IEC61850 format
                "fc": str       # Optional - Functional constraint
            }

        Returns:
            dict: {
                "ok": True,
                "success": True,
                "objRef": str,
                "value": any  # The read value
            }

        Raises:
            HTTPException 400: If objRef is missing
            HTTPException 403: If client is not connected
            HTTPException 404: If instance not available or timeout
        """
        try:
            # Check WebSocket connection before attempting to read
            _check_websocket_connection()

            obj_ref = request.obj_ref
            fc = request.fc

            cp = request.cp
            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500,
                )

            if not obj_ref:
                rti_so._log_action(
                    "Client readvalue rejected: missing objRef", "warn", kind="acsi"
                )
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400,
                )

            # The call itself is logged (one kind "acsi" entry, linked to its
            # frames) by ACSIClient._invoke_acsi - only rejections, timeouts
            # and exceptions are logged here.
            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.read_value(obj_ref, fc, cp), timeout=10
                )

                plugin_host.emit(
                    ValueRead(
                        obj_ref,
                        result.get("value") if result is not None else None,
                        ok=result is not None,
                    )
                )

                if result is None:
                    rti_so._log_action(
                        "Client readvalue failed: instanceNotAvailable",
                        "warn",
                        detail={"objRef": obj_ref, "fc": fc},
                        kind="acsi",
                    )
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404,
                    )

                return {
                    "ok": True,
                    "success": True,
                    "objRef": obj_ref,
                    "value": result.get("value"),
                }

            except FuturesTimeoutError:
                rti_so._log_action(
                    "Client readvalue timeout",
                    "warn",
                    detail={"objRef": obj_ref, "fc": fc},
                    kind="acsi",
                )
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"}, status_code=504
                )
            except ValueError as exc:
                rti_so._log_action(
                    f"Client readvalue failed: {exc}", "warn", kind="acsi"
                )
                return JSONResponse(
                    content={"ok": False, "error": str(exc)}, status_code=404
                )
            except Exception as exc:
                rti_so._log_action(
                    f"Client readvalue failed: {exc}", "error", kind="acsi"
                )
                return JSONResponse(
                    content={"ok": False, "error": str(exc)}, status_code=500
                )
        except HTTPException:
            raise
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)}, status_code=500
            )

    @router.post(
        "/getDataDefinition",
        summary="Get Data Definition",
        description="Retrieves the data definition for a specified object reference from the connected IEC61850 server. The client must be connected before calling this endpoint.",
        response_description="Data definition result",
        responses={
            200: {"description": "Data definition retrieved successfully"},
            400: {"description": "Missing objRef parameter"},
            403: {"description": "Client is not connected"},
            404: {"description": "Instance not available or retrieval timeout"},
            500: {"description": "Error retrieving data definition"},
        },
        tags=["Data Access"],
    )
    async def api_get_data_definition(request: GetDataDefinitionRequest):
        """Read a value from the connected server.

        Request Body:
            ReadvalueRequest: {
                "objRef": str,  # Required - Object reference in IEC61850 format
                "fc": str       # Optional - Functional constraint
            }

        Returns:
            dict: {
                "ok": True,
                "success": True,
                "objRef": str,
                "value": any  # The read value
            }

        Raises:
            HTTPException 400: If objRef is missing
            HTTPException 403: If client is not connected
            HTTPException 404: If instance not available or timeout
        """
        try:
            # Check WebSocket connection before attempting to get data definition
            _check_websocket_connection()

            ld_inst = request.ld_inst
            ln_inst = request.ln_inst
            do_path = request.do_path

            cp = request.cp
            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500,
                )

            obj_ref = (
                f"{ld_inst}/{ln_inst}.{do_path}" if do_path else f"{ld_inst}/{ln_inst}"
            )

            if not obj_ref:
                rti_so._log_action(
                    "Client readvalue rejected: missing objRef", "warn", kind="acsi"
                )
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400,
                )

            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.get_data_definition(obj_ref, cp), timeout=10
                )

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404,
                    )

                return {
                    "ok": True,
                    "success": True,
                    "objRef": obj_ref,
                    "value": result.get("dataDefinition"),
                }

            except FuturesTimeoutError:
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"}, status_code=504
                )
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)}, status_code=404
                )
            except Exception as exc:
                rti_so._log_action(
                    f"Exception in getDataDefinition: {exc}", "error", kind="acsi"
                )
                return JSONResponse(
                    content={"ok": False, "error": str(exc)}, status_code=500
                )
        except Exception as exc:
            rti_so._log_action(
                f"Unhandled exception in getDataDefinition: {exc}",
                "error",
                kind="acsi",
            )
            return JSONResponse(
                content={"ok": False, "error": str(exc)}, status_code=500
            )

    @router.post(
        "/brcb-read",
        summary="Get brcb values",
        description="Retrieves BRCB values for a specified object reference from the connected IEC61850 server. The client must be connected before calling this endpoint.",
        response_description="Data definition result",
        responses={
            200: {"description": "BRCB values successfully"},
            400: {"description": "Missing objRef parameter"},
            403: {"description": "Client is not connected"},
            404: {"description": "Instance not available or retrieval timeout"},
            500: {"description": "Error retrieving data definition"},
        },
        tags=["Data Access"],
    )
    async def api_get_brcb_values(request: ReadRCBValueRequest):
        """Read BRCB values from the connected server."""
        try:
            # Check WebSocket connection before attempting to read BRCB
            _check_websocket_connection()

            obj_ref = request.obj_ref

            cp = request.cp
            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500,
                )

            if not obj_ref:
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400,
                )

            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.get_brcb_definition(obj_ref, cp), timeout=10
                )

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404,
                    )

                return {
                    "ok": True,
                    "success": True,
                    "objRef": obj_ref,
                    "value": result.get("brcbDefinition"),
                }

            except FuturesTimeoutError:
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"}, status_code=504
                )
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)}, status_code=404
                )
            except Exception as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)}, status_code=500
                )
        except HTTPException:
            raise
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)}, status_code=500
            )

    @router.post(
        "/brcb-write",
        summary="Writes brcb values",
        description="Writes BRCB values for a specified object reference from the connected IEC61850 server. The client must be connected before calling this endpoint.",
        response_description="Data definition result",
        responses={
            200: {"description": "BRCB values written successfully"},
            400: {"description": "Missing objRef parameter"},
            403: {"description": "Client is not connected"},
            404: {"description": "Instance not available or retrieval timeout"},
            500: {"description": "Error retrieving data definition"},
        },
        tags=["Data Access"],
    )
    async def api_set_brcb_values(request: WriteRCBValueRequest):
        """Read BRCB values from the connected server."""
        try:
            # Check WebSocket connection before attempting to write BRCB
            _check_websocket_connection()

            obj_ref = request.obj_ref

            cp = request.cp
            data = request.data
            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500,
                )

            if not obj_ref:
                rti_so._log_action(
                    "Client readvalue rejected: missing objRef", "warn", kind="acsi"
                )
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400,
                )
            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.set_brcb_values(cp, data), timeout=10
                )

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404,
                    )

                return {
                    "ok": True,
                    "success": True,
                    "objRef": obj_ref,
                    "value": result.get("result"),
                }

            except FuturesTimeoutError:
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"}, status_code=504
                )
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)}, status_code=404
                )
            except Exception as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)}, status_code=500
                )
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)}, status_code=500
            )

    @router.post(
        "/urcb-read",
        summary="Get brcb values",
        description="Retrieves BRCB values for a specified object reference from the connected IEC61850 server. The client must be connected before calling this endpoint.",
        response_description="Data definition result",
        responses={
            200: {"description": "BRCB values successfully"},
            400: {"description": "Missing objRef parameter"},
            403: {"description": "Client is not connected"},
            404: {"description": "Instance not available or retrieval timeout"},
            500: {"description": "Error retrieving data definition"},
        },
        tags=["Data Access"],
    )
    async def api_get_urcb_values(request: ReadRCBValueRequest):
        """Read BRCB values from the connected server."""
        try:
            # Check WebSocket connection before attempting to read URCB
            _check_websocket_connection()

            obj_ref = request.obj_ref

            cp = request.cp
            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500,
                )

            if not obj_ref:
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400,
                )

            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.get_urcb_definition(obj_ref, cp), timeout=10
                )

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404,
                    )

                return {
                    "ok": True,
                    "success": True,
                    "objRef": obj_ref,
                    "value": result.get("urcbDefinition"),
                }

            except FuturesTimeoutError:
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"}, status_code=504
                )
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)}, status_code=404
                )
            except Exception as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)}, status_code=500
                )
        except HTTPException:
            raise
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)}, status_code=500
            )

    @router.post(
        "/urcb-write",
        summary="Writes urcb values",
        description="Writes URCB values for a specified object reference from the connected IEC61850 server. The client must be connected before calling this endpoint.",
        response_description="Data definition result",
        responses={
            200: {"description": "URCB values written successfully"},
            400: {"description": "Missing objRef parameter"},
            403: {"description": "Client is not connected"},
            404: {"description": "Instance not available or retrieval timeout"},
            500: {"description": "Error retrieving data definition"},
        },
        tags=["Data Access"],
    )
    async def api_set_urcb_values(request: WriteRCBValueRequest):
        """Read BRCB values from the connected server."""
        try:
            # Check WebSocket connection before attempting to write URCB
            _check_websocket_connection()

            obj_ref = request.obj_ref

            cp = request.cp
            data = request.data

            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500,
                )

            if not obj_ref:
                rti_so._log_action(
                    "Client readvalue rejected: missing objRef", "warn", kind="acsi"
                )
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400,
                )
            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.set_urcb_values(cp, data), timeout=10
                )

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404,
                    )

                return {
                    "ok": True,
                    "success": True,
                    "objRef": obj_ref,
                    "value": result.get("result"),
                }

            except FuturesTimeoutError:
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"}, status_code=504
                )
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)}, status_code=404
                )
            except Exception as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)}, status_code=500
                )
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)}, status_code=500
            )

    @router.post(
        "/getDataSetDirectory",
        summary="Get Data Set directory",
        description="Retrieves the data definition for a specified object reference from the connected IEC61850 server. The client must be connected before calling this endpoint.",
        response_description="Data set directory",
        responses={
            200: {"description": "Data definition retrieved successfully"},
            400: {"description": "Missing objRef parameter"},
            403: {"description": "Client is not connected"},
            404: {"description": "Instance not available or retrieval timeout"},
            500: {"description": "Error retrieving data definition"},
        },
        tags=["Data Access"],
    )
    async def api_get_dataset_directory(request: GetDataSetDirectory):

        try:
            # Check WebSocket connection before attempting to get dataset directory
            _check_websocket_connection()

            ld_inst = request.ld_inst
            ln_inst = request.ln_inst
            ds_inst = request.ds_inst

            obj_ref = f"{ld_inst}/{ln_inst}.{ds_inst}"

            cp = request.cp
            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500,
                )

            if not obj_ref:
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400,
                )

            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.get_dataset_directory(ld_inst, ln_inst, ds_inst, cp),
                    timeout=10,
                )

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404,
                    )

                return {
                    "ok": True,
                    "success": True,
                    "objRef": obj_ref,
                    "value": result.get("value"),
                }

            except FuturesTimeoutError:
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"}, status_code=504
                )
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)}, status_code=404
                )
            except Exception as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)}, status_code=500
                )
        except HTTPException:
            raise
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)}, status_code=500
            )

    @router.get(
        "/apis",
        summary="List All API Endpoints",
        description="Returns a comprehensive list of all available API endpoints with their HTTP methods, request body schemas, and response formats.",
        response_description="List of all endpoints with their metadata",
        tags=["Discovery"],
    )
    async def api_list_all_endpoints(request: Request):
        """List all API endpoints with their schemas and metadata.

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
            methods = [m for m in route.methods if m not in ("HEAD", "OPTIONS")]

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
        "/health",
        summary="Health Check",
        description="Generic health endpoint used by external discovery systems (e.g., BFF network scan).",
        response_description="Health status",
        responses={
            200: {"description": "Service is healthy"},
            500: {"description": "Service is unhealthy"},
        },
        tags=["Health"],
    )
    async def api_health(request: Request):
        """Generic health endpoint used by external discovery."""
        try:
            return {
                "status": "ok",
                "service": "SO",
                "server": {
                    "status": "ok",
                    "host": "localhost",
                    "port": int(os.getenv("PORT", "5000")),
                },
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.post(
        "/writevalue",
        summary="Write Value",
        description="Writes a value to the connected Acsi-Server. The client must be connected before calling this endpoint.",
        response_description="Write value confirmation",
        responses={
            200: {"description": "Value written successfully"},
            400: {"description": "Missing parameters (objRef, fc, or value)"},
            403: {"description": "Client is not connected"},
            500: {"description": "Error writing value"},
        },
        tags=["Data Access"],
    )
    async def api_write_value(request: WriteValueRequest):
        """Write a value to the connected server.

        Request Body:
            WriteValueRequest: {
                "objRef": str,     # Required - Object reference
                "fc": str,        # Required - Functional constraint
                "value": any,     # Required - Value to write
                "value_type": str # Optional - Value type hint
            }

        Returns:
            dict: {
                "ok": True,
                "success": True,
                "objRef": str,
                "fc": str,
                "value": any  # The written value
            }

        Raises:
            HTTPException 400: If objRef, fc, or value is missing
            HTTPException 403: If client is not connected
            HTTPException 500: If write operation fails
        """
        try:
            # Check WebSocket connection before attempting to write value
            _check_websocket_connection()

            obj_ref = request.obj_ref
            fc = request.fc
            value = request.value
            value_type = request.data_type

            cp = request.cp
            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500,
                )

            if not obj_ref:
                rti_so._log_action(
                    "Writevalue request rejected: missing objRef",
                    "warn",
                    kind="acsi",
                )
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400,
                )

            if not fc:
                rti_so._log_action(
                    "Writevalue request rejected: missing fc", "warn", kind="acsi"
                )
                return JSONResponse(
                    content={"ok": False, "error": "fc is required"}, status_code=400
                )

            if fc.lower() not in ("cf", "sp"):
                rti_so._log_action(
                    "Access Violation: Write only allowed to CF and SP FCs",
                    "warn",
                    kind="acsi",
                )
                return JSONResponse(
                    content={
                        "ok": False,
                        "error": "Access Violation: Write only allowed to CF and SP FCs",
                    },
                    status_code=400,
                )

            if value is None:
                rti_so._log_action(
                    f"Writevalue request rejected: missing value for objRef={obj_ref}",
                    "warn",
                    kind="acsi",
                )
                return JSONResponse(
                    content={"ok": False, "error": "value is required"}, status_code=400
                )

            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.write_value(obj_ref, value, fc, value_type, cp), timeout=10
                )

                plugin_host.emit(
                    ValueWritten(
                        obj_ref,
                        value,
                        ok=result is not None and result.get("error") is None,
                    )
                )

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404,
                    )
                else:
                    if result.get("error") is None:
                        return {
                            "ok": True,
                            "success": True,
                            "objRef": obj_ref,
                            "fc": fc,
                            "value": result.get("value"),
                        }
                    else:
                        return JSONResponse(
                            content={"ok": False, "error": result.get("error")},
                            status_code=500,
                        )

            except FuturesTimeoutError:
                rti_so._log_action("WriteValue timeout", "error", kind="acsi")
                return JSONResponse(
                    content={"ok": False, "error": "write timeout"}, status_code=504
                )
            except ValueError as exc:
                rti_so._log_action(
                    f"WriteValue value error: {exc}", "error", kind="acsi"
                )
                return JSONResponse(
                    content={"ok": False, "error": str(exc)}, status_code=404
                )
            except Exception as exc:
                rti_so._log_action(f"WriteValue error: {exc}", "error", kind="acsi")
                return JSONResponse(
                    content={"ok": False, "error": str(exc)}, status_code=500
                )
        except Exception as exc:
            rti_so._log_action(f"WriteValue error: {exc}", "error", kind="acsi")

            return JSONResponse(
                content={"ok": False, "error": str(exc)}, status_code=500
            )

    @router.post(
        "/select",
        summary="Select",
        description="Selects a controllable DO on the connected Acsi-Server (select-before-operate). The client must be connected before calling this endpoint.",
        response_description="{ok, error}: ok only when the server selected it",
        responses={
            200: {"description": "The server answered; ok says whether it selected"},
            400: {"description": "Missing objRef"},
            503: {"description": "No active WebSocket connection"},
            504: {"description": "Select timeout"},
        },
        tags=["Data Access"],
    )
    async def api_select(request: SelectRequest):
        """Select a controllable DO - the request ControlModal's Select sends."""
        _check_websocket_connection()
        obj_ref = request.obj_ref
        cp = request.cp
        if not obj_ref:
            return JSONResponse(
                content={"ok": False, "error": "objRef is required"}, status_code=400
            )
        if rti_so.get_iec61850_client(cp) is None:
            return JSONResponse(
                content={"ok": False, "error": "ACSI client not found!"},
                status_code=500,
            )
        try:
            result = rti_so.invoke_on_runtime_loop(
                rti_so.select(obj_ref, cp), timeout=10
            )
        except FuturesTimeoutError:
            return JSONResponse(
                content={"ok": False, "error": "Select timeout"}, status_code=504
            )
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)}, status_code=500
            )
        return control_answer(
            result.get("result") if isinstance(result, dict) else None
        )

    @router.post(
        "/operate",
        summary="Operate",
        description="Sends an operate command to the connected Acsi-Server. The client must be connected before calling this endpoint.",
        response_description="Operate command",
        responses={
            200: {"description": "Operate command sent successfully"},
            400: {"description": "Missing parameters (objRef or value)"},
            403: {"description": "Client is not connected"},
            500: {"description": "Error writing value"},
        },
        tags=["Data Access"],
    )
    async def api_operate(request: OperateRequest):
        """Send an Operate command to the connected server.

        Request Body:
            WriteValueRequest: {
                "objRef": str,     # Required - Object reference
                "value": any,     # Required - Value to write
                "value_type": str # Optional - Value type hint
            }

        Returns:
            dict: {
                "ok": True,
                "success": True,
                "objRef": str,
                "value": any  # The written value
            }

        Raises:
            HTTPException 400: If objRef or value is missing
            HTTPException 403: If client is not connected
            HTTPException 500: If write operation fails
        """
        try:
            # Check WebSocket connection before attempting to operate
            _check_websocket_connection()

            obj_ref = request.obj_ref
            value = request.value
            value_type = request.value_type

            cp = request.cp
            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500,
                )

            if not obj_ref:
                rti_so._log_action(
                    "Operate request rejected: missing objRef", "warn", kind="acsi"
                )
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400,
                )
            if value is None:
                rti_so._log_action(
                    "Operate request rejected: missing value", "warn", kind="acsi"
                )
                return JSONResponse(
                    content={"ok": False, "error": "value is required"}, status_code=400
                )
            try:
                originator(request.origin)
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)}, status_code=400
                )

            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.operate(
                        obj_ref,
                        value,
                        value_type,
                        cp,
                        ctl_num=request.ctl_num,
                        origin=request.origin,
                        test=request.test,
                    ),
                    timeout=10,
                )

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404,
                    )
                else:
                    answer = result.get("result")
                    plugin_host.emit(
                        OperateResponse(
                            success=answer is True,
                            add_cause=answer
                            if isinstance(answer, str) and answer
                            else None,
                            obj_ref=obj_ref,
                            value=value,
                            data=result,
                        )
                    )
                    return control_answer(result.get("result"))
            except FuturesTimeoutError:
                return JSONResponse(
                    content={"ok": False, "error": "Operate timeout"}, status_code=504
                )
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)}, status_code=404
                )
            except Exception as exc:
                logger.info(f"Exception in api_operate: {exc}")
                return JSONResponse(
                    content={"ok": False, "error": str(exc)}, status_code=500
                )
        except HTTPException:
            raise
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)}, status_code=500
            )

    return router, rti_so


if __name__ == "__main__":
    import argparse

    import uvicorn

    _LOG_CHOICES = ["critical", "error", "warning", "info", "debug", "trace"]

    parser = argparse.ArgumentParser(
        description="RTI Demo SO (ACSI client) BFF endpoint"
    )
    parser.add_argument(
        "--host",
        default=os.getenv("HOST", "0.0.0.0"),
        help="Host interface to bind (default: %(default)s, env: HOST)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", "5000")),
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
    # (covers the app + ws61850 + acsi_client loggers). Re-resolve here so an
    # explicit --log-level on the command line wins, and hand the same value to
    # uvicorn so its own 'uvicorn'/'uvicorn.error'/'uvicorn.access' loggers
    # follow suit.
    resolved = resolve_log_level(args.log_level)
    logging.getLogger().setLevel(resolved)
    uvicorn_log_level = args.log_level.lower()
    if uvicorn_log_level not in _LOG_CHOICES:
        uvicorn_log_level = logging.getLevelName(resolved).lower()

    logger.info(
        "Starting RTI Demo SO BFF on %s:%d (log level %s)",
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
