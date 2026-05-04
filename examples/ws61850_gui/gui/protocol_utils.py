from typing import Any


def convert_bytes_to_hex(obj: Any) -> Any:
    if isinstance(obj, bytes):
        return obj.hex()
    if isinstance(obj, dict):
        return {key: convert_bytes_to_hex(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [convert_bytes_to_hex(item) for item in obj]
    if isinstance(obj, tuple):
        return tuple(convert_bytes_to_hex(item) for item in obj)
    return obj


def parse_nested_structure(struct_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parsed = []
    for component in struct_list:
        if not isinstance(component, dict):
            continue
        name = component.get("cmpName")
        cmp_type = component.get("cmpType")
        if not name:
            continue
        sub_attr = {
            "name": name,
            "hasStructure": False,
            "subAttributes": [],
            "type": None,
        }
        if isinstance(cmp_type, (list, tuple)) and len(cmp_type) >= 2:
            sub_attr["type"] = cmp_type[0]
            if cmp_type[0] == "structure" and isinstance(cmp_type[1], list):
                sub_attr["hasStructure"] = True
                sub_attr["subAttributes"] = parse_nested_structure(cmp_type[1])
        elif isinstance(cmp_type, str):
            sub_attr["type"] = cmp_type
        parsed.append(sub_attr)
    return parsed


def parse_da_structure(da_def: dict[str, Any]) -> dict[str, Any] | None:
    da_ref = da_def.get("daRef")
    if not da_ref:
        return None

    fc = da_def.get("fc", "mx")
    if fc:
        fc = fc.lower()

    result = {
        "daRef": da_ref,
        "hasStructure": False,
        "subAttributes": [],
        "type": None,
        "fc": fc,
    }

    da_type = da_def.get("daType")
    if isinstance(da_type, (list, tuple)) and len(da_type) >= 2:
        result["type"] = da_type[0]
        if da_type[0] == "structure" and isinstance(da_type[1], list):
            result["hasStructure"] = True
            result["subAttributes"] = parse_nested_structure(da_type[1])
    elif isinstance(da_type, str):
        result["type"] = da_type

    return result


def format_typed_value(value: Any, data_type: str) -> Any:
    if data_type == "boolean":
        return "boolean", bool(value)
    if data_type in {"int8", "int16", "int32", "int8u", "int16u", "int32u", "int64"}:
        return data_type, int(value)
    if data_type in {"float32", "float64"}:
        return data_type, float(value)
    if data_type in {
        "visString32",
        "visString64",
        "visString65",
        "visString129",
        "visString255",
        "string",
        "enumerated",
    }:
        return data_type, str(value)
    if data_type == "octetString":
        if isinstance(value, str) and value.startswith("0x"):
            return "octetString", bytes.fromhex(value[2:])
        return "octetString", value.encode() if isinstance(value, str) else value
    if data_type == "timeStamp":
        if isinstance(value, int):
            return (
                "timeStamp",
                {
                    "secondSinceEpoch": value,
                    "fractionOfSecond": 0,
                    "timeQuality": {
                        "leapSecondsKown": False,
                        "clockFailure": False,
                        "clockNotSynchronized": False,
                        "timeAccuracy": 0,
                    },
                },
            )
        return "timeStamp", value
    if isinstance(value, bool):
        return "boolean", value
    if isinstance(value, int):
        return "int32", value
    if isinstance(value, float):
        return "float32", value
    if isinstance(value, str):
        return "visString255", value
    return data_type, value


def format_value_for_write(value: Any, data_type: str, attr_name: str) -> list[dict[str, Any]]:
    return [{"name": attr_name, "data": format_typed_value(value, data_type)}]
