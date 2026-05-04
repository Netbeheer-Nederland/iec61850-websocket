from flask import Blueprint, jsonify, request

from gui.backend.context import connection_manager, runtime

bp = Blueprint("monitoring", __name__)


@bp.get("/actions")
def api_actions():
    target = request.args.get("target")
    return jsonify({"actions": connection_manager.snapshot_actions(target=target)})


@bp.get("/messages")
def api_messages():
    target = request.args.get("target")
    return jsonify({"messages": connection_manager.snapshot_messages(target=target)})


@bp.post("/messages/clear")
def api_messages_clear():
    target = (request.get_json(silent=True) or {}).get("target")
    try:
        connection_manager.clear_messages(target=target)
        return jsonify({"status": "cleared"})
    except Exception as exc:
        return jsonify({"status": "error", "error": str(exc)}), 500


@bp.route("/messages/settings", methods=["GET", "POST"])
def api_messages_settings():
    target = (request.get_json(silent=True) or {}).get("target") if request.method == "POST" else request.args.get("target")
    try:
        if request.method == "GET":
            return jsonify({"max": connection_manager._get_state(target).messages_max})
        new_max = int((request.get_json(silent=True) or {}).get("max", runtime.messages_max))
        return jsonify({"status": "updated", "max": connection_manager.set_message_retention(new_max, target=target)})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.get("/report-updates")
def api_report_updates():
    target = request.args.get("target")
    return jsonify({"updates": connection_manager.drain_report_updates(target=target)})
