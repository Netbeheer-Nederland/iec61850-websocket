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
from datetime import datetime

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
        #self.cp: str = "cp1"
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

        self.write_callback: Optional[Callable] = None
        self.report_callback: Optional[Callable] = None
        self.connected_callback: Optional[Callable] = None


class ACSIClient:
    """IEC 61850 WebSocket client controller."""

    def __init__(self):
        self.runtime = ACSIClientRuntime()
        self.runtime.endpoint = PassiveEndpoint()
        self.runtime.endpoint.recv_msg_callback = self._on_recv_message
        self.runtime.endpoint.send_msg_callback = self._on_send_message
        #self.runtime.client = IEC61850Client(self.runtime.cp)
        #self.runtime.endpoint.add_iec61850_client(self.runtime.client)
        self.runtime.client_list = self.runtime.endpoint.client_list

        # Model and tree caching
        self.model_list = []

        # Track ModelInfo by cp to preserve state
        self._model_info_dict = {}  # cp -> ModelInfo
        self._update_model_info_dict()

        #start Websocket Passive instance
        self.connect("0.0.0.0", 8765)

    def install_write_callback(self, callback):
       self.runtime.write_callback = callback;

    def install_report_callback(self, callback):
        """Install a callback to be invoked when report messages are received.
        
        The callback receives: rptID, dataSet, data (list of {dataRef, value})
        """
        self.runtime.report_callback = callback;

    def install_connected_callback(self, callback):
        """Install a callback to be invoked when associateResponse messages are received.
        
        The callback receives: associateResponse data (dict)
        """
        self.runtime.connected_callback = callback;

    def _on_recv_message(self, msg, ts):
        """Callback for received WebSocket messages."""
        # Check if this is a report service message
        is_report = False
        report_info = {}
        
        # Parse msg if it's a string or bytes
        msg_dict = msg
        if isinstance(msg, bytes):
            try:
                msg_dict = json.loads(msg.decode("utf-8", errors="replace"))
            except (json.JSONDecodeError, AttributeError):
                msg_dict = {}
        elif isinstance(msg, str):
            try:
                msg_dict = json.loads(msg)
            except (json.JSONDecodeError, AttributeError):
                msg_dict = {}
        
        if isinstance(msg_dict, dict):
            # Get service_data from either unconfirmed or associate path
            service_data = msg_dict.get("unconfirmed", {}).get("service", {})
            if not service_data:
                service_data = msg_dict.get("associate", {}).get("service", {})
            
            if isinstance(service_data, dict):
                service_name = next(iter(service_data.keys())) if service_data else None
                is_report = service_name == "report"
                if is_report:
                    report_data = service_data.get("report", {})
                    report_info = {
                        "rptID": report_data.get("rptID"),
                        "dataSet": report_data.get("dataSet"),
                        "data": []
                    }
                    # Extract dataRef + values from entryData
                    entry_data = report_data.get("entryData", [])
                    if isinstance(entry_data, list):
                        for entry in entry_data:
                            if isinstance(entry, dict):
                                data_ref = entry.get("dataRef")
                                value = entry.get("value")
                                report_info["data"].append({
                                    "dataRef": data_ref,
                                    "value": value
                                })
                    
                    # Call external report callback if installed
                    if self.runtime.report_callback is not None:
                        self.runtime.report_callback(
                            report_info["rptID"],
                            report_info["dataSet"],
                            report_info["data"]
                        )
                elif service_name == "associateResponse":
                    # Handle associateResponse service
                    associate_response = service_data.get("associateResponse", {})
                    if self.runtime.connected_callback is not None:
                        self.runtime.connected_callback(associate_response)
        
        self._log_message("recv", msg, ts)

    def _on_send_message(self, msg, ts):
        """Callback for sent WebSocket messages."""
        self._log_message("send", msg, ts)

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
        cp = ""
        try:
            msg = json.loads(raw)
            if not isinstance(msg, dict):
                return {"service_type": service_type, "category": category, "cp": cp}

            if "request" in msg:
                category = "request"
                service = msg.get("request", {}).get("service", {})
                request = msg["request"]
                cp = request.get("associateId", "")
                if isinstance(service, dict) and service:
                    service_type = next(iter(service.keys()))
            elif "response" in msg:
                category = "response"
                service = msg.get("response", {}).get("service", {})
                response = msg["response"]
                cp = response.get("associateId", "")
                if isinstance(service, dict) and service:
                    service_type = next(iter(service.keys()))
            elif "associate" in msg:
                category = "associate"
                service = msg.get("associate", {}).get("service", {})
                cp = msg.get("associate", {}).get("service", {}).get("calledAP", "")

                # associateId is inside associateResponse
                if "associateResponse" in service:
                    cp = service["associateResponse"].get("associateId", "")

                # calledAP is inside associateRequest
                elif "associateRequest" in service:
                    cp = service["associateRequest"].get("calledAP", "")

                if isinstance(service, dict) and service:
                    service_type = next(iter(service.keys()))
        except Exception:
            service_type = "parse-error"
            category = "parse-error"

        return {"service_type": service_type, "category": category, "cp": cp}

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
                    "cp": meta["cp"]
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

    async def _connect_async(self, host: str, port: int) -> None:
        """Connect to the server asynchronously."""
        self._set_runtime_state(
            host=host,
            port=port,
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
                detail={"host": host, "port": port},
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

    def _event_loop_thread(self, host: str, port: int) -> None:
        """Run the event loop in a separate thread."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._set_runtime_state(loop=loop)

        connect_task = loop.create_task(
            self._connect_async(host, port), name="client-connect"
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

    def connect(self, host: str, port: int) -> None:
        """Connect to the server in a background thread."""
        self._validate_connection_params(host, port)

        with self.runtime.lock:
            status = self.runtime.status
            if status in ("connecting", "connected"):
                raise RuntimeError("Client is already connected or connecting")
            self.runtime.status = "connecting"

        t = threading.Thread(
            target=self._event_loop_thread, args=(host, port), daemon=True
        )
        self._set_runtime_state(thread=t)
        t.start()
        self._log_action("Connection initiated", detail={"host": host, "port": port})

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
            #"cp": self.runtime.cp,
            "error": self.runtime.error,
            #"modelStatus": model_info.model_status,
            #"modelError": model_info.model_error,
        }

    async def get_server_directory_tree(self, cp: str, ws_info: Optional[Any] = None) -> Dict[str, Any]:
        """Get list of all Logical Devices on the server.
        
        Args:
            cp: Communication point identifier
            ws_info: Optional WebSocketInfo (auto-fetched if None)
            
        Returns:
            dict: {"logicalDevices": [...], "source": "live"}
        """
        client = self.get_iec61850_client(cp)
        if not client:
            raise RuntimeError(f"ACSI Client for {cp} not found")
        
        if ws_info is None:
            ws_info = self.runtime.endpoint.get_websocket_info(client)
        if not ws_info:
            raise RuntimeError('no-websocket-info')

        # Serialize every request over this connection through the shared
        # invoke_lock — without this, two calls issued close together (e.g.
        # a background model-rebuild racing a manual UI click) can have
        # their responses arrive out of order, which the passive endpoint
        # treats as a protocol violation and closes the connection for.
        async with self.runtime.invoke_lock:
            ld_list = await client.get_server_directory(ws_info, None, None)
        if not isinstance(ld_list, list):
            raise RuntimeError('unexpected-server-directory')

        return {"logicalDevices": ld_list, "source": "live"}

    async def get_logical_device_tree(self, ld_inst: str, cp: str, ws_info: Optional[Any] = None) -> Dict[str, Any]:
        """Get all Logical Nodes for a specific Logical Device.

        Args:
            ld_inst: Logical Device instance name (e.g., "LD0")
            cp: Communication point identifier
            ws_info: Optional WebSocketInfo (auto-fetched if None)

        Returns:
            dict: {"logicalDevice": str, "logicalNodes": [...], "source": "live"}
        """
        client = self.get_iec61850_client(cp)
        if not client:
            raise RuntimeError(f"ACSI Client for {cp} not found")

        if ws_info is None:
            ws_info = self.runtime.endpoint.get_websocket_info(client)
        if not ws_info:
            raise RuntimeError('no-websocket-info')

        async with self.runtime.invoke_lock:
            ln_list = await client.get_logical_device_directory(ld_inst, ws_info, None, None)
        if not isinstance(ln_list, list):
            raise RuntimeError('unexpected-ln-list')

        return {"logicalDevice": ld_inst, "logicalNodes": ln_list, "source": "live"}

    async def get_logical_node_tree(self, ld_inst: str, ln_inst: str, cp: str, ws_info: Optional[Any] = None) -> Dict[str, Any]:
        """Get complete tree for a specific Logical Node.

        Fetches DO, DA, BRCB, URCB, and DataSet directories in parallel.

        Args:
            ld_inst: Logical Device instance name (e.g., "LD0")
            ln_inst: Logical Node instance name (e.g., "LLN0")
            cp: Communication point identifier
            ws_info: Optional WebSocketInfo (auto-fetched if None)

        Returns:
            dict: {"logicalNode": str, "dataObjects": [...], "dataAttributes": [...],
                   "reportControlBlocks": [...], "dataSets": [...], "source": "live"}
        """
        client = self.get_iec61850_client(cp)
        if not client:
            raise RuntimeError(f"ACSI Client for {cp} not found")

        if ws_info is None:
            ws_info = self.runtime.endpoint.get_websocket_info(client)
        if not ws_info:
            raise RuntimeError('no-websocket-info')

        # Fetch all directory types in parallel
        directory_types = ['dataObject', 'brcb', 'urcb', 'dataset']

        async def fetch_directory(directory_type):
            try:
                # Still fetched "concurrently" from the caller's perspective,
                # but each actual network call is serialized through the
                # shared lock so responses can't arrive out of order on the
                # wire.
                async with self.runtime.invoke_lock:
                    items = await client.get_logical_node_directory(ld_inst, ln_inst, directory_type, ws_info, None, None)
                return directory_type, items if items else []
            except Exception:
                return directory_type, []

        dir_tasks = [fetch_directory(dt) for dt in directory_types]
        dir_results = await asyncio.gather(*dir_tasks)

        result = {"logicalNode": f"{ld_inst}/{ln_inst}", "source": "live"}
        for dir_type, items in dir_results:
            result[dir_type] = items

        return result

    async def get_data_object_details(self, ld_inst: str, ln_inst: str, do_name: str, cp: str, ws_info: Optional[Any] = None) -> Dict[str, Any]:
        """Get complete details for a specific Data Object including its data attributes.

        Args:
            ld_inst: Logical Device instance name (e.g., 'LD0')
            ln_inst: Logical Node instance name (e.g., 'LLN0')
            do_name: Data Object name (e.g., 'Mod')
            cp: Communication point identifier
            ws_info: Optional WebSocketInfo (auto-fetched if None)

        Returns:
            dict: Data object details including data attributes
        """
        client = self.get_iec61850_client(cp)
        if not client:
            raise RuntimeError(f"ACSI Client for {cp} not found")

        if ws_info is None:
            ws_info = self.runtime.endpoint.get_websocket_info(client)
        if not ws_info:
            raise RuntimeError('no-websocket-info')

        obj_ref = f"{ld_inst}/{ln_inst}.{do_name}"

        # Get the data definition for this data object
        async with self.runtime.invoke_lock:
            defn = await client.get_data_definition(obj_ref, ws_info, None, None)

        # Build result with the data definition
        # The data definition typically includes: cdc, fc, type, etc.
        result = {
            "dataObject": do_name,
            "objRef": obj_ref,
            "definition": defn if isinstance(defn, dict) else {},
            "source": "live"
        }

        return result

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
        async with self.runtime.invoke_lock:
            result = await client.get_data_values(obj_ref, fc, False, websocket_info, None, None)
        return {"value": result}

    async def get_dataset_directory(self, ld_inst: str, ln_inst: str, ds_inst: str, cp: str) -> Dict[str, Any]:
        """Read a value from the server."""
        client = self.get_iec61850_client(cp)
        if not client:
            raise RuntimeError(f"ACSI Client for {cp} not found!", cp)

        websocket_info = self.runtime.endpoint.get_websocket_info(client)
        async with self.runtime.invoke_lock:
            result = await client.get_dataset_directory(ld_inst, ln_inst, ds_inst, websocket_info, None, None)
        return {"value": result}

    async def get_data_definition(self, obj_ref: str, cp: str) -> Dict[str, Any]:
        """Read a value from the server."""
        try:
            client = self.get_iec61850_client(cp)
            if not client:
                raise RuntimeError(f"ACSI Client for {cp} not found!", cp)

            websocket_info = self.runtime.endpoint.get_websocket_info(client)
            async with self.runtime.invoke_lock:
                result = await client.get_data_definition(obj_ref, websocket_info, None, None)
            return {"dataDefinition": result}
        except Exception as e:
            print("error in get_data_definition:", e)
            logger.error(f"Error in get_data_definition: {e}")
            raise

    async def get_brcb_definition(self, obj_ref: str, cp: str) -> Dict[str, Any]:
        """Read a value from the server."""

        client = self.get_iec61850_client(cp)
        if not client:
            raise RuntimeError(f"ACSI Client for {cp} not found!", cp)

        websocket_info = self.runtime.endpoint.get_websocket_info(client)
        async with self.runtime.invoke_lock:
            result = await client.get_BRCB_values(obj_ref, websocket_info, None, None)
        return {"brcbDefinition": result}

    def create_rcb_from_frontend_data(self, rcb_data, type: str):
        """
        Map frontend JSON data to IEC61850 ClientReportControlBlock

        Args:
            data: dict from frontend request body
            client: IEC61850Client instance

        Returns:
            Configured ClientReportControlBlock
        """
        # Extract from nested data structure
        obj_ref = rcb_data.get('ref', '')
        is_buffered = True if type == 'BRCB' else False

        # Create BRCB instance
        rcb = IEC61850Client.ClientReportControlBlock(obj_ref, rcb_data.get('rptEna', is_buffered))

        # Map fields from frontend
        rcb.dataSet = rcb_data.get('dataSet', '')
        rcb.intgPd = rcb_data.get('intgPd', 0)
        rcb.rptEna = rcb_data.get('rptEna', True)

        # Map optFlds - convert dict to expected format
        opt_flds_data = rcb_data.get('optFlds', {})
        rcb.optFlds = {
            'seqNum': opt_flds_data.get('seqNum', False),
            'timeStamp': opt_flds_data.get('timeStamp', True),
            'dataSet': opt_flds_data.get('dataSet', True),
            'bufOvfl': opt_flds_data.get('bufOvfl', True),
            'configRef': opt_flds_data.get('configRef', False),
            'entryID': opt_flds_data.get('entryID', True),
            'dataRef': opt_flds_data.get('dataRef', True),
            'reasonCode': opt_flds_data.get('reasonCode', False)
        }

        # Map trgOps (note: capital O in BRCB)
        trg_op_data = rcb_data.get('trgOp', {})
        rcb.trgOps = {
            'dchg': trg_op_data.get('dchg', False),
            'qchg': trg_op_data.get('qchg', False),
            'dupd': trg_op_data.get('dupd', False),
            'integrity': trg_op_data.get('integrity', True),
            'gi': trg_op_data.get('gi', False)
        }

        # Set defaults for other required fields
        rcb.confRev = 1
        rcb.bufTm = 1000
        rcb.sqNum = 0
        rcb.gi = rcb.trgOps.get('gi', False)
        rcb.purgeBuf = False
        rcb.entryId = b"\x01\x02\x03\x04\x05\x06\x07\x08"
        rcb.timeOfEntry = datetime.now()
        rcb.resvTms = 5

        return rcb

    async def set_brcb_values(self, cp: str, data: Any) -> Dict[str, Any]:
        """Read a value from the server."""

        brcb = self.create_rcb_from_frontend_data(data, "BRCB")

        client = self.get_iec61850_client(cp)
        if not client:
            raise RuntimeError(f"ACSI Client for {cp} not found!", cp)

        websocket_info = self.runtime.endpoint.get_websocket_info(client)
        async with self.runtime.invoke_lock:
            result = await client.set_BRCB_values(brcb, websocket_info , None, None)
        return {"result": result}

    async def set_urcb_values(self, cp: str, data: Any) -> Dict[str, Any]:
        """Read a value from the server."""

        rcb = self.create_rcb_from_frontend_data(data, "URCB")

        print("created urcb:", rcb.__dict__)
        client = self.get_iec61850_client(cp)
        if not client:
            raise RuntimeError(f"ACSI Client for {cp} not found!", cp)

        websocket_info = self.runtime.endpoint.get_websocket_info(client)
        async with self.runtime.invoke_lock:
            result = await client.set_URCB_values(rcb, websocket_info , None, None)
        return {"result": result}

    async def get_urcb_definition(self, obj_ref: str, cp: str) -> Dict[str, Any]:
        """Read a value from the server."""

        client = self.get_iec61850_client(cp)
        if not client:
            raise RuntimeError(f"ACSI Client for {cp} not found!", cp)

        websocket_info = self.runtime.endpoint.get_websocket_info(client)
        async with self.runtime.invoke_lock:
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
        async with self.runtime.invoke_lock:
            result = await client.set_data_values(obj_ref, fc, [{"data": (data_type, value)}], websocket_info, self.runtime.write_callback, None)
        print(result)
        print("Write operation completed successfully.")
        print("new value:", value)
        print("obj_ref:", obj_ref)
        if result is True:
            return {"objRef": obj_ref, "value": value}
        else:
            return {"objRef": obj_ref, "value": None, "error": result}

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

        async with self.runtime.invoke_lock:
            result = await client.operate(oper_val, websocket_info, None, None)
        return {"objRef": obj_ref, "result": result}
