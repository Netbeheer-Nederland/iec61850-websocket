from flask import Blueprint, jsonify

from gui.backend.context import connection_manager
from gui.backend.http.utils import error_code, normalize_fc, request_json
from gui.protocol_utils import format_value_for_write

bp = Blueprint("data", __name__)


@bp.post("/readvalue")
def api_read_value():
    data = request_json()
    obj_ref = data.get("objRef")
    fc = normalize_fc(data.get("fc"))
    if not obj_ref:
        return jsonify({"error": "objRef is required"}), 400

    aid = connection_manager.log_action_start("getDataValues", {"ref": obj_ref, "fc": fc})
    try:
        result = connection_manager.invoke(
            lambda client, _endpoint, ws_info: client.get_data_values(obj_ref, fc, True, ws_info, None, None),
            timeout=10,
        )
        if isinstance(result, str):
            connection_manager.log_action_end(aid, success=False, error=result)
            return jsonify({"error": result}), 400
        connection_manager.log_action_end(
            aid,
            success=True,
            extra_detail={"values": len(result) if isinstance(result, list) else 1},
        )
        return jsonify({"success": True, "objRef": obj_ref, "fc": fc, "values": result})
    except RuntimeError as exc:
        connection_manager.log_action_end(aid, success=False, error=str(exc))
        connection_manager.log_action(f"Error getDataValues {obj_ref}: {exc}", "error")
        return jsonify({"error": str(exc)}), error_code(exc)
    except Exception as exc:
        connection_manager.log_action_end(aid, success=False, error=str(exc))
        connection_manager.log_action(f"Exception getDataValues {obj_ref}: {exc}", "error")
        return jsonify({"error": str(exc)}), 500


@bp.post("/writevalue")
def api_write_value():
    data = request_json()
    obj_ref = data.get("objRef")
    fc = normalize_fc(data.get("fc"))
    value = data.get("value")
    data_type = data.get("dataType", "unknown")
    if not obj_ref:
        return jsonify({"error": "objRef is required"}), 400
    if value is None:
        return jsonify({"error": "value is required"}), 400

    aid = connection_manager.log_action_start("setDataValues", {"ref": obj_ref, "fc": fc, "value": value})
    attr_name = obj_ref.split(".")[-1]
    formatted_value = format_value_for_write(value, data_type, attr_name)
    try:
        result = connection_manager.invoke(
            lambda client, _endpoint, ws_info: client.set_data_values(obj_ref, fc, formatted_value, ws_info, None, None),
            timeout=10,
        )
        if isinstance(result, str) and "error" in result.lower():
            connection_manager.log_action_end(aid, success=False, error=result)
            return jsonify({"error": result}), 400
        connection_manager.log_action_end(aid, success=True)
        return jsonify({"success": True, "objRef": obj_ref, "fc": fc})
    except RuntimeError as exc:
        connection_manager.log_action_end(aid, success=False, error=str(exc))
        connection_manager.log_action(f"Error setDataValues {obj_ref}: {exc}", "error")
        return jsonify({"error": str(exc)}), error_code(exc)
    except Exception as exc:
        connection_manager.log_action_end(aid, success=False, error=str(exc))
        connection_manager.log_action(f"Exception setDataValues {obj_ref}: {exc}", "error")
        return jsonify({"error": str(exc)}), 500


@bp.post("/getfcs")
def api_get_fcs():
    data = request_json()
    obj_ref = data.get("objRef")
    if not obj_ref:
        return jsonify({"error": "objRef is required"}), 400

    aid = connection_manager.log_action_start("getDataDirectory", {"ref": obj_ref})
    try:
        result = connection_manager.invoke(
            lambda client, _endpoint, ws_info: client.get_data_directory(obj_ref, ws_info),
            timeout=10,
        )
        if isinstance(result, str):
            definition = connection_manager.invoke(
                lambda client, _endpoint, ws_info: client.get_data_definition(obj_ref, ws_info, None, None),
                timeout=10,
            )
            if isinstance(definition, dict):
                attributes = definition.get("dataAttributes") or definition.get("dataAttributeDefinition") or []
                fallback = sorted(
                    {
                        (item.get("fc") or "").lower()
                        for item in attributes
                        if isinstance(item, dict) and item.get("fc")
                    }
                )
                if fallback:
                    result = fallback
        if isinstance(result, str):
            connection_manager.log_action_end(aid, success=False, error=result)
            return jsonify({"error": result}), 400
        fcs = [fc.lower() if isinstance(fc, str) else fc for fc in result] if isinstance(result, list) else []
        connection_manager.log_action_end(aid, success=True, extra_detail={"fcs": len(fcs)})
        return jsonify({"success": True, "objRef": obj_ref, "fcs": fcs})
    except RuntimeError as exc:
        connection_manager.log_action_end(aid, success=False, error=str(exc))
        connection_manager.log_action(f"Error getDataDirectory {obj_ref}: {exc}", "error")
        return jsonify({"error": str(exc)}), error_code(exc)
    except Exception as exc:
        connection_manager.log_action_end(aid, success=False, error=str(exc))
        connection_manager.log_action(f"Exception getDataDirectory {obj_ref}: {exc}", "error")
        return jsonify({"error": str(exc)}), 500
