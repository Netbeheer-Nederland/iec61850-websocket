"""Core IEC 61850 WebSocket client module with ACSI operations.

This module handles:
- WebSocket endpoint lifecycle management
- IEC 61850 client instantiation and control
- Connection management
- Async event loop management
"""

from __future__ import annotations

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
from ws61850.iec61850.client.iec61850_client import IEC61850Client

class ModelInfo:
    def __init__(self, cp):
        self.model_status: str = "idle"  # idle|building|ready|error
        self.model_data: Optional[Dict[str, Any]] = None
        self.model_error: Optional[str] = None
        self.model_progress: Optional[Dict[str, Any]] = None
        self.model_ready_event = asyncio.Event()
        self.cp = cp

class ACSIClientRuntime:
    """Manages IEC 61850 WebSocket client runtime state and lifecycle."""

    def __init__(self):
        self.status: str = "disconnected"  # disconnected|connecting|connected|disconnecting|error
        self.host: str = "localhost"
        self.port: int = 8765
        self.cp: str = "cp1"
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.thread: Optional[threading.Thread] = None
        self.client = None
        self.endpoint = None
        self.error: Optional[str] = None
        self.actions: deque = deque(maxlen=200)
        self.messages: deque = deque(maxlen=500)
        self.action_seq: int = 0
        self.message_seq: int = 0
        self.last_status_log_signature: Optional[tuple] = None
        self.lock: threading.Lock = threading.Lock()
        self.invoke_lock: asyncio.Lock = asyncio.Lock()
        self.client_list = None

        # Callbacks for message logging
        self.recv_msg_callback: Optional[Callable] = None
        self.send_msg_callback: Optional[Callable] = None


class ACSIClient:
    """IEC 61850 WebSocket client controller."""

    def __init__(self):
        self.runtime = ACSIClientRuntime()
        self.runtime.endpoint = PassiveEndpoint()
        self.runtime.endpoint.recv_msg_callback = lambda msg, ts: self._log_message("recv", msg, ts)
        self.runtime.endpoint.send_msg_callback = lambda msg, ts: self._log_message("send", msg, ts)
        #self.runtime.client = IEC61850Client(self.runtime.cp)
        #self.runtime.endpoint.add_iec61850_client(self.runtime.client)
        self.runtime.client_list = self.runtime.endpoint.client_list

        # Model and tree caching
        self.model_list = []

        # Track ModelInfo by cp to preserve state
        self._model_info_dict = {}  # cp -> ModelInfo
        self._update_model_info_dict()


    def _update_model_info_dict(self):
        """Sync ModelInfo dict with current client_list, preserving existing objects"""
        current_cps = {client.cp for client in self.runtime.client_list}

        # Add new clients
        for client in self.runtime.client_list:
            if client.cp not in self._model_info_dict:
                self._model_info_dict[client.cp] = ModelInfo(client.cp)

        # Remove clients that are gone
        for cp in list(self._model_info_dict.keys()):
            if cp not in current_cps:
                del self._model_info_dict[cp]


    @property
    def model_info_list(self):
        """Returns list of ModelInfo objects (preserves state between calls)"""
        return list(self._model_info_dict.values())

    def get_model_info(self, cp):
        """Get or create ModelInfo for a CP."""
        if cp not in self._model_info_dict:
            self._model_info_dict[cp] = ModelInfo(cp)  # New object (default values)
        return self._model_info_dict[cp]  # ✅ Returns EXISTING object with all its data

    def get_iec61850_client(self, cp):
        return next((client for client in self.runtime.client_list if client.cp == cp), None)

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

    def _set_runtime_state(self, **kwargs: Any) -> None:
        """Atomically update runtime state."""
        with self.runtime.lock:
            for key, value in kwargs.items():
                setattr(self.runtime, key, value)

    def _validate_connection_params(self, host: str, port: int) -> None:
        """Validate connection parameters."""
        if port < 1 or port > 65535:
            raise ValueError("Port must be in range 1..65535")

    async def _connect_async(self, host: str, port: int, cp: str) -> None:
        """Connect to the server asynchronously."""
        self._set_runtime_state(
            host=host,
            port=port,
            cp=cp,
            status="connecting",
            error=None,
        )

        try:
            
            # Now client gets callbacks automatically
            # endpoint.start() runs a reconnect loop forever, so we must NOT
            # await it directly. Schedule it as a background task and instead
            # wait for the client's ready_event, which is set once the IEC 61850
            # association has been established.
            start_task = asyncio.create_task(
                self.runtime.endpoint.start(host, port),
                name="so-active"
            )

            #client = self.get_iec61850_client(cp)
            #if not client:
            #    raise RuntimeError(f"ACSI Client for {cp} not found!")

            # Remember the task so we can cancel it on disconnect.
            self._set_runtime_state(
                endpoint=self.runtime.endpoint,
                #client=client,
                _start_task=start_task,
            )


            #try:
            #    await asyncio.wait_for(client.ready_event.wait(), None)
            #except asyncio.TimeoutError as exc:
            #    start_task.cancel()
            #    raise RuntimeError(
            #        f"Association with {host}:{port}/{cp} timed out"
            #    ) from exc
            status = "disconnected"
            if self.runtime.endpoint.get_endpoint_status():
                status = "connected"


            self._set_runtime_state(
                status=status,
                error=None,
            )

            self._log_action(
                "Connected to server",
                detail={"host": host, "port": port, "cp": cp},
            )

        except Exception as exc:
            self._set_runtime_state(status="error", error=str(exc))
            self._log_action(f"Connection failed: {exc}", "error")
            raise

    async def _disconnect_async(self) -> None:
        """Disconnect from the server asynchronously."""
        endpoint = self.runtime.endpoint
        #client = self.runtime.client

        self._log_action("Disconnecting...")
        self._set_runtime_state(status="disconnecting")

        # ✅ Cancel the background task first
        if hasattr(self.runtime, '_start_task') and self.runtime._start_task:
            self.runtime._start_task.cancel()

        if endpoint is not None:
            try:
                await endpoint.stop_passive()
            except Exception as exc:
                self._log_action(f"stop_active error: {exc}", "warn")

        self._set_runtime_state(
            endpoint=None,
            client=None,
            status="disconnected",
            error=None,
        )

        self._log_action("Disconnected")
        asyncio.get_running_loop().call_soon(asyncio.get_running_loop().stop)

    def _event_loop_thread(self, host: str, port: int, cp: str) -> None:
        """Run the event loop in a separate thread."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._set_runtime_state(loop=loop)

        connect_task = loop.create_task(
            self._connect_async(host, port, cp), name="client-connect"
        )

        def _on_connect_done(task: asyncio.Task) -> None:
            try:
                task.result()
            except asyncio.CancelledError:
                return
            except Exception as exc:
                self._set_runtime_state(status="error", error=str(exc))
                self._log_action(f"Connect failed: {exc}", "error")
                loop.call_soon_threadsafe(loop.stop)

        connect_task.add_done_callback(_on_connect_done)

        try:
            loop.run_forever()
        except Exception as exc:
            print(f"Event loop error: {exc}")
            self._log_action(f"Event loop error: {exc}", "error")
        finally:
            pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()
            self._set_runtime_state(loop=None, thread=None)

    def _convert_operate_val_to_its_type(self, oper_val: Any, val_type: str) -> Any:
        """Convert the operate value to its specified type."""
        if val_type == "boolean":
            return bool(oper_val)
        elif val_type == "int32":
            return int(oper_val)
        elif val_type == "float32":
            return float(oper_val)
        elif val_type == "string":
            return str(oper_val)
        else:
            raise ValueError(f"Unsupported value type: {val_type}")

    def connect(self, host: str, port: int, cp: str = "cp1") -> None:
        """Connect to the server in a background thread."""
        self._validate_connection_params(host, port)

        with self.runtime.lock:
            status = self.runtime.status
            if status in ("connecting", "connected"):
                raise RuntimeError("Client is already connected or connecting")
            self.runtime.status = "connecting"

        t = threading.Thread(
            target=self._event_loop_thread, args=(host, port, cp), daemon=True
        )
        self._set_runtime_state(thread=t)
        t.start()
        self._log_action("Connection initiated", detail={"host": host, "port": port, "cp": cp})

    def disconnect(self) -> None:
        """Disconnect from the server."""
        loop = self.runtime.loop
        status = self.runtime.status

        if status in (None, "disconnected"):
            self._set_runtime_state(status="disconnected")
            return

        if loop is None or not loop.is_running():
            self._set_runtime_state(
                status="disconnected", endpoint=None, client=None, error=None
            )
            return

        self._set_runtime_state(status="disconnecting")
        fut = asyncio.run_coroutine_threadsafe(self._disconnect_async(), loop)
        try:
            fut.result(timeout=10)
        except FuturesTimeoutError:
            self._log_action("Disconnect in progress (timeout).", "warn")
        except Exception:
            current = self.runtime.status
            if current not in ("disconnecting", "disconnected"):
                raise

    def invoke_on_runtime_loop(self, coro: Any, timeout: int = 10) -> Any:
        """Execute a coroutine on the runtime event loop."""
        loop = self.runtime.loop
        if loop is None or not loop.is_running():
            raise RuntimeError("client-not-connected")
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)

    def get_status(self) -> Dict[str, Any]:
        """Get current client status."""
        return {
            "status": self.runtime.status,
            "host": self.runtime.host,
            "port": self.runtime.port,
            "cp": self.runtime.cp,
            "error": self.runtime.error,
            #"modelStatus": model_info.model_status,
            #"modelError": model_info.model_error,
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

    async def read_value(self, obj_ref: str, fc: str, cp: str) -> Dict[str, Any]:
        """Read a value from the server."""
        client = self.get_iec61850_client(cp)
        if not client:
            raise RuntimeError(f"ACSI Client for {cp} not found!", cp)

        websocket_info = self.runtime.endpoint.get_websocket_info(client)
        result = await client.get_data_values(obj_ref, fc, False, websocket_info, None, None)
        return {"value": result}

    async def get_dataset_directory(self, ld_inst: str, ln_inst: str, ds_inst: str, cp: str) -> Dict[str, Any]:
        """Read a value from the server."""
        client = self.get_iec61850_client(cp)
        if not client:
            raise RuntimeError(f"ACSI Client for {cp} not found!", cp)

        websocket_info = self.runtime.endpoint.get_websocket_info(client)
        result = await client.get_dataset_directory(ld_inst, ln_inst, ds_inst, websocket_info, None, None)
        return {"value": result}

    async def get_data_definition(self, obj_ref: str, cp: str) -> Dict[str, Any]:
        """Read a value from the server."""

        client = self.get_iec61850_client(cp)
        if not client:
            raise RuntimeError(f"ACSI Client for {cp} not found!", cp)

        websocket_info = self.runtime.endpoint.get_websocket_info(client)
        result = await client.get_data_definition(obj_ref, websocket_info, None, None)
        return {"dataDefinition": result}

    async def get_brcb_definition(self, obj_ref: str, cp: str) -> Dict[str, Any]:
        """Read a value from the server."""

        client = self.get_iec61850_client(cp)
        if not client:
            raise RuntimeError(f"ACSI Client for {cp} not found!", cp)

        websocket_info = self.runtime.endpoint.get_websocket_info(client)
        result = await client.get_BRCB_values(obj_ref, websocket_info, None, None)
        return {"brcbDefinition": result}

    async def get_urcb_definition(self, obj_ref: str, cp: str) -> Dict[str, Any]:
        """Read a value from the server."""

        client = self.get_iec61850_client(cp)
        if not client:
            raise RuntimeError(f"ACSI Client for {cp} not found!", cp)

        websocket_info = self.runtime.endpoint.get_websocket_info(client)
        result = await client.get_URCB_values(obj_ref, websocket_info, None, None)
        return {"urcbDefinition": result}

    async def write_value(self, obj_ref: str, value: Any, fc: str, data_type: str, cp:str) -> Dict[str, Any]:
        """Write a value to the server."""
        client = self.get_iec61850_client(cp)
        if not client:
            raise RuntimeError(f"ACSI Client for {cp} not found!", cp)

        websocket_info = self.runtime.endpoint.get_websocket_info(client)
        if data_type == "boolean":
            value = bool(value)
        result = await client.set_data_values(obj_ref, fc, [{"data": (data_type, value)}], websocket_info, None, None)
        print(result)
        print("Write operation completed successfully.")
        print("new value:", value)
        print("obj_ref:", obj_ref)
        return {"objRef": obj_ref, "value": value}

    async def operate(self, obj_ref, oper_val, val_type: str, cp: str) -> Dict[str, Any]:
        """Perform an operate command on the server."""
        client = self.get_iec61850_client(cp)
        if not client:
            raise RuntimeError(f"ACSI Client for {cp} not found!", cp)

        websocket_info = self.runtime.endpoint.get_websocket_info(client)

        oper_val = {
            "ref": obj_ref,
            "ctlVal": (val_type, self._convert_operate_val_to_its_type(oper_val, val_type)),
            "origin": {"orCat": "stationControl", "orIdent": b"ORIGIN_ID_1234567890"},
            "ctlNum": 0,
            "t": {
                "secondSinceEpoch": 1757588367,
                "fractionOfSecond": 8120140,
                "timeQuality": {
                    "leapSecondsKown": False,
                    "clockFailure": False,
                    "clockNotSynchronized": False,
                    "timeAccuracy": 3,
                },
            },
            "test": True,
            "check": {"synchroCheck": False, "interlockCheck": False},
        }

        result = await client.operate(oper_val, websocket_info, None, None)
        return {"objRef": obj_ref, "result": result}
