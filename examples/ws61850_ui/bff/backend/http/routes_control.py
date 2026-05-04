import time

from flask import Blueprint, jsonify

from bff.backend.context import connection_manager
from bff.backend.http.utils import error_code, request_json
from bff.protocol_utils import convert_bytes_to_hex, format_typed_value
from ws61850.iec61850.client.iec61850_client import IEC61850Client

bp = Blueprint("control", __name__)


@bp.post("/rcb/values")
def api_get_rcb_values():
    data = request_json()
    rcb_ref = data.get("rcbRef")
    rcb_type = data.get("rcbType")
    if not rcb_ref or not rcb_type:
        return jsonify({"error": "rcbRef and rcbType required"}), 400

    try:
        if rcb_type == "BRCB":
            result = connection_manager.invoke(
                lambda client, _endpoint, ws_info: client.get_BRCB_values(rcb_ref, ws_info, None, None),
                timeout=10,
            )
        elif rcb_type == "URCB":
            result = connection_manager.invoke(
                lambda client, _endpoint, ws_info: client.get_URCB_values(rcb_ref, ws_info, None, None),
                timeout=10,
            )
        else:
            return jsonify({"error": f"Invalid rcbType: {rcb_type}"}), 400

        enabled = result.get("RptEna", result.get("rptEna", False)) if isinstance(result, dict) else False
        return jsonify({"values": convert_bytes_to_hex(result), "enabled": enabled})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), error_code(exc)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.post("/rcb/set")
def api_set_rcb_values():
    data = request_json()
    rcb_ref = data.get("rcbRef")
    rcb_type = data.get("rcbType")
    values = data.get("values", {})
    if not rcb_ref or not rcb_type:
        return jsonify({"error": "rcbRef and rcbType required"}), 400

    is_buffered = rcb_type == "BRCB"
    if rcb_type not in {"BRCB", "URCB"}:
        return jsonify({"error": f"Invalid rcbType: {rcb_type}"}), 400

    rcb_block = IEC61850Client.ClientReportControlBlock(rcb_ref, is_buffered)
    field_mapping = {
        "RptEna": "rptEna",
        "DatSet": "dataSet",
        "dataSet": "dataSet",
        "DataSet": "dataSet",
        "datSet": "dataSet",
        "IntgPd": "intgPd",
        "GI": "gi",
        "PurgeBuf": "purgeBuf",
        "OptFlds": "optFlds",
        "TrgOps": "trgOps",
    }
    for frontend_name, backend_name in field_mapping.items():
        if frontend_name in values:
            setattr(rcb_block, backend_name, values[frontend_name])
    if getattr(rcb_block, "dataSet", None) is None:
        for key, value in values.items():
            if isinstance(key, str) and key.lower() == "dataset":
                setattr(rcb_block, "dataSet", value)
                break

    try:
        if is_buffered:
            connection_manager.invoke(
                lambda client, _endpoint, ws_info: client.set_BRCB_values(rcb_block, ws_info, None, None),
                timeout=10,
            )
            result = connection_manager.invoke(
                lambda client, _endpoint, ws_info: client.get_BRCB_values(rcb_ref, ws_info, None, None),
                timeout=10,
            )
        else:
            connection_manager.invoke(
                lambda client, _endpoint, ws_info: client.set_URCB_values(rcb_block, ws_info, None, None),
                timeout=10,
            )
            result = connection_manager.invoke(
                lambda client, _endpoint, ws_info: client.get_URCB_values(rcb_ref, ws_info, None, None),
                timeout=10,
            )
        enabled = result.get("RptEna", result.get("rptEna", False)) if isinstance(result, dict) else False
        return jsonify(
            {
                "values": convert_bytes_to_hex(result),
                "enabled": enabled,
                "dataSetApplied": getattr(rcb_block, "dataSet", None),
            }
        )
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), error_code(exc)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.post("/control/select")
def control_select():
    data = request_json()
    obj_ref = data.get("objRef")
    if not obj_ref:
        return jsonify({"error": "objRef is required"}), 400
    try:
        result = connection_manager.invoke(
            lambda client, _endpoint, ws_info: client.select(obj_ref, ws_info, None, None),
            timeout=30,
        )
        return jsonify({"success": True, "ctlNum": result if isinstance(result, int) else 0})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.post("/control/operate")
def control_operate():
    data = request_json()
    obj_ref = data.get("objRef")
    ctl_val = data.get("ctlVal")
    ctl_num = data.get("ctlNum", 0)
    origin = data.get("origin", {"orCat": 1, "orIdent": "0"})
    test = data.get("test", False)
    if not obj_ref:
        return jsonify({"error": "objRef is required"}), 400
    if ctl_val is None:
        return jsonify({"error": "ctlVal is required"}), 400

    formatted_ctl_val = ("enumerated", ctl_val) if isinstance(ctl_val, str) else format_typed_value(ctl_val, "unknown")
    origin_category_map = {
        0: "notSupported",
        1: "bayControl",
        2: "stationControl",
        3: "remoteControl",
        4: "automaticBay",
        5: "automaticStation",
        6: "automaticRemote",
        7: "maintenance",
        8: "process",
    }
    oper_val = {
        "ref": obj_ref,
        "ctlVal": formatted_ctl_val,
        "origin": {
            "orCat": (
                origin["orCat"] if isinstance(origin.get("orCat"), str) else origin_category_map.get(origin.get("orCat"), "bayControl")
            ),
            "orIdent": (
                origin.get("orIdent", "0").encode()
                if isinstance(origin.get("orIdent", "0"), str)
                else origin.get("orIdent", b"0")
            ),
        },
        "ctlNum": ctl_num,
        "t": {
            "secondSinceEpoch": int(time.time()),
            "fractionOfSecond": 0,
            "timeQuality": {
                "leapSecondsKown": False,
                "clockFailure": False,
                "clockNotSynchronized": False,
                "timeAccuracy": 0,
            },
        },
        "test": test,
        "check": {"synchroCheck": False, "interlockCheck": False},
    }

    try:
        result = connection_manager.invoke(
            lambda client, _endpoint, ws_info: client.operate(oper_val, ws_info, None, None),
            timeout=30,
        )
        return jsonify({"success": True, "result": str(result)})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@bp.post("/control/cancel")
def control_cancel():
    data = request_json()
    obj_ref = data.get("objRef")
    if not obj_ref:
        return jsonify({"error": "objRef is required"}), 400

    try:
        client, _endpoint, _ws_info, _loop = connection_manager.ensure_connection(timeout=10)
        if not hasattr(client, "cancel"):
            return jsonify({"error": "Cancel operation not yet implemented"}), 501
        connection_manager.invoke(
            lambda client, _endpoint, ws_info: client.cancel(obj_ref, ws_info, None, None),
            timeout=30,
        )
        return jsonify({"success": True})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
