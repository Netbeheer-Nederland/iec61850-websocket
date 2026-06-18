
"""Backend for Frontend (BFF) endpoint providing REST API for ACSI client control.

This module exposes REST API endpoints that interact with the ACSI client,
handling connection management, value operations, and IED model access.
"""

from __future__ import annotations

import os
import logging
import traceback
import asyncio
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any, Dict, Optional
from fastapi import FastAPI, APIRouter, Request, HTTPException, status
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
    fc: Optional[str] = Field(
        default=None,
        description="Functional constraint (ST, MX, CO, etc.) - optional",
        json_schema_extra={"example": "ST"}
    )

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
    value_type: Optional[str] = Field(
        default=None,
        description="Optional value type hint for coercion",
        json_schema_extra={"example": "BOOLEAN"}
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "objRef": "LD0/LLN0$ST$Mod",
            "fc": "ST",
            "value": "ON",
            "value_type": "BOOLEAN"
        }
    })

def create_bff_router() -> tuple[APIRouter, ACSIClient]:
    """Create a FastAPI router for the ACSI client BFF API.

    Returns:
        Tuple of (APIRouter, ACSIClient instance)
    """
    router = APIRouter(
        prefix="/api",
        tags=["IEC61850-WS Client"],
        responses={404: {"description": "Not found"}, 500: {"description": "Internal server error"}}
    )
    client = ACSIClient()

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

    async def _aget_ln_details(ld_inst: str, ln_inst: str, client: Any, ws_info) -> Dict[str, Any]:
        """Async variant used internally for concurrent model assembly.
        Sequential (more stable) fetch of dataObject, brcb, urcb, dataset directories.
        """
        async def _safe(coro):
            try:
                return await coro
            except Exception:
                return None

        do_items = await _safe(_invoke_ln_directory_async(client, ws_info, ld_inst, ln_inst, 'dataObject'))
        brcb_items = await _safe(_invoke_ln_directory_async(client, ws_info, ld_inst, ln_inst, 'brcb'))
        urcb_items = await _safe(_invoke_ln_directory_async(client, ws_info, ld_inst, ln_inst, 'urcb'))
        dataset_items = await _safe(_invoke_ln_directory_async(client, ws_info, ld_inst, ln_inst, 'dataset'))

        # Parse data objects / attributes
        data_objects = []
        data_attributes = []

        # Extract the list of data object names
        do_list = []
        if isinstance(do_items, dict):
            do_list = do_items.get('dataObjects', do_items.get('instanceNames', [])) or []
            data_attributes = do_items.get('dataAttributes', []) or []
        elif isinstance(do_items, list):
            do_list = do_items

        # Fetch CDC for each data object
        if do_list:
            lock = client.runtime.invoke_lock

            for do_name in do_list:
                defn = None
                try:
                    obj_ref = f"{ld_inst}/{ln_inst}.{do_name}"
                    if lock is None:
                        defn = await client.get_data_definition(obj_ref, ws_info, None, None)
                    else:
                        async with lock:
                            defn = await client.get_data_definition(obj_ref, ws_info, None, None)

                    cdc = None
                    if isinstance(defn, dict):
                        cdc = defn.get('cdc')
                    data_objects.append({'name': do_name, 'cdc': cdc})
                except Exception:
                    data_objects.append({'name': do_name, 'cdc': None})

        # Parse RCBs and fetch their values
        def _extract_rcb(entries, kind):
            out = []
            if isinstance(entries, list):
                out = entries
            elif isinstance(entries, dict):
                out = entries.get('instanceNames') or entries.get('reportControlBlocks') or []
            return [{'name': ref, 'type': kind} for ref in out]

        rcbs = []
        lock = client.runtime.invoke_lock

        # Process BRCBs
        brcb_list = _extract_rcb(brcb_items, 'BRCB')
        for rcb_info in brcb_list:
            rcb_name = rcb_info['name']
            rcb_ref = f"{ld_inst}/{ln_inst}.{rcb_name}"
            rcb_values = None
            try:
                if lock is None:
                    rcb_values = await client.get_BRCB_values(rcb_ref, ws_info, None, None)
                else:
                    async with lock:
                        rcb_values = await client.get_BRCB_values(rcb_ref, ws_info, None, None)

                rpt_ena = False
                if isinstance(rcb_values, dict):
                    rpt_ena = rcb_values.get('RptEna', False)
                    rcb_values = _convert_bytes_to_hex(rcb_values)

                rcbs.append({
                    'name': rcb_name,
                    'type': 'BRCB',
                    'values': rcb_values,
                    'enabled': rpt_ena
                })
            except Exception:
                rcbs.append({
                    'name': rcb_name,
                    'type': 'BRCB',
                    'values': None,
                    'enabled': False
                })

        # Process URCBs
        urcb_list = _extract_rcb(urcb_items, 'URCB')
        for rcb_info in urcb_list:
            rcb_name = rcb_info['name']
            rcb_ref = f"{ld_inst}/{ln_inst}.{rcb_name}"
            rcb_values = None
            try:
                if lock is None:
                    rcb_values = await client.get_URCB_values(rcb_ref, ws_info, None, None)
                else:
                    async with lock:
                        rcb_values = await client.get_URCB_values(rcb_ref, ws_info, None, None)

                rpt_ena = False
                if isinstance(rcb_values, dict):
                    rpt_ena = rcb_values.get('RptEna', False)
                    rcb_values = _convert_bytes_to_hex(rcb_values)

                rcbs.append({
                    'name': rcb_name,
                    'type': 'URCB',
                    'values': rcb_values,
                    'enabled': rpt_ena
                })
            except Exception:
                rcbs.append({
                    'name': rcb_name,
                    'type': 'URCB',
                    'values': None,
                    'enabled': False
                })

        # Parse datasets
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

    def _invoke_ln_directory(client, ws_info, ld_inst, ln_inst, mode):
        """Return coroutine that performs directory call under a lock."""
        async def _coro():
            lock = client.runtime.invoke_lock
            if lock is None:
                return await client.get_logical_node_directory(ld_inst, ln_inst, mode, ws_info, None, None)
            async with lock:
                return await client.get_logical_node_directory(ld_inst, ln_inst, mode, ws_info, None, None)
        return _coro()

    def _invoke_ln_directory_async(client, ws_info, ld_inst, ln_inst, mode):
        return _invoke_ln_directory(client, ws_info, ld_inst, ln_inst, mode)

    # ================ Background Model Build ================
    async def _abuild_full_model() -> None:
        """Build full model sequentially with progress updates."""
        endpoint = client.runtime.endpoint
        loop = client.runtime.loop
        if not client or not endpoint or not loop or not client.runtime.client.is_connected:
            raise RuntimeError('not-connected')
        ws_info = endpoint.get_websocket_info(client)
        if ws_info is None:
            raise RuntimeError('no-websocket-info')

        logical_node_details = {}
        logical_device_map = {}
        logical_device_status = {}

        def _init_progress(ld_list):
            with client.runtime.lock:
                client.runtime.model_progress = {
                    'lds_total': len(ld_list), 'lds_done': 0,
                    'lns_total': 0, 'lns_done': 0,
                    'current_ld': None, 'current_ln': None
                }

        def _set_current_ld(ld):
            with client.runtime.lock:
                if client.runtime.model_progress:
                    client.runtime.model_progress['current_ld'] = ld

        def _add_lns_total(n):
            if n:
                with client.runtime.lock:
                    if client.runtime.model_progress:
                        client.runtime.model_progress['lns_total'] += n

        def _set_current_ln(ln):
            with client.runtime.lock:
                if client.runtime.model_progress:
                    client.runtime.model_progress['current_ln'] = ln

        def _inc_ln_done():
            with client.runtime.lock:
                if client.runtime.model_progress:
                    client.runtime.model_progress['lns_done'] += 1

        def _finish_ld():
            with client.runtime.lock:
                if client.runtime.model_progress:
                    client.runtime.model_progress['lds_done'] += 1
                    client.runtime.model_progress['current_ln'] = None

        async def _process_ld(ld):
            try:
                _set_current_ld(ld)
                ln_list = await client.runtime.client.get_logical_device_directory(ld, ws_info, None, None)
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
                        details = await _aget_ln_details(ld, ln_inst, client, ws_info)
                        logical_node_details[f"{ld}/{ln_inst}"] = details
                    except Exception:
                        pass
                    finally:
                        _inc_ln_done()
            except Exception:
                logical_device_map[ld] = []
                logical_device_status[ld] = 'error'
            finally:
                _finish_ld()

        try:
            ld_list = await client.runtime.client.get_server_directory(ws_info, None, None)
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
            with client.runtime.lock:
                client.runtime.model_data = model
                client.runtime.model_status = 'ready'
                client.runtime.model_error = None
        except Exception as e:
            with client.runtime.lock:
                client.runtime.model_status = 'error'
                client.runtime.model_error = str(e)
            raise

    def _start_model_build_if_needed():
        """Schedule background model build if idle or error."""
        with client.runtime.lock:
            status = client.runtime.model_status
            if status in ('ready', 'building'):
                return status
            client.runtime.model_data = None
            client.runtime.model_error = None
            client.runtime.model_status = 'building'

        loop = client.runtime.loop
        if not loop:
            with client.runtime.lock:
                client.runtime.model_status = 'error'
                client.runtime.model_error = 'no-loop'
            return 'error'

        try:
            client._log_action("Scheduling model build", "info")
            fut = asyncio.run_coroutine_threadsafe(_abuild_full_model(), loop)
            client._log_action("Model build scheduled", "info")
        except Exception as e:
            with client.runtime.lock:
                client.runtime.model_status = 'error'
                client.runtime.model_error = str(e)
            client._log_action(f"Failed to schedule model build: {e}", "error")
            return 'error'

        with client.runtime.lock:
            client.runtime.model_task = fut

        def _on_model_task_done(future):
            try:
                exc = future.exception()
            except Exception:
                exc = None
            with client.runtime.lock:
                try:
                    client.runtime.model_task = None
                except Exception:
                    pass
                if exc is not None:
                    client.runtime.model_status = 'error'
                    client.runtime.model_error = str(exc)
                    client._log_action(f"Model build failed: {exc}", "error")
                else:
                    if client.runtime.model_status != 'ready':
                        client.runtime.model_status = 'ready'
                        client.runtime.model_error = None
                    client._log_action("Model build completed", "info")

        try:
            fut.add_done_callback(_on_model_task_done)
        except Exception as e:
            client._log_action(f"Failed to attach model task callback: {e}", "warn")

        return 'building'

    # ==================== Route Handlers ====================

    @router.get(
        "/status",
        summary="Get Client Status",
        description="Returns the current operational status of the IEC61850 client.",
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
            return client.get_status()
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.get(
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
    def api_connections():
        """Get connection information.

        Returns:
            dict: {
                "ok": True,
                "status": str,
                "connected": bool,
                "server_role": "ACSI_Client",
                "ws_mode": "passive",
                "connection": {
                    "peer_address": str | None,
                    "peer_port": int | None,
                    "local_role": "ACSI_Client",
                    "ws_mode": "passive",
                    "remote_role": "ACSI_Server",
                    "cp": str
                } | None
            }
        """
        try:
            endpoint = client.runtime.endpoint
            connection_info = {
                "ok": True,
                "status": client.runtime.status,
                "connected": client.runtime.status == "connected",
                "server_role": "ACSI_Client",
                "ws_mode": "passive",
                "connection": None,
            }

            if endpoint is not None and client.runtime.client is not None:
                ws_info = endpoint.get_websocket_info(client.runtime.client)
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
                        "local_role": "ACSI_Client",
                        "ws_mode": "passive",
                        "remote_role": "ACSI_Server",
                        "cp": client.runtime.cp,
                    }

            return connection_info
        except Exception as exc:
            client._log_action(f"Get connections failed: {exc}", "error")
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
                "acsi_role": "ACSI_Client",
                "ws_mode": "passive"
            }
        """
        return {
            "ok": True,
            "acsi_role": "ACSI_Client",
            "ws_mode": "passive",
        }

    @router.post(
        "/connect",
        summary="Connect to Server",
        description="Establishes a WebSocket connection to an IEC61850 server. Must be called before any data operations.",
        response_description="Connection confirmation",
        responses={
            200: {"description": "Connection initiated successfully"},
            400: {"description": "Invalid parameters (port must be integer)"},
            500: {"description": "Connection failed"}
        },
        tags=["Connection Management"]
    )
    def api_connect(request: ConnectRequest):
        """Connect to an IEC61850 WebSocket server.

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
            cp = request.cp.lower()

            try:
                client.connect(host, port, cp)
                return {"ok": True, "status": "connecting", "host": host, "port": port, "cp": cp}
            except (ValueError, RuntimeError) as exc:
                client._log_action(f"Connect rejected: {exc}", "warn")
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
        except Exception as exc:
            client._log_action(f"Connect failed: {exc}", "error")
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.post(
        "/disconnect",
        summary="Disconnect from Server",
        description="Closes the current WebSocket connection to the IEC61850 server.",
        response_description="Disconnection confirmation",
        responses={
            200: {"description": "Disconnection status"},
            500: {"description": "Error during disconnection"}
        },
        tags=["Connection Management"]
    )
    def api_disconnect():
        """Disconnect from the IEC61850 WebSocket server.

        Returns:
            dict: {
                "ok": True,
                "status": str  # "disconnected" or "disconnecting"
            }

        Raises:
            HTTPException 500: If error occurs during disconnection
        """
        try:
            status = client.runtime.status
            if status in (None, "disconnected"):
                return {"ok": True, "status": "disconnected"}

            try:
                client.disconnect()
                current = client.runtime.status
                if current in ("disconnecting", "connected"):
                    return {"ok": True, "status": "disconnecting"}
                return {"ok": True, "status": "disconnected"}
            except Exception as exc:
                current = client.runtime.status
                if current in ("disconnecting", "disconnected"):
                    return {"ok": True, "status": current}
                client._log_action(f"Disconnect failed: {exc}", "error")
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
    def api_model():
        """Get the IED model tree from the connected server.

        The model is built asynchronously on first request. Subsequent requests
        return the cached model until it needs to be refreshed.

        Returns:
            dict: {
                "status": str,  # "ready", "building", or "error"
                "model": dict | None  # Complete model data when ready
                "progress": dict | None  # Progress info when building
            }
        """
        try:
            loop = client.runtime.loop
            if loop is None or not getattr(loop, "is_running", lambda: False)():
                return JSONResponse(
                    content={"ok": False, "error": "client-not-connected"},
                    status_code=503
                )

            with client.runtime.lock:
                status = client.runtime.model_status
                data = client.runtime.model_data
                error = client.runtime.model_error

            if status == 'ready' and data:
                return {'status': 'ready', 'model': data}
            if status == 'error':
                return JSONResponse(
                    content={'status': 'error', 'error': error},
                    status_code=500
                )

            if status == 'idle':
                start_result = _start_model_build_if_needed()
                if start_result == 'error':
                    client._log_action('Model build scheduling failed', 'error')
                    return JSONResponse(
                        content={'status': 'error', 'error': client.runtime.model_error},
                        status_code=503
                    )

            with client.runtime.lock:
                progress = client.runtime.model_progress
            return {'status': 'building', 'progress': progress}

        except Exception as exc:
            client._log_action(f"Get model failed (outer): {exc}", "error")
            logger.exception("Unhandled outer exception in api_model")
            tb = traceback.format_exc()
            return JSONResponse(
                content={"ok": False, "error": str(exc), "traceback": tb},
                status_code=500
            )

    @router.get(
        "/actions",
        summary="Get Action Log",
        description="Retrieves the logged client actions for debugging and auditing. Actions include connection events, model builds, and data operations.",
        response_description="List of logged actions",
        responses={
            200: {"description": "Action log returned successfully"},
            500: {"description": "Error retrieving actions"}
        },
        tags=["Logging"]
    )
    def api_actions():
        """Get logged client actions.

        Returns:
            dict: { "actions": list[dict] }
        """
        try:
            return {"actions": client.get_actions()}
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.post(
        "/actions/clear",
        summary="Clear Action Log",
        description="Clears all logged client actions.",
        response_description="Clear confirmation",
        responses={
            200: {"description": "Actions cleared successfully"},
            500: {"description": "Error clearing actions"}
        },
        tags=["Logging"]
    )
    def api_actions_clear():
        """Clear action log.

        Returns:
            dict: { "ok": True }
        """
        try:
            client.clear_actions()
            return {"ok": True}
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

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
    def api_messages():
        """Get logged protocol messages.

        Returns:
            dict: { "messages": list[dict] }
        """
        try:
            return {"messages": client.get_messages()}
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.post(
        "/messages/clear",
        summary="Clear Message Log",
        description="Clears all logged protocol messages.",
        response_description="Clear confirmation",
        responses={
            200: {"description": "Messages cleared successfully"},
            500: {"description": "Error clearing messages"}
        },
        tags=["Logging"]
    )
    def api_messages_clear():
        """Clear message log.

        Returns:
            dict: { "ok": True }
        """
        try:
            client.clear_messages()
            return {"ok": True}
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.post(
        "/readvalue",
        summary="Read Value",
        description="Reads a value from the connected IEC61850 server. The client must be connected before calling this endpoint.",
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
    def api_read_value(request: ReadvalueRequest):
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

            if not obj_ref:
                client._log_action("Client readvalue rejected: missing objRef", "warn")
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400
                )

            if client.runtime.client is None:
                client._log_action(
                    "Client readvalue rejected: not connected",
                    "warn",
                    detail={"objRef": obj_ref, "fc": fc},
                )
                return JSONResponse(
                    content={"ok": False, "error": "Client is not connected"},
                    status_code=503
                )

            try:
                result = client.invoke_on_runtime_loop(
                    client.read_value(obj_ref, fc), timeout=10
                )

                if result is None:
                    client._log_action(
                        "Client readvalue failed: instanceNotAvailable",
                        "warn",
                        detail={"objRef": obj_ref, "fc": fc}
                    )
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404
                    )

                client._log_action(
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
                client._log_action(
                    "Client readvalue timeout",
                    "warn",
                    detail={"objRef": obj_ref, "fc": fc},
                )
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"},
                    status_code=504
                )
            except ValueError as exc:
                client._log_action(f"Client readvalue failed: {exc}", "warn")
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                client._log_action(f"Client readvalue failed: {exc}", "error")
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
        "/writevalue",
        summary="Write Value",
        description="Writes a value to the connected IEC61850 server. The client must be connected before calling this endpoint.",
        response_description="Write value confirmation",
        responses={
            200: {"description": "Value written successfully"},
            400: {"description": "Missing parameters (objRef, fc, or value)"},
            403: {"description": "Client is not connected"},
            500: {"description": "Error writing value"}
        },
        tags=["Data Access"]
    )
    def api_write_value(request: WriteValueRequest):
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
            value_type = request.value_type

            if not obj_ref:
                client._log_action("Client writevalue rejected: missing objRef", "warn")
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400
                )

            if not fc:
                client._log_action("Client writevalue rejected: missing fc", "warn")
                return JSONResponse(
                    content={"ok": False, "error": "fc is required"},
                    status_code=400
                )

            if value is None:
                client._log_action(
                    "Client writevalue rejected: missing value",
                    "warn",
                    detail={"objRef": obj_ref, "fc": fc}
                )
                return JSONResponse(
                    content={"ok": False, "error": "value is required"},
                    status_code=400
                )

            if client.runtime.client is None:
                client._log_action(
                    "Client writevalue rejected: not connected",
                    "warn",
                    detail={"objRef": obj_ref, "fc": fc, "value": value},
                )
                return JSONResponse(
                    content={"ok": False, "error": "Client is not connected"},
                    status_code=503
                )

            try:
                result = client.invoke_on_runtime_loop(
                    client.write_value(obj_ref, value, fc, value_type), timeout=10
                )
                return {
                    "ok": True,
                    "success": True,
                    "objRef": obj_ref,
                    "fc": fc,
                    "value": result.get("value"),
                }
            except FuturesTimeoutError:
                client._log_action(
                    "Client writevalue timeout",
                    "warn",
                    detail={"objRef": obj_ref},
                )
                return JSONResponse(
                    content={"ok": False, "error": "write timeout"},
                    status_code=504
                )
            except ValueError as exc:
                client._log_action(f"Client writevalue failed: {exc}", "warn")
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                client._log_action(f"Client writevalue failed: {exc}", "error")
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
            path = f"/api{route.path}"
            methods = list(route.methods)

            body_schema = None
            if hasattr(route, 'body_field') and route.body_field:
                try:
                    model = route.body_field.annotation
                    if model is not Any:
                        adapter = TypeAdapter(model)
                        body_schema = adapter.json_schema()
                except Exception:
                    body_schema = None

            routes.append({
                "path": path,
                "methods": methods,
                "endpoint": route.name,
                "body_schema": body_schema
            })

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
            500: {"description": "Service is unhealthy"}
        },
        tags=["Health"]
    )
    def api_health():
        """Generic health endpoint used by external discovery.

        Returns:
            dict: {
                "status": "ok",
                "service": "SO",
                "server": {
                    "status": "ok",
                    "host": "localhost",
                    "port": 8080
                }
            }
        """
        try:
            return {
                "status": "ok",
                "service": "SO",
                "server": {
                    "status": "ok",
                    "host": "localhost",
                    "port": 8080,
                },
            }
        except Exception as exc:
            return JSONResponse(
                content={"status": "degraded", "service": "SO", "error": str(exc)},
                status_code=500
            )

    @router.get(
        "/internal/model/status",
        summary="Internal Model Status",
        description="Internal diagnostic endpoint exposing model build state for debugging purposes.",
        response_description="Model build state",
        responses={
            200: {"description": "Model build status returned"},
            500: {"description": "Error retrieving status"}
        },
        tags=["Diagnostics"]
    )
    def _internal_model_status():
        """Internal diagnostic endpoint exposing model build state.

        Returns:
            dict: {
                "ok": True,
                "model_status": str,
                "model_progress": dict | None,
                "model_error": str | None,
                "model_task_present": bool,
                "loop_running": bool,
                "client_connected": bool
            }
        """
        try:
            with client.runtime.lock:
                status = getattr(client.runtime, 'model_status', None)
                progress = getattr(client.runtime, 'model_progress', None)
                error = getattr(client.runtime, 'model_error', None)
                task = getattr(client.runtime, 'model_task', None)
                loop = getattr(client.runtime, 'loop', None)
                client_conn = getattr(client.runtime, 'client', None)

            loop_running = False
            try:
                loop_running = bool(loop and getattr(loop, 'is_running', lambda: False)())
            except Exception:
                loop_running = False

            client_connected = False
            try:
                client_connected = bool(client_conn and getattr(client_conn, 'is_connected', False))
            except Exception:
                client_connected = False

            return {
                'ok': True,
                'model_status': status,
                'model_progress': progress,
                'model_error': error,
                'model_task_present': task is not None,
                'loop_running': loop_running,
                'client_connected': client_connected,
            }
        except Exception as exc:
            client._log_action(f"Internal model status failed: {exc}", 'error')
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    return router, client

def create_fastapi_app() -> FastAPI:
    """Create and configure the FastAPI application for IEC61850 client BFF."""
    app = FastAPI(
        title="IEC61850 Client WS Client",
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
                "description": "Get client status, connections, and properties"
            },
            {
                "name": "Connection Management",
                "description": "Connect to and disconnect from IEC61850 servers"
            },
            {
                "name": "Model Access",
                "description": "Retrieve and explore IED models from connected servers"
            },
            {
                "name": "Data Access",
                "description": "Read and write values to/from connected servers"
            },
            {
                "name": "Logging",
                "description": "View and clear action and message logs"
            },
            {
                "name": "Health",
                "description": "Service health checks and status monitoring"
            },
            {
                "name": "Discovery",
                "description": "API introspection and endpoint discovery"
            },
            {
                "name": "Diagnostics",
                "description": "Internal diagnostic endpoints"
            }
        ]
    )
    router, _client = create_bff_router()
    app.include_router(router)
    app.state.client = _client
    return app

if __name__ == "__main__":
    import uvicorn
    app = create_fastapi_app()
    port = int(os.getenv("PORT", "5003"))
    uvicorn.run(app, host="0.0.0.0", port=port)
