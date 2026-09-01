"""Backend for Frontend (BFF) endpoint providing REST API for ACSI server control.

This module exposes REST API endpoints that interact with the ACSI server,
handling model management, server lifecycle, and value operations.
"""
from __future__ import annotations

import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(threadName)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)  # Force stdout for Docker
    ],
    force=True  # Override any existing config
)

logger = logging.getLogger(__name__)

# Global flag to control io_client usage
_use_io_client = True

from concurrent.futures import TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Any, Dict, List, Optional
from acsi_server import ACSIServer
from ws61850.iec61850.data_model.ied_model import DataAttribute, DataObject, IedModel
from fastapi import FastAPI, APIRouter, Request, HTTPException, status, UploadFile, File
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict
import ssl
from ws61850.security.tls import TLSConfig
import asyncio
import json

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


class IoClientConfigRequest(BaseModel):
    """Request body for enabling/disabling io_client usage."""
    enabled: bool = Field(
        ...,
        description="Whether to enable io_client for device sync",
        json_schema_extra={"example": True}
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

class TLSConnectionCreateConfigRequest(BaseModel):
    """Request body for creating a new connection."""

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

    connection_name: str = Field(..., description="Human-readable name for the connection", json_schema_extra={"example": "RTI-FSP-01"})
    enable_tls: bool = Field(default=False, description="enable TLS", json_schema_extra={"example": False})
    tls_version: str = Field(default= "1.2", description="TLS version", json_schema_extra={"example": "1.2"})

    server_key: str | None = Field(
        default=None,
        description="Server private key",
        json_schema_extra={"example": "-----BEGIN PRIVATE KEY-----..."},
    )
    server_cert: str | None = Field(
        default=None,
        description="Server certificate",
        json_schema_extra={"example": "-----BEGIN CERTIFICATE-----..."},
    )
    server_ca: str | None = Field(
        default=None,
        description="Server CA certificate",
        json_schema_extra={"example": "-----BEGIN CERTIFICATE-----..."},
    )

    ws_mode : str = Field(default="passive", description="WebSocket mode (passive or active)", json_schema_extra={"example": "passive"})

class OAUTHCreateConfigRequest(BaseModel):
    """Request body for OAuth reconfiguration."""
    connection_name: Optional[str] = Field(default=None, description="Connection name (optional, auto-detected)", json_schema_extra={"example": "RTI-FSP-01"})
    enable_oauth: bool = Field(default=False, description="Enable OAuth authentication", json_schema_extra={"example": False})
    host: str = Field(default="127.0.0.1", description="ws host", json_schema_extra={"example": "127.0.0.1"})
    port: str = Field(default="8765", description="ws port", json_schema_extra={"example": "8765"})
    cp: str = Field(default="cp1", description="Communication point identifier", json_schema_extra={"example": "cp1"})
    ws_mode: str = Field(default="active", description="WebSocket mode (passive or active)", json_schema_extra={"example": "active"})
    # OAuth settings for FSP (active mode)
    token_endpoint_url: Optional[str] = Field(default=None, description="OAuth Token endpoint URL", json_schema_extra={"example": "https://auth.example.com/token"})
    client_id: Optional[str] = Field(default=None, description="OAuth Client ID", json_schema_extra={"example": "my-client-id"})
    client_secret: Optional[str] = Field(default=None, description="OAuth Client Secret", json_schema_extra={"example": "my-client-secret"})
    ca_certificate: Optional[str] = Field(default=None, description="Server CA certificate", json_schema_extra={"example": "-----BEGIN CERTIFICATE-----..."})
    enable_token_refresh: bool = Field(default=False, description="Enable token refresh", json_schema_extra={"example": False})

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

    def on_connected_callback(associate_response):
        """Callback for sent associateResponse messages."""
        logger.info(f"[FSP CONNECTED] associateResponse: {associate_response}")
        
        if _use_io_client:
            try:
                from demo_IO.io_client.io_router import get_io_client, get_mapping_manager
                from demo_IO.io_client.io_utils import sync_to_io_device, write_to_lcd
                
                io_client = get_io_client()
                mapping_manager = get_mapping_manager()
                logger.info(f"[FSP] IO client for connected: {io_client}")
                if io_client:
                    # Use associateId as identifier, or a default
                    associate_id = associate_response.get("associateId", "fsp_connected")
                    # Turn LED ON (write True/1 to the LED reference)
                    asyncio.create_task(
                        sync_to_io_device(io_client, associate_id, True)
                    )
                    
                    # Write connection info to LCD
                    value = f"FSP Connected: {associate_id}"
                    asyncio.create_task(
                        write_to_lcd(io_client, associate_id, value, mapping_manager=mapping_manager)
                    )
                else:
                    logger.warning("[FSP] IO client is None - cannot turn on LED. Call /api/io/connect first.")
            except ImportError as e:
                logger.error(f"[FSP] ImportError - Cannot import IO client: {e}")
            except Exception as e:
                logger.error(f"[FSP] Exception in IO connected callback: {e}")

    rti_fsp.install_connected_callback(on_connected_callback)

    def on_operate_received_callback(operate_data):
        """Callback for received operate request messages - blinks LED."""
        logger.info(f"[FSP OPERATE RECEIVED] operate request: {operate_data}")
        
        # Blink LED on operate
        if _use_io_client:
            try:
                from demo_IO.io_client.io_router import get_io_client, get_mapping_manager
                from demo_IO.io_client.io_utils import blink_led_task
                
                io_client = get_io_client()
                mapping_manager = get_mapping_manager()
                if io_client:
                
                    asyncio.create_task(
                        blink_led_task(io_client, "oper_rcv", interval=0.2, count=1, mapping_manager=mapping_manager)
                    )
                else:
                    logger.warning("[FSP] IO client is None - cannot blink LED. Call /api/io/connect first.")
            except ImportError as e:
                logger.error(f"[FSP] ImportError - Cannot import IO client: {e}")
            except Exception as e:
                logger.error(f"[FSP] Exception in operate received callback: {e}")

    def on_operate_response_callback(operate_response):
        """Callback for sent operate response messages - prints to LCD."""
        logger.info(f"[FSP OPERATE RESPONSE] operate response: {operate_response}")
        
        # Print operation result to LCD
        if _use_io_client:
            try:
                from demo_IO.io_client.io_router import get_io_client, get_mapping_manager
                from demo_IO.io_client.io_utils import write_to_lcd
                
                io_client = get_io_client()
                if io_client:
                    mapping_manager = get_mapping_manager()

                    success = operate_response.get("success", False)
                    add_cause = operate_response.get("addCause", "")
                    
                    if success:
                        value = "Operation: SUCCESS"
                    else:
                        value = f"Operation: FAILED - {add_cause}" if add_cause else "Operation: FAILED"
                    
                    asyncio.create_task(
                        write_to_lcd(io_client, "oper_send", value, mapping_manager=mapping_manager)
                    )
                else:
                    logger.warning("[FSP] IO client is None - cannot write to LCD. Call /api/io/connect first.")
            except ImportError as e:
                logger.error(f"[FSP] ImportError - Cannot import IO client: {e}")
            except Exception as e:
                logger.error(f"[FSP] Exception in operate response callback: {e}")

    rti_fsp.install_operate_received_callback(on_operate_received_callback)
    rti_fsp.install_operate_response_callback(on_operate_response_callback)

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

    async def _wait_for_runtime_loop(rti_fsp, timeout: float = 5.0) -> asyncio.AbstractEventLoop:
        """Poll until the server's background event loop is created and running,
        or raise if it doesn't show up within `timeout` seconds."""
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            loop = rti_fsp.runtime.loop
            if loop is not None and loop.is_running():
                return loop
            if asyncio.get_event_loop().time() >= deadline:
                raise RuntimeError("server-failed-to-start")
            await asyncio.sleep(0.05)

    @router.post(
        "/reconfig-connection",
        summary="Get Connection Info",
        description="Returns detailed information about the current WebSocket connection, including peer address, port, and connection status.",
        response_description="Connection details",
        responses={
            200: {"description": "Connection information returned successfully"},
            500: {"description": "Error retrieving connection info"}
        },
        tags=["Client Status"]
    )
    async def api_reconfig_connection(request: TLSConnectionCreateConfigRequest):
        """Reconfigure the connection with a new communication point."""
        try:
            rti_fsp._log_action(f"Starting connection reconfiguration for host: {request.host}, port: {request.port}", "info")
            # Normalize tls_version to handle "1.2", "1.3", "TLSv1_2", "TLSv1_3" formats
            tls_version_str = (request.tls_version or "1.3").lower()
            if "1.2" in tls_version_str or "1_2" in tls_version_str:
                tls_version = ssl.TLSVersion.TLSv1_2
            else:
                tls_version = ssl.TLSVersion.TLSv1_3
            rti_fsp._log_action(f"TLS version determined: {tls_version} (from request: {request.tls_version})", "info")
            print("tls_version in reconfig connection: ", tls_version, "(from request:", request.tls_version, ")")
            host = request.host
            request_port = request.port
            if request.ws_mode.lower() == "active":
                # Only create TLSConfig if TLS is enabled
                tls_config = None
                if request.enable_tls:
                    tls_config = TLSConfig(
                        mode="client",
                        cafile=request.server_ca,
                        min_version=tls_version,
                        max_version=tls_version,
                        keylog_file=os.path.join("/app/fsp", "tlskeys.log"),
                    )
                cp = os.getenv("CP", "cp1")

                loop = rti_fsp.runtime.loop
                if loop is None or not loop.is_running():
                    rti_fsp._log_action("Server not running, starting server instance", "info")
                    print("server not running, starting server instance")
                    rti_fsp.start_server(host, int(request_port))
                    loop = await _wait_for_runtime_loop(rti_fsp, timeout=5.0)
                    rti_fsp._log_action("Server instance started", "info")

                endpoint = rti_fsp.runtime.endpoint
                if endpoint is None:
                    return JSONResponse(
                        content={"ok": False, "error": "Endpoint not initialized"},
                        status_code=500,
                    )

                # Call reconfigure_connection on the endpoint's event loop
                # The library handles TLS config and task restart internally
                rti_fsp._log_action(f"Calling reconfigure_connection for host: {host}, port: {request_port}, TLS: {request.enable_tls}", "info")
                fut = asyncio.run_coroutine_threadsafe(
                    endpoint.reconfigure_connection(
                        host, request_port, cp, request.enable_tls, tls_config=tls_config
                    ),
                    loop,
                )
                # Wait for the reconfiguration to complete
                try:
                    await asyncio.wrap_future(fut)
                    rti_fsp._log_action("Connection reconfigured successfully", "info")
                except Exception as e:
                    rti_fsp._log_action(f"Error during reconfigure_connection: {e}", "error")
                    print(f"Error during reconfigure_connection: {e}")
                    # Don't fail the endpoint - the connection may still have been restarted
                    # Just log and continue
                
                rti_fsp.runtime.tasks["ws"] = endpoint._connect_task

                print("Reconfigured connection with TLS enabled:", request.enable_tls)
                return JSONResponse(
                    content={"ok": True, "status": "reconfigured", "ws_mode": request.ws_mode,
                             "enable_tls": request.enable_tls},
                    status_code=200,
                )
            else:
                return JSONResponse(
                    content={"ok": False, "error": "Only active mode is supported for reconfiguration."},
                    status_code=400,
                )
        except Exception as exc:
            rti_fsp._log_action(f"api_reconfig_connection failed: {exc}", "error")
            return JSONResponse(content={"ok": False, "error": str(exc)}, status_code=500)

    @router.get(
        "/tls-config",
        summary="Get TLS Configuration",
        description="Returns the current TLS configuration from runtime variables.",
        response_description="TLS configuration from runtime",
        responses={
            200: {"description": "TLS configuration returned successfully"},
            500: {"description": "Error retrieving TLS configuration"}
        },
        tags=["TLS"]
    )
    def api_get_tls_config():
        """Get current TLS configuration from runtime.

        Returns: TLS configuration from the endpoint's runtime state including:
        - enable_tls: Whether TLS is enabled
        - tls_version: TLS version (1.2 or 1.3)
        - server_key: Server private key (for server mode)
        - server_cert: Server certificate (for server mode)
        - server_ca: CA certificate (for client mode)
        - ws_mode: WebSocket mode (active or passive)
        """
        try:
            endpoint = rti_fsp.runtime.endpoint
            if endpoint is None:
                return JSONResponse(
                    content={"ok": False, "error": "Endpoint not available"},
                    status_code=500
                )

            # Get TLS config from runtime
            enable_tls = False
            tls_version = "1.2"
            server_key = None
            server_cert = None
            server_ca = None

            if hasattr(endpoint, '_tls_config') and endpoint._tls_config is not None:
                tls_config = endpoint._tls_config
                enable_tls = True
                # Extract TLS version from config
                if hasattr(tls_config, 'min_version'):
                    if tls_config.min_version == ssl.TLSVersion.TLSv1_3:
                        tls_version = "1.3"
                    elif tls_config.min_version == ssl.TLSVersion.TLSv1_2:
                        tls_version = "1.2"
                if hasattr(tls_config, 'cafile'):
                    server_ca = tls_config.cafile
                if hasattr(tls_config, 'certfile'):
                    server_cert = tls_config.certfile
                if hasattr(tls_config, 'keyfile'):
                    server_key = tls_config.keyfile
            
            # Get ws_mode
            ws_mode = "active"
            if hasattr(endpoint, 'ws_mode'):
                ws_mode = endpoint.ws_mode
            elif hasattr(rti_fsp.runtime, 'ws_mode'):
                ws_mode = rti_fsp.runtime.ws_mode

            return {
                "ok": True,
                "enable_tls": enable_tls,
                "tls_version": tls_version,
                "server_key": server_key,
                "server_cert": server_cert,
                "server_ca": server_ca,
                "ws_mode": ws_mode
            }
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.post(
        "/reconfig-oauth",
        summary="Get Connection Info",
        description="Returns detailed information about the current WebSocket connection, including peer address, port, and connection status.",
        response_description="Connection details",
        responses={
            200: {"description": "Connection information returned successfully"},
            500: {"description": "Error retrieving connection info"}
        },
        tags=["Client Status"]
    )
    async def api_reconfig_oauth(request: OAUTHCreateConfigRequest):
        """Reconfigure OAuth settings. OAuth config should be provided in the request by BFF."""
        try:
            rti_fsp._log_action(f"Starting OAuth reconfiguration for connection: {request.connection_name or 'unknown'}", "info")
            cp = request.cp or os.getenv("CP", "cp1")
            host = request.host
            oauth_port = request.port
            
            # Get OAuth settings from request (BFF should provide these from connections.json)
            token_endpoint = getattr(request, 'token_endpoint_url', None) or getattr(request, 'token_endpoint', None)
            client_id = getattr(request, 'client_id', None)
            client_secret = getattr(request, 'client_secret', None)
            ca_certificate = getattr(request, 'ca_certificate', None)
            enable_token_refresh = getattr(request, 'enable_token_refresh', False)
            
            connection_name = request.connection_name or "unknown"
            rti_fsp._log_action(f"OAuth configuration - enable: {request.enable_oauth}, connection: {connection_name}", "info")
            
            # Validate that required OAuth settings are provided
            if request.enable_oauth and not token_endpoint:
                error_msg = f"token_endpoint is required for OAuth but was not provided in request for connection: {connection_name}"
                rti_fsp._log_action(error_msg, "error")
                raise ValueError(error_msg)
            
            # When disabling OAuth, pass None to signal that OAuth should be disabled
            # The underlying library should handle None properly
            if not request.enable_oauth:
                rti_fsp._log_action("Disabling OAuth for connection", "info")
                token_endpoint = None
                client_id = None
                client_secret = None
                ca_certificate = None
            
            print("Reconfiguring OAuth with connection: ", connection_name)
            print(f"OAuth enable: {request.enable_oauth}, token_endpoint: {token_endpoint}")

            loop = rti_fsp.runtime.loop
            if loop is None or not loop.is_running():
                rti_fsp._log_action("Server not running, starting server instance for OAuth reconfig", "info")
                print("server not running, starting server instance")
                rti_fsp.start_server(host, int(oauth_port))
                loop = await _wait_for_runtime_loop(rti_fsp, timeout=5.0)
                rti_fsp._log_action("Server instance started for OAuth reconfig", "info")

            # When disabling OAuth, stop the endpoint first to avoid issues with ClientCredentialsProvider
            if not request.enable_oauth:
                rti_fsp._log_action("Disabling OAuth - stopping endpoint first", "info")
                print("Disabling OAuth - stopping endpoint first")
                # Stop the current connection if it exists
                if hasattr(rti_fsp.runtime.endpoint, '_connect_task') and rti_fsp.runtime.endpoint._connect_task is not None:
                    stop_fut = asyncio.run_coroutine_threadsafe(
                        rti_fsp.runtime.endpoint._cancel_task(rti_fsp.runtime.endpoint._connect_task),
                        loop,
                    )
                    await asyncio.wrap_future(stop_fut)
                rti_fsp._log_action("Endpoint stopped, now reconfiguring with OAuth disabled", "info")
                print("Endpoint stopped, now reconfiguring with OAuth disabled")

            # Call reconfigure_oauth with settings from connection
            rti_fsp._log_action(f"Calling reconfigure_oauth for host: {host}, port: {oauth_port}, OAuth: {request.enable_oauth}", "info")
            fut = asyncio.run_coroutine_threadsafe(
                rti_fsp.runtime.endpoint.reconfigure_oauth(
                    host=host,
                    port=str(oauth_port),
                    cp=cp,
                    oauth_enable=request.enable_oauth,
                    token_endpoint=token_endpoint,
                    client_id=client_id,
                    client_secret=client_secret,
                    kc_cert=ca_certificate,
                    enable_token_refresh=enable_token_refresh,
                ),
                loop,
            )
            await asyncio.wrap_future(fut)
            rti_fsp._log_action("OAuth reconfigured successfully", "info")
            rti_fsp.runtime.tasks["ws"] = rti_fsp.runtime.endpoint._connect_task

            return JSONResponse(
                content={"ok": True, "status": "reconfigured", "ws_mode": "active",
                         "enable_oauth": request.enable_oauth},
                status_code=200,
            )
        except Exception as exc:
            import traceback
            print("Reconfig OAuth error:", exc)
            print("Traceback:", traceback.format_exc())
            rti_fsp._log_action(f"api_reconfig_oauth failed: {exc}", "error")
            return JSONResponse(content={"ok": False, "error": str(exc)}, status_code=500)

    @router.get(
        "/oauth-status",
        summary="Get OAuth Status",
        description="Returns whether OAuth is currently enabled or disabled for this FSP server.",
        response_description="OAuth enable status",
        responses={
            200: {"description": "OAuth status returned successfully"},
            500: {"description": "Error retrieving OAuth status"}
        },
        tags=["OAuth"]
    )
    def api_get_oauth_status():
        """Get current OAuth enable/disable status from the FSP server.

        Returns:
            dict: {
                "ok": True,
                "enable_oauth": bool  # Current OAuth status
            }
        """
        try:
            # Check the runtime endpoint's OAuth enable status
            if hasattr(rti_fsp.runtime, 'endpoint') and hasattr(rti_fsp.runtime.endpoint, '_oauth_enable'):
                enable_oauth = rti_fsp.runtime.endpoint._oauth_enable
                return {"ok": True, "enable_oauth": enable_oauth}
            else:
                # If endpoint not available or attribute not found, check if OAuth is configured
                return {"ok": True, "enable_oauth": False}
        except Exception as exc:
            return JSONResponse(
                content={"ok": False, "error": str(exc)},
                status_code=500
            )

    @router.get(
        "/io-client",
        summary="Get IO Client Status",
        description="Returns whether io_client is enabled for device sync.",
        response_description="IO client status",
        responses={
            200: {"description": "IO client status returned successfully"}
        },
        tags=["IO Client"]
    )
    def api_get_io_client_status():
        """Get current io_client usage status.
        
        Returns:
            dict: {"enabled": bool}
        """
        return {"enabled": _use_io_client}

    @router.post(
        "/io-client",
        summary="Set IO Client Usage",
        description="Enable or disable io_client for syncing writes to physical IO devices.",
        response_description="IO client configuration confirmation",
        responses={
            200: {"description": "IO client configuration updated successfully"},
            500: {"description": "Error updating configuration"}
        },
        tags=["IO Client"]
    )
    def api_set_io_client(request: IoClientConfigRequest):
        """Enable or disable io_client usage.
        
        When enabled, writes to the ACSI server will be synced to physical IO devices.
        When disabled, writes will only affect the ACSI server model.
        
        Request Body:
            IoClientConfigRequest: {"enabled": bool}
        
        Returns:
            dict: {"ok": True, "enabled": bool, "message": str}
        """
        global _use_io_client
        _use_io_client = request.enabled
        logger.info(f"IO client usage set to: {_use_io_client}")
        return {
            "ok": True,
            "enabled": _use_io_client,
            "message": f"IO client {'enabled' if _use_io_client else 'disabled'}"
        }

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
                
                # Sync with mapped device if io_client is enabled (fire-and-forget)
                if _use_io_client:
                    try:
                        # Get the existing IO router's client and mapping manager
                        from demo_IO.io_client.io_router import get_io_client, get_mapping_manager
                        from demo_IO.io_client.io_utils import sync_to_io_device, write_to_lcd
                        
                        io_client = get_io_client()
                        logger.info(f"IO client for sync: {io_client}")
                        if io_client:
                            # Fire-and-forget: don't wait for IO sync to complete
                            # Check health and sync in background
                            asyncio.create_task(
                                sync_to_io_device(io_client, obj_ref, value)
                            )

                            value_write = f"{obj_ref} : {value}"

                            asyncio.create_task(
                                write_to_lcd(io_client, "writeValue", value_write, mapping_manager=mapping_manager)
                            )
                        else:
                            logger.warning("IO client is None - cannot sync to device. Call /api/io/connect first.")
                    except ImportError as e:
                        logger.error(f"ImportError - Cannot import IO client: {e}")
                    except Exception as e:
                        logger.error(f"Exception in IO sync setup: {e}")
                
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
            },
            {
                "name": "IO Client",
                "description": "Enable/disable and check IO client sync with physical devices"
            }
        ]
    )

    resolved_factory_dir = os.getenv('MODELPATH') or factory_dir or Path(__file__).parent
    router, _server = create_bff_router(resolved_factory_dir)
    app.include_router(router)
    
    # Include IO router for device control via demo_IO
    # Add CORS middleware to allow requests from frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
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
        logger.info("IO router included for demo_IO device control")
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
