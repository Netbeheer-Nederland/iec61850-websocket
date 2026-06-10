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
import os
import sys
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ws61850.endpoint import PassiveEndpoint
from ws61850.endpoint import ActiveEndpoint
from ws61850.iec61850.client.iec61850_client import IEC61850Client


class ACSIClientRuntime:
    """Manages IEC 61850 WebSocket client runtime state and lifecycle."""

    def __init__(self):
        self.status: str = "disconnected"  # disconnected|connecting|connected|disconnecting|error
        self.host: str = "localhost"
        self.port: int = 8765
        self.cp: str = "cp1"
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.thread: Optional[threading.Thread] = None
        self.endpoint: Optional[Any] = None
        self.client: Optional[IEC61850Client] = None
        self.error: Optional[str] = None
        self.actions: deque = deque(maxlen=200)
        self.messages: deque = deque(maxlen=500)
        self.action_seq: int = 0
        self.message_seq: int = 0
        self.last_status_log_signature: Optional[tuple] = None
        self.lock: threading.Lock = threading.Lock()

        # Model and tree caching
        self.model_status: str = "idle"  # idle|building|ready|error
        self.model_data: Optional[Dict[str, Any]] = None
        self.model_error: Optional[str] = None
        self.model_progress: Optional[Dict[str, Any]] = None
        
        # Callbacks for message logging
        self.recv_msg_callback: Optional[Callable] = None
        self.send_msg_callback: Optional[Callable] = None


class ACSIClient:
    """IEC 61850 WebSocket client controller."""

    def __init__(self):
        self.runtime = ACSIClientRuntime()

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
            endpoint = PassiveEndpoint()
            endpoint.recv_msg_callback = lambda msg, ts: self._log_message("recv", msg, ts)
            endpoint.send_msg_callback = lambda msg, ts: self._log_message("send", msg, ts)

            client = IEC61850Client(cp)
            endpoint.add_iec61850_client(client)

            # endpoint.start() runs a reconnect loop forever, so we must NOT
            # await it directly. Schedule it as a background task and instead
            # wait for the client's ready_event, which is set once the IEC 61850
            # association has been established.
            start_task = asyncio.create_task(
                endpoint.start(host, port),
                name=f"so-active-{cp}",
            )

            # Remember the task so we can cancel it on disconnect.
            self._set_runtime_state(
                endpoint=endpoint,
                client=client,
                _start_task=start_task,
            )

            try:
                await asyncio.wait_for(client.ready_event.wait(), timeout=15)
            except asyncio.TimeoutError as exc:
                start_task.cancel()
                raise RuntimeError(
                    f"Association with {host}:{port}/{cp} timed out"
                ) from exc

            self._set_runtime_state(
                status="connected",
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
        client = self.runtime.client

        self._log_action("Disconnecting...")
        self._set_runtime_state(status="disconnecting")

        if endpoint is not None:
            try:
                await endpoint.stop_active()
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
        finally:
            pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()
            self._set_runtime_state(loop=None, thread=None)

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
            "modelStatus": self.runtime.model_status,
            "modelError": self.runtime.model_error,
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

    async def read_value(self, obj_ref: str, fc: str) -> Dict[str, Any]:
        """Read a value from the server."""
        client = self.runtime.client
        if client is None:
            raise RuntimeError("Client is not connected")

        websocket_info = self.runtime.endpoint.get_websocket_info(self.runtime.client)
        result = await client.get_data_values(obj_ref, fc, False, websocket_info, None, None)
        return {"value": result}

    async def write_value(self, obj_ref: str, value: Any, fc: str, data_type: str) -> Dict[str, Any]:
        """Write a value to the server."""
        client = self.runtime.client
        if client is None:
            raise RuntimeError("Client is not connected")

        websocket_info = self.runtime.endpoint.get_websocket_info(self.runtime.client)
        # dataAttrVal expects [{"data": (type_str, value)}]
        await client.set_data_values(obj_ref, fc, [{"data": (data_type, value)}], websocket_info, None, None)
        return {"objRef": obj_ref, "value": value}

    async def get_model(self) -> Dict[str, Any]:
        """Read a value from the server."""
        client = self.runtime.client
        if client is None:
            raise RuntimeError("Client is not connected")

        websocket_info = self.runtime.endpoint.get_websocket_info(self.runtime.client)
        #result = await client.get_data_values(obj_ref, fc, False, websocket_info, None, None)
        result = {"objRef": "mock_objRef", "value": "mock_value"}
        # Use logger.debug/info instead of logging.log(msg) because
        # logging.log(level, msg) expects the first arg to be an int level.
        # Calling logging.log(f"...") will raise TypeError: level must be an int.
        logger.debug(f"the result: {result}")
        return result

