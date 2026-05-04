from flask import Blueprint, jsonify

from bff.backend.context import connection_manager, model_service
from bff.backend.http.utils import request_json

bp = Blueprint("connection", __name__)


@bp.post("/connect")
def api_connect():
    data = request_json()
    target = data.get("target")
    url = data.get("url")
    port = data.get("port")
    cp = data.get("cp")
    is_server = bool(data.get("is_server", False))
    is_direct = bool(data.get("is_direct", False))
    security = data.get("security")
    application_role = data.get("application_role")

    if is_server:
        if not port or not cp:
            return jsonify({"error": "port and cp are required for server mode"}), 400
        mode = "passive"
        url = "0.0.0.0"
        is_direct = True
        connection_manager.log_action(f"Server mode: listening on port {port} cp={cp}", target=target)
    else:
        if not url or not port or not cp:
            return jsonify({"error": "url, port and cp are required for client mode"}), 400
        mode = "active"
        sec_msg = ""
        if security:
            if security.get("enableTLS"):
                sec_msg += " [TLS]"
            if security.get("enableOAuth"):
                sec_msg += " [OAuth]"
        connection_manager.log_action(
            f"Client mode: connecting to {url}:{port} cp={cp} direct={is_direct}{sec_msg}",
            target=target,
        )

    try:
        connection_manager.start_connection(
            url,
            int(port),
            cp,
            is_direct=is_direct,
            mode=mode,
            security=security,
            application_role=application_role,
            target=target,
        )
        return jsonify({"status": "listening" if is_server else "connecting"})
    except RuntimeError as exc:
        code = 409 if str(exc) == "connection-already-active" else 500
        connection_manager.log_action(f"Connect error: {exc}", "error", target=target)
        return jsonify({"error": str(exc)}), code
    except Exception as exc:
        connection_manager.log_action(f"Connect error: {exc}", "error", target=target)
        return jsonify({"error": str(exc)}), 500


@bp.post("/disconnect")
def api_disconnect():
    data = request_json()
    target = data.get("target")
    try:
        status = connection_manager.disconnect(target=target)
        if connection_manager._normalize_target(target) == "rti-so":
            model_service.reset()
        return jsonify({"status": status})
    except Exception as exc:
        connection_manager.log_action(f"Disconnect error: {exc}", "error", target=target)
        return jsonify({"error": str(exc)}), 500


@bp.get("/status")
def api_status():
    from flask import request

    target = request.args.get("target")
    try:
        return jsonify(connection_manager.status(target=target))
    except Exception as exc:
        connection_manager.log_action(f"Status error: {exc}", "error", target=target)
        return jsonify({"state": "error", "error": str(exc)}), 500


@bp.get("/statuses")
def api_statuses():
    try:
        return jsonify(connection_manager.statuses())
    except Exception as exc:
        connection_manager.log_action(f"Statuses error: {exc}", "error")
        return jsonify({"error": str(exc)}), 500
