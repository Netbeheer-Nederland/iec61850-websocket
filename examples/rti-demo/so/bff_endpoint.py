"""Backend for Frontend (BFF) endpoint providing REST API for ACSI client control.

This module exposes FastAPI endpoints that interact with the ACSI client,
handling connection management and value operations.
"""

from __future__ import annotations

import logging
import os
import sys
import traceback
import asyncio
import os
from concurrent.futures import TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import FastAPI, APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict

from acsi_client import ACSIClient

from ws61850.security.tls import TLSConfig
import ssl
import json

logger = logging.getLogger(__name__)

# Global flag to control io_client usage for writevalue sync
_use_io_client = True

# ==================== Helper Functions ====================

def _find_connections_file() -> str:
    """Find the connections.json file path using the same logic as BFF server."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.exists('/app'):
        return '/app/connections.json'
    elif os.path.exists(os.path.join(script_dir, 'connections.json')):
        return os.path.join(script_dir, 'connections.json')
    else:
        parent_dir = os.path.dirname(script_dir)
        if os.path.exists(os.path.join(parent_dir, 'connections.json')):
            return os.path.join(parent_dir, 'connections.json')
        return os.path.join(script_dir, 'connections.json')


def _load_connections_from_file() -> list:
    """Load connections from connections.json file."""
    connections_file = _find_connections_file()
    if os.path.exists(connections_file):
        try:
            with open(connections_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading connections: {e}")
    return []


# ==================== Pydantic Models ====================
class ConnectRequest(BaseModel):
    """Request body for connecting to an IEC61850 WebSocket server.

    Used by: POST /api/connect
    """
    host: str = Field(
        default="localhost",
        description="Server hostname or IP address to connect to",
        json_schema_extra={"example": "localhost"}
    )
    port: int = Field(
        default=8765,
        description="Server port number (1-65535)",
        ge=1,
        le=65535,
        json_schema_extra={"example": 8765}
    )

class ModelRequest(BaseModel):
    """Request body for connecting to an IEC61850 WebSocket server.

    Used by: POST /api/model
    """
    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"}
    )

class ServerDirectoryRequest(BaseModel):
    """Request body for getting server directory.

    Used by: POST /api/server-directory
    """
    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"}
    )

class LogicalDeviceRequest(BaseModel):
    """Request body for getting logical device directory.

    Used by: POST /api/logical-device
    """
    ld_inst: str = Field(
        ...,
        description="Logical Device instance name (e.g., 'LD0')",
        json_schema_extra={"example": "LD0"}
    )
    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"}
    )

class LogicalNodeRequest(BaseModel):
    """Request body for getting logical node tree.

    Used by: POST /api/logical-node
    """
    ld_inst: str = Field(
        ...,
        description="Logical Device instance name (e.g., 'LD0')",
        json_schema_extra={"example": "LD0"}
    )
    ln_inst: str = Field(
        ...,
        description="Logical Node instance name (e.g., 'LLN0')",
        json_schema_extra={"example": "LLN0"}
    )
    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"}
    )

class DataObjectRequest(BaseModel):
    """Request body for getting data object details.

    Used by: POST /api/data-object
    """
    ld_inst: str = Field(
        ...,
        description="Logical Device instance name (e.g., 'LD0')",
        json_schema_extra={"example": "LD0"}
    )
    ln_inst: str = Field(
        ...,
        description="Logical Node instance name (e.g., 'LLN0')",
        json_schema_extra={"example": "LLN0"}
    )
    do_name: str = Field(
        ...,
        description="Data Object name (e.g., 'Mod')",
        json_schema_extra={"example": "Mod"}
    )
    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"}
    )

class ReadvalueRequest(BaseModel):
    """Request body for reading a value from the connected server.

    Used by: POST /api/readvalue
    """
    objRef: str = Field(
        ...,
        description="Object reference in IEC61850 format (e.g., 'LD0/LLN0$ST$Mod')",
        json_schema_extra={"example": "LD0/LLN0$ST$Mod"}
    )
    fc: str = Field(
        default=None,
        description="Functional constraint (ST, MX, CO, etc.) - optional",
        json_schema_extra={"example": "ST"}
    )

    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"}
    )

class ReadRCBValueRequest(BaseModel):
    """Request body for reading a value from the connected server.

    Used by: POST /api/readvalue
    """
    objRef: str = Field(
        ...,
        description="Object reference in IEC61850 format (e.g., 'LD0/LLN0$ST$Mod')",
        json_schema_extra={"example": "LD0/LLN0$ST$Mod"}
    )

    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"}
    )

class WriteRCBValueRequest(BaseModel):
    """Request body for reading a value from the connected server.

    Used by: POST /api/readvalue
    """
    objRef: str = Field(
        ...,
        description="Object reference in IEC61850 format (e.g., 'LD0/LLN0$ST$Mod')",
        json_schema_extra={"example": "LD0/LLN0$ST$Mod"}
    )

    data: Any = Field(
        ...,
        description="Data to write (will be converted to appropriate type)",
    )

    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"}
    )

class GetDataDefinitionRequest(BaseModel):
    """Request body for reading a value from the connected server.

    Used by: POST /api/readvalue
    """
    ld_inst: str = Field(
        ...,
        description="LD name (e.g., 'LD0')",
        json_schema_extra={"example": "LD0"}
    )
    ln_inst: Optional[str] = Field(
        ...,
        description="LN name (e.g., 'LLN0')",
        json_schema_extra={"example": "LLN0"}
    )
    do_path: Optional[str] = Field(
        ...,
        description="Data Object path (e.g., 'Mod')",
        json_schema_extra={"example": "Mod"}
    )

    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"}
    )

class GetDataSetDirectory(BaseModel):
    """Request body for reading a value from the connected server.

    Used by: POST /api/readvalue
    """
    ld_inst: str = Field(
        ...,
        description="LD name (e.g., 'LD0')",
        json_schema_extra={"example": "LD0"}
    )
    ln_inst: str = Field(
        ...,
        description="LN name (e.g., 'LLN0')",
        json_schema_extra={"example": "LLN0"}
    )
    ds_inst: str = Field(
        ...,
        description="DataSet name (e.g., 'Event1')",
        json_schema_extra={"example": "Event1"}
    )

    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"}
    )


class OperateRequest(BaseModel):
    """Request body for writing a value to the connected server.

    Used by: POST /api/operate
    """
    objRef: str = Field(
        ...,
        description="Controllable DO Object reference in IEC61850 format",
        json_schema_extra={"example": "LD0/MMXU.WMaxSpt"}
    )
    value: Any = Field(
        ...,
        description="Value to write (will be converted to appropriate type)",
        json_schema_extra={"example": "12.4"}
    )
    value_type: Any = Field(
        ...,
        description="Value type hint for coercion (BOOLEAN, INT32, FLOAT32, etc.)",
        json_schema_extra={"example": "float32"}
    )

    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"}
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "objRef": "LD0/MMXU.WMaxSpt",
            "value": "2.11",
            "value_type": "float32",
            "cp": "cp1",
        }
    })


class IoClientConfigRequest(BaseModel):
    """Request body for enabling/disabling io_client usage for writevalue sync."""
    enabled: bool = Field(
        ...,
        description="Whether to enable io_client for device sync in writevalue",
        json_schema_extra={"example": True}
    )

class TLSConnectionCreateConfigRequest(BaseModel):
    """Request body for creating a new connection."""
    connection_name: str = Field(..., description="Human-readable name for the connection", json_schema_extra={"example": "RTI-FSP-01"})
    enable_tls: bool = Field(default=False, description="enable TLS", json_schema_extra={"example": False})
    tls_version: str = Field(default= "1.2", description="TLS version", json_schema_extra={"example": "1.2"})

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

    ws_mode : str = Field(default="passive", description="WebSocket mode (passive or active)", json_schema_extra={"example": "passive"})

class OAUTHCreateConfigRequest(BaseModel):
    """Request body for OAuth reconfiguration."""
    connection_name: Optional[str] = Field(default=None, description="Connection name (optional, auto-detected)", json_schema_extra={"example": "RTI-SO-01"})
    enable_oauth: bool = Field(default=False, description="Enable OAuth authentication", json_schema_extra={"example": False})
    ws_mode: str = Field(default="passive", description="WebSocket mode (passive or active)", json_schema_extra={"example": "passive"})
    # OAuth settings for SO (passive mode)
    certificate_endpoint_url: Optional[str] = Field(default=None, description="OAuth Certificate endpoint URL", json_schema_extra={"example": "https://auth.example.com/certs"})
    token_issuer_url: Optional[str] = Field(default=None, description="token issuer url", json_schema_extra={"example": "https://auth.example.com"})
    ca_certificate: Optional[str] = Field(default=None, description="Server CA certificate", json_schema_extra={"example": "-----BEGIN CERTIFICATE-----..."})


class WriteValueRequest(BaseModel):
    """Request body for writing a value to the connected server.

    Used by: POST /api/writevalue
    """
    objRef: str = Field(
        ...,
        description="Object reference in IEC61850 format",
        json_schema_extra={"example": "LD0/LLN0$ST$Mod"}
    )
    fc: str = Field(
        ...,
        description="Functional constraint (ST, MX, CO, etc.)",
        json_schema_extra={"example": "ST"}
    )
    value: Any = Field(
        ...,
        description="Value to write (will be converted to appropriate type)",
        json_schema_extra={"example": "ON"}
    )
    dataType: Optional[str] = Field(
        default=None,
        description="Optional value type hint for coercion",
        json_schema_extra={"example": "BOOLEAN"}
    )

    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"}
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "objRef": "LD0/LLN0$ST$Mod",
            "fc": "ST",
            "value": "ON",
            "value_type": "BOOLEAN",
            "cp": "cp1"
        }
    })

def create_fastapi_app() -> FastAPI:
    """Create and configure the FastAPI application for Acsi-Client BFF."""
    app = FastAPI(
        title="ACSI Client WS Passive",
        description="Backend for Frontend (BFF) endpoint providing REST API for ACSI client control. "
                    "This service manages IEC61850 WebSocket client connections, data access, "
                    "model retrieval, and provides comprehensive monitoring capabilities.",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        openapi_tags=[
            {"name": "Client Status", "description": "Get client status, connections, and properties"},
            {"name": "Connection Management", "description": "Connect to and disconnect from Acsi-Servers"},
            {"name": "Model Access", "description": "Retrieve and explore IED models from connected servers"},
            {"name": "Data Access", "description": "Read and write values to/from connected servers"},
            {"name": "Logging", "description": "View and clear action and message logs"},
            {"name": "Health", "description": "Service health checks and status monitoring"},
            {"name": "Discovery", "description": "API introspection and endpoint discovery"},
            {"name": "Diagnostics", "description": "Internal diagnostic endpoints"},
            {"name": "IO Client", "description": "Enable/disable and check IO client sync with physical devices"}
        ]
    )
    router, _client = create_bff_router(app)
    app.include_router(router)
    app.state.client = _client
    
    # Include IO router for device control via demo_IO
    try:
        # Add parent directory to path so we can import from demo_IO
        demo_io_parent = Path(__file__).parent.parent
        if str(demo_io_parent) not in sys.path:
            sys.path.insert(0, str(demo_io_parent))
        
        from demo_IO.io_client.io_router import create_io_router
        io_router = create_io_router()
        app.include_router(io_router)
        logger.info("[SO] IO router included for demo_IO device control")
    except ImportError as e:
        logger.warning(f"[SO] IO router not available (missing dependencies): {e}")
    except Exception as e:
        logger.error(f"[SO] Failed to include IO router: {e}")
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
        responses={404: {"description": "Not found"}, 500: {"description": "Internal server error"}}
    )
    rti_so = ACSIClient()

    # ==================== Helper Functions ====================
    def _check_websocket_connection():
        """Verify that an active WebSocket connection exists.

        Raises:
            HTTPException 503: If no WebSocket connection is established
        """
        endpoint = rti_so.runtime.endpoint
        if endpoint is None or len(endpoint.websocket_info_list) == 0:
            raise HTTPException(status_code=503, detail="no-active-websocket-connection")

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

    async def _aget_ln_details(ld_inst: str, ln_inst: str, acsi_client: Any, ws_info) -> Dict[str, Any]:
        """Async variant used internally for concurrent model assembly."""
        async def _safe(coro):
            try:
                return await coro
            except Exception:
                return None

        do_items =  await _invoke_ln_directory_async(acsi_client, ws_info, ld_inst, ln_inst, 'dataObject')
        brcb_items =  await _invoke_ln_directory_async(acsi_client, ws_info, ld_inst, ln_inst, 'brcb')
        urcb_items =  await _invoke_ln_directory_async(acsi_client, ws_info, ld_inst, ln_inst, 'urcb')
        dataset_items =  await _invoke_ln_directory_async(acsi_client, ws_info, ld_inst, ln_inst, 'dataset')

        data_objects = []
        data_attributes = []

        do_list = []
        if isinstance(do_items, dict):
            do_list = do_items.get('dataObjects', do_items.get('instanceNames', [])) or []
            data_attributes = do_items.get('dataAttributes', []) or []
        elif isinstance(do_items, list):
            do_list = do_items
        if do_list:
            lock = rti_so.runtime.invoke_lock
            for do_name in do_list:
                defn = None
                try:
                    obj_ref = f"{ld_inst}/{ln_inst}.{do_name}"
                    if lock is None:
                        defn = await acsi_client.get_data_definition(obj_ref, ws_info, None, None)
                    else:
                        async with lock:
                            defn = await acsi_client.get_data_definition(obj_ref, ws_info, None, None)

                    cdc = None
                    if isinstance(defn, dict):
                        cdc = defn.get('cdc')
                    data_objects.append({'name': do_name, 'cdc': cdc})
                except Exception:
                    data_objects.append({'name': do_name, 'cdc': None})

        def _extract_rcb(entries, kind):
            out = []
            if isinstance(entries, list):
                out = entries
            elif isinstance(entries, dict):
                out = entries.get('instanceNames') or entries.get('reportControlBlocks') or []
            return [{'name': ref, 'type': kind} for ref in out]

        rcbs = []
        lock = rti_so.runtime.invoke_lock

        brcb_list = _extract_rcb(brcb_items, 'BRCB')
        for rcb_info in brcb_list:
            rcb_name = rcb_info['name']
            rcb_ref = f"{ld_inst}/{ln_inst}.{rcb_name}"
            rcb_values = None
            try:
                if lock is None:
                    rcb_values = await acsi_client.get_BRCB_values(rcb_ref, ws_info, None, None)
                else:
                    async with lock:
                        rcb_values = await acsi_client.get_BRCB_values(rcb_ref, ws_info, None, None)
                rpt_ena = False
                if isinstance(rcb_values, dict):
                    rpt_ena = rcb_values.get('RptEna', False)
                    rcb_values = _convert_bytes_to_hex(rcb_values)
                rcbs.append({'name': rcb_name, 'type': 'BRCB', 'values': rcb_values, 'enabled': rpt_ena})
            except Exception:
                rcbs.append({'name': rcb_name, 'type': 'BRCB', 'values': None, 'enabled': False})

        urcb_list = _extract_rcb(urcb_items, 'URCB')
        for rcb_info in urcb_list:
            rcb_name = rcb_info['name']
            rcb_ref = f"{ld_inst}/{ln_inst}.{rcb_name}"
            rcb_values = None
            try:
                if lock is None:
                    rcb_values = await acsi_client.get_URCB_values(rcb_ref, ws_info, None, None)
                else:
                    async with lock:
                        rcb_values = await acsi_client.get_URCB_values(rcb_ref, ws_info, None, None)
                rpt_ena = False
                if isinstance(rcb_values, dict):
                    rpt_ena = rcb_values.get('RptEna', False)
                    rcb_values = _convert_bytes_to_hex(rcb_values)
                rcbs.append({'name': rcb_name, 'type': 'URCB', 'values': rcb_values, 'enabled': rpt_ena})
            except Exception:
                rcbs.append({'name': rcb_name, 'type': 'URCB', 'values': None, 'enabled': False})

        datasets = []
        if isinstance(dataset_items, list):
            datasets = dataset_items
        elif isinstance(dataset_items, dict):
            datasets = dataset_items.get('instanceNames') or dataset_items.get('dataSets') or []

        return {
            'dataObjects': data_objects,
            'dataAttributes': data_attributes,
            'reportControlBlocks': rcbs,
            'dataSets': datasets,
        }

    def _invoke_ln_directory(acsi_client, ws_info, ld_inst, ln_inst, mode):
        """Return coroutine that performs directory call under a lock."""
        async def _coro():
            lock = rti_so.runtime.invoke_lock
            if lock is None:
                items = await acsi_client.get_logical_node_directory(ld_inst, ln_inst, mode, ws_info, None, None)
                return items
            async with lock:
                items = await acsi_client.get_logical_node_directory(ld_inst, ln_inst, mode, ws_info, None, None)
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
            raise HTTPException(status_code=404, detail=f"Client with cp={cp} not found")
        else:
            logger.info("client found with cp: ", acsi_client.cp)

        if not rti_so or not endpoint or not loop or not acsi_client.is_connected:
            raise RuntimeError('not-connected')
        try:
            ws_info = endpoint.get_websocket_info(acsi_client)
        except Exception as e:
            print(f"CRASHED in get_websocket_info: {type(e).__name__}: {e}")
            raise

        if ws_info is None:
            raise RuntimeError('no-websocket-info')

        model_info = rti_so.get_model_info(cp)

        def _init_progress(ld_list):
            with rti_so.runtime.lock:
                model_info.model_progress = {
                    'lds_total': len(ld_list), 'lds_done': 0,
                    'lns_total': 0, 'lns_done': 0,
                    'current_ld': None, 'current_ln': None
                }

        def _set_current_ld(ld):
            with rti_so.runtime.lock:
                if model_info.model_progress:
                    model_info.model_progress['current_ld'] = ld

        def _add_lns_total(n):
            if n:
                with rti_so.runtime.lock:
                    if model_info.model_progress:
                        model_info.model_progress['lns_total'] += n

        def _set_current_ln(ln):
            with rti_so.runtime.lock:
                if model_info.model_progress:
                    model_info.model_progress['current_ln'] = ln

        def _inc_ln_done():
            with rti_so.runtime.lock:
                if model_info.model_progress:
                    model_info.model_progress['lns_done'] += 1

        def _finish_ld():
            with rti_so.runtime.lock:
                if model_info.model_progress:
                    model_info.model_progress['lds_done'] += 1
                    model_info.model_progress['current_ln'] = None

        try:
            # Step 1: Get all LDs
            ld_list = await acsi_client.get_server_directory(ws_info, None, None)
            if not isinstance(ld_list, list):
                raise RuntimeError('unexpected-server-directory')
            
            _init_progress(ld_list)
            
            # Step 2: Fetch all LD directories in PARALLEL
            async def fetch_ld_directory(ld):
                try:
                    _set_current_ld(ld)
                    ln_list = await acsi_client.get_logical_device_directory(ld, ws_info, None, None)
                    if not isinstance(ln_list, list):
                        raise RuntimeError('unexpected-ln-list')
                    return {'ld': ld, 'ln_list': ln_list, 'status': 'ok'}
                except Exception as e:
                    logger.error(f"Failed to get directory for {ld}: {e}")
                    return {'ld': ld, 'ln_list': [], 'status': 'error'}
                finally:
                    _finish_ld()
            
            ld_coros = [fetch_ld_directory(ld) for ld in ld_list]
            ld_results = await asyncio.gather(*ld_coros)
            
            # Build maps from results
            logical_device_map = {}
            logical_device_status = {}
            all_ln_tasks = []  # List of (ld, ln_inst) tuples
            
            for result in ld_results:
                ld = result['ld']
                ln_list = result['ln_list']
                logical_device_map[ld] = ln_list
                logical_device_status[ld] = result['status']
                _add_lns_total(len(ln_list))
                
                # Collect all LNs for parallel fetching
                for ln_full in ln_list:
                    if '/' in ln_full:
                        ln_inst = ln_full.split('/')[-1]
                    elif ':' in ln_full:
                        ln_inst = ln_full.split(':')[-1]
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
                    return {'ld': ld, 'ln_inst': ln_inst, 'details': details}
                except Exception as e:
                    print(f"Failed to get details for {ld}/{ln_inst}: {e}")
                    _inc_ln_done()
                    return {'ld': ld, 'ln_inst': ln_inst, 'details': None}
            
            ln_coros = [fetch_ln_details(task) for task in all_ln_tasks]
            ln_results = await asyncio.gather(*ln_coros)
            
            # Build logical_node_details
            logical_node_details = {}
            for result in ln_results:
                if result['details']:
                    logical_node_details[f"{result['ld']}/{result['ln_inst']}"] = result['details']
            
            model = {
                'server': {'logicalDevices': ld_list},
                'logicalDeviceMap': logical_device_map,
                'logicalDeviceStatus': logical_device_status,
                'logicalNodeDetails': logical_node_details,
                'source': 'live'
            }
            with rti_so.runtime.lock:
                model_info.model_data = model
                model_info.model_error = None
                model_info.model_status = 'ready'
                model_info.model_ready_event.set()

        except Exception as e:
            with rti_so.runtime.lock:
                model_info.model_status = 'error'
                model_info.model_error = str(e)
            raise

    def _start_model_build_if_needed(cp):
        """Schedule background model build if idle or error."""
        model_info = rti_so.get_model_info(cp)

        with rti_so.runtime.lock:
            model_status = model_info.model_status
            if model_status in ('ready', 'building'):
                return model_status
            model_info.model_data = None
            model_info.model_error = None
            model_info.model_status = 'building'

        loop = rti_so.runtime.loop
        if not loop:
            with rti_so.runtime.lock:
                model_info.model_status = 'error'
                model_info.model_error = 'no-loop'
            return 'error'

        try:
            #client._log_action("Scheduling model build", "info")
            fut = asyncio.run_coroutine_threadsafe(_abuild_full_model(cp), loop)
            #client._log_action("Model build scheduled", "info")
        except Exception as e:
            with rti_so.runtime.lock:
                model_info.model_status = 'error'
                model_info.model_error = str(e)
            #client._log_action(f"Failed to schedule model build: {e}", "error")
            return 'error'

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
                    model_info.model_status = 'error'
                    model_info.model_error = str(exc)
                    #client._log_action(f"Model build failed: {exc}", "error")
                else:
                    if model_info.model_status != 'ready':
                        model_info.model_status = 'ready'
                        model_info.model_error = None
                    #client._log_action("Model build completed", "info")

        try:
            fut.add_done_callback(_on_model_task_done)
        except Exception as e:
            print(f"Failed to attach model task callback: {e}")
           # client._log_action(f"Failed to attach model task callback: {e}", "warn")

        return 'building'

    # ==================== Helper Methods ====================

    async def _sync_to_io_device(io_client, obj_ref: str, value: Any):
        """Background task to sync a write to IO devices from SO. Fire-and-forget.
        
        This is used only in the /writevalue endpoint to sync IEC61850 writes
        to physical IO devices when io_client is enabled.
        """
        try:
            # Check if client is healthy before attempting sync
            if await io_client.is_healthy():
                await io_client.write_iec61850_value(obj_ref, value)
                logger.info(f"[SO] Synced IEC61850 write to device: {obj_ref}={value}")
            else:
                logger.debug("[SO] IO client not healthy, skipping device sync")
        except Exception as sync_exc:
            logger.warning(f"[SO] Device sync failed for {obj_ref}: {sync_exc}")

    # ==================== Route Handlers ====================
    @router.get(
        "/status",
        summary="Get Client Status",
        description="Returns the current operational status of the Acsi-Client.",
        response_description="Client status information",
        responses={
            200: {"description": "Client status returned successfully"},
            500: {"description": "Error retrieving client status"}
        },
        tags=["Client Status"]
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
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.post(
        "/connections",
        summary="Get Connection Info",
        description="Returns detailed information about the current WebSocket connection, including peer address, port, and connection status.",
        response_description="Connection details",
        responses={
            200: {"description": "Connection information returned successfully"},
            500: {"description": "Error retrieving connection info"}
        },
        tags=["Client Status"]
    )
    def api_connections(request:ModelRequest):
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
                    status_code=500
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
                        "cp": rti_so.runtime.cp,
                    }

            return connection_info
        except Exception as exc:
            rti_so._log_action(f"Get connections failed: {exc}", "error")
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.post(
        "/reconfig-connection",
        summary="Get Connection Info",
        description="Returns detailed information about the current WebSocket connection, including peer address, port, and connection status.",
        response_description="Connection details",
        responses={
            200: {"description": "Connection information returned successfully"},
            500: {"description": "Error retrieving connection info"}
        },
        tags=["Client Status"]
    )
    async def api_reconfig_connection(request: TLSConnectionCreateConfigRequest):
        """Reconfigure the connection with a new communication point."""
        try:
            # Normalize tls_version to handle "1.2", "1.3", "TLSv1_2", "TLSv1_3" formats
            tls_version_str = (request.tls_version or "1.3").lower()
            if "1.2" in tls_version_str or "1_2" in tls_version_str:
                tls_version = ssl.TLSVersion.TLSv1_2
            else:
                tls_version = ssl.TLSVersion.TLSv1_3
            print("Reconfiguring connection with TLS version: ", tls_version, "(from request:", request.tls_version, ")")
            if request.ws_mode.lower() == "passive":
                print("Reconfiguring passive endpoint with TLS: ", request.enable_tls)
                # Only create TLSConfig if TLS is enabled
                tls_config = None
                if request.enable_tls:
                    tls_config = TLSConfig(
                        mode="server",
                        certfile=request.server_cert,
                        keyfile=request.server_key,
                        min_version=tls_version,
                        max_version=tls_version,
                        keylog_file=os.path.join("tlskeys.log"),
                    )
                print("TLS Config: ", tls_config)

                # Explicitly clear the endpoint's TLS config if TLS is being disabled
                endpoint = rti_so.runtime.endpoint
                if endpoint is not None and not request.enable_tls:
                    if hasattr(endpoint, '_tls_config'):
                        endpoint._tls_config = None
                    print("Cleared endpoint TLS config")

                # Cancel existing connection task before reconnecting
                if endpoint is not None and hasattr(endpoint, '_connect_task'):
                    connect_task = endpoint._connect_task
                    if connect_task and not connect_task.done():
                        print("Cancelling endpoint's _connect_task")
                        connect_task.cancel()

                # Run on the loop that actually owns the endpoint (runtime.loop),
                # not uvicorn's own loop — matches the pattern used by
                # read_value/write_value/operate elsewhere in this router.
                rti_so.invoke_on_runtime_loop(
                    rti_so.runtime.endpoint.reconfigure_endpoint(request.enable_tls, tls_config=tls_config),
                    timeout=30,  # stop_passive + restart can take a few seconds
                )

                if request.enable_tls:
                    rti_so.invoke_on_runtime_loop(
                        rti_so.runtime.endpoint._endpoint_running_event.wait(),
                        timeout=20,
                    )
                    print("endpoint status is: ", rti_so.runtime.endpoint._is_endpoint_running)

                return JSONResponse(
                    content={"ok": True, "status": "reconfigured", "ws_mode": request.ws_mode,
                             "enable_tls": request.enable_tls},
                    status_code=200,
                )
            else:
                return JSONResponse(
                    content={"ok": False, "error": "Only passive mode is supported for reconfiguration."},
                    status_code=400,
                )
        except Exception as exc:
            import traceback
            print("reconfig error:", repr(exc))
            traceback.print_exc()
            rti_so._log_action(f"Reconfig connection failed: {exc}", "error")
            return JSONResponse(content={"ok": False, "error": str(exc)}, status_code=500)

    @router.get(
        "/tls-config",
        summary="Get TLS Configuration",
        description="Returns the current TLS configuration from runtime variables.",
        response_description="TLS configuration from runtime",
        responses={
            200: {"description": "TLS configuration returned successfully"},
            500: {"description": "Error retrieving TLS configuration"}
        },
        tags=["TLS"]
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
                    status_code=500
                )

            # Get TLS config from runtime
            enable_tls = False
            tls_version = "1.2"
            server_key = None
            server_cert = None
            server_ca = None

            if hasattr(endpoint, '_tls_config') and endpoint._tls_config is not None:
                tls_config = endpoint._tls_config
                enable_tls = True
                # Extract TLS version from config
                if hasattr(tls_config, 'min_version'):
                    if tls_config.min_version == ssl.TLSVersion.TLSv1_3:
                        tls_version = "1.3"
                    elif tls_config.min_version == ssl.TLSVersion.TLSv1_2:
                        tls_version = "1.2"
                if hasattr(tls_config, 'cafile'):
                    server_ca = tls_config.cafile
                if hasattr(tls_config, 'certfile'):
                    server_cert = tls_config.certfile
                if hasattr(tls_config, 'keyfile'):
                    server_key = tls_config.keyfile
            
            # Get ws_mode
            ws_mode = "passive"
            if hasattr(endpoint, 'ws_mode'):
                ws_mode = endpoint.ws_mode
            elif hasattr(rti_so.runtime, 'ws_mode'):
                ws_mode = rti_so.runtime.ws_mode

            return {
                "ok": True,
                "enable_tls": enable_tls,
                "tls_version": tls_version,
                "server_key": server_key,
                "server_cert": server_cert,
                "server_ca": server_ca,
                "ws_mode": ws_mode
            }
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.post(
        "/reconfig-oauth",
        summary="Get Connection Info",
        description="Returns detailed information about the current WebSocket connection, including peer address, port, and connection status.",
        response_description="Connection details",
        responses={
            200: {"description": "Connection information returned successfully"},
            500: {"description": "Error retrieving connection info"}
        },
        tags=["Client Status"]
    )
    async def api_reconfig_oauth(request: OAUTHCreateConfigRequest):
        """Reconfigure OAuth settings. OAuth config should be provided in the request by BFF."""
        try:
            # Get OAuth settings from request (BFF should provide these from connections.json)
            certificate_endpoint = getattr(request, 'certificate_endpoint_url', None) or getattr(request, 'certificate_endpoint', None)
            token_issuer_url = getattr(request, 'token_issuer_url', None) or getattr(request, 'token_issuer', None)
            # If we have token_endpoint but not token_issuer, extract issuer from endpoint URL
            token_endpoint_from_req = getattr(request, 'token_endpoint', None) or getattr(request, 'token_endpoint_url', None)
            if token_endpoint_from_req and not token_issuer_url:
                # token_endpoint is like: https://localhost:8443/realms/iec61850-websocket/protocol/openid-connect/token
                # token_issuer should be: https://localhost:8443/realms/iec61850-websocket
                token_issuer_url = token_endpoint_from_req.replace('/protocol/openid-connect/token', '')
            ca_certificate = getattr(request, 'ca_certificate', None)
            
            # Validate that required OAuth settings are provided
            connection_name = request.connection_name or "unknown"
            if request.enable_oauth and (not certificate_endpoint or not token_issuer_url):
                raise ValueError(f"certificate_endpoint and token_issuer_url are required for OAuth but were not provided in request for connection: {connection_name}")
            
            # When disabling OAuth, pass None to signal that OAuth should be disabled
            # The underlying library should handle None properly
            if not request.enable_oauth:
                certificate_endpoint = None
                token_issuer_url = None
                ca_certificate = None
            
            if request.ws_mode.lower() == "passive":
                loop = rti_so.runtime.loop
                if loop is None or not loop.is_running():
                    raise HTTPException(status_code=503, detail="client-not-connected")

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
                    wait_fut = asyncio.run_coroutine_threadsafe(
                        rti_so.runtime.endpoint._endpoint_running_event.wait(), loop
                    )
                    await asyncio.wrap_future(wait_fut)
                    print("endpoint status is: ", rti_so.runtime.endpoint._is_endpoint_running)

                return JSONResponse(
                    content={"ok": True, "status": "reconfigured", "ws_mode": "passive",
                             "enable_oauth": request.enable_oauth},
                    status_code=200,
                )
            else:
                return JSONResponse(
                    content={"ok": False, "error": "Only passive mode is supported for OAuth reconfiguration."},
                    status_code=400,
                )
        except Exception as exc:
            import traceback
            print("reconfig oauth error:", exc)
            print("Traceback:", traceback.format_exc())
            rti_so._log_action(f"Reconfig OAuth failed: {exc}", "error")
            return JSONResponse(content={"ok": False, "error": str(exc)}, status_code=500)

    @router.get(
        "/oauth-status",
        summary="Get OAuth Status",
        description="Returns whether OAuth is currently enabled or disabled for this SO client.",
        response_description="OAuth enable status",
        responses={
            200: {"description": "OAuth status returned successfully"},
            500: {"description": "Error retrieving OAuth status"}
        },
        tags=["OAuth"]
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
            # Check the runtime endpoint's OAuth enable status
            if hasattr(rti_so.runtime, 'endpoint') and hasattr(rti_so.runtime.endpoint, '_oauth_enable'):
                enable_oauth = rti_so.runtime.endpoint._oauth_enable
                return {"ok": True, "enable_oauth": enable_oauth}
            else:
                # If endpoint not available or attribute not found, check if OAuth is configured
                return {"ok": True, "enable_oauth": False}
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.get(
        "/properties",
        summary="Get Client Properties",
        description="Returns the static properties and configuration of the ACSI client.",
        response_description="Client properties",
        tags=["Client Status"]
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
        }

    @router.post(
        "/connect",
        summary="Connect to Server",
        description="Start an Active WS instance.",
        response_description="Connection confirmation",
        responses={
            200: {"description": "Connection initiated successfully"},
            400: {"description": "Invalid parameters (port must be integer)"},
            500: {"description": "Connection failed"}
        },
        tags=["Connection Management"]
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

            try:
                rti_so.connect(host, port)
                return {"ok": True, "status": "connecting", "host": host, "port": port}
            except (ValueError, RuntimeError) as exc:
                rti_so._log_action(f"Connect rejected: {exc}", "warn")
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
        except Exception as exc:
            rti_so._log_action(f"Connect failed: {exc}", "error")
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.post(
        "/disconnect",
        summary="Disconnect from Server",
        description="Stops the passive websocket endpoint.",
        response_description="Disconnection confirmation",
        responses={
            200: {"description": "Disconnection status"},
            500: {"description": "Error during disconnection"}
        },
        tags=["Connection Management"]
    )
    async def api_disconnect(request: Request):
        """Disconnect from the IEC 61850 WebSocket server."""
        try:
            status = rti_so.runtime.status
            if status in (None, "disconnected"):
                return {"ok": True, "status": "disconnected"}

            try:
                rti_so.disconnect()
                current = rti_so.runtime.status
                if current in ("disconnecting", "connected"):
                    return {"ok": True, "status": "disconnecting"}
                return {"ok": True, "status": "disconnected"}
            except Exception as exc:
                current = rti_so.runtime.status
                if current in ("disconnecting", "disconnected"):
                    return {"ok": True, "status": current}
                rti_so._log_action(f"Disconnect failed: {exc}", "error")
                raise HTTPException(status_code=500, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.post(
        "/model/tree",
        summary="Get IED Model Tree",
        description="Retrieves the complete IED model tree from the connected server. This includes logical devices, logical nodes, data objects, and data attributes.",
        response_description="Complete IED model hierarchy",
        responses={
            200: {"description": "Model tree returned successfully"},
            503: {"description": "Client not connected"},
            500: {"description": "Error retrieving model"}
        },
        tags=["Model Access"]
    )
    async def api_model(request: ModelRequest, refresh: bool = False):
        """Get the IED model tree from the connected server."""

        cp = request.cp
        model_info = rti_so.get_model_info(cp)

        if refresh:
                with rti_so.runtime.lock:
                    model_info.model_status = 'idle'
                    model_info.model_data = None
                    model_info.model_error = None
                    model_info.model_ready_event.clear()

        try:
            loop = rti_so.runtime.loop
            if loop is None or not getattr(loop, "is_running", lambda: False)():
                raise HTTPException(status_code=503, detail="client-not-connected")

            _check_websocket_connection()

            with rti_so.runtime.lock:
                model_status = model_info.model_status
                data = model_info.model_data
                error = model_info.model_error
            if model_status == 'ready' and data:
                return {'status': 'ready', 'model': data}
            if model_status == 'error':
                raise HTTPException(status_code=500, detail=error)
            if model_status == 'idle':
                start_result = _start_model_build_if_needed(cp)
                if start_result == 'error':
                    rti_so._log_action('Model build scheduling failed', 'error')
                    raise HTTPException(status_code=503, detail=rti_so.runtime.model_error)
                else:
                    await model_info.model_ready_event.wait()
                    data = model_info.model_data
                    return {"status": "ready", "model": data}

            return {'status': 'error', 'model': None}
        except HTTPException:
            raise
        except Exception as exc:
            rti_so._log_action(f"Get model failed (outer): {exc}", "error")
            logger.exception("Unhandled outer exception in api_model")
            raise HTTPException(
                status_code=500,
                detail={"error": str(exc), "traceback": traceback.format_exc()}
            )

    @router.post(
        "/server-directory",
        summary="Get Server Directory",
        description="Retrieves the list of all Logical Devices from the connected IEC61850 server. This is a modular endpoint for incremental model building.",
        response_description="Server directory with list of logical devices",
        responses={
            200: {"description": "Server directory returned successfully"},
            503: {"description": "Client not connected"},
            500: {"description": "Error retrieving server directory"}
        },
        tags=["Model Access"]
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
                    status_code=500
                )

            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.get_server_directory_tree(cp), timeout=10
                )

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404
                    )

                return {
                    "ok": True,
                    "success": True,
                    "serverDirectory": result,
                }

            except FuturesTimeoutError:
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"},
                    status_code=504
                )
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
        except HTTPException:
            raise
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
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
            500: {"description": "Error retrieving logical device directory"}
        },
        tags=["Model Access"]
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
                    status_code=500
                )

            if not ld_inst:
                return JSONResponse(
                    content={"ok": False, "error": "ld_inst is required"},
                    status_code=400
                )

            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.get_logical_device_tree(ld_inst, cp), timeout=10
                )

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404
                    )

                return {
                    "ok": True,
                    "success": True,
                    "logicalDevice": result,
                }

            except FuturesTimeoutError:
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"},
                    status_code=504
                )
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
        except HTTPException:
            raise
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
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
            500: {"description": "Error retrieving logical node tree"}
        },
        tags=["Model Access"]
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
                    status_code=500
                )

            if not ld_inst:
                return JSONResponse(
                    content={"ok": False, "error": "ld_inst is required"},
                    status_code=400
                )

            if not ln_inst:
                return JSONResponse(
                    content={"ok": False, "error": "ln_inst is required"},
                    status_code=400
                )

            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.get_logical_node_tree(ld_inst, ln_inst, cp), timeout=10
                )

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404
                    )

                return {
                    "ok": True,
                    "success": True,
                    "logicalNode": result,
                }

            except FuturesTimeoutError:
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"},
                    status_code=504
                )
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
        except HTTPException:
            raise
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
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
            500: {"description": "Error retrieving data object details"}
        },
        tags=["Model Access"]
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
                    status_code=500
                )

            if not ld_inst:
                return JSONResponse(
                    content={"ok": False, "error": "ld_inst is required"},
                    status_code=400
                )

            if not ln_inst:
                return JSONResponse(
                    content={"ok": False, "error": "ln_inst is required"},
                    status_code=400
                )

            if not do_name:
                return JSONResponse(
                    content={"ok": False, "error": "do_name is required"},
                    status_code=400
                )

            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.get_data_object_details(ld_inst, ln_inst, do_name, cp), timeout=10
                )

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404
                    )

                return {
                    "ok": True,
                    "success": True,
                    "dataObject": result,
                }

            except FuturesTimeoutError:
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"},
                    status_code=504
                )
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
        except HTTPException:
            raise
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.get(
        "/actions-logs",
        summary="Get Action Log",
        description="Retrieves the logged client actions for debugging and auditing. Actions include connection events, model builds, and data operations.",
        response_description="List of logged actions",
        responses={
            200: {"description": "Action log returned successfully"},
            500: {"description": "Error retrieving actions"}
        },
        tags=["Logging"]
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
            500: {"description": "Error clearing actions"}
        },
        tags=["Logging"]
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
            500: {"description": "Error retrieving messages"}
        },
        tags=["Logging"]
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
            500: {"description": "Error clearing messages"}
        },
        tags=["Logging"]
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
            500: {"description": "Error reading value"}
        },
        tags=["Data Access"]
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
            # ✅ Check WebSocket connection before attempting to read
            _check_websocket_connection()

            obj_ref = request.objRef
            fc = request.fc

            cp = request.cp
            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500
                )

            if not obj_ref:
                rti_so._log_action("Client readvalue rejected: missing objRef", "warn")
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400
                )

            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.read_value(obj_ref, fc, cp), timeout=10
                )

                if result is None:
                    rti_so._log_action(
                        "Client readvalue failed: instanceNotAvailable",
                        "warn",
                        detail={"objRef": obj_ref, "fc": fc}
                    )
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404
                    )

                rti_so._log_action(
                    "Client readvalue",
                    detail={
                        "objRef": obj_ref,
                        "value": result.get("value"),
                    },
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
                )
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"},
                    status_code=504
                )
            except ValueError as exc:
                rti_so._log_action(f"Client readvalue failed: {exc}", "warn")
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                rti_so._log_action(f"Client readvalue failed: {exc}", "error")
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
        except HTTPException:
            raise
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
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
            500: {"description": "Error retrieving data definition"}
        },
        tags=["Data Access"]
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
            # ✅ Check WebSocket connection before attempting to get data definition
            _check_websocket_connection()

            ld_inst = request.ld_inst
            ln_inst = request.ln_inst
            do_path = request.do_path

            cp = request.cp
            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500
                )

            obj_ref = f"{ld_inst}/{ln_inst}.{do_path}" if do_path else f"{ld_inst}/{ln_inst}"

            if not obj_ref:
                #client._log_action("Client readvalue rejected: missing objRef", "warn")
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400
                )

            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.get_data_definition(obj_ref, cp), timeout=10
                )

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404
                    )

                return {
                    "ok": True,
                    "success": True,
                    "objRef": obj_ref,
                    "value": result.get("dataDefinition"),
                }

            except FuturesTimeoutError:
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"},
                    status_code=504
                )
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
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
            500: {"description": "Error retrieving data definition"}
        },
        tags=["Data Access"]
    )

    async def api_get_brcb_values(request: ReadRCBValueRequest):
        """Read BRCB values from the connected server."""
        try:
            # ✅ Check WebSocket connection before attempting to read BRCB
            _check_websocket_connection()

            obj_ref = request.objRef

            cp = request.cp
            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500
                )

            if not obj_ref:
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400
                )

            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.get_brcb_definition(obj_ref, cp), timeout=10
                )

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404
                    )

                return {
                    "ok": True,
                    "success": True,
                    "objRef": obj_ref,
                    "value": result.get("brcbDefinition"),
                }

            except FuturesTimeoutError:
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"},
                    status_code=504
                )
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
        except HTTPException:
            raise
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
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
            500: {"description": "Error retrieving data definition"}
        },
        tags=["Data Access"]
    )
    async def api_set_brcb_values(request: WriteRCBValueRequest):
        """Read BRCB values from the connected server."""
        try:
            # ✅ Check WebSocket connection before attempting to write BRCB
            _check_websocket_connection()

            obj_ref = request.objRef

            cp = request.cp
            data = request.data
            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500
                )

            if not obj_ref:
                # client._log_action("Client readvalue rejected: missing objRef", "warn")
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400
                )
            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.set_brcb_values(cp, data), timeout=10
                )

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404
                    )

                return {
                    "ok": True,
                    "success": True,
                    "objRef": obj_ref,
                    "value": result.get("result"),
                }

            except FuturesTimeoutError:
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"},
                    status_code=504
                )
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
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
            500: {"description": "Error retrieving data definition"}
        },
        tags=["Data Access"]
    )

    async def api_get_urcb_values(request: ReadRCBValueRequest):
        """Read BRCB values from the connected server."""
        try:
            # ✅ Check WebSocket connection before attempting to read URCB
            _check_websocket_connection()

            obj_ref = request.objRef

            cp = request.cp
            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500
                )

            if not obj_ref:
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400
                )

            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.get_urcb_definition(obj_ref, cp), timeout=10
                )

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404
                    )

                return {
                    "ok": True,
                    "success": True,
                    "objRef": obj_ref,
                    "value": result.get("urcbDefinition"),
                }

            except FuturesTimeoutError:
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"},
                    status_code=504
                )
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
        except HTTPException:
            raise
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
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
            500: {"description": "Error retrieving data definition"}
        },
        tags=["Data Access"]
    )
    async def api_set_urcb_values(request: WriteRCBValueRequest):
        """Read BRCB values from the connected server."""
        try:
            # ✅ Check WebSocket connection before attempting to write URCB
            _check_websocket_connection()

            obj_ref = request.objRef

            cp = request.cp
            data = request.data

            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500
                )

            if not obj_ref:
                # client._log_action("Client readvalue rejected: missing objRef", "warn")
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400
                )
            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.set_urcb_values(cp, data), timeout=10
                )

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404
                    )

                return {
                    "ok": True,
                    "success": True,
                    "objRef": obj_ref,
                    "value": result.get("result"),
                }

            except FuturesTimeoutError:
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"},
                    status_code=504
                )
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
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
            500: {"description": "Error retrieving data definition"}
        },
        tags=["Data Access"]
    )
    async def api_get_dataset_directory(request: GetDataSetDirectory):

        try:
            # ✅ Check WebSocket connection before attempting to get dataset directory
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
                    status_code=500
                )

            if not obj_ref:
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400
                )

            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.get_dataset_directory(ld_inst, ln_inst, ds_inst, cp), timeout=10
                )

                print("get ds result: ", result)

                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404
                    )

                return {
                    "ok": True,
                    "success": True,
                    "objRef": obj_ref,
                    "value": result.get("value"),
                }

            except FuturesTimeoutError:
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"},
                    status_code=504
                )
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
        except HTTPException:
            raise
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.get(
        "/apis",
        summary="List All API Endpoints",
        description="Returns a comprehensive list of all available API endpoints with their HTTP methods, request body schemas, and response formats.",
        response_description="List of all endpoints with their metadata",
        tags=["Discovery"]
    )
    async def api_list_all_endpoints(request: Request):
        """List all API endpoints."""
        routes = []
        for rule in app.url_map.iter_rules():
            path = str(rule)
            if path.startswith("/api/iec61850client/"):
                methods = [m for m in rule.methods if m not in ("HEAD", "OPTIONS")]
                routes.append({"path": path, "methods": methods, "endpoint": rule.endpoint})
        return {"ok": True, "count": len(routes), "endpoints": sorted(routes, key=lambda x: x["path"])}

    @router.get(
        "/health",
        summary="Health Check",
        description="Generic health endpoint used by external discovery systems (e.g., BFF network scan).",
        response_description="Health status",
        responses={
            200: {"description": "Service is healthy"},
            500: {"description": "Service is unhealthy"}
        },
        tags=["Health"]
    )
    async def api_health(request: Request):
        """Generic health endpoint used by external discovery."""
        try:
            return {
                "status": "ok",
                "service": "SO",
                "server": {"status": "ok", "host": "localhost", "port": 8080},
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
            500: {"description": "Error writing value"}
        },
        tags=["Data Access"]
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
            # ✅ Check WebSocket connection before attempting to write value
            _check_websocket_connection()

            obj_ref = request.objRef
            fc = request.fc
            value = request.value
            value_type = request.dataType

            cp = request.cp
            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500
                )

            if not obj_ref:
                #client._log_action("Client writevalue rejected: missing objRef", "warn")
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400
                )

            if not fc:
                #client._log_action("Client writevalue rejected: missing fc", "warn")
                return JSONResponse(
                    content={"ok": False, "error": "fc is required"},
                    status_code=400
                )

            if value is None:
                #client._log_action(
                #    "Client writevalue rejected: missing value",
                #    "warn",
                #    detail={"objRef": obj_ref, "fc": fc}
                #)
                return JSONResponse(
                    content={"ok": False, "error": "value is required"},
                    status_code=400
                )

            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.write_value(obj_ref, value, fc, value_type, cp), timeout=10
                )
                
                # Sync with mapped device if io_client is enabled (fire-and-forget)
                if _use_io_client:
                    try:
                        # Get the existing IO router's client and mapping manager
                        from demo_IO.io_client.io_router import get_io_client, get_mapping_manager
                        
                        io_client = get_io_client()
                        logger.info(f"[SO] IO client for sync: {io_client}")
                        if io_client:
                            # Fire-and-forget: don't wait for IO sync to complete
                            # Check health and sync in background
                            asyncio.create_task(
                                _sync_to_io_device(io_client, obj_ref, value)
                            )
                        else:
                            logger.warning("[SO] IO client is None - cannot sync to device. Call /api/io/connect first.")
                    except ImportError as e:
                        logger.error(f"[SO] ImportError - Cannot import IO client: {e}")
                    except Exception as e:
                        logger.error(f"[SO] Exception in IO sync setup: {e}")
                
                if result is None:
                    #client._log_action(
                    #    "Client writevalue failed: instanceNotAvailable",
                    #    "warn",
                    #    detail={"objRef": obj_ref, "fc": fc, "value": value},
                    #)
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404
                    )
                else:
                    return {
                        "ok": True,
                        "success": True,
                        "objRef": obj_ref,
                        "fc": fc,
                        "value": result.get("value"),
                    }
            except FuturesTimeoutError:
                #client._log_action(
                #    "Client writevalue timeout",
                #    "warn",
                #    detail={"objRef": obj_ref},
                #)
                return JSONResponse(
                    content={"ok": False, "error": "write timeout"},
                    status_code=504
                )
            except ValueError as exc:
                #client._log_action(f"Client writevalue failed: {exc}", "warn")
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                #client._log_action(f"Client writevalue failed: {exc}", "error")
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
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
            500: {"description": "Error writing value"}
        },
        tags=["Data Access"]
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
            # ✅ Check WebSocket connection before attempting to operate
            _check_websocket_connection()

            obj_ref = request.objRef
            value = request.value
            value_type = request.value_type

            cp = request.cp
            acsi_client = rti_so.get_iec61850_client(cp)
            if acsi_client is None:
                return JSONResponse(
                    content={"ok": False, "error": "ACSI client not found!"},
                    status_code=500
                )

            if not obj_ref:
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400
                )
            if value is None:
                return JSONResponse(
                    content={"ok": False, "error": "value is required"},
                    status_code=400
                )

            try:
                result = rti_so.invoke_on_runtime_loop(
                    rti_so.operate(obj_ref, value, value_type, cp), timeout=10
                )
                if result is None:
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404
                    )
                else:
                    print("operate result in so: ", result)
                    #operate_result = result.get('result', {})
                    success = result.get('result', False)
                    error = result.get('serviceError', "")
                    return {
                        "ok": success,
                        "error": error,
                    }
            except FuturesTimeoutError:
                return JSONResponse(
                    content={"ok": False, "error": "Operate timeout"},
                    status_code=504
                )
            except ValueError as exc:
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                print("entered here 1")
                print(f"Exception in api_operate: {exc}")
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
        except HTTPException:
            raise
        except Exception as exc:
            print("entered here 2")
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    # @router.get(
    #     "/internal/model/status",
    #     summary="Internal Model Status",
    #     description="Internal diagnostic endpoint exposing model build state for debugging purposes.",
    #     response_description="Model build state",
    #     responses={
    #         200: {"description": "Model build status returned"},
    #         500: {"description": "Error retrieving status"}
    #     },
    #     tags=["Diagnostics"]
    # )
    # async def _internal_model_status(request: Request):
    #     """Internal diagnostic endpoint exposing model build state."""
    #     try:
    #         with rti_so.runtime.lock:
    #             status = getattr(rti_so.runtime, 'model_status', None)
    #             progress = getattr(rti_so.runtime, 'model_progress', None)
    #             error = getattr(rti_so.runtime, 'model_error', None)
    #             task = getattr(rti_so.runtime, 'model_task', None)
    #             loop = getattr(rti_so.runtime, 'loop', None)
    #             client_conn = getattr(rti_so.runtime, 'client', None)
    #
    #         loop_running = False
    #         try:
    #             loop_running = bool(loop and getattr(loop, 'is_running', lambda: False)())
    #         except Exception:
    #             loop_running = False
    #
    #         client_connected = False
    #         try:
    #             client_connected = bool(client_conn and getattr(client_conn, 'is_connected', False))
    #         except Exception:
    #             client_connected = False
    #
    #         return {
    #             'ok': True,
    #             'model_status': status,
    #             'model_progress': progress,
    #             'model_error': error,
    #             'model_task_present': task is not None,
    #             'loop_running': loop_running,
    #             'client_connected': client_connected,
    #         }
    #     except Exception as exc:
    #         rti_so._log_action(f"Internal model status failed: {exc}", 'error')
    #         raise HTTPException(status_code=500, detail=str(exc))

    # ==================== IO Client Endpoints ====================

    @router.get(
        "/io-client",
        summary="Get IO Client Status",
        description="Returns whether io_client is enabled for device sync in writevalue.",
        response_description="IO client status",
        responses={
            200: {"description": "IO client status returned successfully"}
        },
        tags=["IO Client"]
    )
    def api_get_io_client_status():
        """Get current io_client usage status for writevalue sync.
        
        Returns:
            dict: {"enabled": bool}
        """
        return {"enabled": _use_io_client}

    @router.post(
        "/io-client",
        summary="Set IO Client Usage",
        description="Enable or disable io_client for syncing writes to physical IO devices in writevalue endpoint.",
        response_description="IO client configuration confirmation",
        responses={
            200: {"description": "IO client configuration updated successfully"},
            500: {"description": "Error updating configuration"}
        },
        tags=["IO Client"]
    )
    def api_set_io_client(request: IoClientConfigRequest):
        """Enable or disable io_client usage for writevalue sync.
        
        When enabled, writes to the ACSI server via /writevalue will be synced 
        to physical IO devices. When disabled, writes will only affect the ACSI 
        server model.
        
        Request Body:
            IoClientConfigRequest: {"enabled": bool}
        
        Returns:
            dict: {"ok": True, "enabled": bool, "message": str}
        """
        global _use_io_client
        _use_io_client = request.enabled
        logger.info(f"[SO] IO client usage set to: {_use_io_client}")
        return {
            "ok": True,
            "enabled": _use_io_client,
            "message": f"IO client {'enabled' if _use_io_client else 'disabled'} for writevalue sync"
        }

    return router, rti_so

if __name__ == "__main__":
    import uvicorn
    app = create_fastapi_app()
    port = int(os.getenv("PORT", "5003"))
    uvicorn.run(app, host="0.0.0.0", port=port)

