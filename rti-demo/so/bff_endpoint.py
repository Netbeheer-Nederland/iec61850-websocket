"""Backend for Frontend (BFF) endpoint providing REST API for ACSI client control.

This module exposes Flask endpoints that interact with the ACSI client,
handling connection management and value operations.
"""

from __future__ import annotations

from concurrent.futures import TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Any, Dict, Optional

from flask import Blueprint, Flask, app, jsonify, redirect, request, current_app

from acsi_client import ACSIClient


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
            "server_role": "ACSI_Client",
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

    @app.get("/api/iec61850client/apis")
    def api_list_all_endpoints():
        routes = []

        print("Enumerating routes:", len(current_app.url_map._rules))

        for rule in current_app.url_map.iter_rules():
            path = str(rule)

            if path.startswith("/api/iec61850client/"):

                methods = [
                    m for m in rule.methods
                    if m not in ("HEAD", "OPTIONS")
                ]

                routes.append({
                    "path": path,
                    "methods": methods,
                    "endpoint": rule.endpoint,
                })

        return {
            "ok": True,
            "count": len(routes),
            "endpoints": sorted(routes, key=lambda x: x["path"]),
        }

            
    @app.get("/api/health")
    def api_health():
        """Generic health endpoint used by external discovery (for example BFF network scan)."""
        try:
            return jsonify(
                {
                    "status": "ok",
                    "service": "SO",
                    "server": {
                        "status": "ok",
                        "host": "localhost",
                        "port": 8080,
                    },
                }
            )
        except Exception as exc:
            return jsonify({"status": "degraded", "service": "SO", "error": str(exc)}), 500
  

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
    app.run(host="0.0.0.0", port=port, debug=False)
