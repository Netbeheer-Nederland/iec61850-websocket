"""Backend for Frontend (BFF) endpoint providing REST API for ACSI client control.

This module exposes FastAPI endpoints that interact with the ACSI client,
handling connection management and value operations.
"""

from __future__ import annotations

import logging
import traceback
import asyncio
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any, Dict, Optional
from fastapi import FastAPI, APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ConfigDict

from acsi_client import ACSIClient

logger = logging.getLogger(__name__)

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
            {"name": "Diagnostics", "description": "Internal diagnostic endpoints"}
        ]
    )
    router, _client = create_bff_router(app)
    app.include_router(router)
    app.state.client = _client
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
        """Build full model sequentially with progress updates."""
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

        logical_node_details = {}
        logical_device_map = {}
        logical_device_status = {}

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

        async def _process_ld(ld):
            try:
                _set_current_ld(ld)
                ln_list = await acsi_client.get_logical_device_directory(ld, ws_info, None, None)
                if not isinstance(ln_list, list):
                    raise RuntimeError('unexpected-ln-list')
                logical_device_map[ld] = ln_list
                logical_device_status[ld] = 'ok'
                _add_lns_total(len(ln_list))
                for ln_full in ln_list:
                    if '/' in ln_full:
                        ln_inst = ln_full.split('/')[-1]
                    elif ':' in ln_full:
                        ln_inst = ln_full.split(':')[-1]
                    else:
                        ln_inst = ln_full
                    _set_current_ln(ln_inst)
                    try:
                        details = await _aget_ln_details(ld, ln_inst, acsi_client, ws_info)
                        logical_node_details[f"{ld}/{ln_inst}"] = details
                    except Exception as e:
                        print(f"Failed to get details for {ld}/{ln_inst}: {e}")
                        #pass
                    finally:
                        _inc_ln_done()
            except Exception as e:
                logger.error(f"Failed to get directory for {ld}: {e}")

                logical_device_map[ld] = []
                logical_device_status[ld] = 'error'
            finally:
                _finish_ld()

        try:
            ld_list = await acsi_client.get_server_directory(ws_info, None, None)
            if not isinstance(ld_list, list):
                raise RuntimeError('unexpected-server-directory')
            _init_progress(ld_list)
            for ld in ld_list:
                await _process_ld(ld)
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
        except Exception as exc:
            rti_so._log_action(f"Get model failed (outer): {exc}", "error")
            logger.exception("Unhandled outer exception in api_model")
            raise HTTPException(
                status_code=500,
                detail={"error": str(exc), "traceback": traceback.format_exc()}
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
                    #client._log_action(
                    #    "Client readvalue failed: instanceNotAvailable",
                    #    "warn",
                    #   detail={"objRef": obj_ref, "fc": fc}
                    #)
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404
                    )

                #client._log_action(
                #    "Client readvalue",
                #    detail={
                #       "objRef": obj_ref,
                #        "value": result.get("value"),
                #    },
                #)
                return {
                    "ok": True,
                    "success": True,
                    "objRef": obj_ref,
                    "value": result.get("dataDefinition"),
                }

            except FuturesTimeoutError:
                #client._log_action(
                #    "Client readvalue timeout",
                #    "warn",
                #    detail={"objRef": obj_ref},
                #)
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"},
                    status_code=504
                )
            except ValueError as exc:
                #client._log_action(f"Client readvalue failed: {exc}", "warn")
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                #client._log_action(f"Client readvalue failed: {exc}", "error")
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
            obj_ref = request.objRef

            cp = request.cp
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
            obj_ref = request.objRef

            cp = request.cp
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

            # obj_ref = request.objRef
            # fc = request.fc

            if not obj_ref:
                # client._log_action("Client readvalue rejected: missing objRef", "warn")
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
                    # client._log_action(
                    #    "Client readvalue failed: instanceNotAvailable",
                    #    "warn",
                    #   detail={"objRef": obj_ref, "fc": fc}
                    # )
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404
                    )

                # client._log_action(
                #    "Client readvalue",
                #    detail={
                #       "objRef": obj_ref,
                #        "value": result.get("value"),
                #    },
                # )
                return {
                    "ok": True,
                    "success": True,
                    "objRef": obj_ref,
                    "value": result.get("value"),
                }

            except FuturesTimeoutError:
                # client._log_action(
                #    "Client readvalue timeout",
                #    "warn",
                #    detail={"objRef": obj_ref},
                # )
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"},
                    status_code=504
                )
            except ValueError as exc:
                # client._log_action(f"Client readvalue failed: {exc}", "warn")
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                # client._log_action(f"Client readvalue failed: {exc}", "error")
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
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

    return router, rti_so

if __name__ == "__main__":
    import uvicorn
    import os
    app = create_fastapi_app()
    port = int(os.getenv("PORT", "5003"))
    uvicorn.run(app, host="0.0.0.0", port=port)

