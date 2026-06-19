"""Backend for Frontend (BFF) endpoint providing REST API for ACSI client control.

This module exposes FastAPI endpoints that interact with the ACSI client,
handling connection management and value operations.
"""

from __future__ import annotations

from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any, Dict
import logging
import traceback
import asyncio

from fastapi import FastAPI, APIRouter, Request, HTTPException, status
from fastapi.responses import JSONResponse

from acsi_client import ACSIClient

logger = logging.getLogger(__name__)

def create_fastapi_app() -> FastAPI:
    """Create and configure the FastAPI application for IEC61850 client BFF."""
    app = FastAPI(
        title="IEC61850 Client WS Server",
        description="Backend for Frontend (BFF) endpoint providing REST API for ACSI client control. "
                    "This service manages IEC61850 WebSocket client connections, data access, "
                    "model retrieval, and provides comprehensive monitoring capabilities.",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        openapi_tags=[
            {"name": "Client Status", "description": "Get client status, connections, and properties"},
            {"name": "Connection Management", "description": "Connect to and disconnect from IEC61850 servers"},
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
        tags=["IEC61850-Client"],
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
        """Async variant used internally for concurrent model assembly."""
        async def _safe(coro):
            try:
                return await coro
            except Exception:
                return None

        do_items = await _safe(_invoke_ln_directory_async(client, ws_info, ld_inst, ln_inst, 'dataObject'))
        brcb_items = await _safe(_invoke_ln_directory_async(client, ws_info, ld_inst, ln_inst, 'brcb'))
        urcb_items = await _safe(_invoke_ln_directory_async(client, ws_info, ld_inst, ln_inst, 'urcb'))
        dataset_items = await _safe(_invoke_ln_directory_async(client, ws_info, ld_inst, ln_inst, 'dataset'))

        data_objects = []
        data_attributes = []

        do_list = []
        if isinstance(do_items, dict):
            do_list = do_items.get('dataObjects', do_items.get('instanceNames', [])) or []
            data_attributes = do_items.get('dataAttributes', []) or []
        elif isinstance(do_items, list):
            do_list = do_items

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

        def _extract_rcb(entries, kind):
            out = []
            if isinstance(entries, list):
                out = entries
            elif isinstance(entries, dict):
                out = entries.get('instanceNames') or entries.get('reportControlBlocks') or []
            return [{'name': ref, 'type': kind} for ref in out]

        rcbs = []
        lock = client.runtime.invoke_lock

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
                    rcb_values = await client.get_URCB_values(rcb_ref, ws_info, None, None)
                else:
                    async with lock:
                        rcb_values = await client.get_URCB_values(rcb_ref, ws_info, None, None)
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
            endpoint = client.runtime.endpoint
            connection_info = {
                "ok": True,
                "status": client.runtime.status,
                "connected": client.runtime.status == "connected",
                "server_role": "ACSI-Client",
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
                        "local_role": "ACSI-Client",
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
    async def api_connect(request: Request):
        """Connect to an IEC 61850 WebSocket server."""
        try:
            body = await request.json()
            host = str(body.get("host", "0.0.0.0"))
            raw_port = body.get("port", 8765)
            cp = str(body.get("cp", "cp1")).lower()

            try:
                port = int(raw_port)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"Invalid port value: {raw_port!r}")

            try:
                client.connect(host, port, cp)
                return {"ok": True, "status": "connecting", "host": host, "port": port, "cp": cp}
            except (ValueError, RuntimeError) as exc:
                client._log_action(f"Connect rejected: {exc}", "warn")
                raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            client._log_action(f"Connect failed: {exc}", "error")
            raise HTTPException(status_code=400, detail=str(exc))

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
                raise HTTPException(status_code=500, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

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
    async def api_model(request: Request):
        """Get the IED model tree from the connected server."""
        try:
            loop = client.runtime.loop
            if loop is None or not getattr(loop, "is_running", lambda: False)():
                raise HTTPException(status_code=503, detail="client-not-connected")

            with client.runtime.lock:
                status = client.runtime.model_status
                data = client.runtime.model_data
                error = client.runtime.model_error
            if status == 'ready' and data:
                return {'status': 'ready', 'model': data}
            if status == 'error':
                raise HTTPException(status_code=500, detail=error)
            if status == 'idle':
                start_result = _start_model_build_if_needed()
                if start_result == 'error':
                    client._log_action('Model build scheduling failed', 'error')
                    raise HTTPException(status_code=503, detail=client.runtime.model_error)
            with client.runtime.lock:
                progress = client.runtime.model_progress
            return {'status': 'building', 'progress': progress}
        except Exception as exc:
            client._log_action(f"Get model failed (outer): {exc}", "error")
            logger.exception("Unhandled outer exception in api_model")
            raise HTTPException(
                status_code=500,
                detail={"error": str(exc), "traceback": traceback.format_exc()}
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
    async def api_actions(request: Request):
        """Get logged client actions."""
        try:
            return {"actions": client.get_actions()}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

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
    async def api_actions_clear(request: Request):
        """Clear action log."""
        try:
            client.clear_actions()
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
            return {"messages": client.get_messages()}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

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
    async def api_messages_clear(request: Request):
        """Clear message log."""
        try:
            client.clear_messages()
            return {"ok": True}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

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
    async def api_read_value(request: Request):
        """Read a value from the connected server."""
        try:
            data = await request.json() or {}
            obj_ref = data.get("objRef")
            fc = data.get("fc")

            if not obj_ref:
                client._log_action("Client readvalue rejected: missing objRef", "warn")
                raise HTTPException(status_code=400, detail="objRef is required")

            if client.runtime.client is None:
                client._log_action("Client readvalue rejected: not connected", "warn", detail={"objRef": obj_ref, "fc": fc})
                raise HTTPException(status_code=503, detail="Client is not connected")

            try:
                result = client.invoke_on_runtime_loop(client.read_value(obj_ref, fc), timeout=10)

                if result is None:
                    client._log_action("Client readvalue failed: instanceNotAvailable", "warn", detail={"objRef": obj_ref, "fc": fc})
                    raise HTTPException(status_code=404, detail="instanceNotAvailable")

                client._log_action("Client readvalue", detail={"objRef": obj_ref, "value": result.get("value")})
                return {"ok": True, "success": True, "objRef": obj_ref, "value": result.get("value")}
            except FuturesTimeoutError:
                client._log_action("Client readvalue timeout", "warn", detail={"objRef": obj_ref, "fc": fc})
                raise HTTPException(status_code=504, detail="read timeout")
            except ValueError as exc:
                client._log_action(f"Client readvalue failed: {exc}", "warn")
                raise HTTPException(status_code=404, detail=str(exc))
            except Exception as exc:
                client._log_action(f"Client readvalue failed: {exc}", "error")
                raise HTTPException(status_code=500, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

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
    async def api_write_value(request: Request):
        """Write a value to the connected server."""
        try:
            data = await request.json() or {}
            obj_ref = data.get("objRef")
            fc = data.get("fc")
            value = data.get("value")
            value_type = data.get("value_type")

            if not obj_ref:
                client._log_action("Client writevalue rejected: missing objRef", "warn")
                raise HTTPException(status_code=400, detail="objRef is required")
            if not fc:
                client._log_action("Client writevalue rejected: missing fc", "warn")
                raise HTTPException(status_code=400, detail="fc is required")
            if value is None:
                client._log_action("Client writevalue rejected: missing value", "warn", detail={"objRef": obj_ref, "fc": fc})
                raise HTTPException(status_code=400, detail="value is required")
            if client.runtime.client is None:
                client._log_action("Client writevalue rejected: not connected", "warn", detail={"objRef": obj_ref, "fc": fc, "value": value})
                raise HTTPException(status_code=503, detail="Client is not connected")

            try:
                result = client.invoke_on_runtime_loop(client.write_value(obj_ref, value, fc, value_type), timeout=10)
                return {"ok": True, "success": True, "objRef": obj_ref, "fc": fc, "value": result.get("value")}
            except FuturesTimeoutError:
                client._log_action("Client writevalue timeout", "warn", detail={"objRef": obj_ref})
                raise HTTPException(status_code=504, detail="write timeout")
            except ValueError as exc:
                client._log_action(f"Client writevalue failed: {exc}", "warn")
                raise HTTPException(status_code=404, detail=str(exc))
            except Exception as exc:
                client._log_action(f"Client writevalue failed: {exc}", "error")
                raise HTTPException(status_code=500, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

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
    async def _internal_model_status(request: Request):
        """Internal diagnostic endpoint exposing model build state."""
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
            raise HTTPException(status_code=500, detail=str(exc))

    return router, client

if __name__ == "__main__":
    import uvicorn
    import os
    app = create_fastapi_app()
    port = int(os.getenv("PORT", "5003"))
    uvicorn.run(app, host="0.0.0.0", port=port)