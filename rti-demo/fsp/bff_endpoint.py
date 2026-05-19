"""Backend for Frontend (BFF) endpoint providing REST API for ACSI server control.

This module exposes Flask endpoints that interact with the ACSI server,
handling model management, server lifecycle, and value operations.
"""

from __future__ import annotations

from concurrent.futures import TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Blueprint, Flask, jsonify, redirect, request

from acsi_server import ACSIServer
from ws61850.iec61850.data_model.ied_model import DataAttribute, DataObject, IedModel


def create_bff_blueprint(
    factory_dir: Path,
    scl_default_path: Optional[Path] = None,
) -> tuple[Blueprint, ACSIServer]:
    """Create a Flask blueprint for the ACSI server BFF API.

    Args:
        factory_dir: Path to the fsp directory containing model.py
        scl_default_path: Unused. Kept only for backward compatibility.

    Returns:
        Tuple of (Flask Blueprint, ACSIServer instance)
    """
    app = Blueprint("iec61850_server", __name__)
    server = ACSIServer(factory_dir)

    # ==================== Helper Functions ====================

    def serialize_data_attribute(da: DataAttribute) -> Dict[str, Any]:
        """Serialize a DataAttribute to JSON-compatible dict."""
        return {
            "kind": "DA",
            "name": da.name,
            "fc": da.fc.name if da.fc is not None else None,
            "type": da.type.name if da.type is not None else None,
            "children": [serialize_data_attribute(child) for child in (da.data_attributes or [])],
        }

    def serialize_data_object(do: DataObject) -> Dict[str, Any]:
        """Serialize a DataObject to JSON-compatible dict."""
        children: List[Dict[str, Any]] = []
        for item in do.do_or_da or []:
            if isinstance(item, DataObject):
                children.append(serialize_data_object(item))
            elif isinstance(item, DataAttribute):
                children.append(serialize_data_attribute(item))

        return {
            "kind": "DO",
            "name": do.name,
            "cdc": do.cdc,
            "children": children,
        }

    def serialize_ied_tree(ied: IedModel) -> Dict[str, Any]:
        """Serialize an IED model tree to JSON-compatible dict."""
        return {
            "kind": "IED",
            "name": ied.name,
            "children": [
                {
                    "kind": "LD",
                    "name": ld.name,
                    "ldName": ld.ldName,
                    "children": [
                        {
                            "kind": "LN",
                            "name": ln.name,
                            "children": [
                                serialize_data_object(do) for do in (ln.data_objects or [])
                            ],
                        }
                        for ln in (ld.logical_nodes or [])
                    ],
                }
                for ld in (ied.logical_devices or [])
            ],
        }

    def collect_da_paths_from_do(data_object: DataObject, prefix: str) -> List[tuple]:
        """Collect flattened (path, fc_name) tuples under a DO path."""
        results: List[tuple] = []
        for item in (data_object.do_or_da or []):
            if isinstance(item, DataAttribute):
                da_path = f"{prefix}.{item.name}"
                fc_name = item.fc.name if item.fc is not None else None
                results.append((da_path, fc_name))
                results.extend(collect_da_paths_from_da(item, da_path))
            elif isinstance(item, DataObject):
                sub_prefix = f"{prefix}.{item.name}"
                results.extend(collect_da_paths_from_do(item, sub_prefix))
        return results

    def collect_da_paths_from_da(data_attribute: DataAttribute, prefix: str) -> List[tuple]:
        """Collect flattened (path, fc_name) tuples for nested DA paths."""
        results: List[tuple] = []
        for child in (data_attribute.data_attributes or []):
            child_path = f"{prefix}.{child.name}"
            fc_name = child.fc.name if child.fc is not None else None
            results.append((child_path, fc_name))
            results.extend(collect_da_paths_from_da(child, child_path))
        return results

    def build_logical_node_details(ied_model: Optional[IedModel]) -> Dict[str, Dict[str, Any]]:
        """Build UI-friendly logical node details."""
        details: Dict[str, Dict[str, Any]] = {}
        if ied_model is None:
            return details

        for ld in (ied_model.logical_devices or []):
            for ln in (ld.logical_nodes or []):
                data_objects: List[Dict[str, Any]] = []
                data_attributes: List[str] = []
                da_fc_map: Dict[str, str] = {}
                ln_prefix = f"{ld.name}/{ln.name}."

                for data_object in (ln.data_objects or []):
                    data_objects.append({"name": data_object.name, "cdc": data_object.cdc})
                    for da_path, fc_name in collect_da_paths_from_do(data_object, data_object.name):
                        data_attributes.append(da_path)
                        if fc_name:
                            da_fc_map[f"{ln_prefix}{da_path}"] = fc_name

                ln_key = f"{ld.name}/{ln.name}"
                details[ln_key] = {
                    "dataObjects": data_objects,
                    "dataAttributes": sorted(set(data_attributes)),
                    "dataAttributeFcs": da_fc_map,
                    "reportControlBlocks": [],
                    "dataSets": [],
                }

        return details

    def extract_tpa_info(websocket_info: Any) -> Dict[str, Any]:
        """Extract TPA (Three Part Address) and connection info from websocket_info."""
        info = {
            "peer_address": None,
            "peer_port": None,
            "server_role": "ACSI_Server",
            "ws_mode": "passive",  # Our endpoint is passive (accepts connections)
            "remote_role": None,
            "tpa": None,
                    "status": "active",  # Connection health status
        }

        try:
            # Try to extract peer address from websocket info
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

            # Try to extract TPA from connection metadata
            if hasattr(websocket_info, "tpa"):
                info["tpa"] = str(websocket_info.tpa)
            elif hasattr(websocket_info, "request") and hasattr(websocket_info.request, "headers"):
                # Check for TPA in WebSocket headers
                headers = websocket_info.request.headers
                if "X-TPA" in headers:
                    info["tpa"] = headers["X-TPA"]

            # Check connection health status
            if hasattr(websocket_info, "connected") and not websocket_info.connected:
                info["status"] = "disconnected"
            elif hasattr(websocket_info, "is_open") and not websocket_info.is_open():
                info["status"] = "disconnected"
        except Exception:
            pass

        return info

    # ==================== Route Handlers ====================

    @app.before_request
    def log_api_calls() -> None:
        """Log API calls for debugging."""
        path = request.path or ""
        if not path.startswith("/api/iec61850server/"):
            return

        if request.method == "POST":
            payload = request.get_json(silent=True) or {}
            detail = {
                "path": path,
                "objRef": payload.get("objRef"),
                "fc": payload.get("fc"),
                "value": payload.get("value"),
                "dataType": payload.get("dataType"),
            }
            server._log_action(f"API POST {path}", detail=detail)
            return

        if request.method == "GET" and path == "/api/iec61850server/status":
            signature = (
                server.runtime.status,
                server.runtime.host,
                server.runtime.port,
                server.runtime.error,
            )
            if signature != server.runtime.last_status_log_signature:
                server.runtime.last_status_log_signature = signature
                server._log_action(
                    "API GET /api/iec61850server/status",
                    detail={
                        "status": server.runtime.status,
                        "host": server.runtime.host,
                        "port": server.runtime.port,
                        "error": server.runtime.error,
                    },
                )



    @app.get("/api/iec61850server/status")
    def api_status():
        """Get current server status."""
        try:
            return jsonify(server.get_status())
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.get("/api/iec61850server/connections")
    def api_connections():
        """Get TPA information for all connected clients."""
        try:
            endpoint = server.runtime.endpoint
            connections = []

            if endpoint is not None and hasattr(endpoint, "websocket_info_list"):
                for ws_info in endpoint.websocket_info_list:
                    tpa_data = extract_tpa_info(ws_info)
                    connections.append(tpa_data)

            return jsonify(
                {
                    "ok": True,
                    "server_role": "ACSI_Server",
                    "ws_mode": "passive",
                    "connected_clients": len(connections),
                    "connections": connections,
                }
            )
        except Exception as exc:
            server._log_action(f"Get connections failed: {exc}", "error")
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.get("/api/iec61850server/model")
    def api_model():
        """Return current loaded model descriptor for UI rendering."""
        try:
            ied_model: Optional[IedModel] = server.runtime.ied_model
            source = server.runtime.model_source
            selected_ied = server.runtime.model_ied_name

            logical_devices: List[str] = []
            if ied_model is not None:
                logical_devices = [ld.name for ld in (ied_model.logical_devices or [])]

            tree_data = serialize_ied_tree(ied_model) if ied_model is not None else None
            logical_node_details = build_logical_node_details(ied_model)

            result = {
                "status": "ready",
                "model": {
                    "server": {
                        "name": "IEC61850 WS Server",
                        "mode": "passive",
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
            print(
                f"[GET /api/iec61850server/model] "
                f"ied_model={ied_model is not None} "
                f"has_tree={has_tree} "
                f"source={source!r} "
                f"iedName={selected_ied!r} "
                f"logicalDevices={logical_devices}"
            )
            return jsonify(result)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.post("/api/iec61850server/update-iedmodel")
    def api_update_iedmodel():
        """Update model.py in fsp directory and reload IED model."""
        try:
            with server.runtime.lock:
                if server.runtime.status in ("starting", "listening", "stopping"):
                    return (
                        jsonify({"ok": False, "error": "Stop server before updating model.py."}),
                        400,
                    )

            payload = request.get_json(silent=True) or {}
            model_py = payload.get("modelPy")

            if not isinstance(model_py, str) or not model_py.strip():
                return jsonify({"ok": False, "error": "modelPy is required and must be a non-empty string."}), 400

            ied_model = server.update_model_file(model_py)
            server._log_action(
                "IED model updated",
                detail={"source": str(server.model_file), "ied": ied_model.name},
            )
            return jsonify(
                {
                    "ok": True,
                    "source": str(server.model_file),
                    "ied": ied_model.name,
                }
            )
        except Exception as exc:
            server._log_action(f"IED model update failed: {exc}", "error")
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.post("/api/iec61850server/start")
    def api_start():
        """Start the IEC 61850 WebSocket server."""
        try:
            body = request.get_json(silent=True) or {}
            host = str(body.get("host", server.runtime.host or "localhost"))
            raw_port = body.get("port", server.runtime.port or 8765)
            mode = str(body.get("mode", "server")).lower()
            cp = (body.get("cp") or "").strip() or None

            if mode != "server":
                return (
                    jsonify({"ok": False, "error": "Only 'server' mode is supported in this app."}),
                    400,
                )

            try:
                port = int(raw_port)
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": f"Invalid port value: {raw_port!r}"}), 400

            # If the frontend explicitly provided a cp, update runtime before starting
            if cp:
                server._set_runtime_state(cp=cp)

            try:
                server.start_server(host, port)
                return jsonify({"ok": True, "status": "starting", "host": host, "port": port})
            except (ValueError, PermissionError) as exc:
                server._log_action(f"Start rejected: {exc}", "warn")
                return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            server._log_action(f"Start failed: {exc}", "error")
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.post("/api/iec61850server/stop")
    def api_stop():
        """Stop the IEC 61850 WebSocket server."""
        try:
            status = server.runtime.status
            if status in (None, "stopped"):
                return jsonify({"ok": True, "status": "stopped"})

            try:
                server.stop_server()
                current = server.runtime.status
                if current in ("stopping", "starting"):
                    return jsonify({"ok": True, "status": "stopping"})
                return jsonify({"ok": True, "status": "stopped"})
            except Exception as exc:
                current = server.runtime.status
                if current in ("stopping", "stopped"):
                    return jsonify({"ok": True, "status": current})
                server._log_action(f"Stop failed: {exc}", "error")
                return jsonify({"ok": False, "error": str(exc)}), 500
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.get("/api/iec61850server/actions")
    def api_actions():
        """Get logged server actions."""
        try:
            return jsonify({"actions": server.get_actions()})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.post("/api/iec61850server/actions/clear")
    def api_actions_clear():
        """Clear action log."""
        try:
            server.clear_actions()
            return jsonify({"ok": True})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.get("/api/iec61850server/messages")
    def api_messages():
        """Get logged protocol messages."""
        try:
            return jsonify({"messages": server.get_messages()})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.post("/api/iec61850server/messages/clear")
    def api_messages_clear():
        """Clear message log."""
        try:
            server.clear_messages()
            return jsonify({"ok": True})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.post("/api/iec61850server/readvalue")
    def api_read_value():
        """Read a value from the server IED model.

        Expects JSON body with:
          - objRef: object reference
        Optional:
          - fc: functional constraint
        """
        try:
            data = request.get_json(silent=True) or {}
            obj_ref = data.get("objRef")
            fc = (data.get("fc") or "mx").lower()

            if not obj_ref:
                server._log_action("Server readvalue rejected: missing objRef", "warn")
                return jsonify({"ok": False, "error": "objRef is required"}), 400

            if server.runtime.server_cp1 is None:
                server._log_action(
                    "Server readvalue rejected: server not running",
                    "warn",
                    detail={"objRef": obj_ref, "fc": fc},
                )
                return jsonify({"ok": False, "error": "Server is not running"}), 503

            try:
                result = server.read_value(obj_ref)

                if result is None:
                    server._log_action(
                        "Server readvalue failed: instanceNotAvailable",
                        "warn",
                        detail={"objRef": obj_ref, "fc": fc},
                    )
                    return jsonify({"ok": False, "error": "instanceNotAvailable"}), 404

                # Format response to match client API: wrap single value in a list
                values = [result]

                print(
                    f"[POST /api/iec61850server/readvalue] SUCCESS objRef={obj_ref!r} "
                    f"fc={fc!r} type={result.get('type')!r} value={result.get('value')!r}"
                )

                server._log_action(
                    "Server readvalue",
                    detail={
                        "objRef": obj_ref,
                        "fc": fc,
                        "type": result.get("type"),
                        "value": result.get("value"),
                    },
                )
                return jsonify(
                    {
                        "ok": True,
                        "success": True,
                        "objRef": obj_ref,
                        "fc": fc,
                        "values": values,
                    }
                )
            except FuturesTimeoutError:
                server._log_action(
                    "Server readvalue timeout",
                    "warn",
                    detail={"objRef": obj_ref, "fc": fc},
                )
                return jsonify({"ok": False, "error": "read timeout"}), 504
            except ValueError as exc:
                server._log_action(f"Server readvalue failed: {exc}", "warn")
                return jsonify({"ok": False, "error": str(exc)}), 404
            except Exception as exc:
                server._log_action(f"Server readvalue failed: {exc}", "error")
                return jsonify({"ok": False, "error": str(exc)}), 500
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.post("/api/iec61850server/writevalue")
    def api_write_value():
        """Write a value in the server IED model.

        Expects JSON body with:
          - objRef: object reference
          - value: value to write
        Optional:
          - fc: functional constraint
          - dataType: used to coerce value
        """
        try:
            data = request.get_json() or {}
            obj_ref = data.get("objRef")
            fc = (data.get("fc") or "mx").lower()
            value = data.get("value")
            data_type = data.get("dataType", "unknown")

            if not obj_ref:
                server._log_action("Server writevalue rejected: missing objRef", "warn")
                return jsonify({"ok": False, "error": "objRef is required"}), 400

            if value is None:
                server._log_action(
                    "Server writevalue rejected: missing value",
                    "warn",
                    detail={"objRef": obj_ref, "fc": fc},
                )
                return jsonify({"ok": False, "error": "value is required"}), 400

            if server.runtime.server_cp1 is None:
                server._log_action(
                    "Server writevalue rejected: server not running",
                    "warn",
                    detail={"objRef": obj_ref, "fc": fc, "value": value},
                )
                return jsonify({"ok": False, "error": "Server is not running"}), 503

            try:
                result = server.write_value(obj_ref, value, data_type)
                return jsonify(
                    {
                        "ok": True,
                        "success": True,
                        "objRef": result["objRef"],
                        "fc": fc,
                        "value": result["value"],
                        "dataType": result["dataType"],
                    }
                )
            except FuturesTimeoutError:
                server._log_action(
                    "Server writevalue timeout",
                    "warn",
                    detail={"objRef": obj_ref, "fc": fc},
                )
                return jsonify({"ok": False, "error": "write timeout"}), 504
            except ValueError as exc:
                server._log_action(f"Server writevalue failed: {exc}", "warn")
                return jsonify({"ok": False, "error": str(exc)}), 404
            except Exception as exc:
                server._log_action(f"Server writevalue failed: {exc}", "error")
                return jsonify({"ok": False, "error": str(exc)}), 500
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    return app, server


def create_flask_app(factory_dir: Optional[Path] = None) -> Flask:
    """Create Flask app and register BFF blueprint."""
    resolved_factory_dir = factory_dir or Path(__file__).parent
    app = Flask(__name__, template_folder="templates", static_folder="static")
    blueprint, _server = create_bff_blueprint(resolved_factory_dir, scl_default_path=None)
    app.register_blueprint(blueprint)
    return app


if __name__ == "__main__":
    import os
    factory_dir = Path(__file__).parent
    app = create_flask_app(factory_dir)
    port = int(os.getenv("PORT", "5001"))
    print(
        f"[bff_endpoint] starting API on 0.0.0.0:{port}, factory_dir={factory_dir}",
        flush=True,
    )
    app.run(host="0.0.0.0", port=port, debug=False)
