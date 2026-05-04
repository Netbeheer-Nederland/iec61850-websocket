import asyncio
import json
import logging
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any

from gui.connection.profile import ApplicationRole, ConnectionProfile
from gui.connection.runtime import ConnectionRuntime
from gui.connection.security import SecurityFactory
from gui.protocol_utils import convert_bytes_to_hex
from gui.state import RuntimeState
from ws61850.endpoint.endpoint import WebSocketEndpoint, WebSocketInfo
from ws61850.iec61850.client.iec61850_client import IEC61850Client
from ws61850.iec61850.data_model.example_ieds import build_model1, build_model2
from ws61850.iec61850.server.iec61850_server import IEC61850Server

logger = logging.getLogger(__name__)

DEFAULT_TARGET = "server-client"
KNOWN_TARGETS = ("server-client", "client-server")
TARGET_ALIASES = {
    "server-client": "server-client",
    "serverClient": "server-client",
    "client-server": "client-server",
    "clientServer": "client-server",
}


def _build_default_ied_model(cp: str):
    if cp == "cp2":
        return build_model2()
    return build_model1()


def create_default_server(cp: str) -> IEC61850Server:
    return IEC61850Server(_build_default_ied_model(cp), cp)


class ConnectionManager:
    def __init__(
        self,
        state: RuntimeState,
        *,
        endpoint_cls: type[WebSocketEndpoint] = WebSocketEndpoint,
        client_cls: type[IEC61850Client] = IEC61850Client,
        server_factory: Callable[[str], IEC61850Server] | None = None,
        security_factory: SecurityFactory | None = None,
    ) -> None:
        self.endpoint_cls = endpoint_cls
        self.client_cls = client_cls
        self.server_factory = server_factory or create_default_server
        self.security_factory = security_factory or SecurityFactory()
        self.states: dict[str, RuntimeState] = {
            "server-client": state,
            "client-server": RuntimeState(),
        }
        self.state = self.states[DEFAULT_TARGET]
        self._runtimes: dict[str, ConnectionRuntime | None] = {target: None for target in KNOWN_TARGETS}
        self._action_serial = 0
        self._message_serial = 0

    def _normalize_target(self, target: str | None) -> str:
        if target is None:
            return DEFAULT_TARGET
        return TARGET_ALIASES.get(target, target)

    def _get_state(self, target: str | None) -> RuntimeState:
        normalized = self._normalize_target(target)
        if normalized not in self.states:
            self.states[normalized] = RuntimeState()
            self._runtimes[normalized] = None
        return self.states[normalized]

    def _next_action_serial(self) -> int:
        self._action_serial += 1
        return self._action_serial

    def _next_message_serial(self) -> int:
        self._message_serial += 1
        return self._message_serial

    def log_action(self, message: str, level: str = "info", *, target: str | None = None) -> None:
        state = self._get_state(target)
        ts = time.strftime("%H:%M:%S")
        with state.actions_lock:
            action_id = self._next_action_serial()
            state.action_seq = action_id
            state.actions.append(
                {
                    "id": action_id,
                    "target": self._normalize_target(target),
                    "time": ts,
                    "level": level,
                    "message": message,
                    "op": None,
                    "status": "done",
                    "start_ts": ts,
                    "end_ts": ts,
                    "duration_ms": 0,
                    "detail": {},
                }
            )

    def log_action_start(
        self,
        op: str,
        detail: dict[str, Any] | None = None,
        level: str = "info",
        *,
        target: str | None = None,
    ) -> int:
        state = self._get_state(target)
        detail = detail or {}
        start_wall = time.strftime("%H:%M:%S")
        entry = {
            "id": self._next_action_serial(),
            "target": self._normalize_target(target),
            "op": op,
            "detail": detail,
            "time": start_wall,
            "start_ts": start_wall,
            "end_ts": None,
            "level": level,
            "status": "in-progress",
            "message": f"{op} start",
            "perf_start": time.perf_counter(),
            "duration_ms": None,
        }
        with state.actions_lock:
            state.action_seq = entry["id"]
            state.actions.append(entry)
        return entry["id"]

    def log_action_end(
        self,
        aid: int | None,
        success: bool = True,
        error: str | None = None,
        extra_detail: dict[str, Any] | None = None,
        *,
        target: str | None = None,
    ) -> None:
        if aid is None:
            self.log_action("connect completion missing action id", "warn", target=target)
            return
        state = self._get_state(target)
        missing = False
        with state.actions_lock:
            entry = next((item for item in reversed(state.actions) if item.get("id") == aid), None)
            if entry is None:
                missing = True
            else:
                perf_start = entry.pop("perf_start", None)
                duration_ms = int((time.perf_counter() - perf_start) * 1000) if perf_start is not None else None
                entry["end_ts"] = time.strftime("%H:%M:%S")
                entry["duration_ms"] = duration_ms
                if extra_detail:
                    entry["detail"].update(extra_detail)
                if success:
                    entry["status"] = "done"
                    entry["message"] = (
                        f"{entry['op']} ok ({duration_ms} ms)" if duration_ms is not None else f"{entry['op']} ok"
                    )
                else:
                    entry["status"] = "error"
                    entry["level"] = "error"
                    entry["message"] = f"{entry['op']} error: {error}"
        if missing:
            self.log_action(f"{aid} completion missing (success={success})", "warn", target=target)

    def _process_report_message(self, report: dict[str, Any], *, target: str | None = None) -> None:
        state = self._get_state(target)
        if not isinstance(report, dict):
            return
        entry = report.get("entry")
        if not isinstance(entry, dict):
            return
        entry_data_list = entry.get("entryData", [])
        if not isinstance(entry_data_list, list):
            return
        updates = []
        for entry_data in entry_data_list:
            if not isinstance(entry_data, dict):
                continue
            data_ref = entry_data.get("dataRef")
            values = entry_data.get("value")
            if not data_ref or values is None:
                continue
            updates.append({"dataRef": data_ref, "values": values, "timestamp": time.time()})
        if not updates:
            return
        with state.report_lock:
            state.report_updates.extend(updates)
            state.report_updates = state.report_updates[-100:]

    def log_message(self, direction: str, raw_message: str | bytes, timestamp: Any, *, target: str | None = None) -> None:
        state = self._get_state(target)
        service_type = "unknown"
        category = "unknown"
        message_preview = ""

        try:
            if isinstance(raw_message, bytes):
                raw_message = raw_message.decode("utf-8")
            msg_json = json.loads(raw_message)
            message_preview = raw_message[:200] + ("..." if len(raw_message) > 200 else "")
            if isinstance(msg_json, dict):
                for category_name in ("request", "response", "associate", "unconfirmed"):
                    payload = msg_json.get(category_name)
                    if not isinstance(payload, dict) or "service" not in payload:
                        continue
                    category = category_name
                    service = payload["service"]
                    if isinstance(service, dict):
                        service_type = next(iter(service.keys()), category_name)
                        if category_name == "unconfirmed" and "report" in service and direction == "recv":
                            self._process_report_message(service["report"], target=target)
                    else:
                        service_type = category_name
                    break
        except Exception:
            message_preview = str(raw_message)[:200]
            service_type = "parse-error"
            category = "parse-error"

        ts = timestamp.strftime("%H:%M:%S.%f")[:-3] if hasattr(timestamp, "strftime") else time.strftime("%H:%M:%S")
        message_text = raw_message if isinstance(raw_message, str) else raw_message.decode("utf-8", errors="replace")
        with state.messages_lock:
            message_id = self._next_message_serial()
            state.message_seq = message_id
            state.messages.append(
                {
                    "id": message_id,
                    "target": self._normalize_target(target),
                    "timestamp": ts,
                    "direction": direction,
                    "category": category,
                    "service_type": service_type,
                    "message": message_text,
                    "preview": message_preview,
                }
            )

    def start_connection(
        self,
        url: str,
        port: int,
        cp: Any,
        is_direct: bool = False,
        mode: str = "active",
        security: dict[str, Any] | None = None,
        *,
        application_role: ApplicationRole | None = None,
        profile: ConnectionProfile | None = None,
        target: str | None = None,
    ) -> None:
        profile = profile or ConnectionProfile.from_legacy(
            url=url,
            port=port,
            cp=cp,
            is_direct=is_direct,
            mode=mode,
            security=security,
            application_role=application_role,
        )
        resolved_target = target
        if resolved_target is None:
            resolved_target = profile.target if application_role is not None else DEFAULT_TARGET
        target = self._normalize_target(resolved_target)
        state = self._get_state(target)
        logger.info(
            "start_connection requested target=%s transport_role=%s application_role=%s host=%s port=%s cp=%s is_direct=%s",
            target,
            profile.transport_role,
            profile.application_role,
            profile.host,
            profile.port,
            profile.cp,
            profile.is_direct,
        )
        with state.state_lock:
            if self._runtimes.get(target) is not None or state.endpoint or state.loop or state.client or state.server:
                logger.warning("start_connection rejected: connection already active target=%s", target)
                raise RuntimeError("connection-already-active")
            state.connect_aid = self.log_action_start(
                "connect",
                {
                    "transportRole": profile.transport_role,
                    "applicationRole": profile.application_role,
                    "url": profile.host,
                    "port": profile.port,
                    "cp": profile.cp,
                },
                target=target,
            )
            state.cancel_connect = False
            state.manual_disconnect = False
            state.status = profile.ui_state
            state.mode = profile.endpoint_mode
            state.is_direct = profile.is_direct
            runtime = ConnectionRuntime(
                self,
                state,
                profile,
                target,
                endpoint_cls=self.endpoint_cls,
                client_cls=self.client_cls,
                server_factory=self.server_factory,
                security_factory=self.security_factory,
            )
            self._runtimes[target] = runtime
            thread = threading.Thread(target=self._run_runtime, args=(target, runtime), daemon=True)
            state.connection_thread = thread
        thread.start()

    def _run_runtime(self, target: str, runtime: ConnectionRuntime) -> None:
        try:
            asyncio.run(runtime.run())
        except Exception:
            logger.debug("runtime exited with propagated exception cp=%s target=%s", runtime.cp, target)

    def _clear_connection_refs(self, target: str, runtime: ConnectionRuntime, *, cleanup_files: bool) -> None:
        normalized = self._normalize_target(target)
        state = self._get_state(normalized)
        with state.state_lock:
            if self._runtimes.get(normalized) is runtime:
                self._runtimes[normalized] = None
            state.endpoint = None
            state.client = None
            state.server = None
            state.loop = None
            state.invoke_lock = None
            state.connection_thread = None
            state.endpoint_task = None
            state.token_refresh_task = None
            state.status = "not-connected"
            state.connect_aid = None
            state.connection_profile = None
            state.application_role = "iec_client"
            state.security_files.clear()
        if cleanup_files:
            runtime.security_context.cleanup()

    def _get_runtime(self, target: str | None) -> ConnectionRuntime | None:
        return self._runtimes.get(self._normalize_target(target))

    def ensure_connection(
        self, timeout: int = 10, *, target: str | None = None
    ) -> tuple[Any, WebSocketEndpoint, WebSocketInfo, asyncio.AbstractEventLoop]:
        runtime = self._get_runtime(target)
        if runtime is None:
            raise RuntimeError("not-connected")
        return runtime.ensure_connection(timeout=timeout)

    def invoke(
        self,
        coro_factory: Callable[[Any, WebSocketEndpoint, WebSocketInfo], Any],
        timeout: int = 10,
        *,
        locked: bool = True,
        target: str | None = None,
    ) -> Any:
        state = self._get_state(target)
        client, endpoint, ws_info, loop = self.ensure_connection(timeout=timeout, target=target)

        async def _runner() -> Any:
            lock = state.invoke_lock
            if locked and lock is not None:
                async with lock:
                    return await coro_factory(client, endpoint, ws_info)
            return await coro_factory(client, endpoint, ws_info)

        fut = asyncio.run_coroutine_threadsafe(_runner(), loop)
        return fut.result(timeout=timeout)

    def disconnect(self, *, target: str | None = None) -> str:
        runtime = self._get_runtime(target)
        if runtime is None:
            return "no-active-connection"
        return runtime.disconnect()

    def status(self, *, target: str | None = None) -> dict[str, Any]:
        runtime = self._get_runtime(target)
        if runtime is None:
            return {"state": "not-connected", "detail": {}}
        return runtime.status()

    def statuses(self) -> dict[str, dict[str, Any]]:
        return {target: self.status(target=target) for target in KNOWN_TARGETS}

    def clear_messages(self, *, target: str | None = None) -> None:
        if target is None:
            for runtime_state in self.states.values():
                with runtime_state.messages_lock:
                    runtime_state.messages.clear()
                    runtime_state.message_seq = 0
            return
        state = self._get_state(target)
        with state.messages_lock:
            state.messages.clear()
            state.message_seq = 0

    def set_message_retention(self, new_max: int, *, target: str | None = None) -> int:
        if new_max < 50 or new_max > 5000:
            raise ValueError("max out of allowed range (50-5000)")
        states = self.states.values() if target is None else [self._get_state(target)]
        for state in states:
            with state.messages_lock:
                existing = list(state.messages)
                if len(existing) > new_max:
                    existing = existing[-new_max:]
                state.messages = deque(existing, maxlen=new_max)
                state.messages_max = new_max
        return new_max

    def drain_report_updates(self, *, target: str | None = None) -> list[dict[str, Any]]:
        state = self._get_state(target)
        with state.report_lock:
            updates = list(state.report_updates)
            state.report_updates.clear()
        return updates

    def snapshot_actions(self, *, target: str | None = None) -> list[dict[str, Any]]:
        if target is not None:
            state = self._get_state(target)
            with state.actions_lock:
                return list(state.actions)
        items: list[dict[str, Any]] = []
        for state in self.states.values():
            with state.actions_lock:
                items.extend(list(state.actions))
        return sorted(items, key=lambda item: item.get("id", 0))

    def snapshot_messages(self, *, target: str | None = None) -> list[dict[str, Any]]:
        if target is not None:
            state = self._get_state(target)
            with state.messages_lock:
                return list(state.messages)
        items: list[dict[str, Any]] = []
        for state in self.states.values():
            with state.messages_lock:
                items.extend(list(state.messages))
        return sorted(items, key=lambda item: item.get("id", 0))

    def transform_result(self, result: Any) -> Any:
        return convert_bytes_to_hex(result)
