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

from ws61850.endpoint import ActiveEndpoint
from ws61850.iec61850.data_model.ied_model import DataAttribute, IedModel
from ws61850.iec61850.server.iec61850_server import IEC61850Server
from ws61850.iec61850.server.control_handling import ControlHandlerResult, ControlServiceStatusKind
from ws61850.iec61850.server.service_error import ServiceStatusKind



class ACSIServerRuntime:
    """Manages IEC 61850 WebSocket server runtime state and lifecycle."""

    def __init__(self):
        self.endpoint = None
        self.server = None
        self.status: str = "stopped"  # stopped|starting|listening|stopping|error|reloading
        self.host: str = "localhost"
        self.port: int = 8765
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.thread: Optional[threading.Thread] = None
        self.tasks: Dict[str, asyncio.Task] = {}
        self.error: Optional[str] = None
        self.actions: deque = deque(maxlen=200)
        self.messages: deque = deque(maxlen=500)
        self.action_seq: int = 0
        self.message_seq: int = 0
        self.ied_model: Optional[IedModel] = None
        self.model_ied_name: Optional[str] = None
        self.model_source: Optional[str] = None
        self.cp: str =  os.getenv('CP', 'cp1')
        self.last_status_log_signature: Optional[tuple] = None
        self.lock: threading.Lock = threading.Lock()
        self.model_lock: threading.Lock = threading.Lock()  # Separate lock for model operations
        
        # Dynamic model reloading state
        self.model_version: int = 0  # Incremented on each model update
        self.pending_model: Optional[IedModel] = None  # New model waiting to be applied
        self.model_reload_in_progress: bool = False
        self.old_server_cp: Optional[IEC61850Server] = None  # For cleanup after hot-swap
        
        # Callbacks for message logging
        self.recv_msg_callback: Optional[Callable] = None
        self.send_msg_callback: Optional[Callable] = None

        # Service-specific callbacks
        self.write_callback: Optional[Callable] = None
        self.connected_callback: Optional[Callable] = None


class ACSIServer:
    """IEC 61850 WebSocket server controller."""

    def __init__(self, model_path):
        self.runtime = ACSIServerRuntime()
        self.runtime.ied_model = None
        self.runtime.model_ied_name = None
        self.runtime.model_source = None
        self.runtime.model_version = 0

        self.runtime.endpoint = ActiveEndpoint()
        self.runtime.endpoint.recv_msg_callback = self._on_recv_message
        self.runtime.endpoint.send_msg_callback = self._on_send_message

        print(f"[DEBUG] New ACSIServer instance: model_path={model_path}, id={id(self.runtime)}")

        # Prefer the model already in runtime (freshly loaded from SCL/model.py)
        # Only reload from file as fallback if runtime model is missing
        #self.factory_dir = factory_dir
        #self.model_file = factory_dir / "model.py"
        self.model_file = Path(model_path)
        # If model_path is a directory, append model.py
        if self.model_file.is_dir():
            self.model_file = self.model_file / "model.py"
        factory_dir = str(self.model_file.parent)

        # Ensure `import model` resolves to the expected fsp/model.py directory.
        if factory_dir not in sys.path:
            sys.path.insert(0, factory_dir)

        if not self.model_file.exists():
            raise FileNotFoundError(
                f"Model file not found: {self.model_file}. "
                "Create model.py in the fsp directory before starting the server."
            )


        if self.runtime.ied_model is None:
            try:
                print("[_start_server_async] No model in runtime, loading from file...")
                self.runtime.ied_model = self.load_current_runtime_model()
            except FileNotFoundError:
                print("[_start_server_async] Model file not found")
                raise RuntimeError("No model loaded. Create fsp/model.py first.")
        else:
            print(
                f"[_start_server_async] Using model from runtime: "
                f"ied_model.name={self.runtime.ied_model.name!r} "
                f"model_ied_name={self.runtime.model_ied_name!r}"
            )

        if self.runtime.ied_model is None:
            raise RuntimeError("No model loaded. Create fsp/model.py first.")

        self._set_runtime_state(
            model_source=str(self.model_file),
            model_ied_name=self.runtime.ied_model.name,
        )

        def control_handler(obj_ref, ctlVal_value, parameter):
            ctl_val = ctlVal_value['value']
            print("entered control handler: obj_ref:", obj_ref, "ctlVal_value:", ctl_val, "parameter:", parameter)

            TYPE_MAP = {
                "boolean": bool,
                "int32": int,
                "float32" : float,
                "string": str,
            }
            if ctlVal_value is not None:
                if ctl_val[0] in TYPE_MAP:
                    if isinstance(ctl_val[1], TYPE_MAP[ctl_val[0]]):
                        return ControlHandlerResult.OK, None
                    else:
                        return ControlHandlerResult.FAILED, ControlServiceStatusKind.invalidPosition
            else:
                return None, ServiceStatusKind.instanceNotAvailable
            return None, None


        iec61850_instance = IEC61850Server(self.runtime.ied_model, self.runtime.cp)
        iec61850_instance.set_control_handler(control_handler, None)
        iec61850_instance.send_msg_callback = self.runtime.endpoint.send_msg_callback
        iec61850_instance.recv_msg_callback = self.runtime.endpoint.recv_msg_callback
        self.runtime.server = iec61850_instance
        self.runtime.endpoint.add_iec61850_server(self.runtime.server)

    def install_write_callback(self, callback):
        """Install a callback to be invoked when write messages are received."""
        self.runtime.write_callback = callback

    def install_connected_callback(self, callback):
        """Install a callback to be invoked when associateResponse messages are received.
        
        The callback receives: associateResponse data (dict)
        """
        self.runtime.connected_callback = callback

    def load_current_runtime_model(self) -> IedModel:
        """Load the current runtime model from model.py."""
        if not self.model_file.exists():
            raise FileNotFoundError(f"Model file not found: {self.model_file}")

        # Use importlib.util to load without polluting sys.modules
        import importlib.util
        spec = importlib.util.spec_from_file_location(self.model_file.stem, self.model_file)
        model_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(model_module)

        ied = getattr(model_module, "ied", None)
        if ied is None and hasattr(model_module, "build_ied_model"):
            ied = model_module.build_ied_model()
        if ied is None:
            raise RuntimeError(f"{self.model_file.stem}.py does not define 'ied' or build_ied_model()")
        if not isinstance(ied, IedModel):
            raise RuntimeError(f"Model in {self.model_file.stem}.py is not an IedModel")
        return ied

    def update_model_file(self, model_source: str, apply_dynamically: bool = True) -> IedModel:
        """Update model.py and reload runtime model. Reverts on validation failure.
        
        Args:
            model_source: Complete Python code for model.py
            apply_dynamically: If True and server is running, apply model hot-swap.
                            If False, only update the model file and runtime state.
        
        Returns:
            IedModel: The newly loaded model
        
        Raises:
            ValueError: If model_source is invalid
            Exception: If model validation fails
        """
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

        # Increment model version and set as pending
        # Note: runtime.ied_model is NOT updated here - it will be updated
        # after hot-swap completes to avoid race conditions
        with self.runtime.model_lock:
            self.runtime.model_version += 1
            self.runtime.pending_model = ied_model
            self.runtime.model_source = str(self.model_file)
            self.runtime.model_ied_name = ied_model.name

        # If server is running and dynamic application is requested, trigger hot-swap
        if apply_dynamically and self.runtime.status == "listening":
            self._apply_model_hot_swap()
        else:
            # Server not running - just update runtime model reference directly
            # No hot-swap needed, model will be loaded when server starts
            with self.runtime.model_lock:
                self.runtime.ied_model = ied_model

        return ied_model

    def _apply_model_hot_swap(self) -> bool:
        """Apply pending model to running server via hot-swap.
        
        This method updates the existing IEC61850Server instance with the new model
        by calling update_ied_model(), preserving WebSocket connections.
        
        Returns:
            bool: True if hot-swap was successful, False otherwise
        """
        with self.runtime.model_lock:
            if self.runtime.status != "listening":
                self._log_action("Hot-swap aborted: server not in listening state", "warn")
                return False
                
            if self.runtime.model_reload_in_progress:
                self._log_action("Hot-swap aborted: reload already in progress", "warn")
                return False
                
            if self.runtime.pending_model is None:
                self._log_action("Hot-swap aborted: no pending model", "warn")
                return False
                
            self.runtime.model_reload_in_progress = True
            pending_model = self.runtime.pending_model
            old_server = self.runtime.server
            
            # Set reload status
            self._set_runtime_state(status="reloading")

        try:
            # Execute hot-swap on the event loop
            loop = self.runtime.loop
            if loop is None or not loop.is_running():
                raise RuntimeError("Event loop not available for hot-swap")
                
            # Use run_coroutine_threadsafe to execute on the server's event loop
            future = asyncio.run_coroutine_threadsafe(
                self._perform_hot_swap_async(pending_model, old_server),
                loop
            )
            result = future.result(timeout=30)
            
            with self.runtime.model_lock:
                self.runtime.model_reload_in_progress = False
                if result:
                    self.runtime.pending_model = None
                    self._set_runtime_state(status="listening")
                    self._log_action(
                        "Model hot-swap completed successfully",
                        detail={"ied": pending_model.name, "version": self.runtime.model_version}
                    )
                else:
                    self._set_runtime_state(status="listening")
                    self._log_action("Model hot-swap completed with warnings", "warn")
                
            return result
            
        except Exception as exc:
            with self.runtime.model_lock:
                self.runtime.model_reload_in_progress = False
                self._set_runtime_state(status="listening")
            self._log_action(f"Model hot-swap failed: {exc}", "error")
            # No server restoration needed - we updated in-place
            # The old server instance is still valid with its original model
            return False

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

    def _on_send_message(self, message: Any, timestamp: Any) -> None:
        """Callback for sent WebSocket messages."""
        # Check for associateResponse in sent messages
        msg_dict = message
        if isinstance(message, bytes):
            try:
                msg_dict = json.loads(message.decode("utf-8", errors="replace"))
            except (json.JSONDecodeError, AttributeError):
                msg_dict = {}
        elif isinstance(message, str):
            try:
                msg_dict = json.loads(message)
            except (json.JSONDecodeError, AttributeError):
                msg_dict = {}
        
        if isinstance(msg_dict, dict):
            # Get service_data from associate path for sent messages
            service_data = msg_dict.get("associate", {}).get("service", {})
            
            if isinstance(service_data, dict):
                service_name = next(iter(service_data.keys())) if service_data else None
                if service_name == "associateResponse":
                    associate_response = service_data.get("associateResponse", {})
                    if self.runtime.connected_callback is not None:
                        self.runtime.connected_callback(associate_response)
        
        self._log_message("send", message, timestamp)

    def _on_recv_message(self, msg, ts):
        """Callback for received WebSocket messages."""
        self._log_message("recv", msg, ts)

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

    async def _perform_hot_swap_async(
        self, new_model: IedModel, old_server: Optional[IEC61850Server]
    ) -> bool:
        """Perform the actual hot-swap operation on the event loop.
        
        This coroutine updates the existing IEC61850Server instance with the new model
        by calling update_ied_model(), preserving WebSocket connections.
        
        Args:
            new_model: The new IedModel to use
            old_server: The current IEC61850Server instance to update
            
        Returns:
            bool: True if swap was successful
        """
        try:
            endpoint = self.runtime.endpoint
            if endpoint is None:
                self._log_action("Hot-swap failed: endpoint is None", "error")
                return False
            
            cp = self.runtime.cp or "cp1"
            
            # Update the existing server in-place with new model
            if old_server is not None:
                # Call the new update_ied_model method to refresh services
                old_server.update_ied_model(new_model)
                
                # Cancel periodic reporting from old server (will be restarted below)
                try:
                    for task_name, task in list(self.runtime.tasks.items()):
                        if task_name.startswith(f"{cp}-periodic-report") and not task.done():
                            task.cancel()
                            try:
                                await task
                            except asyncio.CancelledError:
                                pass
                except Exception as cancel_exc:
                    self._log_action(f"Warning: Failed to cancel old tasks: {cancel_exc}", "warn")
                
                # Update runtime state references (server instance stays the same)
                # Use lock to ensure atomic update
                with self.runtime.model_lock:
                    self.runtime.ied_model = new_model
                    self.runtime.model_ied_name = new_model.name
                
                # Restart periodic reporting with updated server
                report_task = asyncio.create_task(
                    old_server.periodic_report_start(), 
                    name=f"{cp}-periodic-report"
                )
                self.runtime.tasks["report"] = report_task
                
                # Restart custom demo tasks if the new model has the required objects
                if old_server.find_object_in_tree("LD0/DGEN1.DEROpSt.stVal") is not None:
                    toggle_task = asyncio.create_task(
                        self._toggle_custom_value(old_server, "LD0/DGEN1.DEROpSt.stVal"),
                        name="toggle-value"
                    )
                    self.runtime.tasks["toggle"] = toggle_task
                
                self._log_action(
                    "Server services updated with new model",
                    detail={
                        "server": str(old_server),
                        "model": new_model.name
                    }
                )
            else:
                # No existing server, this shouldn't happen but handle it
                self._log_action("Hot-swap failed: no existing server to update", "error")
                return False
            
            return True
            
        except Exception as exc:
            self._log_action(f"Hot-swap async execution failed: {exc}", "error")
            return False

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

        # Cleanup old server instance from hot-swap
        if self.runtime.old_server_cp is not None:
            try:
                # The old server should be cleaned up, but we don't need to explicitly stop it
                # as it's been replaced in the endpoint
                self.runtime.old_server_cp = None
            except Exception as exc:
                self._log_action(f"Cleanup old server error: {exc}", "warn")

        if endpoint is not None:
            try:
                await endpoint.stop_passive()
            except Exception as exc:
                self._log_action(f"stop_passive error: {exc}", "warn")

        # Reset model reloading state
        with self.runtime.model_lock:
            self.runtime.pending_model = None
            self.runtime.model_reload_in_progress = False
            self.runtime.old_server_cp = None

        self._set_runtime_state(
            #endpoint=None,
            #server_cp=None,
            tasks={},
            status="stopped",
            error=None,
        )

        self._log_action("Server stopped")
        asyncio.get_running_loop().call_soon(asyncio.get_running_loop().stop)

    async def _start_server_async(self, host: str, port: int) -> None:
        """Start the server asynchronously."""

        cp = self.runtime.cp or "cp1"

        # ready_event is bound to whichever loop is running when it's created.
        # Since self.runtime.server is a long-lived singleton reused across
        # stop/start cycles, but each start_server() spins up a brand-new event
        # loop, we must recreate ready_event here — on the loop that will
        # actually use it — rather than relying on the one created once in
        # IEC61850Server.__init__ (which becomes stale after the first restart).
        self.runtime.server.ready_event = asyncio.Event()

        report_task = asyncio.create_task(
            self.runtime.server.periodic_report_start(), name=f"{cp}-periodic-report"
        )
        tasks: Dict[str, asyncio.Task] = {"report": report_task}

        if self.runtime.server.find_object_in_tree("LD0/DGEN1.DEROpSt.stVal") is not None:
            tasks["toggle"] = asyncio.create_task(
                self._toggle_custom_value(self.runtime.server, "LD0/DGEN1.DEROpSt.stVal"),
                name="toggle-value",
            )

        ws_task = self.runtime.endpoint.run_in_background(host, port, cp)
        tasks["ws"] = ws_task

        self._set_runtime_state(
            endpoint=self.runtime.endpoint,
            server_cp=self.runtime.server,
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
        server = self.runtime.server
        if server is None:
            raise RuntimeError("Server is not running")

        result = self.invoke_on_runtime_loop(server.get_data_value_and_type(obj_ref), timeout=10)
        #result = server.read_value(obj_ref)

        if result is None:
            raise ValueError(f"instanceNotAvailable: {obj_ref}")

        return result

    def write_value(self, obj_ref: str, value: Any, data_type: str = "unknown") -> Dict[str, Any]:
        """Write a value to the server."""
        server = self.runtime.server
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
        """Get current server status including model versioning information."""
        endpoint = self.runtime.endpoint
        connected = len(endpoint.websocket_info_list) if endpoint is not None else 0
        tasks = self.runtime.tasks or {}

        status_info = {
            "status": self.runtime.status,
            "host": self.runtime.host,
            "port": self.runtime.port,
            "error": self.runtime.error,
            "connectedClients": connected,
            "tasks": {k: (not v.done()) for k, v in tasks.items()},
            "accessPoints": [self.runtime.cp or "cp1"],
            # Model versioning information
            "modelVersion": self.runtime.model_version,
            "modelReloadInProgress": self.runtime.model_reload_in_progress,
            "pendingModel": self.runtime.pending_model is not None,
            "modelName": self.runtime.model_ied_name,
            "modelSource": self.runtime.model_source,
        }
        
        # Add model reload progress if in reloading state
        if self.runtime.status == "reloading":
            status_info["reloadProgress"] = "swapping_server_instances"
        
        return status_info

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

    def reload_model_dynamically(self) -> bool:
        """Reload the model from model.py file and apply it to the running server.
        
        This method loads the current model from the model.py file and performs
        a hot-swap if the server is running.
        
        Returns:
            bool: True if model was reloaded successfully, False otherwise
        
        Raises:
            RuntimeError: If model file doesn't exist or model loading fails
        """
        if not self.model_file.exists():
            raise RuntimeError(f"Model file not found: {self.model_file}")
        
        try:
            # Load the current model from file
            ied_model = self.load_current_runtime_model()
            
            # Update runtime state with new model
            with self.runtime.model_lock:
                self.runtime.model_version += 1
                self.runtime.pending_model = ied_model
                self.runtime.model_source = str(self.model_file)
                self.runtime.model_ied_name = ied_model.name
                self.runtime.ied_model = ied_model
            
            # Apply hot-swap if server is running
            if self.runtime.status == "listening":
                return self._apply_model_hot_swap()
            else:
                # Server not running, just update the model
                with self.runtime.model_lock:
                    self.runtime.pending_model = None
                self._log_action(
                    "Model reloaded (server not running)",
                    detail={"source": str(self.model_file), "ied": ied_model.name}
                )
                return True
                
        except Exception as exc:
            self._log_action(f"Dynamic model reload failed: {exc}", "error")
            raise RuntimeError(f"Failed to reload model: {exc}")

    def get_model_version_info(self) -> Dict[str, Any]:
        """Get information about current and pending models.
        
        Returns:
            dict: Model versioning information
        """
        with self.runtime.model_lock:
            return {
                "currentModelVersion": self.runtime.model_version,
                "currentModelName": self.runtime.model_ied_name,
                "currentModelSource": self.runtime.model_source,
                "pendingModelAvailable": self.runtime.pending_model is not None,
                "pendingModelName": self.runtime.pending_model.name if self.runtime.pending_model else None,
                "reloadInProgress": self.runtime.model_reload_in_progress,
            }
