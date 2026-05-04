from flask import Blueprint, jsonify

from gui.backend.context import connection_manager, model_service
from gui.backend.http.utils import describe_connection_error, error_code
from gui.protocol_utils import parse_da_structure

bp = Blueprint("model", __name__)


@bp.get("/dodef/<ld_inst>/<ln_inst>/<path:do_path>")
def api_do_definition(ld_inst: str, ln_inst: str, do_path: str):
    obj_ref = f"{ld_inst}/{ln_inst}.{do_path}" if do_path else f"{ld_inst}/{ln_inst}"
    aid = connection_manager.log_action_start("getDataDefinition", {"ref": obj_ref})
    try:
        definition = connection_manager.invoke(
            lambda client, _endpoint, ws_info: client.get_data_definition(obj_ref, ws_info, None, None),
            timeout=10,
        )
        if not isinstance(definition, dict):
            connection_manager.log_action_end(aid, success=True, extra_detail={"subDO": 0, "DA": 0})
            return jsonify({"subDataObjects": [], "dataAttributes": []})

        sub_defs = definition.get("subDataDefinition") or []
        da_defs = definition.get("dataAttributeDefinition") or []
        sub_data_objects = [
            {"name": sub.get("name"), "cdc": sub.get("cdc")}
            for sub in sub_defs
            if isinstance(sub, dict) and sub.get("name")
        ]
        data_attributes = [parsed for item in da_defs if isinstance(item, dict) if (parsed := parse_da_structure(item))]
        connection_manager.log_action_end(
            aid,
            success=True,
            extra_detail={"subDO": len(sub_data_objects), "DA": len(data_attributes)},
        )
        return jsonify({"subDataObjects": sub_data_objects, "dataAttributes": data_attributes})
    except RuntimeError as exc:
        connection_manager.log_action_end(aid, success=False, error=str(exc))
        connection_manager.log_action(f"Error getDataDefinition {obj_ref}: {exc}", "error")
        return jsonify({"error": str(exc)}), error_code(exc)
    except Exception as exc:
        connection_manager.log_action_end(aid, success=False, error=str(exc))
        connection_manager.log_action(f"Exception getDataDefinition {obj_ref}: {exc}", "error")
        return jsonify({"error": str(exc)}), 500


@bp.get("/model")
def api_model():
    try:
        connection_manager.ensure_connection()
    except Exception as exc:
        detail = describe_connection_error(exc, connection_manager.status())
        connection_manager.log_action(f"Model fetch unavailable: {detail}", "warn")
        return jsonify({"status": "error", "error": detail, "detail": {"connection": connection_manager.status()}}), 503

    status, data, error, progress = model_service.get_cached_response()
    if status == "ready" and data:
        return jsonify({"status": "ready", "model": data})
    if status == "error":
        return jsonify({"status": "error", "error": error}), 500
    if status == "idle":
        status = model_service.start_build_if_needed()
        _, _, _, progress = model_service.get_cached_response()
    return jsonify({"status": status, "progress": progress})


@bp.post("/model/rebuild")
def api_model_rebuild():
    try:
        connection_manager.ensure_connection()
    except Exception as exc:
        detail = describe_connection_error(exc, connection_manager.status())
        connection_manager.log_action(f"Model rebuild unavailable: {detail}", "warn")
        return jsonify({"status": "error", "error": detail, "detail": {"connection": connection_manager.status()}}), 503
    model_service.reset()
    return jsonify({"status": model_service.start_build_if_needed()})


@bp.get("/ld/<ld_inst>")
def api_ld(ld_inst: str):
    try:
        logical_nodes = connection_manager.invoke(
            lambda client, _endpoint, ws_info: client.get_logical_device_directory(ld_inst, ws_info, None, None),
            timeout=10,
        )
        return jsonify({"ld": {"logicalNodes": logical_nodes}, "source": "live"})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), error_code(exc)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.get("/ln/<ld_inst>/<ln_inst>")
def api_ln(ld_inst: str, ln_inst: str):
    try:
        return jsonify({"ln": model_service.get_ln_details(ld_inst, ln_inst), "source": "live"})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), error_code(exc)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
