from typing import Any

from flask import request


def request_json() -> dict[str, Any]:
    return request.get_json(silent=True) or {}


def error_code(exc: RuntimeError) -> int:
    return 503 if str(exc) in {"not-connected", "no-websocket-info"} else 500


def describe_connection_error(exc: Exception, status: dict[str, Any] | None = None) -> str:
    raw = str(exc)
    state = (status or {}).get("state")

    if raw == "not-connected":
        if state == "listening":
            return (
                "Model rebuild requires an active IEC 61850 association. "
                "The WebSocket service is listening, but no client has connected yet."
            )
        if state == "connecting":
            return (
                "Model rebuild requires an active IEC 61850 association. "
                "The WebSocket client is still connecting."
            )
        if state == "starting":
            return (
                "Model rebuild requires an active IEC 61850 association. "
                "The WebSocket session is starting but not ready yet."
            )
        return (
            "Model rebuild requires an active IEC 61850 association. "
            "No active WebSocket connection is available."
        )

    if raw == "no-websocket-info":
        return (
            "Model rebuild could not resolve WebSocket session metadata for the current IEC 61850 association."
        )

    return raw


def normalize_fc(fc: Any, default: str = "mx") -> str:
    value = fc or default
    return value.lower() if isinstance(value, str) else default
