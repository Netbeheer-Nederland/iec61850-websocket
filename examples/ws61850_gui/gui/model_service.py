import asyncio
import time
from typing import Any

from gui.connection_manager import ConnectionManager
from gui.protocol_utils import convert_bytes_to_hex
from gui.state import RuntimeState


class ModelService:
    def __init__(self, state: RuntimeState, connection_manager: ConnectionManager) -> None:
        self.state = state
        self.connection_manager = connection_manager

    def reset(self) -> None:
        with self.state.model_lock:
            self.state.model_status = "idle"
            self.state.model_data = None
            self.state.model_error = None
            self.state.model_task = None
            self.state.model_started_at = None
            self.state.model_progress = None

    def get_cached_response(self) -> tuple[str, dict[str, Any] | None, str | None, dict[str, Any] | None]:
        with self.state.model_lock:
            return (
                self.state.model_status,
                self.state.model_data,
                self.state.model_error,
                self.state.model_progress,
            )

    def start_build_if_needed(self) -> str:
        with self.state.model_lock:
            if self.state.model_status in {"ready", "building"}:
                return self.state.model_status
            self.state.model_data = None
            self.state.model_error = None
            self.state.model_status = "building"
            self.state.model_started_at = time.perf_counter()

        _, _, _, loop = self.connection_manager.ensure_connection(timeout=10)
        fut = asyncio.run_coroutine_threadsafe(self._build_full_model(), loop)
        with self.state.model_lock:
            self.state.model_task = fut
        return "building"

    async def _invoke_ln_directory(
        self,
        client: Any,
        ws_info: Any,
        ld_inst: str,
        ln_inst: str,
        mode: str,
    ) -> Any:
        lock = self.state.invoke_lock
        if lock is None:
            self.connection_manager.log_action(f"Request: getLogicalNodeDirectory {mode} {ld_inst}/{ln_inst}")
            return await client.get_logical_node_directory(ld_inst, ln_inst, mode, ws_info, None, None)
        async with lock:
            self.connection_manager.log_action(f"Request: getLogicalNodeDirectory {mode} {ld_inst}/{ln_inst}")
            return await client.get_logical_node_directory(ld_inst, ln_inst, mode, ws_info, None, None)

    async def _aget_ln_details(self, ld_inst: str, ln_inst: str, client: Any, ws_info: Any) -> dict[str, Any]:
        async def _safe(coro: Any) -> Any:
            try:
                return await coro
            except Exception:
                return None

        def _parse_do(items: Any) -> tuple[list[Any], list[Any]]:
            if isinstance(items, dict):
                return (
                    items.get("dataObjects", items.get("instanceNames", [])) or [],
                    items.get("dataAttributes", []) or [],
                )
            if isinstance(items, list):
                return items, []
            return [], []

        def _extract_rcb(entries: Any, kind: str) -> list[dict[str, Any]]:
            if isinstance(entries, list):
                names = entries
            elif isinstance(entries, dict):
                names = entries.get("instanceNames") or entries.get("reportControlBlocks") or []
            else:
                names = []
            return [{"name": ref, "type": kind} for ref in names]

        aid = self.connection_manager.log_action_start("lnDetails", {"ld": ld_inst, "ln": ln_inst})
        do_items = await _safe(self._invoke_ln_directory(client, ws_info, ld_inst, ln_inst, "dataObject"))
        brcb_items = await _safe(self._invoke_ln_directory(client, ws_info, ld_inst, ln_inst, "brcb"))
        urcb_items = await _safe(self._invoke_ln_directory(client, ws_info, ld_inst, ln_inst, "urcb"))
        dataset_items = await _safe(self._invoke_ln_directory(client, ws_info, ld_inst, ln_inst, "dataset"))

        data_objects = []
        do_list, data_attributes = _parse_do(do_items)
        if do_list:
            for do_name in do_list:
                try:
                    obj_ref = f"{ld_inst}/{ln_inst}.{do_name}"
                    if self.state.invoke_lock is None:
                        definition = await client.get_data_definition(obj_ref, ws_info, None, None)
                    else:
                        async with self.state.invoke_lock:
                            definition = await client.get_data_definition(obj_ref, ws_info, None, None)
                    cdc = definition.get("cdc") if isinstance(definition, dict) else None
                    data_objects.append({"name": do_name, "cdc": cdc})
                except Exception:
                    data_objects.append({"name": do_name, "cdc": None})

        rcbs = []
        for rcb_info in _extract_rcb(brcb_items, "BRCB"):
            rcbs.append(await self._fetch_rcb_values(client, ws_info, ld_inst, ln_inst, rcb_info, buffered=True))
        for rcb_info in _extract_rcb(urcb_items, "URCB"):
            rcbs.append(await self._fetch_rcb_values(client, ws_info, ld_inst, ln_inst, rcb_info, buffered=False))

        if isinstance(dataset_items, list):
            datasets = dataset_items
        elif isinstance(dataset_items, dict):
            datasets = dataset_items.get("instanceNames") or dataset_items.get("dataSets") or []
        else:
            datasets = []

        result = {
            "dataObjects": data_objects,
            "dataAttributes": data_attributes,
            "reportControlBlocks": rcbs,
            "dataSets": datasets,
        }
        self.connection_manager.log_action_end(
            aid,
            success=True,
            extra_detail={
                "do": len(data_objects),
                "da": len(data_attributes),
                "rcb": len(rcbs),
                "ds": len(datasets),
            },
        )
        return result

    async def _fetch_rcb_values(
        self,
        client: Any,
        ws_info: Any,
        ld_inst: str,
        ln_inst: str,
        rcb_info: dict[str, Any],
        *,
        buffered: bool,
    ) -> dict[str, Any]:
        rcb_name = rcb_info["name"]
        rcb_ref = f"{ld_inst}/{ln_inst}.{rcb_name}"
        try:
            if self.state.invoke_lock is None:
                values = (
                    await client.get_BRCB_values(rcb_ref, ws_info, None, None)
                    if buffered
                    else await client.get_URCB_values(rcb_ref, ws_info, None, None)
                )
            else:
                async with self.state.invoke_lock:
                    values = (
                        await client.get_BRCB_values(rcb_ref, ws_info, None, None)
                        if buffered
                        else await client.get_URCB_values(rcb_ref, ws_info, None, None)
                    )
            enabled = values.get("RptEna", False) if isinstance(values, dict) else False
            return {
                "name": rcb_name,
                "type": "BRCB" if buffered else "URCB",
                "values": convert_bytes_to_hex(values),
                "enabled": enabled,
            }
        except Exception:
            return {"name": rcb_name, "type": "BRCB" if buffered else "URCB", "values": None, "enabled": False}

    async def _build_full_model(self) -> None:
        client = self.state.client
        endpoint = self.state.endpoint
        loop = self.state.loop
        if not client or not endpoint or not loop or not client.is_connected:
            raise RuntimeError("not-connected")
        ws_info = endpoint.get_websocket_info(client)
        if ws_info is None:
            raise RuntimeError("no-websocket-info")

        started = time.perf_counter()
        model_aid = self.connection_manager.log_action_start("modelFetch", {})
        logical_node_details: dict[str, Any] = {}
        logical_device_map: dict[str, Any] = {}
        logical_device_status: dict[str, str] = {}

        def _update_progress(**changes: Any) -> None:
            with self.state.model_lock:
                if self.state.model_progress is None:
                    return
                self.state.model_progress.update(changes)

        try:
            if self.state.invoke_lock is None:
                ld_list = await client.get_server_directory(ws_info, None, None)
            else:
                async with self.state.invoke_lock:
                    ld_list = await client.get_server_directory(ws_info, None, None)
            if not isinstance(ld_list, list):
                raise RuntimeError("unexpected-server-directory")

            with self.state.model_lock:
                self.state.model_progress = {
                    "lds_total": len(ld_list),
                    "lds_done": 0,
                    "lns_total": 0,
                    "lns_done": 0,
                    "current_ld": None,
                    "current_ln": None,
                }

            for ld in ld_list:
                _update_progress(current_ld=ld)
                try:
                    if self.state.invoke_lock is None:
                        ln_list = await client.get_logical_device_directory(ld, ws_info, None, None)
                    else:
                        async with self.state.invoke_lock:
                            ln_list = await client.get_logical_device_directory(ld, ws_info, None, None)
                    if not isinstance(ln_list, list):
                        raise RuntimeError("unexpected-ln-list")
                    logical_device_map[ld] = ln_list
                    logical_device_status[ld] = "ok"
                    with self.state.model_lock:
                        if self.state.model_progress is not None:
                            self.state.model_progress["lns_total"] += len(ln_list)
                    for ln_full in ln_list:
                        ln_inst = ln_full.split("/")[-1].split(":")[-1]
                        _update_progress(current_ln=ln_inst)
                        try:
                            details = await self._aget_ln_details(ld, ln_inst, client, ws_info)
                            logical_node_details[f"{ld}/{ln_inst}"] = details
                        finally:
                            with self.state.model_lock:
                                if self.state.model_progress is not None:
                                    self.state.model_progress["lns_done"] += 1
                except Exception:
                    logical_device_map[ld] = []
                    logical_device_status[ld] = "error"
                finally:
                    with self.state.model_lock:
                        if self.state.model_progress is not None:
                            self.state.model_progress["lds_done"] += 1
                            self.state.model_progress["current_ln"] = None

            with self.state.model_lock:
                self.state.model_data = {
                    "server": {"logicalDevices": ld_list},
                    "logicalDeviceMap": logical_device_map,
                    "logicalDeviceStatus": logical_device_status,
                    "logicalNodeDetails": logical_node_details,
                    "source": "live",
                }
                self.state.model_status = "ready"
                self.state.model_error = None
            self.connection_manager.log_action_end(
                model_aid,
                success=True,
                extra_detail={"lds": len(ld_list), "lnDetails": len(logical_node_details)},
            )
        except Exception as exc:
            with self.state.model_lock:
                self.state.model_status = "error"
                self.state.model_error = str(exc)
            self.connection_manager.log_action_end(model_aid, success=False, error=str(exc))
            raise
        finally:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self.connection_manager.log_action(f"Model build elapsed {elapsed_ms} ms")

    def get_ln_details(self, ld_inst: str, ln_inst: str, timeout: int = 10) -> dict[str, Any]:
        return self.connection_manager.invoke(
            lambda client, _endpoint, ws_info: self._aget_ln_details(ld_inst, ln_inst, client, ws_info),
            timeout=timeout,
            locked=False,
        )
