"""Backend for Frontend (BFF) endpoint providing REST API for ACSI client control.

This module exposes Flask endpoints that interact with the ACSI client,
handling connection management and value operations.
"""

from __future__ import annotations

from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any, Dict
import logging
import traceback
import asyncio
from flask import Blueprint, Flask, jsonify, request

from acsi_client import ACSIClient

logger = logging.getLogger(__name__)


def create_bff_blueprint() -> tuple[Blueprint, ACSIClient]:
    """Create a Flask blueprint for the ACSI client BFF API.

    Returns:
        Tuple of (Flask Blueprint, ACSIClient instance)
    """
    app = Blueprint("iec61850_client", __name__)
    client = ACSIClient()

    # ==================== Route Handlers ====================

    @app.before_request
    def log_api_calls() -> None:
        """Log API calls for debugging."""
        path = request.path or ""
        if not path.startswith("/api/iec61850client/"):
            return

        if request.method == "POST":
            payload = request.get_json(silent=True) or {}
            detail = {
                "path": path,
                "host": payload.get("host"),
                "port": payload.get("port"),
                "objRef": payload.get("objRef"),
                "value": payload.get("value"),
            }
            client._log_action(f"API POST {path}", detail=detail)
            return

        if request.method == "GET" and path == "/api/iec61850client/status":
            signature = (
                client.runtime.status,
                client.runtime.host,
                client.runtime.port,
                client.runtime.error,
            )
            if signature != client.runtime.last_status_log_signature:
                client.runtime.last_status_log_signature = signature
                client._log_action(
                    "API GET /api/iec61850client/status",
                    detail={
                        "status": client.runtime.status,
                        "host": client.runtime.host,
                        "port": client.runtime.port,
                        "error": client.runtime.error,
                    },
                )

    @app.get("/api/iec61850client/status")
    def api_status():
        """Get current client status."""
        try:
            return jsonify(client.get_status())
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.get("/api/iec61850client/connections")
    def api_connections():
        """Get connection information."""
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

            return jsonify(connection_info)
        except Exception as exc:
            client._log_action(f"Get connections failed: {exc}", "error")
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.get("/api/iec61850client/properties")
    def api_properties():
        """Get connection information."""
        return jsonify({
            "ok": True,
            "acsi_role": "ACSI_Client",
            "ws_mode": "passive",
        })

    @app.post("/api/iec61850client/connect")
    def api_connect():
        """Connect to an IEC 61850 WebSocket server."""
        try:
            body = request.get_json(silent=True) or {}
            host = str(body.get("host", "localhost"))
            raw_port = body.get("port", 8765)
            cp = str(body.get("cp", "cp1")).lower()

            try:
                port = int(raw_port)
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": f"Invalid port value: {raw_port!r}"}), 400

            try:
                client.connect(host, port, cp)
                return jsonify({"ok": True, "status": "connecting", "host": host, "port": port, "cp": cp})
            except (ValueError, RuntimeError) as exc:
                client._log_action(f"Connect rejected: {exc}", "warn")
                return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            client._log_action(f"Connect failed: {exc}", "error")
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.post("/api/iec61850client/disconnect")
    def api_disconnect():
        """Disconnect from the IEC 61850 WebSocket server."""
        try:
            status = client.runtime.status
            if status in (None, "disconnected"):
                return jsonify({"ok": True, "status": "disconnected"})

            try:
                client.disconnect()
                current = client.runtime.status
                if current in ("disconnecting", "connected"):
                    return jsonify({"ok": True, "status": "disconnecting"})
                return jsonify({"ok": True, "status": "disconnected"})
            except Exception as exc:
                current = client.runtime.status
                if current in ("disconnecting", "disconnected"):
                    return jsonify({"ok": True, "status": current})
                client._log_action(f"Disconnect failed: {exc}", "error")
                return jsonify({"ok": False, "error": str(exc)}), 500
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

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
        Sequential (more stable) fetch of dataObject, brcb, urcb, dataset directories with structured timing."""

        async def _safe(coro):
            try:
                return await coro
            except Exception:
                return None

        #aid = log_action_start('lnDetails', {'ld': ld_inst, 'ln': ln_inst})
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
            # Get the invoke lock to synchronize requests
            lock = client.runtime.invoke_lock

            for do_name in do_list:
                defn = None
                try:
                    obj_ref = f"{ld_inst}/{ln_inst}.{do_name}"

                    # Use lock to ensure invoke_id is managed correctly
                    if lock is None:
                        defn = await client.get_data_definition(obj_ref, ws_info, None, None)
                    else:
                        async with lock:
                            defn = await client.get_data_definition(obj_ref, ws_info, None, None)

                    cdc = None
                    if isinstance(defn, dict):
                        # CDC is at the top level of the data definition
                        cdc = defn.get('cdc')
                    data_objects.append({'name': do_name, 'cdc': cdc})
                except Exception as e:
                    # If we can't get the definition, just add the name
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
        lock = client.runtime.invoke_lock  # reuse same lock for all RCB value fetches to preserve invoke_id integrity

        # Process BRCBs
        brcb_list = _extract_rcb(brcb_items, 'BRCB')
        for rcb_info in brcb_list:
            rcb_name = rcb_info['name']
            rcb_ref = f"{ld_inst}/{ln_inst}.{rcb_name}"
            rcb_values = None
            try:
                # Fetch BRCB values
                if lock is None:
                    rcb_values = await client.get_BRCB_values(rcb_ref, ws_info, None, None)
                else:
                    async with lock:
                        rcb_values = await client.get_BRCB_values(rcb_ref, ws_info, None, None)

                # Extract RptEna value and convert bytes to hex strings for JSON serialization
                rpt_ena = False
                if isinstance(rcb_values, dict):
                    rpt_ena = rcb_values.get('RptEna', False)
                    # Convert any bytes values to hex strings for JSON serialization
                    rcb_values = _convert_bytes_to_hex(rcb_values)

                rcbs.append({
                    'name': rcb_name,
                    'type': 'BRCB',
                    'values': rcb_values,
                    'enabled': rpt_ena
                })
            except Exception as e:
                # If fetch fails, still add the RCB without values
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
                # Fetch URCB values
                if lock is None:
                    rcb_values = await client.get_URCB_values(rcb_ref, ws_info, None, None)
                else:
                    async with lock:
                        rcb_values = await client.get_URCB_values(rcb_ref, ws_info, None, None)

                # Extract RptEna value and convert bytes to hex strings for JSON serialization
                rpt_ena = False
                if isinstance(rcb_values, dict):
                    rpt_ena = rcb_values.get('RptEna', False)
                    # Convert any bytes values to hex strings for JSON serialization
                    rcb_values = _convert_bytes_to_hex(rcb_values)

                rcbs.append({
                    'name': rcb_name,
                    'type': 'URCB',
                    'values': rcb_values,
                    'enabled': rpt_ena
                })
            except Exception as e:
                # If fetch fails, still add the RCB without values
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

        result = {
            'dataObjects': data_objects,
            'dataAttributes': data_attributes,
            'reportControlBlocks': rcbs,
            'dataSets': datasets,
        }
        #log_action_end(aid, success=True,
        #               extra_detail={'do': len(data_objects), 'da': len(data_attributes), 'rcb': len(rcbs),
        #                             'ds': len(datasets)})
        return result

    # ---- InvokeId helpers (stable locked approach) ----
    def _invoke_ln_directory(client, ws_info, ld_inst, ln_inst, mode):
        """Return coroutine that performs directory call under a lock to preserve invoke_id integrity."""

        async def _coro():
            lock = client.runtime.invoke_lock
            if lock is None:
                #log_action(f'Request: getLogicalNodeDirectory {mode} {ld_inst}/{ln_inst}')
                return await client.get_logical_node_directory(ld_inst, ln_inst, mode, ws_info, None, None)
            async with lock:
                #log_action(f'Request: getLogicalNodeDirectory {mode} {ld_inst}/{ln_inst}')
                return await client.get_logical_node_directory(ld_inst, ln_inst, mode, ws_info, None, None)

        return _coro()

    def _invoke_ln_directory_async(client, ws_info, ld_inst, ln_inst, mode):
        # For async path we reuse same implementation; concurrency across modes will be sequentially locked
        return _invoke_ln_directory(client, ws_info, ld_inst, ln_inst, mode)

    # ---------------- Background Model Build -----------------
    async def _abuild_full_model() -> None:
        """Build full model sequentially with progress updates (reduced complexity)."""
        #client = runtime.get('client');
        endpoint = client.runtime.endpoint
        loop = client.runtime.loop
        if not client or not endpoint or not loop or not client.runtime.client.is_connected:
            raise RuntimeError('not-connected')
        ws_info = endpoint.get_websocket_info(client)
        if ws_info is None:
            raise RuntimeError('no-websocket-info')

        #model_aid = log_action_start('modelFetch', {})
        #started = time.perf_counter()

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
                    except Exception as e:
                        print('ln detail fetch error (background)', ld, ln_full, e)
                    finally:
                        _inc_ln_done()
            except Exception as e:
                print('logical node fetch error (background)', ld, e)
                logical_device_map[ld] = []
                logical_device_status[ld] = 'error'
            finally:
                _finish_ld()

        try:
            ld_list = await client.runtime.client.get_server_directory(ws_info, None, None)
            if not isinstance(ld_list, list):
                raise RuntimeError('unexpected-server-directory')
            _init_progress(ld_list)
            for ld in ld_list:  # sequential for stability
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
            #log_action_end(model_aid, success=True,
            #               extra_detail={'lds': len(ld_list), 'lnDetails': len(logical_node_details)})
        except Exception as e:
            with client.runtime.lock:
                client.runtime.model_status = 'error'
                client.runtime.model_error = str(e)
            #log_action_end(model_aid, success=False, error=str(e))
            raise
        #finally:
        #    elapsed_ms = int((time.perf_counter() - started) * 1000)
        #    log_action(f'Model build elapsed {elapsed_ms} ms')

    def _start_model_build_if_needed():
        """Schedule background model build if idle or error. Returns status after scheduling."""
        with client.runtime.lock:
            status = client.runtime.model_status
            if status in ('ready', 'building'):
                return status
            # reset
            client.runtime.model_data = None
            client.runtime.model_error = None
            client.runtime.model_status = 'building'
            #client.runtime. = time.perf_counter()
        loop = client.runtime.loop
        if not loop:
            with client.runtime.lock:
                client.runtime.model_status = 'error'
                client.runtime.model_error = 'no-loop'
            return 'error'
        # schedule
        try:
            client._log_action("Scheduling model build", "info")
            logger.info(f"Scheduling model build for client {getattr(client.runtime, 'host', None)}:{getattr(client.runtime, 'port', None)}")
            fut = asyncio.run_coroutine_threadsafe(_abuild_full_model(), loop)
            client._log_action("Model build scheduled", "info")
            logger.info("Model build scheduled (future stored)")
        except Exception as e:
            with client.runtime.lock:
                client.runtime.model_status = 'error'
                client.runtime.model_error = str(e)
            client._log_action(f"Failed to schedule model build: {e}", "error")
            logger.exception(f"Failed to schedule model build: {e}")
            return 'error'

        # store task and attach a done callback to clear it and record errors
        with client.runtime.lock:
            client.runtime.model_task = fut

        def _on_model_task_done(future):
            # This callback may run in a different thread; use runtime.lock to protect state
            try:
                exc = future.exception()
            except Exception:
                exc = None
            with client.runtime.lock:
                # Clear the task reference
                try:
                    client.runtime.model_task = None
                except Exception:
                    pass
                if exc is not None:
                    # If the coro raised, ensure model_status reflects the error
                    client.runtime.model_status = 'error'
                    client.runtime.model_error = str(exc)
                    client._log_action(f"Model build failed: {exc}", "error")
                    logger.error(f"Background model build task failed: {exc}")
                else:
                    # On success, _abuild_full_model should have set model_status to 'ready'
                    if client.runtime.model_status != 'ready':
                        client.runtime.model_status = 'ready'
                        client.runtime.model_error = None
                    client._log_action("Model build completed", "info")
                    logger.info("Background model build task completed successfully")

        try:
            fut.add_done_callback(_on_model_task_done)
        except Exception as e:
            # If attaching callback fails, still return 'building' but log
            client._log_action(f"Failed to attach model task callback: {e}", "warn")
            logger.warning(f"Failed to attach model task callback: {e}")

        return 'building'

    @app.get("/api/iec61850client/model/tree")
    def api_model():
        """Get the IED model tree from the connected server."""
        try:
            # Ensure runtime loop is running (client must be connected)
            loop = client.runtime.loop
            if loop is None or not getattr(loop, "is_running", lambda: False)():
                return jsonify({"ok": False, "error": "client-not-connected"}), 503

            with client.runtime.lock:
                status = client.runtime.model_status
                data = client.runtime.model_data
                error = client.runtime.model_error
            if status == 'ready' and data:
                return jsonify({'status': 'ready', 'model': data})
            if status == 'error':
                return jsonify({'status': 'error', 'error': error}), 500
            # status idle/building => trigger if idle
            if status == 'idle':
                start_result = _start_model_build_if_needed()
                if start_result == 'error':
                    client._log_action('Model build scheduling failed', 'error')
                    return jsonify({'status': 'error', 'error': client.runtime.model_error}), 503
            with client.runtime.lock:
                progress = client.runtime.model_progress
            return jsonify({'status': 'building', 'progress': progress})

        except Exception as exc:
            client._log_action(f"Get model failed (outer): {exc}", "error")
            logger.exception("Unhandled outer exception in api_model")
            tb = traceback.format_exc()
            return jsonify({"ok": False, "error": str(exc), "traceback": tb}), 500

    @app.get("/api/iec61850client/actions")
    def api_actions():
        """Get logged client actions."""
        try:
            return jsonify({"actions": client.get_actions()})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.post("/api/iec61850client/actions/clear")
    def api_actions_clear():
        """Clear action log."""
        try:
            client.clear_actions()
            return jsonify({"ok": True})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.get("/api/iec61850client/messages")
    def api_messages():
        """Get logged protocol messages."""
        try:
            return jsonify({"messages": client.get_messages()})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.post("/api/iec61850client/messages/clear")
    def api_messages_clear():
        """Clear message log."""
        try:
            client.clear_messages()
            return jsonify({"ok": True})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.post("/api/iec61850client/readvalue")
    def api_read_value():
        """Read a value from the connected server.

        Expects JSON body with:
          - objRef: object reference
        """
        try:
            data = request.get_json(silent=True) or {}
            obj_ref = data.get("objRef")
            fc = data.get("fc")

            if not obj_ref:
                client._log_action("Client readvalue rejected: missing objRef", "warn")
                return jsonify({"ok": False, "error": "objRef is required"}), 400

            if client.runtime.client is None:
                client._log_action(
                    "Client readvalue rejected: not connected",
                    "warn",
                    detail={"objRef": obj_ref, "fc": fc},
                )
                return jsonify({"ok": False, "error": "Client is not connected"}), 503

            try:
                result = client.invoke_on_runtime_loop(
                    #client.runtime.client.read_value(obj_ref, fc), timeout=10
                    client.read_value(obj_ref, fc), timeout=10
                )

                if result is None:
                    client._log_action(
                        "Client readvalue failed: instanceNotAvailable",
                        "warn",
                        detail={"objRef": obj_ref, "fc": fc}
                    )
                    return jsonify({"ok": False, "error": "instanceNotAvailable"}), 404

                client._log_action(
                    "Client readvalue",
                    detail={
                        "objRef": obj_ref,
                        "value": result.get("value"),
                    },
                )
                return jsonify(
                    {
                        "ok": True,
                        "success": True,
                        "objRef": obj_ref,
                        "value": result.get("value"),
                    }
                )
            except FuturesTimeoutError:
                client._log_action(
                    "Client readvalue timeout",
                    "warn",
                    detail={"objRef": obj_ref, "fc": fc},
                )
                return jsonify({"ok": False, "error": "read timeout"}), 504
            except ValueError as exc:
                client._log_action(f"Client readvalue failed: {exc}", "warn")
                return jsonify({"ok": False, "error": str(exc)}), 404
            except Exception as exc:
                client._log_action(f"Client readvalue failed: {exc}", "error")
                return jsonify({"ok": False, "error": str(exc)}), 500
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.post("/api/iec61850client/writevalue")
    def api_write_value():
        """Write a value to the connected server.

        Expects JSON body with:
          - objRef: object reference
          - value: value to write
        """
        try:
            data = request.get_json() or {}
            obj_ref = data.get("objRef")
            fc = data.get("fc")
            value = data.get("value")
            value_type = data.get("value_type")

            if not obj_ref:
                client._log_action("Client writevalue rejected: missing objRef", "warn")
                return jsonify({"ok": False, "error": "objRef is required"}), 400

            if not fc:
                client._log_action("Client writevalue rejected: missing fc", "warn")
                return jsonify({"ok": False, "error": "fc is required"}), 400

            if value is None:
                client._log_action(
                    "Client writevalue rejected: missing value",
                    "warn",
                    detail={"objRef": obj_ref, "fc": fc}
                )
                return jsonify({"ok": False, "error": "value is required"}), 400

            if client.runtime.client is None:
                client._log_action(
                    "Client writevalue rejected: not connected",
                    "warn",
                    detail={"objRef": obj_ref, "fc": fc, "value": value},
                )
                return jsonify({"ok": False, "error": "Client is not connected"}), 503

            try:
                result = client.invoke_on_runtime_loop(
                    client.write_value(obj_ref, value, fc, value_type), timeout=10
                )
                return jsonify(
                    {
                        "ok": True,
                        "success": True,
                        "objRef": obj_ref,
                        "fc": fc,
                        "value": result.get("value"),
                    }
                )
            except FuturesTimeoutError:
                client._log_action(
                    "Client writevalue timeout",
                    "warn",
                    detail={"objRef": obj_ref},
                )
                return jsonify({"ok": False, "error": "write timeout"}), 504
            except ValueError as exc:
                client._log_action(f"Client writevalue failed: {exc}", "warn")
                return jsonify({"ok": False, "error": str(exc)}), 404
            except Exception as exc:
                client._log_action(f"Client writevalue failed: {exc}", "error")
                return jsonify({"ok": False, "error": str(exc)}), 500
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.get('/internal/model/status')
    def _internal_model_status():
        """Internal diagnostic endpoint exposing model build state for debugging."""
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

            return jsonify({
                'ok': True,
                'model_status': status,
                'model_progress': progress,
                'model_error': error,
                'model_task_present': task is not None,
                'loop_running': loop_running,
                'client_connected': client_connected,
            })
        except Exception as exc:
            client._log_action(f"Internal model status failed: {exc}", 'error')
            return jsonify({'ok': False, 'error': str(exc)}), 500

    return app, client


def create_flask_app() -> Flask:
    """Create Flask app and register BFF blueprint."""
    app = Flask(__name__)
    blueprint, _client = create_bff_blueprint()
    app.register_blueprint(blueprint)
    return app


if __name__ == "__main__":
    import os
    app = create_flask_app()
    port = int(os.getenv("PORT", "5002"))
    print(
        f"[bff_endpoint] starting client API on 0.0.0.0:{port}",
        flush=True,
    )
    # Enable threaded server so diagnostic endpoints and other requests are
    # served concurrently while background model builds run on the client's loop.
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True, use_reloader=False)
