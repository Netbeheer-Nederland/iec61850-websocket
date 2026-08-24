"""Backend for Frontend (BFF) endpoint providing REST API for ACSI server control.

This module exposes REST API endpoints that interact with the ACSI server,
handling model management, server lifecycle, and value operations.
"""
from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)

from concurrent.futures import TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Any, Dict, List, Optional
from acsi_server import ACSIServer
from ws61850.iec61850.data_model.ied_model import DataAttribute, DataObject, IedModel
from fastapi import FastAPI, APIRouter, Request, HTTPException, status, UploadFile, File
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field, ConfigDict

# ==================== Pydantic Models ====================
class WritevalueRequest(BaseModel):

    """Request body for writing a value to the ACSI server model."""
    objRef: str = Field(
        ...,
        description="Object reference in ACSI format (e.g., 'LD0/LLN0$ST$Mod')",
        json_schema_extra={"example": "LD0/LLN0$ST$Mod"}
    )
    fc: str = Field(
        ...,
        description="Functional constraint (ST, MX, CO, etc.)",
        json_schema_extra={"example": "ST"}
    )
    value: str = Field(
        ...,
        description="Value to write as string representation",
        json_schema_extra={"example": "ON"}
    )
    dataType: str = Field(
        default="",
        description="Optional data type for value coercion",
        json_schema_extra={"example": "BOOLEAN"}
    )

class UpdateIedmodelRequest(BaseModel):
    """Request body for updating the IED model file."""
    modelPy: str = Field(
        ...,
        description="Complete Python code for model.py file",
        json_schema_extra={"example": "from ws61850... import IedModel\nmodel = IedModel(...)"}
    )

class StartRequest(BaseModel):
    """Request body for starting the ACSI WebSocket Passive."""
    host: str = Field(
        default="0.0.0.0",
        description="Hostname or IP address to bind to",
        json_schema_extra={"example": "0.0.0.0"}
    )
    port: str = Field(
        default="8765",
        description="Port number to listen on",
        json_schema_extra={"example": "8765"}
    )
    mode: str = Field(
        default="server",
        description="Operating mode (only 'server' supported)",
        json_schema_extra={"example": "server"}
    )
    cp: str = Field(
        default="cp1",
        description="Communication point identifier",
        json_schema_extra={"example": "cp1"}
    )

class ReadvalueRequest(BaseModel):

    """Request body for reading a value from the ACSI server model."""
    objRef: str = Field(
        ...,
        description="Object reference in ACSI format",
        json_schema_extra={"example": "LD0/MMXU1$MX$volA"}
    )
    fc: str = Field(
        default="",
        description="Functional constraint (optional)",
        json_schema_extra={"example": "MX"}
    )

def create_bff_router(
    factory_dir,
    scl_default_path: Optional[Path] = None,
) -> tuple[APIRouter, ACSIServer]:
    """Create a FastAPI router for the ACSI server BFF API.

    Args:
        factory_dir: Path to the fsp directory containing model.py
        scl_default_path: Unused. Kept only for backward compatibility.

    Returns:
        Tuple of (APIRouter, ACSIServer instance)
    """
    router = APIRouter(
        prefix="/api",
        tags=["ACSI-Server"],
        responses={404: {"description": "Not found"}, 500: {"description": "Internal server error"}}
    )

    rti_fsp = ACSIServer(factory_dir)

    # ==================== Helper Functions ====================
    def serialize_data_attribute(da: DataAttribute) -> Dict[str, Any]:
        """Serialize a DataAttribute to JSON-compatible dict."""
        return {
            "kind": "DA",
            "type": "DA",
            "name": da.name,
            "fc": da.fc.name if da.fc is not None else None,
            "bType": da.type.name if da.type is not None else None,
            "children": [serialize_data_attribute(child) for child in (da.data_attributes or [])],
        }

    def serialize_data_object(do: DataObject) -> Dict[str, Any]:
        """Serialize a DataObject to JSON-compatible dict."""
        children: List[Dict[str, Any]] = []
        for item in do.do_or_da or []:
            if isinstance(item, DataObject):
                children.append(serialize_data_object(item))
            elif isinstance(item, DataAttribute):
                children.append(serialize_data_attribute(item))

        return {
            "kind": "DO",
            "type": "DO",
            "name": do.name,
            "cdc": do.cdc,
            "children": children,
        }

    def serialize_ied_tree(ied: IedModel) -> Dict[str, Any]:
        """Serialize an IED model tree to JSON-compatible dict."""
        return {
            "kind": "IED",
            "type": "IED",
            "name": ied.name,
            "children": [
                {
                    "kind": "LD",
                    "type": "LDevice",
                    "name": ld.name,
                    "ldName": ld.ldName,
                    "children": [
                        {
                            "kind": "LN",
                            "type": "LogicalNode",
                            "name": ln.name,
                            "children": (
                                [
                                    {
                                        "kind": "Group",
                                        "type": "Group",
                                        "name": "DataSets",
                                        "children": [
                                            {
                                                "kind": "DataSet",
                                                "type": "DataSet",
                                                "name": ds.name,
                                                "ref": f"{ld.name}/{ln.name}.{ds.name}"
                                            }
                                            for ds in (ln.data_sets or [])
                                        ]
                                    }
                                ] if (ln.data_sets or []) else []
                            ) + (
                                [
                                    {
                                        "kind": "Group",
                                        "type": "Group",
                                        "name": "ReportControls",
                                        "children": [
                                            {
                                                "kind": "BRCB" if rcb.buffered else "URCB",
                                                "type": "ReportControl",
                                                "name": rcb.name,
                                                "ref": f"{ld.name}/{ln.name}.{rcb.name}"
                                            }
                                            for rcb in (ln.rcbs or [])
                                        ]
                                    }
                                ] if (ln.rcbs or []) else []
                            ) + [
                                serialize_data_object(do) for do in (ln.data_objects or [])
                            ]
                        }
                        for ln in (ld.logical_nodes or [])
                    ],
                }
                for ld in (ied.logical_devices or [])
            ],
        }

    def collect_da_paths_from_do(data_object: DataObject, prefix: str) -> List[tuple]:
        """Collect flattened (path, fc_name) tuples under a DO path."""
        results: List[tuple] = []
        for item in (data_object.do_or_da or []):
            if isinstance(item, DataAttribute):
                da_path = f"{prefix}.{item.name}"
                fc_name = item.fc.name if item.fc is not None else None
                results.append((da_path, fc_name))
                results.extend(collect_da_paths_from_da(item, da_path))
            elif isinstance(item, DataObject):
                sub_prefix = f"{prefix}.{item.name}"
                results.extend(collect_da_paths_from_do(item, sub_prefix))
        return results

    def collect_da_paths_from_da(data_attribute: DataAttribute, prefix: str) -> List[tuple]:
        """Collect flattened (path, fc_name) tuples for nested DA paths."""
        results: List[tuple] = []
        for child in (data_attribute.data_attributes or []):
            child_path = f"{prefix}.{child.name}"
            fc_name = child.fc.name if child.fc is not None else None
            results.append((child_path, fc_name))
            results.extend(collect_da_paths_from_da(child, child_path))
        return results

    def build_logical_node_details(ied_model: Optional[IedModel]) -> Dict[str, Dict[str, Any]]:
        """Build UI-friendly logical node details."""
        details: Dict[str, Dict[str, Any]] = {}
        if ied_model is None:
            return details

        for ld in (ied_model.logical_devices or []):
            for ln in (ld.logical_nodes or []):
                data_objects: List[Dict[str, Any]] = []
                data_attributes: List[str] = []
                da_fc_map: Dict[str, str] = {}
                report_control_blocks: List[Dict[str, Any]] = []
                datasets: List[Dict[str, Any]] = []
                ln_prefix = f"{ld.name}/{ln.name}."

                for data_object in (ln.data_objects or []):
                    cdc = (data_object.cdc or "").lower()
                    obj_info = {"name": data_object.name, "cdc": data_object.cdc}
                    
                    # Collect DataSets (from DataObjects with cdc="dataset")
                    if cdc == "dataset":
                        datasets.append(obj_info)
                    # Collect Report Control Blocks (RCB, BRCB, URCB) from DataObjects
                    elif cdc in ("rcb", "brcb", "urcb"):
                        report_control_blocks.append(obj_info)
                    
                    data_objects.append(obj_info)
                    for da_path, fc_name in collect_da_paths_from_do(data_object, data_object.name):
                        data_attributes.append(da_path)
                        if fc_name:
                            da_fc_map[f"{ln_prefix}{da_path}"] = fc_name

                # Also collect DataSets from ln.data_sets
                for ds in (ln.data_sets or []):
                    datasets.append({"name": ds.name, "cdc": "dataset"})

                # Also collect ReportControls from ln.rcbs
                for rcb in (ln.rcbs or []):
                    report_control_blocks.append({"name": rcb.name, "cdc": "rcb"})

                ln_key = f"{ld.name}/{ln.name}"
                details[ln_key] = {
                    "dataObjects": data_objects,
                    "dataAttributes": sorted(set(data_attributes)),
                    "dataAttributeFcs": da_fc_map,
                    "reportControlBlocks": report_control_blocks,
                    "dataSets": datasets,
                }

        return details

    def extract_tpa_info(websocket_info: Any) -> Dict[str, Any]:
        """Extract TPA (Three Part Address) and connection info from websocket_info."""
        info = {
            "peer_address": None,
            "peer_port": None,
            "role": "ACSI-Server",
            "ws_mode": "active",
            "remote_role": None,
            "tpa": None,
            "status": "active",
        }

        try:
            if hasattr(websocket_info, "remote_address"):
                addr_tuple = websocket_info.remote_address
                if isinstance(addr_tuple, tuple) and len(addr_tuple) >= 2:
                    info["peer_address"] = addr_tuple[0]
                    info["peer_port"] = addr_tuple[1]
            elif hasattr(websocket_info, "peername"):
                addr_tuple = websocket_info.peername()
                if isinstance(addr_tuple, tuple) and len(addr_tuple) >= 2:
                    info["peer_address"] = addr_tuple[0]
                    info["peer_port"] = addr_tuple[1]

            if hasattr(websocket_info, "tpa"):
                info["tpa"] = str(websocket_info.tpa)
            elif hasattr(websocket_info, "request") and hasattr(websocket_info.request, "headers"):
                headers = websocket_info.request.headers
                if "X-TPA" in headers:
                    info["tpa"] = headers["X-TPA"]

            if hasattr(websocket_info, "connected") and not websocket_info.connected:
                info["status"] = "disconnected"
            elif hasattr(websocket_info, "is_open") and not websocket_info.is_open():
                info["status"] = "disconnected"
        except Exception:
            pass

        return info

    # ==================== Route Handlers ====================

    @router.get(
        "/apis",
        summary="List All API Endpoints",
        description="Returns a comprehensive list of all available API endpoints with their HTTP methods, request body schemas, and response formats.",
        response_description="List of all endpoints with their metadata",
        tags=["Discovery"]
    )
    async def api_list_all_endpoints():
        """List all API endpoints with their schemas and metadata.

        This endpoint provides introspection capabilities, returning:
        - All available routes under /api/
        - HTTP methods supported by each endpoint
        - Request body schemas (when applicable)
        - Endpoint names for programmatic access

        Returns:
            dict: {
                "ok": True,
                "count": int,
                "endpoints": [
                    {
                        "path": str,
                        "methods": list[str],
                        "endpoint": str,
                        "body_schema": dict | None
                    }
                ]
            }
        """
        from pydantic import TypeAdapter

        routes = []
        for route in router.routes:
            path = f"/api{route.path}"
            methods = list(route.methods)

            body_schema = None
            if hasattr(route, 'body_field') and route.body_field:
                try:
                    model = route.body_field.annotation
                    if model is not Any:
                        adapter = TypeAdapter(model)
                        body_schema = adapter.json_schema()
                except Exception:
                    body_schema = None

            routes.append({
                "path": path,
                "methods": methods,
                "endpoint": route.name,
                "body_schema": body_schema
            })

        return {
            "ok": True,
            "count": len(routes),
            "endpoints": sorted(routes, key=lambda x: x["path"]),
        }

    @router.get(
        "/status",
        summary="Get Server Status",
        description="Retrieves the current operational status of the ACSI WebSocket.",
        response_description="Server status information",
        responses={
            200: {"description": "Server status returned successfully"},
            500: {"description": "Error retrieving server status"}
        },
        tags=["Server Control"]
    )
    def api_status():
        """Get current server status.

        Returns:
            JSONResponse: {
                "ok": True,
                "status": str  # One of: "stopped", "starting", "listening", "stopping", "error"
            }
        """
        try:
            return JSONResponse(
                content={"ok": True, "status": str(rti_fsp.get_status())},
                status_code=200
            )
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.get(
        "/health",
        summary="Health Check",
        description="Health check endpoint for service discovery and monitoring. Returns the service status and connection information.",
        response_description="Health status and service information",
        responses={
            200: {"description": "Service is healthy and running"},
            500: {"description": "Service is unhealthy"}
        },
        tags=["Health"]
    )
    def api_health():
        """Generic health endpoint used by external discovery (e.g., BFF network scan).

        Returns:
            dict: {
                "status": "ok",
                "service": "ACSI-Server",
                "server": {
                    "status": str | None,
                    "host": str | None,
                    "port": int | None
                }
            }
        """
        try:
            status = rti_fsp.get_status()
            return {
                "status": "ok",
                "service": "ACSI-Server",
                "server": {
                    "status": status.get("status"),
                    "host": status.get("host"),
                    "port": status.get("port"),
                },
            }
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.get(
        "/connections",
        summary="List Active Connections",
        description="Returns information about all currently connected active WebSockets, including peer addresses and connection status.",
        response_description="List of active WebSocket connections",
        responses={
            200: {"description": "List of connections returned successfully"},
            500: {"description": "Error retrieving connections"}
        },
        tags=["Connections"]
    )
    def api_connections():
        """Get TPA information for all connected servers.

        Returns:
            dict: {
                "ok": True,
                "role": "ACSI-Server",
                "ws_mode": "active",
                "connected_servers": int,
                "connections": list[dict]  # Each containing peer_address, peer_port, tpa, status
            }
        """
        try:
            endpoint = rti_fsp.runtime.endpoint
            connections = []

            if endpoint is not None and hasattr(endpoint, "websocket_info_list"):
                for ws_info in endpoint.websocket_info_list:
                    tpa_data = extract_tpa_info(ws_info)
                    connections.append(tpa_data)

            return {
                "ok": True,
                "role": "ACSI-Server",
                "ws_mode": "active",
                "connected_servers": len(connections),
                "connections": connections,
            }
        except Exception as exc:
            rti_fsp._log_action(f"Get connections failed: {exc}", "error")
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.get(
        "/properties",
        summary="Get Server Properties",
        description="Returns the static properties and capabilities of the ACSI server.",
        response_description="Server role and mode properties",
        tags=["Server Control"]
    )
    def api_roles():
        """Get property information for the server.

        Returns:
            dict: {
                "ok": True,
                "acsi_role": "ACSI-Server",
                "ws_mode": "Active"
            }
        """
        return {
            "ok": True,
            "acsi_role": "ACSI-Server",
            "ws_mode": "Active",
        }

    @router.get(
        "/model",
        summary="Get IED Model",
        description="Returns the current loaded IED model descriptor for UI rendering, including the complete hierarchy of logical devices, logical nodes, data objects, and data attributes.",
        response_description="Complete IED model tree structure",
        responses={
            200: {"description": "IED model data returned successfully"},
            500: {"description": "Error retrieving model"}
        },
        tags=["Model"]
    )
    def api_model():
        """Return current loaded model descriptor for UI rendering.

        The response includes:
        - Server information and access points
        - Complete IED model tree
        - Logical device map
        - Detailed logical node information with data objects and attributes

        Returns:
            dict: {
                "status": "ready",
                "accessPoints": list[str],
                "model": {
                    "server": {...},
                    "tree": {...},
                    "source": str,
                    "iedName": str,
                    "logicalDeviceMap": dict,
                    "logicalNodeDetails": dict
                }
            }
        """
        try:

            print("getting model for cp in fsp: ", rti_fsp.runtime.cp)
            ied_model: Optional[IedModel] = rti_fsp.runtime.ied_model
            source = rti_fsp.runtime.model_source
            selected_ied = rti_fsp.runtime.model_ied_name
            access_points = [rti_fsp.runtime.cp or "cp1"]

            print("selected_ied in fsp: ", selected_ied)

            logical_devices: List[str] = []
            if ied_model is not None:
                logical_devices = [ld.name for ld in (ied_model.logical_devices or [])]

            tree_data = serialize_ied_tree(ied_model) if ied_model is not None else None
            logical_node_details = build_logical_node_details(ied_model)

            result = {
                "status": "ready",
                "accessPoints": access_points,
                "model": {
                    "server": {
                        "name": "ACSI Server WS Active",
                        "mode": "active",
                        "logicalDevices": logical_devices,
                        "iedName": selected_ied,
                        "iedNames": [selected_ied] if selected_ied else [],
                    },
                    "tree": tree_data,
                    "source": source,
                    "iedName": selected_ied,
                    "logicalDeviceMap": {
                        ld.name: [ln.name for ln in (ld.logical_nodes or [])]
                        for ld in (ied_model.logical_devices or [])
                    }
                    if ied_model is not None
                    else {"-": ["No model loaded. Upload an .scl/.scd file."]},
                    "logicalNodeDetails": logical_node_details,
                },
            }
            has_tree = tree_data is not None
            print(
                f"[GET /ap/model] "
                f"ied_model={ied_model is not None} "
                f"has_tree={has_tree} "
                f"source={source!r} "
                f"iedName={selected_ied!r} "
                f"logicalDevices={logical_devices}"
            )
            return result
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.post(
        "/update-iedmodel",
        summary="Update IED Model",
        description="Updates the model.py file in the ACSI-Server directory and reloads the IED model. Supports dynamic hot-swap while server is running.",
        response_description="Model update confirmation",
        responses={
            200: {"description": "Model updated successfully"},
            202: {"description": "Model update accepted, hot-swap in progress"},
            400: {"description": "Invalid request"},
            500: {"description": "Error updating model"}
        },
        tags=["Model"]
    )
    def api_update_iedmodel(request: UpdateIedmodelRequest):
        """Update model.py in fsp directory and reload IED model.

        Supports dynamic model updates while the server is running (hot-swap).
        The new model will be applied immediately if the server is running,
        or loaded when the server starts.

        Request Body:
            UpdateIedmodelRequest: { "modelPy": str }

        Returns:
            dict: {
                "ok": True,
                "source": str,  # Path to the updated model file
                "ied": str,     # Name of the IED model
                "modelVersion": int,  # New model version number
                "dynamicReload": bool, # Whether hot-swap was performed
                "status": str   # "loaded" or "reloading"
            }
        """
        try:
            model_py = request.modelPy

            if not isinstance(model_py, str) or not model_py.strip():
                return JSONResponse(
                    content={"ok": False, "error": "modelPy is required and must be a non-empty string."},
                    status_code=400
                )

            # Check server status
            server_status = rti_fsp.get_status()
            is_running = server_status.get("status") == "listening"

            # Always apply dynamically if server is running
            ied_model = rti_fsp.update_model_file(model_py, apply_dynamically=True)

            rti_fsp._log_action(
                "IED model updated",
                detail={
                    "source": str(rti_fsp.model_file),
                    "ied": ied_model.name,
                    "dynamic": is_running,
                    "version": rti_fsp.runtime.model_version
                },
            )

            # Check if hot-swap is in progress
            if is_running and rti_fsp.runtime.model_reload_in_progress:
                return JSONResponse(
                    content={
                        "ok": True,
                        "source": str(rti_fsp.model_file),
                        "ied": ied_model.name,
                        "modelVersion": rti_fsp.runtime.model_version,
                        "dynamicReload": True,
                        "status": "reloading"
                    },
                    status_code=202  # Accepted - hot-swap in progress
                )
            else:
                return {
                    "ok": True,
                    "source": str(rti_fsp.model_file),
                    "ied": ied_model.name,
                    "modelVersion": rti_fsp.runtime.model_version,
                    "dynamicReload": is_running,
                    "status": "loaded"
                }

        except Exception as exc:
            rti_fsp._log_action(f"IED model update failed: {exc}", "error")
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=400
            )

    @router.post(
        "/update-iedmodel-file",
        summary="Update IED Model from File",
        description="Upload a model.py file directly. Supports dynamic hot-swap while server is running.",
        response_description="Model update confirmation",
        responses={
            200: {"description": "Model updated successfully"},
            202: {"description": "Model update accepted, hot-swap in progress"},
            400: {"description": "Invalid request"},
            500: {"description": "Error updating model"}
        },
        tags=["Model"]
    )
    async def api_update_iedmodel_file(file: UploadFile = File(...)):
        """Upload model.py file directly for update.

        Accepts multipart/form-data with a 'file' field containing the model.py content.
        Supports the same hot-swap behavior as the JSON endpoint.

        Args:
            file: UploadFile - The model.py file to upload

        Returns:
            dict: {
                "ok": True,
                "source": str,  # Path to the updated model file
                "ied": str,     # Name of the IED model
                "modelVersion": int,  # New model version number
                "dynamicReload": bool, # Whether hot-swap was performed
                "status": str   # "loaded" or "reloading"
            }
        """
        try:
            # Read file content as string
            model_py = await file.read()
            model_py = model_py.decode('utf-8')

            if not model_py.strip():
                return JSONResponse(
                    content={"ok": False, "error": "Uploaded file is empty."},
                    status_code=400
                )

            # Reuse existing logic
            server_status = rti_fsp.get_status()
            is_running = server_status.get("status") == "listening"

            ied_model = rti_fsp.update_model_file(model_py, apply_dynamically=True)

            rti_fsp._log_action(
                "IED model updated from file",
                detail={
                    "source": str(rti_fsp.model_file),
                    "ied": ied_model.name,
                    "dynamic": is_running,
                    "version": rti_fsp.runtime.model_version,
                    "filename": file.filename
                },
            )

            # Check if hot-swap is in progress
            if is_running and rti_fsp.runtime.model_reload_in_progress:
                return JSONResponse(
                    content={
                        "ok": True,
                        "source": str(rti_fsp.model_file),
                        "ied": ied_model.name,
                        "modelVersion": rti_fsp.runtime.model_version,
                        "dynamicReload": True,
                        "status": "reloading"
                    },
                    status_code=202  # Accepted - hot-swap in progress
                )
            else:
                return {
                    "ok": True,
                    "source": str(rti_fsp.model_file),
                    "ied": ied_model.name,
                    "modelVersion": rti_fsp.runtime.model_version,
                    "dynamicReload": is_running,
                    "status": "loaded"
                }

        except Exception as exc:
            rti_fsp._log_action(f"IED model file update failed: {exc}", "error")
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=400
            )

    @router.post(
        "/start",
        summary="Start Server",
        description="Starts the ACSI server - Active WebSocket on the specified host and port. Only 'server' mode is supported.",
        response_description="Server start confirmation",
        responses={
            200: {"description": "Server started successfully"},
            400: {"description": "Invalid parameters or server error"}
        },
        tags=["Server Control"]
    )
    def api_start(request: StartRequest):
        """Start the ACSI WebSocket server.

        Request Body:
            StartRequest: {
                "host": str,    # Hostname/IP to bind to
                "port": str,    # Port number to listen on
                "mode": str,    # Only 'server' mode supported
                "cp": str       # Communication point identifier
            }

        Returns:
            dict: {
                "ok": True,
                "status": "listening",
                "host": str,
                "port": int
            }

        Raises:
            HTTPException 400: If mode is not 'server' or port is invalid
            HTTPException 400: If server fails to start
        """
        try:
            host = request.host
            raw_port = request.port
            mode = request.mode
            cp = request.cp

            if mode != "server":
                return JSONResponse(
                    content={"ok": False, "error": "Only 'server' mode is supported in this app."},
                    status_code=400
                )
            try:
                port = int(raw_port)
            except (TypeError, ValueError):
                return JSONResponse(
                    content={"ok": False, "error": f"Invalid port value: {raw_port!r}"},
                    status_code=400
                )

            if cp:
                try:
                    rti_fsp._set_runtime_state(cp=cp)
                except Exception as exc:
                    return JSONResponse(
                        content={"ok": False, "error": f"Failed to set runtime state: {exc}"},
                        status_code=400
                    )

            try:
                rti_fsp.start_server(host, port)
            except Exception as exc:
                return JSONResponse(
                    content={"ok": False, "error": f"Failed to start server: {exc}"},
                    status_code=400
                )

            return {"ok": True, "status": "listening", "host": host, "port": port}
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": f"Unexpected error: {exc}"},
                status_code=400
            )

    @router.post(
        "/stop",
        summary="Stop Server",
        description="Stops the currently running ACSI WebSocket.",
        response_description="Server stop confirmation",
        responses={
            200: {"description": "Server stopped or stopping"},
            500: {"description": "Error stopping server"}
        },
        tags=["Server Control"]
    )
    def api_stop():
        """Stop the ACSI WebSocket Active.

        Returns:
            dict: {
                "ok": True,
                "status": str  # "stopped" or "stopping"
            }

        Raises:
            HTTPException 500: If error occurs during stop
        """
        try:
            status = rti_fsp.runtime.status
            if status in (None, "stopped"):
                return {"ok": True, "status": "stopped"}

            try:
                rti_fsp.stop_server()
                current = rti_fsp.runtime.status
                if current in ("stopping", "starting"):
                    return {"ok": True, "status": "stopping"}
                return {"ok": True, "status": "stopped"}
            except Exception as exc:
                current = rti_fsp.runtime.status
                if current in ("stopping", "stopped"):
                    return {"ok": True, "status": current}
                rti_fsp._log_action(f"Stop failed: {exc}", "error")
                return JSONResponse(
                    content={"ok": False, "error": f"Unexpected error: {exc}"},
                    status_code=500
                )
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": f"Unexpected error: {exc}"},
                status_code=500
            )

    @router.get(
        "/actions-logs",
        summary="Get Action Log",
        description="Retrieves the logged server actions for debugging and auditing purposes.",
        response_description="List of logged actions",
        responses={
            200: {"description": "List of actions returned successfully"},
            500: {"description": "Error retrieving actions"}
        },
        tags=["Logging"]
    )
    def api_actions():
        """Get logged server actions.

        Returns:
            dict: { "actions": list[dict] }
        """
        try:
            return {"actions": rti_fsp.get_actions()}
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": f"Unexpected error: {exc}"},
                status_code=500
            )

    @router.post(
        "/clear-logs",
        summary="Clear Action Log",
        description="Clears all logged server actions.",
        response_description="Action log clear confirmation",
        responses={
            200: {"description": "Actions cleared successfully"},
            500: {"description": "Error clearing actions"}
        },
        tags=["Logging"]
    )
    def api_actions_clear():
        """Clear action log.

        Returns:
            dict: { "ok": True }
        """
        try:
            rti_fsp.clear_actions()
            return {"ok": True}
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": f"Unexpected error: {exc}"},
                status_code=500
            )

    @router.get(
        "/messages",
        summary="Get Message Log",
        description="Retrieves the logged protocol messages for debugging purposes.",
        response_description="List of logged protocol messages",
        responses={
            200: {"description": "List of messages returned successfully"},
            500: {"description": "Error retrieving messages"}
        },
        tags=["Logging"]
    )
    def api_messages():
        """Get logged protocol messages.

        Returns:
            dict: { "messages": list[dict] }
        """
        try:
            return {"messages": rti_fsp.get_messages()}
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": f"Unexpected error: {exc}"},
                status_code=500
            )

    @router.post(
        "/clear-messages",
        summary="Clear Message Log",
        description="Clears all logged protocol messages.",
        response_description="Message log clear confirmation",
        responses={
            200: {"description": "Messages cleared successfully"},
            500: {"description": "Error clearing messages"}
        },
        tags=["Logging"]
    )
    def api_messages_clear():
        """Clear message log.

        Returns:
            dict: { "ok": True }
        """
        try:
            rti_fsp.clear_messages()
            return {"ok": True}
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": f"Unexpected error: {exc}"},
                status_code=500
            )

    @router.post(
        "/readvalue",
        summary="Read Value",
        description="Reads a value from the server's IED model. Requires the server to be running.",
        response_description="Read value result",
        responses={
            200: {"description": "Value read successfully"},
            400: {"description": "Missing objRef parameter"},
            403: {"description": "Server is not running"},
            404: {"description": "Instance not available or read timeout"},
            500: {"description": "Error reading value"}
        },
        tags=["Data Access"]
    )
    def api_read_value(request: ReadvalueRequest):
        """Read a value from the server IED model.

        Request Body:
            ReadvalueRequest: {
                "objRef": str,  # Required - Object reference in ACSI format
                "fc": str        # Optional - Functional constraint
            }

        Returns:
            dict: {
                "ok": True,
                "success": True,
                "objRef": str,
                "fc": str,
                "values": list[dict]  # Each containing type and value
            }

        Raises:
            HTTPException 400: If objRef is missing
            HTTPException 403: If server is not running
            HTTPException 404: If instance not available or timeout
        """
        try:
            obj_ref = request.objRef  # Fixed typo from request,object
            fc = request.fc

            if not obj_ref:
                rti_fsp._log_action("Server readvalue rejected: missing objRef", "warn")
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400
                )

            if rti_fsp.runtime.server is None:
                rti_fsp._log_action(
                    "Server readvalue rejected: server not running",
                    "warn",
                    detail={"objRef": obj_ref, "fc": fc},
                )
                return JSONResponse(
                    content={"ok": False, "error": "Server is not running"},
                    status_code=503
                )

            try:
                result = rti_fsp.read_value(obj_ref)

                if result is None:
                    rti_fsp._log_action(
                        "Server readvalue failed: instanceNotAvailable",
                        "warn",
                        detail={"objRef": obj_ref, "fc": fc},
                    )
                    return JSONResponse(
                        content={"ok": False, "error": "instanceNotAvailable"},
                        status_code=404
                    )



                print(
                    f"[POST /ap/readvalue] SUCCESS objRef={obj_ref!r} "
                    f"fc={fc!r} type={result.get('type')!r} value={result.get('value')!r}"
                )

                rti_fsp._log_action(
                    "Server readvalue",
                    detail={
                        "objRef": obj_ref,
                        "fc": fc,
                        "type": result.get("type"),
                        "value": result.get("value"),
                    },
                )
                return {
                    "ok": True,
                    "success": True,
                    "objRef": obj_ref,
                    "fc": fc,
                    "values": result,
                }

            except FuturesTimeoutError:
                rti_fsp._log_action(
                    "Server readvalue timeout",
                    "warn",
                    detail={"objRef": obj_ref, "fc": fc},
                )
                return JSONResponse(
                    content={"ok": False, "error": "read timeout"},
                    status_code=404
                )
            except ValueError as exc:
                rti_fsp._log_action(f"Server readvalue failed: {exc}", "warn")
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                rti_fsp._log_action(f"Server readvalue failed: {exc}", "error")
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=404
            )

    @router.post(
        "/writevalue",
        summary="Write Value",
        description="Writes a value to the server's IED model. Requires the server to be running.",
        response_description="Write value confirmation",
        responses={
            200: {"description": "Value written successfully"},
            400: {"description": "Missing parameters or invalid value"},
            403: {"description": "Server is not running"},
            404: {"description": "Write timeout"},
            500: {"description": "Error writing value"}
        },
        tags=["Data Access"]
    )
    async def api_write_value(request: WritevalueRequest):
        """Write a value in the server IED model.

        Request Body:
            WritevalueRequest: {
                "objRef": str,     # Required - Object reference
                "fc": str,        # Required - Functional constraint
                "value": str,     # Required - Value to write
                "dataType": str   # Optional - Data type for coercion
            }

        Returns:
            dict: {
                "ok": True,
                "success": True,
                "objRef": str,
                "fc": str,
                "value": any,
                "dataType": str
            }

        Raises:
            HTTPException 400: If objRef, fc, or value is missing
            HTTPException 403: If server is not running
            HTTPException 404: If write timeout occurs
        """
        try:
            obj_ref = request.objRef
            fc = request.fc
            value = request.value
            data_type = request.dataType

            if not obj_ref:
                rti_fsp._log_action("Server writevalue rejected: missing objRef", "warn")
                return JSONResponse(
                    content={"ok": False, "error": "objRef is required"},
                    status_code=400
                )

            if value is None:
                rti_fsp._log_action(
                    "Server writevalue rejected: missing value",
                    "warn",
                    detail={"objRef": obj_ref, "fc": fc},
                )
                return JSONResponse(
                    content={"ok": False, "error": "value is required"},
                    status_code=400
                )

            if rti_fsp.runtime.server is None:
                rti_fsp._log_action(
                    "Server writevalue rejected: server not running",
                    "warn",
                    detail={"objRef": obj_ref, "fc": fc, "value": value},
                )
                return JSONResponse(
                    content={"ok": False, "error": "Server is not running"},
                    status_code=503
                )

            try:
                result = rti_fsp.write_value(obj_ref, value, data_type)
                
                # Sync with mapped LED if mapping exists
                try:
                    # Get the existing IO router's client and mapping manager
                    from demo_IO.io_client.io_router import get_io_client, get_mapping_manager
                    
                    io_client = get_io_client()
                    if io_client and await io_client.is_healthy():
                        try:
                            # Try to sync device state based on written value
                            await io_client.write_iec61850_value(obj_ref, value)
                            logger.info(f"Synced IEC61850 write to device: {obj_ref}={value}")
                        except Exception as sync_exc:
                            logger.warning(f"Device sync failed for {obj_ref}: {sync_exc}")
                    else:
                        logger.debug("IO client not available or not healthy for device sync")
                except Exception as import_exc:
                    logger.debug(f"IO client not available for device sync: {import_exc}")
                
                return {
                    "ok": True,
                    "success": True,
                    "objRef": result["objRef"],
                    "fc": fc,
                    "value": result["value"],
                    "dataType": result["dataType"],
                }

            except FuturesTimeoutError:
                rti_fsp._log_action(
                    "Server writevalue timeout",
                    "warn",
                    detail={"objRef": obj_ref, "fc": fc},
                )
                return JSONResponse(
                    content={"ok": False, "error": "write timeout"},
                    status_code=504
                )
            except ValueError as exc:
                rti_fsp._log_action(f"Server writevalue failed: {exc}", "warn")
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=404
                )
            except Exception as exc:
                rti_fsp._log_action(f"Server writevalue failed: {exc}", "error")
                return JSONResponse(
                    content={"ok": False, "error": str(exc)},
                    status_code=500
                )
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    return router, rti_fsp

def create_fastapi_app(factory_dir: Optional[Path] = None) -> FastAPI:

    """Create and configure the FastAPI application for ACSI server BFF."""
    app = FastAPI(
        title="ACSI Server WS Active",
        description="Backend for Frontend (BFF) endpoint providing REST API for ACSI Server control. "
                    "This service manages ACSI Server WebSocket Active lifecycle, IED models, data access, "
                    "and provides comprehensive monitoring capabilities.",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        openapi_tags=[
            {
                "name": "Server Control",
                "description": "Start, stop, and manage the ACSI Server WebSocket Active lifecycle"
            },
            {
                "name": "Model",
                "description": "Load, update, and manage IED models"
            },
            {
                "name": "Data Access",
                "description": "Read and write values to/from the IED model"
            },
            {
                "name": "Connections",
                "description": "View and manage active WebSocket connections"
            },
            {
                "name": "Logging",
                "description": "View and clear action and message logs"
            },
            {
                "name": "Health",
                "description": "Service health checks and status monitoring"
            },
            {
                "name": "Discovery",
                "description": "API introspection and endpoint discovery"
            }
        ]
    )

    resolved_factory_dir = os.getenv('MODELPATH') or factory_dir or Path(__file__).parent
    router, _server = create_bff_router(resolved_factory_dir)
    app.include_router(router)
    
    # Include IO router for LED control via demo_IO
    try:
        import sys
        # Add parent directory to path so we can import from demo_IO
        demo_io_parent = Path(__file__).parent.parent
        if str(demo_io_parent) not in sys.path:
            sys.path.insert(0, str(demo_io_parent))
        
        from demo_IO.io_client.io_router import create_io_router
        io_router = create_io_router()
        app.include_router(io_router)
        logger.info("IO router included for demo_IO LED control")
    except ImportError as e:
        logger.warning(f"IO router not available (missing dependencies): {e}")
    except Exception as e:
        logger.error(f"Failed to include IO router: {e}")
    
    app.state.server = _server
    return app

if __name__ == "__main__":
    import uvicorn
    factory_dir = Path(__file__).parent
    app = create_fastapi_app(factory_dir)
    port = int(os.getenv("PORT", "5001"))
    uvicorn.run(app, host="0.0.0.0", port=port)
