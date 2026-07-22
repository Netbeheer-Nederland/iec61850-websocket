"""Core IEC 61850 WebSocket server module with ACSI operations.

This module handles:
- WebSocket endpoint lifecycle management
- IEC 61850 server instantiation and control
- Model loading and caching
- Async event loop management
"""

from __future__ import annotations

import asyncio
from concurrent.futures import TimeoutError as FuturesTimeoutError
import importlib
import json
import os
import sys
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from random import randint
from typing import Any, Callable, Dict, List, Optional
import asyncio
import logging
logger = logging.getLogger(__name__)
from concurrent.futures import TimeoutError as FuturesTimeoutError
import json
import threading
import time
from collections import deque
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from ws61850.endpoint import PassiveEndpoint
from ws61850.iec61850.data_model.ied_model import DataAttribute, DataObject, IedModel
from ws61850.iec61850.server.iec61850_server import IEC61850Server


class ACSIServerRuntime:
    """Manages IEC 61850 WebSocket server runtime state and lifecycle."""

    def __init__(self):
        self.status: str = "stopped"  # stopped|starting|listening|stopping|error
        self.host: str = "localhost"
        self.port: int = 8765
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.thread: Optional[threading.Thread] = None
        self.endpoint: Optional[Any] = None
        self.server_cp: Optional[IEC61850Server] = None
        self.tasks: Dict[str, asyncio.Task] = {}
        self.error: Optional[str] = None
        self.actions: deque = deque(maxlen=200)
        self.messages: deque = deque(maxlen=500)
        self.action_seq: int = 0
        self.message_seq: int = 0
        self.ied_model: Optional[IedModel] = None
        self.model_ied_name: Optional[str] = None
        self.model_source: Optional[str] = None
        self.cp: str = "cp1"
        self.last_status_log_signature: Optional[tuple] = None
        self.lock: threading.Lock = threading.Lock()
        
        # Callbacks for message logging
        self.recv_msg_callback: Optional[Callable] = None
        self.send_msg_callback: Optional[Callable] = None


class ACSIServer:
    """IEC 61850 WebSocket server controller."""

    def __init__(self, factory_dir: Path):
        self.runtime = ACSIServerRuntime()
        self.factory_dir = factory_dir
        self.model_file = factory_dir / "model.py"

        # Ensure `import model` resolves to the expected fsp/model.py directory.
        if str(self.factory_dir) not in sys.path:
            sys.path.insert(0, str(self.factory_dir))

        if not self.model_file.exists():
            raise FileNotFoundError(
                f"Model file not found: {self.model_file}. "
                "Create model.py in the fsp directory before starting the server."
            )

        ied_model = self.load_current_runtime_model()
        self._set_runtime_state(
            ied_model=ied_model,
            model_source=str(self.model_file),
            model_ied_name=ied_model.name,
        )

    def load_current_runtime_model(self) -> IedModel:
        """Load the current runtime model from model.py."""
        if not self.model_file.exists():
            raise FileNotFoundError(f"Model file not found: {self.model_file}")

        importlib.invalidate_caches()
        if "model" in sys.modules:
            model_module = importlib.reload(sys.modules["model"])
        else:
            model_module = importlib.import_module("model")

        ied = getattr(model_module, "ied", None)
        if ied is None and hasattr(model_module, "build_ied_model"):
            ied = model_module.build_ied_model()
        if ied is None:
            raise RuntimeError("model.py does not define variable 'ied' or build_ied_model()")
        if not isinstance(ied, IedModel):
            raise RuntimeError("Runtime model is not an IedModel instance")
        return ied

    def update_model_file(self, model_source: str) -> IedModel:
        """Update model.py and reload runtime model. Reverts on validation failure."""
        if not isinstance(model_source, str) or not model_source.strip():
            raise ValueError("modelPy must be a non-empty string")

        previous_content = self.model_file.read_text(encoding="utf-8") if self.model_file.exists() else None
        self.model_file.write_text(model_source, encoding="utf-8")

        try:
            ied_model = self.load_current_runtime_model()
        except Exception:
            if previous_content is not None:
                self.model_file.write_text(previous_content, encoding="utf-8")
            raise

        self._set_runtime_state(
            ied_model=ied_model,
            model_source=str(self.model_file),
            model_ied_name=ied_model.name,
        )
        return ied_model

    def _log_action(
        self, message: str, level: str = "info", detail: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log an action to the runtime actions deque."""
        if detail is None:
            detail = {}
        with self.runtime.lock:
            self.runtime.action_seq += 1
            self.runtime.actions.append(
                {
                    "id": self.runtime.action_seq,
                    "time": time.strftime("%H:%M:%S"),
                    "level": level,
                    "message": message,
                    "detail": detail,
                }
            )

    def _extract_message_meta(self, raw: str) -> Dict[str, str]:
        """Extract metadata from a message (service type, category)."""
        service_type = "unknown"
        category = "unknown"
        try:
            msg = json.loads(raw)
            if not isinstance(msg, dict):
                return {"service_type": service_type, "category": category}

            if "request" in msg:
                category = "request"
                service = msg.get("request", {}).get("service", {})
                if isinstance(service, dict) and service:
                    service_type = next(iter(service.keys()))
            elif "response" in msg:
                category = "response"
                service = msg.get("response", {}).get("service", {})
                if isinstance(service, dict) and service:
                    service_type = next(iter(service.keys()))
            elif "associate" in msg:
                category = "associate"
                service = msg.get("associate", {}).get("service", {})
                if isinstance(service, dict) and service:
                    service_type = next(iter(service.keys()))
            elif "unconfirmed" in msg:
                category = "unconfirmed"
                service = msg.get("unconfirmed", {}).get("service", {})
                if isinstance(service, dict) and service:
                    service_type = next(iter(service.keys()))
        except Exception:
            service_type = "parse-error"
            category = "parse-error"

        return {"service_type": service_type, "category": category}

    def _log_message(self, direction: str, message: Any, timestamp: Any) -> None:
        """Log a message (request/response) to the runtime messages deque."""
        if isinstance(message, bytes):
            text = message.decode("utf-8", errors="replace")
        else:
            text = str(message)

        if isinstance(timestamp, datetime):
            ts = timestamp.strftime("%H:%M:%S.%f")[:-3]
        else:
            ts = time.strftime("%H:%M:%S")

        meta = self._extract_message_meta(text)
        with self.runtime.lock:
            self.runtime.message_seq += 1
            self.runtime.messages.append(
                {
                    "id": self.runtime.message_seq,
                    "timestamp": ts,
                    "direction": direction,
                    "service_type": meta["service_type"],
                    "category": meta["category"],
                    "message": text,
                    "preview": text[:220] + ("..." if len(text) > 220 else ""),
                }
            )

    async def _toggle_custom_value(self, server: IEC61850Server, obj_ref: str) -> None:
        """Periodically update a value for demo purposes."""
        while True:
            value = randint(1, 5)
            await server.update_value(obj_ref, value)
            self._log_action(f"{obj_ref} updated to {value}")
            await asyncio.sleep(5)

    def _set_runtime_state(self, **kwargs: Any) -> None:
        """Atomically update runtime state."""
        with self.runtime.lock:
            for key, value in kwargs.items():
                setattr(self.runtime, key, value)

    def _validate_port(self, port: int) -> None:
        """Validate port number."""
        if port < 1 or port > 65535:
            raise ValueError("Port must be in range 1..65535")

        # On POSIX systems, binding to ports < 1024 requires elevated privileges.
        if os.name != "nt" and port < 1024:
            raise PermissionError(
                f"Port {port} is privileged on this runtime. Use a port >= 1024 or run with elevated privileges."
            )

    async def _stop_server_async(self) -> None:
        """Stop the server asynchronously."""
        endpoint = self.runtime.endpoint
        tasks = self.runtime.tasks or {}

        self._log_action("Stopping server tasks...")

        for task in tasks.values():
            if task and not task.done():
                task.cancel()

        if tasks:
            await asyncio.gather(*tasks.values(), return_exceptions=True)

        if endpoint is not None:
            try:
                await endpoint.stop_passive()
            except Exception as exc:
                self._log_action(f"stop_passive error: {exc}", "warn")

        self._set_runtime_state(
            endpoint=None,
            server_cp=None,
            tasks={},
            status="stopped",
            error=None,
        )

        self._log_action("Server stopped")
        asyncio.get_running_loop().call_soon(asyncio.get_running_loop().stop)

    async def _start_server_async(self, host: str, port: int) -> None:
        """Start the server asynchronously."""
        # Prefer the model already in runtime (freshly loaded from SCL/model.py)
        # Only reload from file as fallback if runtime model is missing
        ied_model = self.runtime.ied_model

        if ied_model is None:
            try:
                print("[_start_server_async] No model in runtime, loading from file...")
                ied_model = self.load_current_runtime_model()
            except FileNotFoundError:
                print("[_start_server_async] Model file not found")
                raise RuntimeError("No model loaded. Create fsp/model.py first.")
        else:
            print(
                f"[_start_server_async] Using model from runtime: "
                f"ied_model.name={ied_model.name!r} "
                f"model_ied_name={self.runtime.model_ied_name!r}"
            )

        if ied_model is None:
            raise RuntimeError("No model loaded. Create fsp/model.py first.")

        self._set_runtime_state(
            ied_model=ied_model,
            model_source=self.runtime.model_source or str(self.model_file),
            model_ied_name=ied_model.name,
            cp=self.runtime.cp or "cp1",
        )

        endpoint = self._create_endpoint()
        endpoint.recv_msg_callback = lambda msg, ts: self._log_message("recv", msg, ts)
        endpoint.send_msg_callback = lambda msg, ts: self._log_message("send", msg, ts)
        
        cp = self.runtime.cp or "cp1"
        server = IEC61850Server(ied_model, cp)

        server.send_msg_callback = endpoint.send_msg_callback
        server.recv_msg_callback = endpoint.recv_msg_callback

        endpoint.add_iec61850_server(server)

        report_task = asyncio.create_task(
            server.periodic_report_start(), name=f"{cp}-periodic-report"
        )
        tasks: Dict[str, asyncio.Task] = {"report": report_task}

        if server.find_object_in_tree("LD0/DGEN1.DEROpSt.stVal") is not None:
            tasks["toggle"] = asyncio.create_task(
                self._toggle_custom_value(server, "LD0/DGEN1.DEROpSt.stVal"),
                name="toggle-value",
            )

        ws_task = asyncio.create_task(
            endpoint.start(host, port)
        )
        tasks["ws"] = ws_task

        self._set_runtime_state(
            endpoint=endpoint,
            server_cp=server,
            tasks=tasks,
            error=None,
        )

        # Give the event loop one cycle so the ws_task can actually bind the port
        # before we declare the server "listening".
        await asyncio.sleep(0)

        if self.runtime.status != "stopping":
            self._set_runtime_state(status="listening")
            self._log_action("Server listening", detail={"host": host, "port": port, "cps": [cp]})

        try:
            await asyncio.gather(*tasks.values())
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self._set_runtime_state(status="error", error=str(exc))
            self._log_action(f"Server runtime error: {exc}", "error")
            raise

    def _create_endpoint(self):
        """Create a WebSocket endpoint (can be overridden for testing)."""
        return PassiveEndpoint(is_direct=True)

    def _event_loop_thread(self, host: str, port: int) -> None:
        """Run the event loop in a separate thread."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._set_runtime_state(loop=loop)

        startup_task = loop.create_task(self._start_server_async(host, port), name="server-startup")

        def _on_startup_done(task: asyncio.Task) -> None:
            try:
                task.result()
            except asyncio.CancelledError:
                return
            except Exception as exc:
                self._set_runtime_state(status="error", error=str(exc))
                self._log_action(f"Startup failed: {exc}", "error")
                loop.call_soon_threadsafe(loop.stop)

        startup_task.add_done_callback(_on_startup_done)

        try:
            loop.run_forever()
        finally:
            pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()
            self._set_runtime_state(loop=None, thread=None)

    def start_server(self, host: str, port: int) -> None:
        """Start the server in a background thread."""
        self._validate_port(port)

        with self.runtime.lock:
            status = self.runtime.status
            if status in ("starting", "listening"):
                raise RuntimeError("Server is already running")
            self.runtime.status = "starting"
            self.runtime.host = host
            self.runtime.port = port
            self.runtime.error = None

        t = threading.Thread(target=self._event_loop_thread, args=(host, port), daemon=True)
        self._set_runtime_state(thread=t)
        t.start()
        self._log_action("Server startup initiated", detail={"host": host, "port": port})

    def stop_server(self) -> None:
        """Stop the server."""
        loop = self.runtime.loop
        status = self.runtime.status

        if status in (None, "stopped"):
            self._set_runtime_state(status="stopped")
            return

        if loop is None or not loop.is_running():
            # If the event loop is already gone, consider the server stopped.
            self._set_runtime_state(
                status="stopped", endpoint=None, server_cp=None, tasks={}, error=None
            )
            return

        self._set_runtime_state(status="stopping")
        fut = asyncio.run_coroutine_threadsafe(self._stop_server_async(), loop)
        try:
            fut.result(timeout=10)
        except FuturesTimeoutError:
            # Avoid surfacing 500 to UI when shutdown is still unwinding.
            self._log_action("Stop in progress (timeout waiting for shutdown).", "warn")
        except Exception:
            # If stop is already in progress or completed, avoid hard failure.
            current = self.runtime.status
            if current not in ("stopping", "stopped"):
                raise

    def invoke_on_runtime_loop(self, coro: Any, timeout: int = 10) -> Any:
        """Execute a coroutine on the runtime event loop."""
        loop = self.runtime.loop
        if loop is None or not loop.is_running():
            raise RuntimeError("server-not-running")
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)

    def coerce_server_write_value(self, value: Any, data_type: str) -> Any:
        """Coerce a value to the appropriate data type."""
        dt = str(data_type or "").lower()

        if dt == "boolean":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "yes", "on")
            return bool(value)

        if dt in ("int8", "int16", "int32", "int64", "int8u", "int16u", "int32u"):
            return int(value)

        if dt in ("float32", "float64"):
            return float(value)

        if dt in (
            "visstring32",
            "visstring64",
            "visstring65",
            "visstring129",
            "visstring255",
            "string",
            "enumerated",
        ):
            if dt == "enumerated":
                return int(value)
            return str(value)

        return value

    def read_value(self, obj_ref: str) -> Dict[str, Any]:
        """Read a value from the server."""
        server = self.runtime.server_cp
        if server is None:
            raise RuntimeError("Server is not running")

        result = self.invoke_on_runtime_loop(server.read_value(obj_ref), timeout=10)
        #result = server.read_value(obj_ref)

        if result is None:
            raise ValueError(f"instanceNotAvailable: {obj_ref}")

        return result

    def write_value(self, obj_ref: str, value: Any, data_type: str = "unknown") -> Dict[str, Any]:
        """Write a value to the server."""
        server = self.runtime.server_cp
        if server is None:
            raise RuntimeError("Server is not running")

        item = server.find_object_in_tree(obj_ref)
        if item is None:
            raise ValueError(f"instanceNotAvailable: {obj_ref}")

        resolved_data_type = data_type
        if (
            str(data_type or "").lower() in ("", "unknown")
            and isinstance(item, DataAttribute)
            and item.type is not None
        ):
            resolved_data_type = item.type.name

        coerced_value = self.coerce_server_write_value(value, resolved_data_type)
        self.invoke_on_runtime_loop(server.update_value(obj_ref, coerced_value), timeout=10)
        #server.update_value(obj_ref, coerced_value)

        try:
            server.update_timestamp(item)
        except Exception:
            # Not all items have an associated timestamp DA; ignore if missing.
            pass

        return {
            "objRef": obj_ref,
            "value": coerced_value,
            "dataType": resolved_data_type,
        }

    def get_status(self) -> Dict[str, Any]:
        """Get current server status."""
        endpoint = self.runtime.endpoint
        connected = len(endpoint.websocket_info_list) if endpoint is not None else 0
        tasks = self.runtime.tasks or {}

        return {
            "status": self.runtime.status,
            "host": self.runtime.host,
            "port": self.runtime.port,
            "error": self.runtime.error,
            "connectedClients": connected,
            "tasks": {k: (not v.done()) for k, v in tasks.items()},
            "accessPoints": [self.runtime.cp or "cp1"],
        }

    def get_actions(self) -> List[Dict[str, Any]]:
        """Get logged actions."""
        with self.runtime.lock:
            return list(self.runtime.actions)

    def get_messages(self) -> List[Dict[str, Any]]:
        """Get logged messages."""
        with self.runtime.lock:
            return list(self.runtime.messages)

    def clear_actions(self) -> None:
        """Clear action log."""
        with self.runtime.lock:
            self.runtime.actions.clear()

    def clear_messages(self) -> None:
        """Clear message log."""
        with self.runtime.lock:
            self.runtime.messages.clear()
