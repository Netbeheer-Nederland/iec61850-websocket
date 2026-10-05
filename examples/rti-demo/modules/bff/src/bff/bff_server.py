# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
#
# Copyright 2025 Netbeheer Nederland
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import ast
import asyncio
import importlib.util
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx2 as httpx
import requests
from fastapi import (
    FastAPI,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from bff.bff_client import BffClient
from bff.connection_manager import ConnectionManager
from bff.playbook import BffTransport, PlaybookError, parse_playbook, step_label
from bff.playbook_runs import PlaybookBusy, PlaybookRuns
from bff.playbook_store import BuiltinPlaybookError, PlaybookNameError, PlaybookStore
from bff.pydantic_models import (
    ConnectionCreateRequest,
    ConnectionUpdateRequest,
    ExecuteRequest,
    OAUTHConnectionCreateConfigRequest,
    PlaybookRunRequest,
    PlaybookSaveRequest,
    TLSConnectionCreateConfigRequest,
)

# uvloop (which uvicorn runs on when it's installed) resolves hostnames on
# libuv's thread pool - 4 threads unless UV_THREADPOOL_SIZE says otherwise.
# The status monitor checks every instance at once, and a lookup of a
# hostname that no longer resolves (a removed FSP, an IDP that isn't
# running) holds a thread for seconds before failing. Two of those were
# enough to queue the SO's own lookup past its health check's 2 s timeout,
# every round, so a live SO showed as down. libuv reads this when its pool
# first starts, so it is set before the event loop does any work.
os.environ.setdefault("UV_THREADPOOL_SIZE", "32")

# Global state
_bff_clients: dict[str, BffClient] = {}


# Configure logging
def resolve_log_level(value: str | None, default: int = logging.INFO) -> int:
    """Map a level name (case-insensitive) to a logging constant.

    Falls back to ``default`` for unknown/empty values instead of letting
    ``basicConfig`` raise ``ValueError`` and abort startup. Also accepts a
    numeric string (e.g. "10") and uvicorn's "trace" alias.
    """
    if value is None:
        return default
    name = str(value).strip().upper()
    if not name:
        return default
    if name.isdigit():
        return int(name)
    if name == "TRACE":  # uvicorn alias, no stdlib equivalent
        return logging.DEBUG
    level = logging.getLevelName(name)  # returns int for known names, str otherwise
    return level if isinstance(level, int) else default


# Module-level default from the environment; the __main__ CLI can override it.
LOG_LEVEL = resolve_log_level(os.getenv("LOG_LEVEL"))

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(threadName)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)  # Force stdout for Docker
    ],
    force=True,  # Override any existing config
)

# Apply the severity to the root logger here at import time, not only in the
# __main__ block, so every entry point honours LOG_LEVEL: `python
# bff/bff_server.py`, `uvicorn bff.bff_server:app`, a service wrapper, or
# pytest importing the module. Child loggers and the status-monitor / thread
# pool workers inherit this level.
logging.getLogger().setLevel(LOG_LEVEL)

logger = logging.getLogger(__name__)


class HealthCheckAccessFilter(logging.Filter):
    """Demote uvicorn access-log lines for health/status polls to DEBUG.

    The Docker health check hits ``/api/health`` (and the HMI polls it plus
    ``/api/status`` and ``/api/messages``) every few seconds; logged at INFO
    they bury the real request log. Matching records are relabeled DEBUG and
    only pass through when the ``uvicorn.access`` logger is actually at
    DEBUG.
    """

    QUIET_PATHS = ("/api/status", "/api/health", "/api/messages")

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        # uvicorn access records: (client_addr, method, path, http_version, status)
        if not isinstance(args, tuple) or len(args) < 3:
            return True
        path = str(args[2]).split("?", 1)[0]
        if path not in self.QUIET_PATHS:
            return True
        record.levelno = logging.DEBUG
        record.levelname = "DEBUG"
        return logging.getLogger("uvicorn.access").isEnabledFor(logging.DEBUG)


# Check whether the docker Python SDK is available for auto-discovery, without
# actually importing it here since nothing in this module uses it directly.
DOCKER_AVAILABLE = importlib.util.find_spec("docker") is not None
if not DOCKER_AVAILABLE:
    logger.warning(
        "Docker Python SDK not available. Container auto-discovery disabled."
    )

# Determine base directory - check /app (Docker), then script dir, then parent dir
script_dir = os.path.dirname(os.path.abspath(__file__))
if os.path.exists("/app"):
    BASE_DIR = "/app"
elif os.path.exists(os.path.join(script_dir, "connections.json")):
    BASE_DIR = script_dir
else:
    # Try parent directory
    parent_dir = os.path.dirname(script_dir)
    if os.path.exists(os.path.join(parent_dir, "connections.json")):
        BASE_DIR = parent_dir
    else:
        BASE_DIR = script_dir

# Ensure base directory exists
os.makedirs(BASE_DIR, exist_ok=True)

# BFF_CONNECTIONS_FILE lets the deployment override where connection state is
# persisted. In Docker BASE_DIR is '/app', which is root-owned while the process
# runs as the unprivileged 'app' user, so the atomic save (temp file + rename in
# the same directory) fails with EACCES. docker-compose.yml points this at a
# dedicated, writable /config directory backed by a named volume.
CONNECTIONS_FILE = os.environ.get("BFF_CONNECTIONS_FILE") or os.path.join(
    BASE_DIR, "connections.json"
)
STATS_FILE = os.path.join(BASE_DIR, "stats.json")

# Seed a freshly mounted config location (e.g. an empty Docker volume) once from
# the connections.json shipped next to this module, so existing connections
# survive the first start. After that the configured file is authoritative.
_seed_connections = os.path.join(script_dir, "connections.json")
if (
    not os.path.exists(CONNECTIONS_FILE)
    and os.path.exists(_seed_connections)
    and os.path.abspath(_seed_connections) != os.path.abspath(CONNECTIONS_FILE)
):
    try:
        import shutil

        os.makedirs(os.path.dirname(CONNECTIONS_FILE) or ".", exist_ok=True)
        shutil.copyfile(_seed_connections, CONNECTIONS_FILE)
        logger.info("Seeded %s from %s", CONNECTIONS_FILE, _seed_connections)
    except OSError as e:
        logger.warning(
            "Could not seed %s from %s: %s", CONNECTIONS_FILE, _seed_connections, e
        )


# Initialize managers
conn_manager = ConnectionManager(
    bff_clients=_bff_clients, connections_file=CONNECTIONS_FILE, logger=logger
)

# ==================== Browser Push Relay (WebSocket) ====================
#
# The HMI used to learn about connection/message changes purely by polling
# (every 1s for connections, every 5-10s per open MessageMonitor/action log).
# This hub fans out server-pushed updates to every connected browser tab over
# a single /ws endpoint, and push_relay_loop() is the one place that polls the
# RTI-SO/RTI-FSP instances on their behalf, so N open tabs cost one poll
# cycle instead of N.


class WSHub:
    """Tracks connected browser WebSocket clients and broadcasts JSON messages."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def register(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.add(ws)

    async def unregister(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, message: dict[str, Any]) -> None:
        async with self._lock:
            clients = list(self._clients)
        if not clients:
            return
        dead = []
        for ws in clients:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)


ws_hub = WSHub()

# Tracks the highest message "id" already relayed per "host:port" target, so
# push_relay_loop() only broadcasts messages a browser hasn't seen yet.
_last_relayed_message_id: dict[str, int] = {}

# Same, for each target's actions log (only its kind "acsi" entries are
# relayed - see _relay_new_actions).
_last_relayed_action_id: dict[str, int] = {}

# Tracks the last-relayed acsi_client_list snapshot per "host:port" target
# (RTI-SO only), so push_relay_loop() only broadcasts when it actually
# changes (an FSP associating with, or dropping, one of the SO's cps).
_last_relayed_client_list: dict[str, list[str]] = {}


def _parse_status_repr(raw: Any) -> dict[str, Any] | None:
    """Parse the FSP's /api/status 'status' field.

    fsp/acsi_server.py's api_status() returns str(dict) - a Python repr
    (single-quoted, True/False/None) rather than JSON - so json.loads can't
    read it. ast.literal_eval parses that safely without eval().
    """
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return None
    try:
        parsed = ast.literal_eval(raw)
        return parsed if isinstance(parsed, dict) else None
    except (ValueError, SyntaxError):
        return None


async def _fetch_fsp_status(con: dict[str, Any]) -> tuple[str, int, list[str]]:
    """Look up an RTI-FSP connection's live connected-client count and cps.

    The cps are fsp/acsi_server.py's get_status accessPoints - the WebSocket
    path the FSP dials the SO on, which is the same name the SO lists it
    under in its acsi_client_list (see _link_so_to_fsps).
    """
    key = f"{con.get('host')}:{con.get('port')}"
    client = _bff_clients.get(key)
    if not client:
        return con.get("name"), 0, []
    try:
        result = await asyncio.to_thread(client.request, "GET", "/api/status")
        parsed = (
            _parse_status_repr(result.get("status"))
            if isinstance(result, dict)
            else None
        )
        if parsed:
            cps = parsed.get("accessPoints")
            cps = [cp for cp in cps if isinstance(cp, str)] if isinstance(cps, list) else []
            count = (
                parsed.get("connectedClients", 0) or 0
                if parsed.get("status") == "listening"
                else 0
            )
            return con.get("name"), count, cps
    except Exception:
        pass
    return con.get("name"), 0, []


async def _fetch_so_cp_list(con: dict[str, Any]) -> tuple[str, list[str]]:
    """Look up the cps an RTI-SO connection currently has FSPs associated on.

    so/acsi_client.py's get_cp_list() (exposed as /api/properties'
    acsi_client_list) only lists cps with an established association, so
    its length is "how many FSPs are currently connected to this SO" - the
    same list _relay_acsi_client_list() already watches for the ACSI Client
    page.
    """
    key = f"{con.get('host')}:{con.get('port')}"
    client = _bff_clients.get(key)
    if not client:
        return con.get("name"), []
    try:
        result = await asyncio.to_thread(client.request, "GET", "/api/properties")
        client_list = (
            result.get("acsi_client_list") if isinstance(result, dict) else None
        )
        if isinstance(client_list, list):
            return con.get("name"), [cp for cp in client_list if isinstance(cp, str)]
    except Exception:
        pass
    return con.get("name"), []


def _link_so_to_fsps(
    so_cps: list[str], fsp_entries: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Name the FSP behind each of an SO's associated cps.

    One {"cp", "fsp"} per cp; "fsp" is the FSP connection's name, or None
    when no registered FSP reports that cp. A cp is only unique per SO, so
    if several FSPs report it (misconfiguration, or several SOs reusing the
    same cp names) one that has a live WebSocket connection wins.
    """
    links = []
    for cp in so_cps:
        candidates = [f for f in fsp_entries if cp in f.get("accessPoints", [])]
        candidates.sort(key=lambda f: (f.get("connectedClients", 0) or 0) == 0)
        links.append({"cp": cp, "fsp": candidates[0]["name"] if candidates else None})
    return links


async def _build_enriched_connections() -> list[dict[str, Any]]:
    """Mirror the HMI's former client-side enrichFspClientCounts, server-side.

    FSPs get connectedClients and accessPoints (their cps). SOs get
    connectedFsps and fspLinks - which registered FSP sits behind each
    associated cp - so the HMI can tell which SO-FSP link a cp is without
    asking the user for it.
    """
    conns = conn_manager.connections
    fsp_conns = [
        c
        for c in conns
        if c.get("type") == "RTI-FSP"
        and c.get("status") == "connected"
        and c.get("host")
        and c.get("port")
    ]
    so_conns = [
        c
        for c in conns
        if c.get("type") == "RTI-SO"
        and c.get("status") == "connected"
        and c.get("host")
        and c.get("port")
    ]
    fsp_status: dict[str, tuple[int, list[str]]] = {}
    if fsp_conns:
        results = await asyncio.gather(
            *(_fetch_fsp_status(c) for c in fsp_conns), return_exceptions=True
        )
        for r in results:
            if isinstance(r, tuple):
                fsp_status[r[0]] = (r[1], r[2])

    so_cps: dict[str, list[str]] = {}
    if so_conns:
        results = await asyncio.gather(
            *(_fetch_so_cp_list(c) for c in so_conns), return_exceptions=True
        )
        for r in results:
            if isinstance(r, tuple):
                so_cps[r[0]] = r[1]

    enriched = []
    for con in conns:
        entry = dict(con)
        if con.get("type") == "RTI-FSP":
            count, cps = fsp_status.get(con.get("name"), (0, []))
            entry["connectedClients"] = count
            entry["accessPoints"] = cps
        enriched.append(entry)

    fsp_entries = [e for e in enriched if e.get("type") == "RTI-FSP"]
    for entry in enriched:
        if entry.get("type") == "RTI-SO":
            cps = so_cps.get(entry.get("name"), [])
            entry["connectedFsps"] = len(cps)
            entry["fspLinks"] = _link_so_to_fsps(cps, fsp_entries)
    return enriched


async def _relay_new_log_entries(
    target_key: str,
    client: BffClient,
    *,
    path: str,
    list_key: str,
    push_type: str,
    watermarks: dict[str, int],
    include=None,
) -> None:
    """Broadcast `target_key`'s log entries (from GET `path`) logged since the
    last cycle, as {"type": push_type, "target": target_key, "data": [...]}.

    `watermarks` holds the highest entry id already seen per target; it
    advances over every entry, but only those passing `include` (if given)
    are broadcast.
    """
    try:
        result = await asyncio.to_thread(client.request, "GET", path)
    except Exception:
        return
    entries = result.get(list_key) if isinstance(result, dict) else None
    if not entries:
        return

    last_id = watermarks.get(target_key, 0)
    current_max = max(
        (e.get("id", 0) for e in entries if isinstance(e, dict)), default=0
    )
    if current_max < last_id:
        # ids reset - the instance restarted (or its log was cleared).
        last_id = 0

    new_items = [
        e for e in entries if isinstance(e, dict) and e.get("id", 0) > last_id
    ]
    if not new_items:
        return

    watermarks[target_key] = current_max
    if include is not None:
        new_items = [e for e in new_items if include(e)]
        if not new_items:
            return
    await ws_hub.broadcast({"type": push_type, "target": target_key, "data": new_items})


async def _relay_new_messages(target_key: str, client: BffClient) -> None:
    """Broadcast any protocol messages logged by `target_key` since the last cycle."""
    await _relay_new_log_entries(
        target_key,
        client,
        path="/api/messages",
        list_key="messages",
        push_type="messages",
        watermarks=_last_relayed_message_id,
    )


async def _relay_new_actions(target_key: str, client: BffClient) -> None:
    """Broadcast `target_key`'s new ACSI service entries (actions log, kind
    "acsi") - Traffic shows these next to the WebSocket frames. System
    entries stay on the instance's own page (and Diagnostics), so they're
    not pushed. See docs/rti-demo/design/logging-kinds.md.
    """
    await _relay_new_log_entries(
        target_key,
        client,
        path="/api/actions-logs",
        list_key="actions",
        push_type="actions",
        watermarks=_last_relayed_action_id,
        include=lambda e: e.get("kind") == "acsi",
    )


async def _relay_acsi_client_list(target_key: str, client: BffClient) -> None:
    """Broadcast an RTI-SO's acsi_client_list when a cp connects or drops.

    so/acsi_client.py's get_cp_list() only returns cps with an established
    association, so this is exactly the "connected clients" list the ACSI
    Client page shows - it changes on every associate/disassociate, not on
    a fixed schedule, hence relaying only on change rather than every cycle.
    """
    try:
        result = await asyncio.to_thread(client.request, "GET", "/api/properties")
    except Exception:
        return
    client_list = result.get("acsi_client_list") if isinstance(result, dict) else None
    if not isinstance(client_list, list):
        return

    if _last_relayed_client_list.get(target_key) == client_list:
        return
    _last_relayed_client_list[target_key] = client_list
    await ws_hub.broadcast(
        {
            "type": "properties",
            "target": target_key,
            "data": {"acsi_client_list": client_list},
        }
    )


async def push_relay_loop(interval: float = 2.0) -> None:
    """Background task: poll once centrally, push deltas to every browser tab."""
    last_connections_snapshot: str | None = None
    while True:
        try:
            enriched = await _build_enriched_connections()
            snapshot = json.dumps(enriched, sort_keys=True, default=str)
            if snapshot != last_connections_snapshot:
                last_connections_snapshot = snapshot
                await ws_hub.broadcast({"type": "connections", "data": enriched})

            live_targets = [
                (
                    f"{c['host']}:{c['port']}",
                    _bff_clients.get(f"{c['host']}:{c['port']}"),
                )
                for c in conn_manager.connections
                if c.get("type") in ("RTI-SO", "RTI-FSP")
                and c.get("status") == "connected"
                and c.get("host")
                and c.get("port")
            ]
            so_targets = [
                (
                    f"{c['host']}:{c['port']}",
                    _bff_clients.get(f"{c['host']}:{c['port']}"),
                )
                for c in conn_manager.connections
                if c.get("type") == "RTI-SO"
                and c.get("status") == "connected"
                and c.get("host")
                and c.get("port")
            ]
            await asyncio.gather(
                *(
                    [
                        _relay_new_messages(key, client)
                        for key, client in live_targets
                        if client is not None
                    ]
                    + [
                        _relay_new_actions(key, client)
                        for key, client in live_targets
                        if client is not None
                    ]
                    + [
                        _relay_acsi_client_list(key, client)
                        for key, client in so_targets
                        if client is not None
                    ]
                )
            )
        except Exception:
            logger.exception("push_relay_loop iteration failed")

        await asyncio.sleep(interval)


# ==================== FastAPI Application Setup ====================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Installed here (not before uvicorn.run) so it survives uvicorn's own
    # logging dictConfig, which runs before app startup.
    logging.getLogger("uvicorn.access").addFilter(HealthCheckAccessFilter())

    await conn_manager.validate_idp_server_on_start()
    asyncio.create_task(conn_manager.status_monitor(interval=10))
    asyncio.create_task(push_relay_loop(interval=2))

    yield

    # Close the shared health-check client on shutdown.
    await conn_manager.aclose()


# Create FastAPI application
app = FastAPI(
    title="RTI Demo BFF Server",
    description="Backend for Frontend (BFF) server for RTI Demo. Provides service discovery, connection management, data operations, and proxy capabilities for RTI services.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    openapi_tags=[
        {
            "name": "Health",
            "description": "Health check and status monitoring endpoints",
        },
        {
            "name": "Endpoints",
            "description": "Service discovery and endpoint management",
        },
        {
            "name": "Connections",
            "description": "Manage connections to remote RTI endpoints",
        },
        {"name": "Data", "description": "Read and write data to ACSI endpoints"},
        {"name": "Reports", "description": "Generate and export reports"},
        {"name": "Stats", "description": "System statistics and metrics"},
        {
            "name": "Execution",
            "description": "Execute dynamic API calls against registered targets",
        },
        {"name": "Playbooks", "description": "Store and run demo playbooks"},
    ],
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== API Endpoints ====================

# -------------------- Live Updates (WebSocket) --------------------


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Browser-facing push channel.

    The HMI connects once and receives {"type": "connections", "data": [...]}
    and {"type": "messages", "target": "host:port", "data": [...]} events from
    push_relay_loop() instead of polling. Clients don't need to send
    anything; the receive loop below exists only to detect disconnects.
    """
    await websocket.accept()
    await ws_hub.register(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await ws_hub.unregister(websocket)


# -------------------- Health & Status --------------------


def _target_statuses() -> list[dict[str, str]]:
    """Each instance's reachability as the status monitor last saw it.

    Not probed again per call: health used to GET every instance's
    /api/health on each request, so one that was down (a hostname that no
    longer resolves, a container that's gone) held every health check up to
    its 3 s timeout - and every open HMI tab polls it every 10 s. The status
    monitor already checks every instance every 10 s.
    """
    return [
        {
            "target": f"{con['host']}:{con['port']}",
            "status": "reachable" if con.get("status") == "connected" else "unreachable",
        }
        for con in conn_manager.connections
        if con.get("host") and con.get("port") and f"{con['host']}:{con['port']}" in _bff_clients
    ]


@app.get(
    "/api/health",
    summary="Health Check",
    description="Health check endpoint for frontend: BFF status, and each instance's reachability as the status monitor last checked it (every 10 s).",
    response_description="Health status information",
    responses={
        200: {"description": "Service is healthy"},
        500: {"description": "Health check failed"},
    },
    tags=["Health"],
)
async def health_check():
    try:
        bff_status = {"status": "ok", "service": "BFF"}

        targets = _target_statuses()

        return {
            "ok": True,
            "bff": bff_status,
            "targets": targets,
            "count": len(targets),
        }

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


def _fetch_endpoint_properties(endpoint: dict) -> dict:
    """Fetch endpoint properties from server/client properties APIs when available.

    Args:
        endpoint: Endpoint dictionary

    Returns:
        Dictionary with properties information or error.
    """
    host = endpoint.get("host")
    port = endpoint.get("port")
    str(endpoint.get("type", "")).upper()

    if not host or not port:
        return {"available": False, "error": "missing host or port"}

    paths = ["/api/properties", "/api/properties"]

    last_error = None
    for path in paths:
        url = f"http://{host}:{port}{path}"
        try:
            response = requests.get(url, timeout=2)
            if response.status_code >= 400:
                last_error = f"{path} returned {response.status_code}"
                continue

            payload = response.json()
            if isinstance(payload, dict):
                if "properties" in payload:
                    return {
                        "available": True,
                        "source": path,
                        "properties": payload.get("properties"),
                    }
                return {"available": True, "source": path, "properties": payload}

            return {"available": True, "source": path, "properties": payload}
        except Exception as e:
            last_error = str(e)

    return {
        "available": False,
        "error": last_error or "properties endpoint not reachable",
    }


# -------------------- Endpoints Management --------------------


@app.get(
    "/api/endpoints",
    summary="Get All Endpoints",
    description="Get all configured endpoints (including cached auto-discovered).",
    response_description="List of all endpoints with their properties",
    responses={200: {"description": "List of endpoints returned successfully"}},
    tags=["Endpoints"],
)
async def get_endpoints():
    """Retrieve all configured endpoints.

    This endpoint returns:
    - Manual connections from the connection manager
    - Properties information for each endpoint when available

    Returns:
        JSON with endpoints list and count
    """
    endpoints = list(conn_manager.connections)
    properties = await asyncio.gather(
        *(
            asyncio.to_thread(_fetch_endpoint_properties, endpoint)
            for endpoint in endpoints
        )
    )
    for endpoint, props in zip(endpoints, properties):
        endpoint["properties_info"] = props

    return {"endpoints": endpoints, "count": len(endpoints)}


# -------------------- Connections Management --------------------


@app.get(
    "/api/connections",
    summary="Get All Connections",
    description="Get all configured connections to remote endpoints.",
    response_description="List of all connections",
    responses={200: {"description": "Connections retrieved successfully"}},
    tags=["Connections"],
)
async def get_connections():
    """Retrieve all configured connections.

    Returns:
        JSON with list of connections and their count.
    """
    # Ensure all connections have a status field
    connections_with_status = []
    for conn in conn_manager.connections:
        if "status" not in conn:
            # Set default status based on type
            conn["status"] = "disconnected"
        connections_with_status.append(conn)

    return {
        "connections": connections_with_status,
        "count": len(connections_with_status),
    }


@app.post(
    "/api/connections/tls-config",
    summary="update TLS Config for a specific connection",
    description="update TLS Config for a specific connection",
    response_description="apply result",
    responses={
        201: {"description": "Connection with TLS config created successfully"},
        400: {"description": "Missing required fields"},
    },
    tags=["TLS"],
)
async def create_tls_connection(request: TLSConnectionCreateConfigRequest):
    """Create a new connection to a remote RTI endpoint.

    Request Body:
        ConnectionCreateRequest with name, host, port, type

    Returns:
        JSON with the created connection details.

    Raises:
        HTTPException 400: If required fields are missing.
    """
    ws_mode = request.ws_mode
    # Validate required fields based on mode
    if ws_mode == "passive" or ws_mode == "Passive":
        if not request.server_key or not request.server_cert:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required fields: server_key and server_cert for passive mode",
            )
    elif ws_mode == "active" or ws_mode == "Active":
        if not request.server_ca:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required field: server_ca for active mode",
            )

    connection = conn_manager.get_connection(request.connection_name)

    if connection:
        if "TLS" not in connection:
            connection["TLS"] = {}
        connection["TLS"]["enable_tls"] = request.enable_tls
        connection["TLS"]["tls_version"] = request.tls_version

        # Store certificates based on mode
        if ws_mode == "passive" or ws_mode == "Passive":
            connection["TLS"]["server_key"] = request.server_key
            connection["TLS"]["server_cert"] = request.server_cert
            connection["TLS"]["server_ca"] = None
        elif ws_mode == "active" or ws_mode == "Active":
            connection["TLS"]["server_key"] = None
            connection["TLS"]["server_cert"] = None
            connection["TLS"]["server_ca"] = request.server_ca

        conn_manager.save_connections()

        return {
            "ok": True,
            "message": f"TLS config saved for {request.connection_name}",
        }

    return {"ok": False, "message": "Connection not found"}


@app.get(
    "/api/connections/tls-config",
    summary="Get TLS Config for a specific connection",
    description="Retrieve the TLS configuration for a connection.",
    response_description="TLS configuration",
    responses={
        200: {"description": "TLS config returned successfully"},
        404: {"description": "Connection not found"},
    },
    tags=["TLS"],
)
async def get_tls_config(connection_name: str):
    """Get TLS configuration for a connection.

    Query Parameters:
        connection_name: Name of the connection to get TLS config for

    Returns:
        JSON with TLS configuration including enable_tls, tls_version,
        server_key, server_cert, server_ca.

    Raises:
        HTTPException 404: If connection is not found.
    """
    connection = conn_manager.get_connection(connection_name)

    if connection:
        tls_config = connection.get("TLS", {})
        return {
            "ok": True,
            "connection_name": connection_name,
            "enable_tls": tls_config.get("enable_tls", False),
            "tls_version": tls_config.get("tls_version"),
            "server_key": tls_config.get("server_key"),
            "server_cert": tls_config.get("server_cert"),
            "server_ca": tls_config.get("server_ca"),
            "ws_mode": connection.get("ws_mode"),
        }

    return {"ok": False, "message": f"Connection '{connection_name}' not found"}


@app.post(
    "/api/connections/oauth-config",
    summary="Update OAuth Config for a specific connection",
    description="Update OAuth configuration for a connection.",
    response_description="Apply result",
    responses={
        200: {"description": "OAuth config updated successfully"},
        400: {"description": "Missing required fields"},
        404: {"description": "Connection not found"},
    },
    tags=["OAuth"],
)
async def create_oauth_connection(request: OAUTHConnectionCreateConfigRequest):
    """Update OAuth configuration for a connection.

    Request Body:
        OAUTHConnectionCreateConfigRequest with OAuth settings

    Returns:
        JSON with success status.

    Raises:
        HTTPException 400: If required fields are missing.
        HTTPException 404: If connection is not found.
    """
    connection = conn_manager.get_connection(request.connection_name)

    if connection:
        if "OAuth" not in connection:
            connection["OAuth"] = {}

        connection["OAuth"]["enable_oauth"] = request.enable_oauth
        if request.idp_server is not None:
            connection["OAuth"]["idp_server"] = request.idp_server
        if request.realm is not None:
            connection["OAuth"]["realm"] = request.realm

        # Store OAuth fields based on mode
        if request.ws_mode == "passive" or request.ws_mode == "Passive":
            # Server mode - store server OAuth config
            if request.certificate_endpoint_url:
                connection["OAuth"]["certificate_endpoint"] = (
                    request.certificate_endpoint_url
                )
            if request.token_issuer_url:
                connection["OAuth"]["token_issuer"] = request.token_issuer_url
            if request.ca_certificate:
                connection["OAuth"]["auth_server_ca"] = request.ca_certificate
            # Clear client-specific fields for server mode
            connection["OAuth"].pop("token_endpoint", None)
            connection["OAuth"].pop("client_id", None)
            connection["OAuth"].pop("client_secret", None)
            connection["OAuth"].pop("client_ca_cert", None)
        else:
            # Client mode - store client OAuth config
            if request.token_endpoint_url:
                connection["OAuth"]["token_endpoint"] = request.token_endpoint_url
            if request.client_id:
                connection["OAuth"]["client_id"] = request.client_id
            if request.client_secret:
                connection["OAuth"]["client_secret"] = request.client_secret
            if request.ca_certificate:
                connection["OAuth"]["auth_server_ca"] = request.ca_certificate
            if request.client_ca_cert:
                connection["OAuth"]["client_ca_cert"] = request.client_ca_cert
            if request.enable_token_refresh is not None:
                connection["OAuth"]["enable_token_refresh"] = (
                    request.enable_token_refresh
                )
            # Clear server-specific fields for client mode
            connection["OAuth"].pop("certificate_endpoint", None)
            connection["OAuth"].pop("token_issuer", None)

        conn_manager.save_connections()

        return {
            "ok": True,
            "message": f"OAuth config saved for {request.connection_name}",
        }

    return {"ok": False, "message": "Connection not found"}


async def _fetch_oidc_discovery(url: str) -> dict[str, Any]:
    # verify=False: same as the IDP-Server health check - demo IDPs
    # typically run on a self-signed certificate.
    async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()


@app.get(
    "/api/idp/discovery",
    summary="Discover a realm's OAuth endpoints",
    description="Reads the realm's OIDC discovery document from an IDP-Server connection.",
    response_description="Issuer, certificate (JWKS) endpoint and token endpoint",
    tags=["OAuth"],
)
async def get_idp_discovery(idp_server: str, realm: str):
    """Look up a realm's issuer and endpoints on a registered IDP-Server.

    Fetched here rather than in the browser: the IDP's address (e.g.
    http://keycloak:8080) is only resolvable inside the Docker network. The
    issuer comes from the IDP itself, since it can differ from that address
    (Keycloak's KC_HOSTNAME) and the SO rejects tokens whose issuer doesn't
    match exactly.
    """
    idp = conn_manager.get_connection(idp_server)
    if not idp or idp.get("type") != "IDP-Server":
        return {"ok": False, "error": f"IDP server '{idp_server}' not found"}

    base_url = idp.get("endpoint") or (
        f"http://{idp['host']}:{idp['port']}" if idp.get("host") else ""
    )
    if not base_url:
        return {"ok": False, "error": f"IDP server '{idp_server}' has no endpoint"}

    url = f"{base_url.rstrip('/')}/realms/{realm}/.well-known/openid-configuration"
    try:
        discovery = await _fetch_oidc_discovery(url)
    except Exception as e:
        return {"ok": False, "error": f"Could not read {url}: {e}"}

    return {
        "ok": True,
        "issuer": discovery.get("issuer"),
        "certificate_endpoint": discovery.get("jwks_uri"),
        "token_endpoint": discovery.get("token_endpoint"),
    }


@app.get(
    "/api/connections/oauth-status",
    summary="Get OAuth Status for a specific connection",
    description="Retrieve the OAuth enable/disable status for a connection.",
    response_description="OAuth status",
    responses={
        200: {"description": "OAuth status returned successfully"},
        404: {"description": "Connection not found"},
    },
    tags=["OAuth"],
)
async def get_oauth_status(connection_name: str):
    """Get OAuth enable/disable status for a connection.

    Query Parameters:
        connection_name: Name of the connection to check

    Returns:
        JSON with enable_oauth status.

    Raises:
        HTTPException 404: If connection is not found.
    """
    connection = conn_manager.get_connection(connection_name)

    if connection:
        oauth_status = connection.get("OAuth", {}).get("enable_oauth", False)
        return {
            "ok": True,
            "connection_name": connection_name,
            "enable_oauth": oauth_status,
        }

    return {"ok": False, "message": f"Connection '{connection_name}' not found"}


@app.get(
    "/api/connections/oauth-config",
    summary="Get OAuth Config for a specific connection",
    description="Retrieve the full OAuth configuration for a connection.",
    response_description="OAuth configuration",
    responses={
        200: {"description": "OAuth config returned successfully"},
        404: {"description": "Connection not found"},
    },
    tags=["OAuth"],
)
async def get_oauth_config(connection_name: str):
    """Get full OAuth configuration for a connection.

    Query Parameters:
        connection_name: Name of the connection to get config for

    Returns:
        JSON with full OAuth configuration including certificate_endpoint,
        token_issuer_url, client_id, client_secret, etc.

    Raises:
        HTTPException 404: If connection is not found.
    """
    connection = conn_manager.get_connection(connection_name)

    if connection:
        oauth_config = connection.get("OAuth", {})
        return {
            "ok": True,
            "connection_name": connection_name,
            "certificate_endpoint": oauth_config.get("certificate_endpoint"),
            "token_issuer_url": oauth_config.get("token_issuer"),
            "token_endpoint": oauth_config.get("token_endpoint"),
            "client_id": oauth_config.get("client_id"),
            "client_secret": oauth_config.get("client_secret"),
            "auth_server_ca": oauth_config.get("auth_server_ca"),
            "ca_certificate": oauth_config.get("ca_certificate"),
            "realm": oauth_config.get("realm"),
            "idp_server": oauth_config.get("idp_server"),
            "enable_oauth": oauth_config.get("enable_oauth", False),
            "enable_token_refresh": oauth_config.get("enable_token_refresh", False),
        }

    return {"ok": False, "message": f"Connection '{connection_name}' not found"}


@app.post(
    "/api/add-connection",
    summary="Create Connection",
    description="Create a new connection to a remote endpoint.",
    response_description="Created connection details",
    responses={
        201: {"description": "Connection created successfully"},
        400: {"description": "Missing required fields"},
    },
    tags=["Connections"],
)
async def create_connection(request: ConnectionCreateRequest):
    """Create a new connection to a remote RTI endpoint.

    Request Body:
        ConnectionCreateRequest with name, host, port, type

    Returns:
        JSON with the created connection details.

    Raises:
        HTTPException 400: If required fields are missing.
    """
    if not request.name or not request.type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required fields: name, type",
        )

    # For IDP-Server, host and port are not required but endpoint is
    if request.type == "IDP-Server":
        if not request.endpoint:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required field: endpoint",
            )
    else:
        # For other types, host and port are required
        if not request.host or not request.port:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required fields: host, port",
            )
    connection = conn_manager.add_connection(
        name=request.name,
        host=request.host,
        port=request.port,
        ws_port=request.ws_port,
        conn_type=request.type,
        acsi=request.acsi,
        ws_mode=request.ws_mode,
        endpoint=request.endpoint,
        certificate_endpoint=request.certificate_endpoint,
        auth_server_ca=request.auth_server_ca,
        realm=request.realm,
        token_endpoint=request.token_endpoint,
        client_id=request.client_id,
        client_secret=request.client_secret,
        enable_token_refresh=request.enable_token_refresh,
        idp_server=request.idp_server,
        auto_discovered=request.auto_discovered,
        cp=request.cp,
    )
    conn_manager.save_connections()
    # Immediately probe the connection so its status is fresh right away instead
    # of showing "checking" until the background monitor runs.
    await conn_manager.check_connection(connection, conn_manager.get_client())

    return JSONResponse(content=connection, status_code=status.HTTP_201_CREATED)


@app.delete(
    "/api/delete-connection/{conn_name}",
    summary="Delete Connection",
    description="Delete an existing connection.",
    response_description="Deletion confirmation",
    responses={
        200: {"description": "Connection deleted successfully"},
        404: {"description": "Connection not found"},
    },
    tags=["Connections"],
)
async def delete_connection(conn_name: str):
    """Delete a connection by its ID.

    Path Parameters:
        conn_id: The ID of the connection to delete

    Returns:
        JSON with deletion status.
    """
    success = conn_manager.delete_connection(conn_name)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found"
        )
    return {"status": "deleted"}


@app.put(
    "/api/edit-connection/{conn_name}",
    summary="Update Connection",
    description="Update an existing connection.",
    response_description="Updated connection details",
    responses={
        200: {"description": "Connection updated successfully"},
        404: {"description": "Connection not found"},
    },
    tags=["Connections"],
)
async def update_connection(conn_name: str, request: ConnectionUpdateRequest):
    """Update a connection by its ID.

    Path Parameters:
        conn_id: The ID of the connection to update

    Request Body:
        ConnectionUpdateRequest with fields to update

    Returns:
        JSON with the updated connection details.

    Raises:
        HTTPException 404: If connection is not found.
    """
    connection = conn_manager.get_connection(conn_name)
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found"
        )

    # Track old host:port for _bff_clients cleanup
    old_host = connection.get("host")
    old_port = connection.get("port")
    old_key = f"{old_host}:{old_port}" if old_host and old_port else None

    # Update fields from request
    if request.name is not None:
        connection["name"] = request.name
    if request.host is not None:
        connection["host"] = request.host
    if request.port is not None:
        connection["port"] = request.port
    if request.ws_port is not None:
        connection["ws_port"] = request.ws_port
    if request.cp is not None:
        connection["cp"] = request.cp
    if request.type is not None:
        connection["type"] = request.type
    if request.acsi is not None:
        connection["acsi"] = request.acsi
    if request.ws_mode is not None:
        connection["ws_mode"] = request.ws_mode
    if request.endpoint is not None:
        connection["endpoint"] = request.endpoint
    if request.status is not None:
        connection["status"] = request.status

    # Handle OAuth fields - nest them under OAuth object
    oauth_fields = {}
    if request.certificate_endpoint is not None:
        oauth_fields["certificate_endpoint"] = request.certificate_endpoint
    if request.token_issuer_url is not None:
        oauth_fields["token_issuer"] = request.token_issuer_url
    if request.auth_server_ca is not None:
        oauth_fields["auth_server_ca"] = request.auth_server_ca
    if request.realm is not None:
        oauth_fields["realm"] = request.realm
    if request.token_endpoint is not None:
        oauth_fields["token_endpoint"] = request.token_endpoint
    if request.client_id is not None:
        oauth_fields["client_id"] = request.client_id
    if request.client_secret is not None:
        oauth_fields["client_secret"] = request.client_secret
    if request.enable_token_refresh is not None:
        oauth_fields["enable_token_refresh"] = request.enable_token_refresh
    if request.idp_server is not None:
        oauth_fields["idp_server"] = request.idp_server

    # If we have OAuth fields, create/update the OAuth object
    if oauth_fields:
        if "OAuth" not in connection:
            connection["OAuth"] = {}
        connection["OAuth"].update(oauth_fields)

    # Clean up any OAuth fields that were previously at top level
    top_level_oauth_fields = [
        "certificate_endpoint",
        "auth_server_ca",
        "realm",
        "token_endpoint",
        "client_id",
        "client_secret",
        "enable_token_refresh",
        "idp_server",
    ]
    for field in top_level_oauth_fields:
        if field in connection:
            del connection[field]

    # Update _bff_clients if host or port changed
    new_host = connection.get("host")
    new_port = connection.get("port")
    new_key = f"{new_host}:{new_port}" if new_host and new_port else None

    if old_key and new_key and old_key != new_key:
        # Remove old entry
        if old_key in _bff_clients:
            del _bff_clients[old_key]
        # Add new entry
        if new_key not in _bff_clients:
            _bff_clients[new_key] = BffClient(f"http://{new_host}:{new_port}")

    conn_manager.save_connections()

    return connection


# -------------------- Playbooks --------------------

# Built-in playbooks: the repo's examples/rti-demo/playbooks (the Dockerfile
# copies them to the same place in the image). Saved ones (recordings and
# uploads from the HMI) sit next to connections.json - in Docker, on the
# config volume.
playbook_store = PlaybookStore(
    os.environ.get("BFF_PLAYBOOKS_BUILTIN_DIR") or Path(__file__).resolve().parents[4] / "playbooks",
    os.environ.get("BFF_PLAYBOOKS_DIR") or Path(CONNECTIONS_FILE).parent / "playbooks",
)
# A run goes through this BFF's own /api/execute, the path an HMI click takes,
# so Traffic shows every step.
playbook_runs = PlaybookRuns(
    playbook_store, lambda playbook: BffTransport(f"http://localhost:{os.getenv('PORT', '5000')}")
)


def _run_publisher(loop: asyncio.AbstractEventLoop):
    """Push a run's state to every browser - called from the run's thread."""

    def publish(state: dict[str, Any]) -> None:
        coro = ws_hub.broadcast({"type": "playbook-run", "data": state})
        try:
            asyncio.run_coroutine_threadsafe(coro, loop)
        except RuntimeError:
            # The loop is closed (e.g. FastAPI's TestClient, whose per-request
            # loop closes once the request completes) - nothing to push to.
            coro.close()

    return publish


# /api/playbooks/run before /api/playbooks/{name}, so "run" isn't taken for a name.
@app.get("/api/playbooks/run", summary="Current playbook run", tags=["Playbooks"])
async def get_playbook_run():
    return {"ok": True, "run": playbook_runs.state()}


@app.post("/api/playbooks/run/stop", summary="Stop the playbook run", tags=["Playbooks"])
async def stop_playbook_run():
    playbook_runs.stop()
    return {"ok": True, "run": playbook_runs.state()}


@app.get("/api/playbooks", summary="List playbooks", tags=["Playbooks"])
async def list_playbooks():
    return {"ok": True, "playbooks": await asyncio.to_thread(playbook_store.list)}


@app.get("/api/playbooks/{name}", summary="Get a playbook", tags=["Playbooks"])
async def get_playbook(name: str):
    try:
        playbook, builtin = await asyncio.to_thread(playbook_store.get, name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"no playbook {name!r}")
    except PlaybookNameError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PlaybookError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {
        "ok": True,
        "name": name,
        "builtin": builtin,
        "playbook": playbook,
        "labels": [step_label(step) for step in playbook["steps"]],
    }


@app.get("/api/playbooks/{name}/file", summary="Download a playbook file", tags=["Playbooks"])
async def download_playbook(name: str):
    try:
        text, filename = await asyncio.to_thread(playbook_store.file, name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"no playbook {name!r}")
    except PlaybookNameError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Response(
        text,
        media_type="application/json" if filename.endswith(".json") else "application/yaml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.put("/api/playbooks/{name}", summary="Save a playbook", tags=["Playbooks"])
async def save_playbook(name: str, request: PlaybookSaveRequest):
    def do_save():
        if request.playbook is not None:
            playbook = request.playbook
        elif request.text is not None:
            playbook = parse_playbook(request.text, request.format)
        else:
            raise HTTPException(status_code=400, detail="send 'playbook', or 'text' with its 'format'")
        playbook_store.save(name, playbook)

    try:
        await asyncio.to_thread(do_save)
    except (PlaybookNameError, PlaybookError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except BuiltinPlaybookError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"ok": True, "name": name}


@app.delete("/api/playbooks/{name}", summary="Delete a saved playbook", tags=["Playbooks"])
async def delete_playbook(name: str):
    try:
        await asyncio.to_thread(playbook_store.delete, name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"no playbook {name!r}")
    except PlaybookNameError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except BuiltinPlaybookError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"ok": True}


@app.post("/api/playbooks/{name}/run", summary="Run a playbook", tags=["Playbooks"])
async def run_playbook(name: str, request: PlaybookRunRequest | None = None):
    request = request or PlaybookRunRequest()
    publish = _run_publisher(asyncio.get_running_loop())
    try:
        state = await asyncio.to_thread(
            playbook_runs.start, name, pace=request.pace, keep_going=request.keep_going, publish=publish,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"no playbook {name!r}")
    except (PlaybookNameError, PlaybookError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PlaybookBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    # PlaybookRuns.start() already published this initial state itself.
    return {"ok": True, "run": state}


# -------------------- Dynamic API Execution --------------------


@app.post(
    "/api/execute",
    summary="Execute Dynamic API",
    description="Execute a dynamic API call against a registered target.",
    response_description="Execution result",
    responses={
        200: {"description": "API call executed successfully"},
        400: {"description": "Missing required parameters"},
        404: {"description": "Unknown target"},
        500: {"description": "API call failed"},
    },
    tags=["Execution"],
)
async def execute_dynamic_api(request: ExecuteRequest):
    """Execute a dynamic API call against a registered BFF target.

    This endpoint allows the frontend to dynamically call any API on a registered backend.

    Request Body:
        ExecuteRequest with target, path, method (default GET), and optional body

    Returns:
        JSON with execution result including target, method, path, and result.

    Raises:
        HTTPException 400: If target or path is missing.
        HTTPException 404: If target is not registered.
        HTTPException 500: If API call fails.
    """
    target = request.target
    method = request.method.upper()
    path = request.path
    body = request.body

    if not target or not path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="target and path are required",
        )

    # Special handling for OAuth reconfiguration
    # When HMI calls /reconfig-oauth, BFF needs to enrich the request with OAuth settings from connections.json
    if path == "/reconfig-oauth" and body and isinstance(body, dict):
        connection_name = body.get("connection_name")
        if connection_name:
            # Look up the connection
            connection = conn_manager.get_connection(connection_name)
            if connection:
                # Get OAuth config from connection
                oauth_config = connection.get("OAuth", {})

                # Extract cp from connection
                cp = connection.get("cp") or body.get("cp", "cp1")

                # Enrich the request body with OAuth fields from the connection
                # Only add fields that exist in the OAuth config and are not already in the body
                enriched_body = dict(body)

                # Add cp if not already present
                if "cp" not in enriched_body:
                    enriched_body["cp"] = cp

                # Add OAuth fields from connection if not already in body
                # Map connection field names to request field names
                oauth_fields = {
                    "token_endpoint_url": oauth_config.get("token_endpoint")
                    or oauth_config.get("token_issuer"),
                    "certificate_endpoint_url": oauth_config.get(
                        "certificate_endpoint"
                    ),
                    "token_issuer_url": oauth_config.get("token_issuer"),
                    "client_id": oauth_config.get("client_id"),
                    "client_secret": oauth_config.get("client_secret"),
                    "ca_certificate": oauth_config.get("auth_server_ca"),
                    "enable_token_refresh": oauth_config.get(
                        "enable_token_refresh", False
                    ),
                }

                for field, value in oauth_fields.items():
                    # Only add if value exists and not already in body
                    if value is not None and field not in enriched_body:
                        enriched_body[field] = value

                body = enriched_body

    # An RTI-FSP only holds TLS in memory, so after a restart its dial-out
    # would come back as plain WS - /start carries its stored TLS config
    # along (FSP's /start applies it before connecting).
    if path == "/api/start" and isinstance(body, dict):
        host, _, port = target.rpartition(":")
        connection = conn_manager.get_connection_by_host_port(
            host, int(port) if port.isdigit() else port
        )
        stored_tls = (connection or {}).get("TLS")
        if connection and connection.get("type") == "RTI-FSP" and stored_tls:
            body = {
                "enable_tls": bool(stored_tls.get("enable_tls")),
                "tls_version": stored_tls.get("tls_version"),
                "server_ca": stored_tls.get("server_ca"),
                **body,
            }

    try:
        # Get client from registry
        client = _bff_clients.get(target)

        if not client:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Unknown target: {target}",
            )

        # Call API dynamically
        result = client.request(method=method, path=path, json=body)

        return {
            "ok": True,
            "target": target,
            "method": method,
            "path": path,
            "result": result,
        }

    except Exception as e:
        logger.error(f"Dynamic API call failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


# -------------------- Diagnostics --------------------


_DIAGNOSTICS_LEVEL_ORDER = {"error": 0, "warn": 1, "info": 2, "debug": 3}


async def _instance_system_entries(con: dict) -> list[dict[str, Any]]:
    """One instance's kind "system" actions-log entries, tagged with its name.

    Unreachable or not-yet-registered instances contribute nothing - their
    being down is already a BFF event ("... stopped responding").
    """
    client = _bff_clients.get(f"{con.get('host')}:{con.get('port')}")
    if client is None:
        return []
    try:
        result = await asyncio.to_thread(client.request, "GET", "/api/actions-logs")
    except Exception:
        return []
    actions = result.get("actions") if isinstance(result, dict) else None
    if not isinstance(actions, list):
        return []
    name = con.get("name", "")
    return [
        {**a, "instance": name, "source": name}
        for a in actions
        if isinstance(a, dict) and a.get("kind") == "system"
    ]


@app.get(
    "/api/diagnostics",
    summary="System log across all instances",
    description=(
        "The BFF's own system events plus every reachable RTI-SO/RTI-FSP's "
        "kind \"system\" actions-log entries, errors and warnings first, then "
        "newest first. See docs/rti-demo/design/logging-kinds.md."
    ),
    response_description="Merged system entries",
    tags=["Diagnostics"],
)
async def get_diagnostics():
    targets = [
        con
        for con in conn_manager.connections
        if con.get("type") in ("RTI-SO", "RTI-FSP")
        and con.get("status") == "connected"
        and con.get("host")
        and con.get("port")
    ]
    per_instance = await asyncio.gather(*(_instance_system_entries(c) for c in targets))
    entries = [{**e, "source": "BFF"} for e in conn_manager.get_events()]
    for chunk in per_instance:
        entries.extend(chunk)

    # Errors/warnings first, then newest first within a level. Times are
    # each source's own "HH:MM:SS" - fine for ordering within a session.
    entries.sort(key=lambda e: str(e.get("time", "")), reverse=True)
    entries.sort(key=lambda e: _DIAGNOSTICS_LEVEL_ORDER.get(e.get("level"), 2))
    return {
        "entries": entries,
        "sources": ["BFF", *(c.get("name", "") for c in targets)],
    }


# -------------------- Reports --------------------


@app.get(
    "/api/reports",
    summary="Get Reports",
    description="Get available reports.",
    response_description="List of available reports",
    responses={200: {"description": "Reports list returned successfully"}},
    tags=["Reports"],
)
async def get_reports():
    """Get a list of available reports.

    Returns:
        JSON with list of mock reports for demonstration.
    """
    mock_reports = [
        {
            "id": 1,
            "name": "Connection Status Report",
            "description": "Current status of all connections",
            "timestamp": datetime.now().isoformat(),
        },
        {
            "id": 2,
            "name": "Data Access Log",
            "description": "Log of all data read/write operations",
            "timestamp": datetime.now().isoformat(),
        },
        {
            "id": 3,
            "name": "System Performance",
            "description": "System metrics and performance data",
            "timestamp": datetime.now().isoformat(),
        },
    ]

    return {"reports": mock_reports}


@app.post(
    "/api/reports/export",
    summary="Export Reports",
    description="Export reports data.",
    response_description="Exported reports data",
    responses={200: {"description": "Reports exported successfully"}},
    tags=["Reports"],
)
async def export_reports():
    """Export reports data including connections and summary.

    Returns:
        JSON with exported data including connections and reports.
    """
    export_data = {
        "exported_at": datetime.now().isoformat(),
        "connections": conn_manager.connections,
        "reports": [
            {"name": "Export Summary", "timestamp": datetime.now().isoformat()}
        ],
    }

    return {"data": export_data, "status": "success"}


# -------------------- Statistics --------------------


@app.get(
    "/api/stats",
    summary="Get Statistics",
    description="Get system statistics.",
    response_description="System statistics",
    responses={200: {"description": "Statistics returned successfully"}},
    tags=["Stats"],
)
async def get_stats():
    """Get system statistics including report updates, BFF targets count, and uptime.

    Returns:
        JSON with system statistics.
    """
    return {
        "reportUpdates": 0,
        "bffTargets": len(conn_manager.connections),
        "totalRequests": 0,
        "uptime": "00:00:00",
    }


# ==================== Error Handling ====================


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions and return JSON responses."""
    logger.error(f"HTTP error: {exc.status_code} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code, content={"ok": False, "error": exc.detail}
    )


@app.exception_handler(OSError)
async def storage_exception_handler(request: Request, exc: OSError):
    """Surface filesystem failures (e.g. a read-only connections.json) instead
    of collapsing them into a generic 500 with no detail. Covers
    PermissionError, read-only filesystem, and no-space-left errors raised
    while persisting connection changes."""
    logger.error("Storage error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"ok": False, "error": f"Failed to persist data to disk: {exc}"},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    logger.error(f"Internal server error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"ok": False, "error": "Internal server error"},
    )


# ==================== Application Entry Point ====================

if __name__ == "__main__":
    import argparse

    import uvicorn

    _LOG_CHOICES = ["critical", "error", "warning", "info", "debug", "trace"]

    parser = argparse.ArgumentParser(description="RTI Demo BFF Server (FastAPI)")
    parser.add_argument(
        "--host",
        default=os.getenv("HOST", "0.0.0.0"),
        help="Host interface to bind (default: %(default)s, env: HOST)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", "5000")),
        help="Port to listen on (default: %(default)s, env: PORT)",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL", "info"),
        help="Log level: {} (default: %(default)s, env: LOG_LEVEL)".format(
            ", ".join(_LOG_CHOICES)
        ),
    )
    args = parser.parse_args()

    # The playbook runner calls this BFF on its own port.
    os.environ["PORT"] = str(args.port)

    # Module scope already applied LOG_LEVEL from the environment at import.
    # Re-resolve here so an explicit --log-level on the command line wins, and
    # hand the same value to uvicorn so its own 'uvicorn'/'uvicorn.error'/
    # 'uvicorn.access' loggers follow suit.
    resolved = resolve_log_level(args.log_level)
    logging.getLogger().setLevel(resolved)
    uvicorn_log_level = args.log_level.lower()
    if uvicorn_log_level not in _LOG_CHOICES:
        uvicorn_log_level = logging.getLevelName(resolved).lower()

    logger.info(
        "Starting RTI Demo BFF Server (FastAPI) on %s:%d (log level %s)...",
        args.host,
        args.port,
        logging.getLevelName(resolved),
    )
    # log_config=None: don't let uvicorn apply its own logging dictConfig
    # (separate formatter/handlers for the uvicorn/uvicorn.access/
    # uvicorn.error loggers) - let those records propagate to the root
    # logger instead, so they use the same timestamped format as the
    # app's own logger.info(...) calls above.
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level=uvicorn_log_level,
        log_config=None,
    )
