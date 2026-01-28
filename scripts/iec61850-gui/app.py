"""Flask-based GUI for IEC 61850 client operations.
"""
from flask import Flask, jsonify, render_template, request
import os
import threading
import asyncio
import websockets
from collections import deque
import time
from typing import Any, Dict, List, Optional, Tuple, Union

# from Endpoint.endpoint import WebSocketEndpoint, WebSocketInfo
# from IEC61850.client.IEC61850Client import IEC61850Client
# from TLSConfig.TLSConfiguration import *
# from oauth.oauth_functions import *
# from asn1.encode_decode import encode_tpaa_message
# from IEC61850.client.request_functions import create_token_refresh

from testing.ieds.high_level_model import make_ied_model1
from ws61850.endpoint.endpoint import WebSocketEndpoint, WebSocketInfo
from ws61850.iec61850.server.control_handling import ControlHandlerResult, ControlServiceStatusKind
from ws61850.iec61850.server.iec61850_server import IEC61850Server
from ws61850.iec61850.server.service_error import ServiceStatusKind


app = Flask(__name__, template_folder='templates', static_folder='static')

# Runtime state for a connected client
runtime = {
    'endpoint': None,   # WebSocketEndpoint instance
    'client': None,     # Raw IEC61850Client instance
    'loop': None,       # Event loop running the endpoint (thread)
    'actions': deque(maxlen=200),  # recent action log entries
    'invoke_lock': None,  # asyncio.Lock to guard invoke_id (set after loop creation)
    'action_seq': 0,  # incremental id for structured actions
    # Model build cache/state
    'model_status': 'idle',  # idle|building|ready|error
    'model_data': None,      # cached model dict when ready
    'model_error': None,     # error string if error
    'model_task': None,      # concurrent.futures.Future for background build
    'model_started_at': None, # perf counter start time
    'model_lock': threading.Lock(),  # protect scheduling / cache updates from Flask threads
    'model_progress': None,   # dict with progress info (lds_total, lds_done, lns_total, lns_done, current_ld, current_ln)
    # Message monitoring
    'messages': deque(maxlen=500),  # recent protocol messages (sent/received)
    'message_seq': 0,  # incremental id for messages
    'messages_max': 500,  # configurable retention limit
    'messages_lock': threading.Lock(),  # protect retention changes
    # Connection control flags
    'cancel_connect': False,  # set True to abort an in-flight connect before completion
    'manual_disconnect': False,  # set True when user explicitly disconnects so status stays not-connected
}

def log_action(message: str, level: str = 'info') -> None:
    """Backward-compatible simple action (instantaneous)."""
    ts = time.strftime('%H:%M:%S')
    runtime['action_seq'] += 1
    runtime['actions'].append({
        'id': runtime['action_seq'],
        'time': ts,
        'level': level,
        'message': message,
        'op': None,
        'status': 'done',
        'start_ts': ts,
        'end_ts': ts,
        'duration_ms': 0,
        'detail': {}
    })

def log_action_start(op: str, detail: Optional[Dict[str, Any]] = None, level: str = 'info') -> int:
    """Create a structured action entry representing the start of an operation.
    Returns the action id for later completion."""
    if detail is None:
        detail = {}
    runtime['action_seq'] += 1
    aid = runtime['action_seq']
    start_wall = time.strftime('%H:%M:%S')
    entry = {
        'id': aid,
        'op': op,
        'detail': detail,
        'time': start_wall,
        'start_ts': start_wall,
        'end_ts': None,
        'level': level,
        'status': 'in-progress',
        'message': f"{op} start",
        'perf_start': time.perf_counter(),  # internal only (removed on completion)
        'duration_ms': None
    }
    runtime['actions'].append(entry)
    return aid

def log_action_end(aid: int, success: bool = True, error: Optional[str] = None, extra_detail: Optional[Dict[str, Any]] = None) -> None:
    """Complete a structured action, computing duration and updating status/message.
    Reduced branching by isolating steps into helpers."""

    def _locate():
        for entry in reversed(runtime['actions']):
            if entry.get('id') == aid:
                return entry
        return None

    entry = _locate()
    if entry is None:
        log_action(f"{aid} completion missing (success={success})", 'warn')
        return

    perf_start = entry.pop('perf_start', None)
    dur_ms = int((time.perf_counter() - perf_start) * 1000) if perf_start is not None else None
    entry['end_ts'] = time.strftime('%H:%M:%S')
    entry['duration_ms'] = dur_ms
    if extra_detail:
        entry['detail'].update(extra_detail)

    if success:
        entry['status'] = 'done'
        # preserve original level if user raised it beyond info
        if entry.get('level') == 'info':
            entry['level'] = 'info'
        entry['message'] = f"{entry['op']} ok ({dur_ms} ms)" if dur_ms is not None else f"{entry['op']} ok"
        return

    # error path
    entry['status'] = 'error'
    entry['level'] = 'error'
    entry['message'] = f"{entry['op']} error: {error}"

def _process_report_message(report: Dict[str, Any]) -> None:
    """Process a Report message and extract data updates for the tree."""
    try:
        if not isinstance(report, dict):
            return

        # Extract entry data which contains the actual values
        entry = report.get('entry')
        if not entry or not isinstance(entry, dict):
            return

        entry_data_list = entry.get('entryData', [])
        if not isinstance(entry_data_list, list):
            return

        # Process each entryData item
        report_updates = []
        for entry_data in entry_data_list:
            if not isinstance(entry_data, dict):
                continue

            data_ref = entry_data.get('dataRef')
            values = entry_data.get('value')

            if not data_ref or not values:
                continue

            # Store the update for broadcasting to frontend
            report_updates.append({
                'dataRef': data_ref,
                'values': values,
                'timestamp': time.time()
            })

        # Store in runtime for frontend to poll
        if report_updates:
            if 'report_updates' not in runtime:
                runtime['report_updates'] = []
            runtime['report_updates'].extend(report_updates)
            # Keep only last 100 updates to avoid memory issues
            if len(runtime['report_updates']) > 100:
                runtime['report_updates'] = runtime['report_updates'][-100:]

    except Exception as e:
        print(f"Error processing report message: {e}")

def log_message(direction: str, raw_message: Union[str, bytes], timestamp: Any) -> None:
    """Log a protocol message (sent or received) with parsed service type and category."""
    import json

    runtime['message_seq'] += 1
    msg_id = runtime['message_seq']
    ts = timestamp.strftime('%H:%M:%S.%f')[:-3] if hasattr(timestamp, 'strftime') else time.strftime('%H:%M:%S')

    # Parse message to extract service type and category
    service_type = 'unknown'
    category = 'unknown'
    message_preview = ''

    try:
        # Decode if bytes
        if isinstance(raw_message, bytes):
            raw_message = raw_message.decode('utf-8')

        # Try to parse as JSON to extract service info
        msg_json = json.loads(raw_message)
        message_preview = raw_message[:200] + ('...' if len(raw_message) > 200 else '')

        # Extract service type and category from TPAA structure
        if isinstance(msg_json, dict):
            # Check for request/response/associate/unconfirmed
            if 'request' in msg_json:
                category = 'request'
                req = msg_json['request']
                if isinstance(req, dict) and 'service' in req:
                    service = req['service']
                    if isinstance(service, dict):
                        service_type = list(service.keys())[0] if service else 'request'
                    else:
                        service_type = 'request'
            elif 'response' in msg_json:
                category = 'response'
                resp = msg_json['response']
                if isinstance(resp, dict) and 'service' in resp:
                    service = resp['service']
                    if isinstance(service, dict):
                        service_type = list(service.keys())[0] if service else 'response'
                    else:
                        service_type = 'response'
            elif 'associate' in msg_json:
                category = 'associate'
                assoc = msg_json['associate']
                if isinstance(assoc, dict) and 'service' in assoc:
                    service = assoc['service']
                    if isinstance(service, dict):
                        service_type = list(service.keys())[0] if service else 'associate'
                    else:
                        service_type = 'associate'
            elif 'unconfirmed' in msg_json:
                category = 'unconfirmed'
                unconf = msg_json['unconfirmed']
                if isinstance(unconf, dict) and 'service' in unconf:
                    service = unconf['service']
                    if isinstance(service, dict):
                        service_type = list(service.keys())[0] if service else 'unconfirmed'
                        # Process Report messages to extract data updates
                        if 'report' in service and direction == 'recv':
                            _process_report_message(service['report'])
                    else:
                        service_type = 'unconfirmed'
    except Exception as e:
        # If parsing fails, just store raw message
        message_preview = str(raw_message)[:200]
        service_type = 'parse-error'
        category = 'parse-error'

    entry = {
        'id': msg_id,
        'timestamp': ts,
        'direction': direction,  # 'send' or 'recv'
        'category': category,  # 'request', 'response', 'associate', 'unconfirmed'
        'service_type': service_type,
        'message': raw_message if isinstance(raw_message, str) else raw_message.decode('utf-8', errors='replace'),
        'preview': message_preview
    }

    runtime['messages'].append(entry)

## Removed synthetic/fallback model data.

async def refresh_token_if_needed(url, client_id, client_secret, token, websocket_endpoint, cp, client_cert, keycloack_cert):
    #jwks_url = "http://localhost:8080/realms/master/protocol/openid-connect/certs"
    while True:
        websocket_info = next((ws_info for ws_info in websocket_endpoint.websocket_info_list if ws_info.cp == cp), None)

        if websocket_info is not None:
            decoded = jwt.decode(token, options={"verify_signature": False})
            # Check if less than 3 seconds until expiration
            if decoded["exp"] - time.time() < 3:
                print(f"The access token for {cp} endpoint is expiring soon, requesting a new token...")
                token = await get_access_token(url, client_id, client_secret, keycloack_cert, client_cert)
                refresh_token_message = create_token_refresh(websocket_info.associate_id, token)
                encoded_message = encode_tpaa_message(refresh_token_message)

                await websocket_info.websocket.send(encoded_message)

        await asyncio.sleep(1)  # check every second


def start_connection_in_background(url: str, port: int, cp: Any, is_direct: bool = False, mode: str = "active", security=None) -> None:
    """Start a connection in the background and store refs.
    mode: 'active' for client (connect to server), 'passive' for server (listen for client).
    When in passive (server) mode, is_direct should be True to act as IEC61850 server."""
    async def _connect():
        try:
            if mode == "passive":
                log_action_start('connect', {'mode': 'server', 'port': port, 'cp': cp})
            else:
                log_action_start('connect', {'mode': 'client', 'url': f'ws://{url}:{port}', 'cp': cp})

            # Get the current event loop
            loop = asyncio.get_event_loop()

            # In both active and passive modes, when acting as IEC61850 client, use is_direct=False
            # is_direct=True is only for when the endpoint acts as IEC61850 server (has data model)
            # In passive mode (WS server), we're still an IEC61850 client, so is_direct=False
            endpoint_is_direct = is_direct

            # Create endpoint and client
            tls_config = None
            enable_oauth = None
            access_token = None
            token_refresh = None

            certificate_url = None
            token_issuer = None
            kc_cert = None

            client_secret_1 = None
            client_id_1 = None
            token_request_url = None

            if security:
                print("security is: ", security)
                enableTLS = security.get('enableTLS')
                enable_oauth = security.get('enableOAuth')
                token_refresh = security.get('enableTokenRefresh')

                if enableTLS is True:
                    if mode == "active":
                        certificate = security.get('tlsCACert')
                        if certificate != '':
                            with open("ws_server_ca.pem", "w") as f:
                                f.write(certificate)
                        tls_config = TLSConfiguration(is_ws_server=False, cert_path="ws_server_ca.pem", key_path=None)
                    else:
                        certificate = security.get('certificate')
                        private_key = security.get('privateKey')

                        if certificate != '' and private_key != '':
                            with open("ws_server_cert.pem", "w") as f:
                                f.write(certificate)

                            with open("ws_server_key.pem", "w") as f:
                                f.write(private_key)
                            tls_config = TLSConfiguration(is_ws_server=True, cert_path="ws_server_cert.pem", key_path="ws_server_key.pem")
                            if security.get("tlsVersion") == "1.2":
                                tls_config.set_min_and_max_version(min_version=ssl.TLSVersion.TLSv1_2,
                                                                   max_version=ssl.TLSVersion.TLSv1_2)
                            else:
                                tls_config.set_min_and_max_version(min_version=ssl.TLSVersion.TLSv1_3,
                                                                   max_version=ssl.TLSVersion.TLSv1_3)

                            tls_config.ssl_context.keylog_filename = os.path.join("tlskeys.log")

                if enable_oauth is True:
                    if mode == "active":
                        client_cert = None
                        client_secret_1 = security.get('oauthClientSecret')
                        client_id_1 = security.get('oauthClientId')
                        token_request_url = security.get('oauthUrl')
                        keycloack_cert = security.get('oauthCACert')
                        with open("kc_root_ca.pem", "w") as f:
                            f.write(keycloack_cert)
                            kc_cert = "kc_root_ca.pem"

                        access_token = await get_access_token(token_request_url, client_id_1, client_secret_1,
                                                                "kc_root_ca.pem", client_cert)
                        print("access_token: ", access_token)
                    else:
                        certificate_url = security.get('oauthCertEndpoint')
                        token_issuer = security.get('oauthIssuer')
                        kc_cert = security.get('oauthCACert')

                        with open("kc_root_ca_s.pem", "w") as f:
                            f.write(kc_cert)
                            kc_cert = "kc_root_ca_s.pem"

            ws_endpoint = WebSocketEndpoint(is_direct=endpoint_is_direct, tls_config=tls_config, oauth_enable=enable_oauth,
                                            cert_endpoint=certificate_url, token_issuer=token_issuer, kc_cert=kc_cert)
            client = IEC61850Client(cp)

            # Add client to endpoint FIRST (before starting and before setting callbacks)
            # This is critical for passive mode - client must be in client_list before handle_client is called
            ws_endpoint.add_iec61850_client(client)

            # Install callbacks AFTER adding client
            callback_send = lambda msg, ts: log_message('send', msg, ts)
            callback_recv = lambda msg, ts: log_message('recv', msg, ts)

            # Install both callbacks on endpoint (for associate request/response)
            ws_endpoint.send_msg_callback = callback_send
            ws_endpoint.recv_msg_callback = callback_recv

            # Install ONLY send callback on client (for getData, etc. requests)
            # Don't install recv callback on client to avoid duplicates
            # (endpoint already calls recv callback, then passes to client.decode_and_add_to_outstanding_calls)
            client.send_msg_callback = callback_send

            # Store in runtime
            runtime['endpoint'] = ws_endpoint
            runtime['client'] = client
            runtime['loop'] = loop
            runtime['is_direct'] = endpoint_is_direct
            runtime['mode'] = mode

            if mode == "passive":
                runtime['status'] = 'listening'
            else:
                runtime['status'] = 'connecting'

            # Clear any previous cancellation / manual disconnect flags for new attempt
            runtime['cancel_connect'] = False
            runtime['manual_disconnect'] = False

            # Start the endpoint (this will connect or listen depending on mode)
            if mode == "passive":
                # Server mode: listen on specified port
                # Client is already added to endpoint, so handle_client will find it by cp
                await ws_endpoint.start("passive", "0.0.0.0", port)
            else:
                # Client mode: connect to specified URL
                if not token_refresh:
                    await ws_endpoint.start("active", url, port, cp, access_token=access_token)
                else:
                    task_1 = asyncio.create_task(
                        ws_endpoint.start("active", url, port, cp, access_token=access_token)
                    )

                    token_task = asyncio.create_task(
                        refresh_token_if_needed(token_request_url, client_id_1, client_secret_1,
                                                access_token, ws_endpoint, cp, None, kc_cert)
                    )

                    await asyncio.gather(task_1, token_task)

            # If disconnect was requested during connection attempt, abort finalization
            if runtime.get('cancel_connect') or runtime.get('manual_disconnect'):
                try:
                    # Attempt to close any established websocket to clean up
                    ws_info = ws_endpoint.get_websocket_info(client)
                    if ws_info and hasattr(ws_info, 'websocket') and not getattr(ws_info.websocket, 'closed', False):
                        await ws_info.websocket.close()
                except Exception:
                    pass
                runtime['status'] = 'not-connected'
                # Clear endpoint/client references if cancellation requested
                runtime['endpoint'] = None
                runtime['client'] = None
                runtime['loop'] = None
                log_action_end(runtime.get('connect_aid'), False, 'connect-cancelled')
                return

            runtime['status'] = 'connected'
            log_action_end(runtime.get('connect_aid'), True)

        except asyncio.CancelledError:
            # Graceful shutdown of passive server (serve_forever cancelled) or client connect cancelled.
            # This is expected when /api/disconnect is called while we are blocked in ws_endpoint.start().
            # Treat as a normal stop instead of an error; do not re-raise to avoid noisy traceback.
            runtime['status'] = 'not-connected'
            # Mark connect action as completed (not an error) and annotate we stopped.
            try:
                log_action_end(runtime.get('connect_aid'), True, extra_detail={'stopped': True})
            except Exception:
                pass
            # Clear endpoint/client references to ensure subsequent status calls reflect disconnected state.
            runtime['endpoint'] = None
            runtime['client'] = None
            runtime['loop'] = None
            return
        except Exception as e:
            runtime['status'] = 'error'
            log_action_end(runtime.get('connect_aid'), False, str(e))
            raise

    def _run_async():
        asyncio.run(_connect())

    t = threading.Thread(target=_run_async, daemon=True)
    t.start()
    runtime['connection_thread'] = t


@app.route('/')
def index():
    return render_template('index.html')


def _invoke_async(method_coro: Any, timeout: int = 10) -> Any:
    """Run a coroutine belonging to the background connection loop in a thread-safe way."""
    loop = runtime.get('loop')
    if loop is None:
        raise RuntimeError('No active loop')
    fut = asyncio.run_coroutine_threadsafe(method_coro, loop)
    return fut.result(timeout=timeout)

def _ensure_connection(timeout: int = 10) -> Tuple[Any, WebSocketEndpoint, WebSocketInfo]:
    """Ensure there's an active connected client. Returns (client, endpoint, ws_info) or raises."""
    client = runtime.get('client')
    endpoint = runtime.get('endpoint')
    loop = runtime.get('loop')
    if not client or not endpoint or not loop:
        raise RuntimeError('not-connected')
    if not client.is_connected:
        try:
            wait_fut = asyncio.run_coroutine_threadsafe(client.ready_event.wait(), loop)
            wait_fut.result(timeout=timeout)
        except Exception:
            pass
    if not client.is_connected:
        raise RuntimeError('not-connected')
    ws_info = endpoint.get_websocket_info(client)
    if ws_info is None:
        raise RuntimeError('no-websocket-info')
    return client, endpoint, ws_info

def _list_logical_devices(timeout: int = 10) -> Tuple[List[str], Any, WebSocketInfo]:
    client, _, ws_info = _ensure_connection(timeout=timeout)
    aid = log_action_start('getServerDirectory', {'cp': client.cp})
    try:
        ld_list = _invoke_async(client.get_server_directory(ws_info, None, None), timeout=timeout)
        if not isinstance(ld_list, list):
            raise RuntimeError('unexpected-server-directory')
        log_action_end(aid, success=True, extra_detail={'count': len(ld_list)})
    except Exception as e:
        log_action_end(aid, success=False, error=str(e))
        raise
    return ld_list, client, ws_info

def _list_logical_nodes(ld_inst: str, client: Any, ws_info: WebSocketInfo, timeout: int = 10) -> List[str]:
    aid = log_action_start('getLogicalDeviceDirectory', {'ld': ld_inst})
    try:
        ln_list = _invoke_async(client.get_logical_device_directory(ld_inst, ws_info, None, None), timeout=timeout)
        if not isinstance(ln_list, list):
            raise RuntimeError(f'unexpected-ld-directory:{ld_inst}')
        log_action_end(aid, success=True, extra_detail={'count': len(ln_list)})
    except Exception as e:
        log_action_end(aid, success=False, error=str(e))
        raise
    return ln_list

def _get_ln_details(ld_inst: str, ln_inst: str, client: Any, ws_info: WebSocketInfo, timeout: int = 10) -> Dict[str, Any]:
    """Return logical node details: data objects, attributes, report control blocks, datasets.
    Complexity reduced by consolidating parsing logic."""

    def _call(mode):
        try:
            return _invoke_async(_invoke_ln_directory(client, ws_info, ld_inst, ln_inst, mode), timeout=timeout)
        except Exception:
            return None

    def _parse_do(items):
        if isinstance(items, dict):
            return (
                items.get('dataObjects', items.get('instanceNames', [])) or [],
                items.get('dataAttributes', []) or []
            )
        if isinstance(items, list):
            return (items, [])
        return ([], [])

    def _parse_rcb(entries, kind):
        if isinstance(entries, list):
            return [{'name': r, 'type': kind} for r in entries]
        if isinstance(entries, dict):
            names = entries.get('instanceNames') or entries.get('reportControlBlocks') or []
            return [{'name': r, 'type': kind} for r in names]
        return []

    def _parse_datasets(entries):
        if isinstance(entries, list):
            return entries
        if isinstance(entries, dict):
            return entries.get('instanceNames') or entries.get('dataSets') or []
        return []

    do_items = _call('dataObject')
    data_objects, data_attributes = _parse_do(do_items)
    rcbs = _parse_rcb(_call('brcb'), 'BRCB') + _parse_rcb(_call('urcb'), 'URCB')
    datasets = _parse_datasets(_call('dataset'))
    return {
        'dataObjects': data_objects,
        'dataAttributes': data_attributes,
        'reportControlBlocks': rcbs,
        'dataSets': datasets,
    }

def _convert_bytes_to_hex(obj: Any) -> Any:
    """Recursively convert bytes objects to hex strings for JSON serialization."""
    if isinstance(obj, bytes):
        return obj.hex()
    elif isinstance(obj, dict):
        return {k: _convert_bytes_to_hex(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_bytes_to_hex(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(_convert_bytes_to_hex(item) for item in obj)
    else:
        return obj

async def _aget_ln_details(ld_inst: str, ln_inst: str, client: Any, ws_info: WebSocketInfo) -> Dict[str, Any]:
    """Async variant used internally for concurrent model assembly.
    Sequential (more stable) fetch of dataObject, brcb, urcb, dataset directories with structured timing."""
    async def _safe(coro):
        try:
            return await coro
        except Exception:
            return None
    aid = log_action_start('lnDetails', {'ld': ld_inst, 'ln': ln_inst})
    do_items = await _safe(_invoke_ln_directory_async(client, ws_info, ld_inst, ln_inst, 'dataObject'))
    brcb_items = await _safe(_invoke_ln_directory_async(client, ws_info, ld_inst, ln_inst, 'brcb'))
    urcb_items = await _safe(_invoke_ln_directory_async(client, ws_info, ld_inst, ln_inst, 'urcb'))
    dataset_items = await _safe(_invoke_ln_directory_async(client, ws_info, ld_inst, ln_inst, 'dataset'))

    # Parse data objects / attributes
    data_objects = []
    data_attributes = []

    # Extract the list of data object names
    do_list = []
    if isinstance(do_items, dict):
        do_list = do_items.get('dataObjects', do_items.get('instanceNames', [])) or []
        data_attributes = do_items.get('dataAttributes', []) or []
    elif isinstance(do_items, list):
        do_list = do_items

    # Fetch CDC for each data object
    if do_list:
        # Get the invoke lock to synchronize requests
        lock = runtime.get('invoke_lock')

        for do_name in do_list:
            try:
                obj_ref = f"{ld_inst}/{ln_inst}.{do_name}"

                # Use lock to ensure invoke_id is managed correctly
                if lock is None:
                    defn = await client.get_data_definition(obj_ref, ws_info, None, None)
                else:
                    async with lock:
                        defn = await client.get_data_definition(obj_ref, ws_info, None, None)

                cdc = None
                if isinstance(defn, dict):
                    # CDC is at the top level of the data definition
                    cdc = defn.get('cdc')
                data_objects.append({'name': do_name, 'cdc': cdc})
            except Exception as e:
                # If we can't get the definition, just add the name
                data_objects.append({'name': do_name, 'cdc': None})

    # Parse RCBs and fetch their values
    def _extract_rcb(entries, kind):
        out = []
        if isinstance(entries, list):
            out = entries
        elif isinstance(entries, dict):
            out = entries.get('instanceNames') or entries.get('reportControlBlocks') or []
        return [{'name': ref, 'type': kind} for ref in out]

    rcbs = []
    lock = runtime.get('invoke_lock')

    # Process BRCBs
    brcb_list = _extract_rcb(brcb_items, 'BRCB')
    for rcb_info in brcb_list:
        rcb_name = rcb_info['name']
        rcb_ref = f"{ld_inst}/{ln_inst}.{rcb_name}"
        try:
            # Fetch BRCB values
            if lock is None:
                rcb_values = await client.get_BRCB_values(rcb_ref, ws_info, None, None)
            else:
                async with lock:
                    rcb_values = await client.get_BRCB_values(rcb_ref, ws_info, None, None)

            # Extract RptEna value and convert bytes to hex strings for JSON serialization
            rpt_ena = False
            if isinstance(rcb_values, dict):
                rpt_ena = rcb_values.get('RptEna', False)
                # Convert any bytes values to hex strings for JSON serialization
                rcb_values = _convert_bytes_to_hex(rcb_values)

            rcbs.append({
                'name': rcb_name,
                'type': 'BRCB',
                'values': rcb_values,
                'enabled': rpt_ena
            })
        except Exception as e:
            # If fetch fails, still add the RCB without values
            rcbs.append({
                'name': rcb_name,
                'type': 'BRCB',
                'values': None,
                'enabled': False
            })

    # Process URCBs
    urcb_list = _extract_rcb(urcb_items, 'URCB')
    for rcb_info in urcb_list:
        rcb_name = rcb_info['name']
        rcb_ref = f"{ld_inst}/{ln_inst}.{rcb_name}"
        try:
            # Fetch URCB values
            if lock is None:
                rcb_values = await client.get_URCB_values(rcb_ref, ws_info, None, None)
            else:
                async with lock:
                    rcb_values = await client.get_URCB_values(rcb_ref, ws_info, None, None)

            # Extract RptEna value and convert bytes to hex strings for JSON serialization
            rpt_ena = False
            if isinstance(rcb_values, dict):
                rpt_ena = rcb_values.get('RptEna', False)
                # Convert any bytes values to hex strings for JSON serialization
                rcb_values = _convert_bytes_to_hex(rcb_values)

            rcbs.append({
                'name': rcb_name,
                'type': 'URCB',
                'values': rcb_values,
                'enabled': rpt_ena
            })
        except Exception as e:
            # If fetch fails, still add the RCB without values
            rcbs.append({
                'name': rcb_name,
                'type': 'URCB',
                'values': None,
                'enabled': False
            })

    # Parse datasets
    datasets = []
    if isinstance(dataset_items, list):
        datasets = dataset_items
    elif isinstance(dataset_items, dict):
        datasets = dataset_items.get('instanceNames') or dataset_items.get('dataSets') or []

    result = {
        'dataObjects': data_objects,
        'dataAttributes': data_attributes,
        'reportControlBlocks': rcbs,
        'dataSets': datasets,
    }
    log_action_end(aid, success=True, extra_detail={'do': len(data_objects), 'da': len(data_attributes), 'rcb': len(rcbs), 'ds': len(datasets)})
    return result

 # ---- InvokeId helpers (stable locked approach) ----
def _invoke_ln_directory(client, ws_info, ld_inst, ln_inst, mode):
    """Return coroutine that performs directory call under a lock to preserve invoke_id integrity."""
    async def _coro():
        lock = runtime.get('invoke_lock')
        if lock is None:
            log_action(f'Request: getLogicalNodeDirectory {mode} {ld_inst}/{ln_inst}')
            return await client.get_logical_node_directory(ld_inst, ln_inst, mode, ws_info, None, None)
        async with lock:
            log_action(f'Request: getLogicalNodeDirectory {mode} {ld_inst}/{ln_inst}')
            return await client.get_logical_node_directory(ld_inst, ln_inst, mode, ws_info, None, None)
    return _coro()

def _invoke_ln_directory_async(client, ws_info, ld_inst, ln_inst, mode):
    # For async path we reuse same implementation; concurrency across modes will be sequentially locked
    return _invoke_ln_directory(client, ws_info, ld_inst, ln_inst, mode)

# ---------------- Background Model Build -----------------
async def _abuild_full_model() -> None:
    """Build full model sequentially with progress updates (reduced complexity)."""
    client = runtime.get('client'); endpoint = runtime.get('endpoint'); loop = runtime.get('loop')
    if not client or not endpoint or not loop or not client.is_connected:
        raise RuntimeError('not-connected')
    ws_info = endpoint.get_websocket_info(client)
    if ws_info is None:
        raise RuntimeError('no-websocket-info')

    model_aid = log_action_start('modelFetch', {})
    started = time.perf_counter()

    logical_node_details = {}
    logical_device_map = {}
    logical_device_status = {}

    def _init_progress(ld_list):
        with runtime['model_lock']:
            runtime['model_progress'] = {
                'lds_total': len(ld_list), 'lds_done': 0,
                'lns_total': 0, 'lns_done': 0,
                'current_ld': None, 'current_ln': None
            }

    def _set_current_ld(ld):
        with runtime['model_lock']:
            if runtime['model_progress']:
                runtime['model_progress']['current_ld'] = ld

    def _add_lns_total(n):
        if n:
            with runtime['model_lock']:
                if runtime['model_progress']:
                    runtime['model_progress']['lns_total'] += n

    def _set_current_ln(ln):
        with runtime['model_lock']:
            if runtime['model_progress']:
                runtime['model_progress']['current_ln'] = ln

    def _inc_ln_done():
        with runtime['model_lock']:
            if runtime['model_progress']:
                runtime['model_progress']['lns_done'] += 1

    def _finish_ld():
        with runtime['model_lock']:
            if runtime['model_progress']:
                runtime['model_progress']['lds_done'] += 1
                runtime['model_progress']['current_ln'] = None

    async def _process_ld(ld):
        try:
            _set_current_ld(ld)
            ln_list = await client.get_logical_device_directory(ld, ws_info, None, None)
            if not isinstance(ln_list, list):
                raise RuntimeError('unexpected-ln-list')
            logical_device_map[ld] = ln_list
            logical_device_status[ld] = 'ok'
            _add_lns_total(len(ln_list))
            for ln_full in ln_list:
                if '/' in ln_full:
                    ln_inst = ln_full.split('/')[-1]
                elif ':' in ln_full:
                    ln_inst = ln_full.split(':')[-1]
                else:
                    ln_inst = ln_full
                _set_current_ln(ln_inst)
                try:
                    details = await _aget_ln_details(ld, ln_inst, client, ws_info)
                    logical_node_details[f"{ld}/{ln_inst}"] = details
                except Exception as e:
                    print('ln detail fetch error (background)', ld, ln_full, e)
                finally:
                    _inc_ln_done()
        except Exception as e:
            print('logical node fetch error (background)', ld, e)
            logical_device_map[ld] = []
            logical_device_status[ld] = 'error'
        finally:
            _finish_ld()

    try:
        ld_list = await client.get_server_directory(ws_info, None, None)
        if not isinstance(ld_list, list):
            raise RuntimeError('unexpected-server-directory')
        _init_progress(ld_list)
        for ld in ld_list:  # sequential for stability
            await _process_ld(ld)
        model = {
            'server': {'logicalDevices': ld_list},
            'logicalDeviceMap': logical_device_map,
            'logicalDeviceStatus': logical_device_status,
            'logicalNodeDetails': logical_node_details,
            'source': 'live'
        }
        with runtime['model_lock']:
            runtime['model_data'] = model
            runtime['model_status'] = 'ready'
            runtime['model_error'] = None
        log_action_end(model_aid, success=True, extra_detail={'lds': len(ld_list), 'lnDetails': len(logical_node_details)})
    except Exception as e:
        with runtime['model_lock']:
            runtime['model_status'] = 'error'
            runtime['model_error'] = str(e)
        log_action_end(model_aid, success=False, error=str(e))
        raise
    finally:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        log_action(f'Model build elapsed {elapsed_ms} ms')

def _start_model_build_if_needed():
    """Schedule background model build if idle or error. Returns status after scheduling."""
    with runtime['model_lock']:
        status = runtime['model_status']
        if status in ('ready', 'building'):
            return status
        # reset
        runtime['model_data'] = None
        runtime['model_error'] = None
        runtime['model_status'] = 'building'
        runtime['model_started_at'] = time.perf_counter()
    loop = runtime.get('loop')
    if not loop:
        with runtime['model_lock']:
            runtime['model_status'] = 'error'
            runtime['model_error'] = 'no-loop'
        return 'error'
    # schedule
    fut = asyncio.run_coroutine_threadsafe(_abuild_full_model(), loop)
    with runtime['model_lock']:
        runtime['model_task'] = fut
    return 'building'

def _parse_da_structure(da_def):
    """Parse a data attribute definition to extract nested structure if present.
    Returns dict with 'daRef', 'hasStructure', 'type', 'fc' and 'subAttributes' if structured."""
    da_ref = da_def.get('daRef')
    if not da_ref:
        return None

    # Get FC (functional constraint) from definition
    fc = da_def.get('fc', 'mx')
    if fc:
        fc = fc.lower()

    result = {'daRef': da_ref, 'hasStructure': False, 'subAttributes': [], 'type': None, 'fc': fc}

    da_type = da_def.get('daType')
    if isinstance(da_type, (list, tuple)) and len(da_type) >= 2:
        type_key = da_type[0]
        result['type'] = type_key  # Store the type (e.g., 'structure', 'int32', 'boolean', etc.)
        if type_key == 'structure' and isinstance(da_type[1], list):
            result['hasStructure'] = True
            # Parse structure components recursively
            for cmp in da_type[1]:
                if isinstance(cmp, dict):
                    cmp_name = cmp.get('cmpName')
                    cmp_type = cmp.get('cmpType')
                    if cmp_name:
                        sub_attr = {'name': cmp_name, 'hasStructure': False, 'subAttributes': [], 'type': None}
                        # Extract type for component
                        if isinstance(cmp_type, (list, tuple)) and len(cmp_type) >= 2:
                            sub_attr['type'] = cmp_type[0]
                            # Check if component itself has nested structure
                            if cmp_type[0] == 'structure':
                                sub_attr['hasStructure'] = True
                                # Recursively parse nested structure
                                if isinstance(cmp_type[1], list):
                                    sub_attr['subAttributes'] = _parse_nested_structure(cmp_type[1])
                        result['subAttributes'].append(sub_attr)
    elif isinstance(da_type, str):
        result['type'] = da_type

    return result

def _parse_nested_structure(struct_list):
    """Recursively parse nested structure components."""
    parsed = []
    for cmp in struct_list:
        if isinstance(cmp, dict):
            cmp_name = cmp.get('cmpName')
            cmp_type = cmp.get('cmpType')
            if cmp_name:
                sub_attr = {'name': cmp_name, 'hasStructure': False, 'subAttributes': [], 'type': None}
                if isinstance(cmp_type, (list, tuple)) and len(cmp_type) >= 2:
                    sub_attr['type'] = cmp_type[0]
                    if cmp_type[0] == 'structure':
                        sub_attr['hasStructure'] = True
                        if isinstance(cmp_type[1], list):
                            sub_attr['subAttributes'] = _parse_nested_structure(cmp_type[1])
                elif isinstance(cmp_type, str):
                    sub_attr['type'] = cmp_type
                parsed.append(sub_attr)
    return parsed

@app.route('/api/dodef/<ld_inst>/<ln_inst>/<path:do_path>')
def api_do_definition(ld_inst, ln_inst, do_path):
    """Return data definition (subDataObjects & dataAttributes) for a specific data object path.
    do_path may contain dots for nested sub data objects (e.g., DO1.Sub1.Sub2)."""
    try:
        client, _, ws_info = _ensure_connection()
        obj_ref = f"{ld_inst}/{ln_inst}.{do_path}" if do_path else f"{ld_inst}/{ln_inst}"
        aid = log_action_start('getDataDefinition', {'ref': obj_ref})
        try:
            defn = _invoke_async(client.get_data_definition(obj_ref, ws_info, None, None), timeout=10)
        except Exception as e:
            log_action_end(aid, success=False, error=str(e))
            raise
        if not isinstance(defn, dict):
            log_action_end(aid, success=True, extra_detail={'subDO': 0, 'DA': 0})
            return jsonify({'subDataObjects': [], 'dataAttributes': []})
        sub_defs = defn.get('subDataDefinition') or []
        da_defs = defn.get('dataAttributeDefinition') or []
        # Include both name and cdc for sub data objects
        sub_sdos = [{'name': sub.get('name'), 'cdc': sub.get('cdc')}
                    for sub in sub_defs if isinstance(sub, dict) and sub.get('name')]
        # Parse data attributes with structure information
        data_attrs = []
        for da_def in da_defs:
            if isinstance(da_def, dict):
                parsed = _parse_da_structure(da_def)
                if parsed:
                    data_attrs.append(parsed)
        log_action_end(aid, success=True, extra_detail={'subDO': len(sub_sdos), 'DA': len(data_attrs)})
        return jsonify({'subDataObjects': sub_sdos, 'dataAttributes': data_attrs})
    except RuntimeError as re:
        # There will already be an action end if exception came post start; ensure end if not
        log_action(f'Error getDataDefinition {ld_inst}/{ln_inst}.{do_path}: {re}', 'error')
        code = 503 if str(re) in ('not-connected','no-websocket-info') else 500
        return jsonify({'error': str(re)}), code
    except Exception as e:
        log_action(f'Exception getDataDefinition {ld_inst}/{ln_inst}.{do_path}: {e}', 'error')
        return jsonify({'error': str(e)}), 500

@app.route('/api/readvalue', methods=['POST'])
def api_read_value():
    """Read data values for a specific data object or data attribute reference.
    Expects JSON body with 'objRef' and 'fc' (functional constraint)."""
    try:
        data = request.get_json() or {}
        obj_ref = data.get('objRef')
        fc = data.get('fc', 'mx')  # Default to mx if not specified

        # Normalize FC to lowercase (accept both 'mx' and 'MX', 'cf' and 'CF', etc.)
        if fc:
            fc = fc.lower()

        if not obj_ref:
            return jsonify({'error': 'objRef is required'}), 400

        client, _, ws_info = _ensure_connection()
        aid = log_action_start('getDataValues', {'ref': obj_ref, 'fc': fc})

        try:
            # Call get_data_values with include_element_name=True
            result = _invoke_async(
                client.get_data_values(obj_ref, fc, True, ws_info, None, None),
                timeout=10
            )
        except Exception as e:
            log_action_end(aid, success=False, error=str(e))
            raise

        # Check if result is an error message (string) or actual data
        if isinstance(result, str):
            log_action_end(aid, success=False, error=result)
            return jsonify({'error': result}), 400

        log_action_end(aid, success=True, extra_detail={'values': len(result) if isinstance(result, list) else 1})
        return jsonify({'success': True, 'objRef': obj_ref, 'fc': fc, 'values': result})

    except RuntimeError as re:
        log_action(f'Error getDataValues {obj_ref}: {re}', 'error')
        code = 503 if str(re) in ('not-connected','no-websocket-info') else 500
        return jsonify({'error': str(re)}), code
    except Exception as e:
        log_action(f'Exception getDataValues {obj_ref}: {e}', 'error')
        return jsonify({'error': str(e)}), 500

@app.route('/api/writevalue', methods=['POST'])
def api_write_value():
    """Write a data value to a specific data attribute.
    Expects JSON body with 'objRef', 'fc', 'value', and 'dataType'."""
    try:
        data = request.get_json() or {}
        obj_ref = data.get('objRef')
        fc = data.get('fc', 'mx')
        value = data.get('value')
        data_type = data.get('dataType', 'unknown')

        # Normalize FC to lowercase
        if fc:
            fc = fc.lower()

        if not obj_ref:
            return jsonify({'error': 'objRef is required'}), 400
        if value is None:
            return jsonify({'error': 'value is required'}), 400

        client, _, ws_info = _ensure_connection()
        aid = log_action_start('setDataValues', {'ref': obj_ref, 'fc': fc, 'value': value})

        print(f"[Write Value] objRef={obj_ref}, fc={fc}, value={value} (type={type(value).__name__}), dataType={data_type}")

        # Extract the attribute name from the object reference
        # e.g., "LD0/DWMX1.WMaxSetPct.setMag.f" -> "f"
        attr_name = obj_ref.split('.')[-1]
        
        # Format the value based on data type for the TPAA protocol
        formatted_value = format_value_for_write(value, data_type, attr_name)
        
        print(f"[Write Value] Formatted value: {formatted_value}")

        try:
            # Call set_data_values
            result = _invoke_async(
                client.set_data_values(obj_ref, fc, formatted_value, ws_info, None, None),
                timeout=10
            )
        except Exception as e:
            log_action_end(aid, success=False, error=str(e))
            raise

        # Check if result indicates success
        if isinstance(result, str) and 'error' in result.lower():
            log_action_end(aid, success=False, error=result)
            return jsonify({'error': result}), 400

        log_action_end(aid, success=True)
        return jsonify({'success': True, 'objRef': obj_ref, 'fc': fc})

    except RuntimeError as re:
        log_action(f'Error setDataValues {obj_ref}: {re}', 'error')
        code = 503 if str(re) in ('not-connected','no-websocket-info') else 500
        return jsonify({'error': str(re)}), code
    except Exception as e:
        log_action(f'Exception setDataValues {obj_ref}: {e}', 'error')
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

def format_value_for_write(value, data_type, attr_name):
    """Format a value for setDataValues according to its data type for TPAA protocol.
    Returns a list with a dictionary containing 'name' and 'data' keys.
    The 'data' value is a TUPLE (type_name, value) for the ASN.1 encoder."""
    
    # Create the typed value tuple (required by ASN.1 encoder)
    if data_type == 'boolean':
        typed_value = ('boolean', bool(value))
    elif data_type in ['int8', 'int16', 'int32']:
        typed_value = (data_type, int(value))
    elif data_type in ['int8u', 'int16u', 'int32u']:
        typed_value = (data_type, int(value))
    elif data_type == 'int64':
        typed_value = ('int64', int(value))
    elif data_type in ['float32', 'float64']:
        typed_value = (data_type, float(value))
    elif data_type in ['visString32', 'visString64', 'visString65', 'visString129', 'visString255', 'string']:
        typed_value = (data_type, str(value))
    elif data_type == 'enumerated':
        typed_value = ('enumerated', str(value))
    elif data_type == 'octetString':
        # Handle hex string conversion if needed
        if isinstance(value, str) and value.startswith('0x'):
            typed_value = ('octetString', bytes.fromhex(value[2:]))
        else:
            typed_value = ('octetString', value.encode() if isinstance(value, str) else value)
    elif data_type == 'timeStamp':
        # Handle timestamp - could be Unix timestamp or ISO format
        if isinstance(value, int):
            typed_value = ('timeStamp', {
                'secondSinceEpoch': value,
                'fractionOfSecond': 0,
                'timeQuality': {
                    'leapSecondKnown': False,
                    'clockFailure': False,
                    'clockNotSynchronized': False,
                    'timeAccuracy': 0
                }
            })
        else:
            typed_value = ('timeStamp', value)
    else:
        # Unknown type - try to infer from Python type
        if isinstance(value, bool):
            typed_value = ('boolean', value)
        elif isinstance(value, int):
            typed_value = ('int32', value)
        elif isinstance(value, float):
            typed_value = ('float32', value)
        elif isinstance(value, str):
            typed_value = ('visString255', value)
        else:
            typed_value = (data_type, value)
    
    # Wrap in the required format: list with dict containing 'name' and 'data'
    return [{'name': attr_name, 'data': typed_value}]

def format_value_for_type(value, data_type):
    """Format a value according to its data type for TPAA protocol."""
    # Map common data types to TPAA format
    if data_type == 'boolean':
        return ('boolean', bool(value))
    elif data_type in ['int8', 'int16', 'int32']:
        return (data_type, int(value))
    elif data_type in ['int8u', 'int16u', 'int32u']:
        return (data_type, int(value))
    elif data_type == 'int64':
        return ('int64', int(value))
    elif data_type in ['float32', 'float64']:
        return (data_type, float(value))
    elif data_type in ['visString32', 'visString64', 'visString65', 'visString129', 'visString255', 'string']:
        return (data_type, str(value))
    elif data_type == 'enumerated':
        return ('enumerated', str(value))
    elif data_type == 'octetString':
        # Handle hex string conversion if needed
        if isinstance(value, str) and value.startswith('0x'):
            return ('octetString', bytes.fromhex(value[2:]))
        return ('octetString', value.encode() if isinstance(value, str) else value)
    elif data_type == 'timeStamp':
        # Handle timestamp - could be Unix timestamp or ISO format
        if isinstance(value, int):
            return ('timeStamp', {
                'secondSinceEpoch': value,
                'fractionOfSecond': 0,
                'timeQuality': {
                    'leapSecondKnown': False,
                    'clockFailure': False,
                    'clockNotSynchronized': False,
                    'timeAccuracy': 0
                }
            })
        return ('timeStamp', value)
    else:
        # Unknown type - try to infer from Python type
        if isinstance(value, bool):
            return ('boolean', value)
        elif isinstance(value, int):
            return ('int32', value)
        elif isinstance(value, float):
            return ('float32', value)
        elif isinstance(value, str):
            return ('visString255', value)
        else:
            return (data_type, value)

@app.route('/api/getfcs', methods=['POST'])
def api_get_fcs():
    """Get available functional constraints for a data object.
    Uses getDataDirectory service to retrieve FC list."""
    try:
        data = request.get_json() or {}
        obj_ref = data.get('objRef')

        if not obj_ref:
            return jsonify({'error': 'objRef is required'}), 400

        client, _, ws_info = _ensure_connection()
        aid = log_action_start('getDataDirectory', {'ref': obj_ref})

        try:
            # Attempt to discover FCs via data directory (implemented as wrapper over data definition)
            result = _invoke_async(
                client.get_data_directory(obj_ref, ws_info),
                timeout=10
            )
            # If result is an error string, attempt direct data definition and derive FCs
            if isinstance(result, str):
                dd = _invoke_async(
                    client.get_data_definition(obj_ref, ws_info, None, None),
                    timeout=10
                )
                if isinstance(dd, dict):
                    fcs_from_dd = sorted({(da.get('fc') or '').lower() for da in dd.get('dataAttributes', []) if isinstance(da, dict) and da.get('fc')})
                    if fcs_from_dd:
                        result = fcs_from_dd
        except Exception as e:
            log_action_end(aid, success=False, error=str(e))
            raise

        # Check if result is an error message (string) or actual data
        if isinstance(result, str):
            log_action_end(aid, success=False, error=result)
            return jsonify({'error': result}), 400

        # Result should be a list of FC names
        fcs = []
        if isinstance(result, list):
            fcs = [fc.lower() if isinstance(fc, str) else fc for fc in result]

        log_action_end(aid, success=True, extra_detail={'fcs': len(fcs)})
        return jsonify({'success': True, 'objRef': obj_ref, 'fcs': fcs})

    except RuntimeError as re:
        log_action(f'Error getDataDirectory {obj_ref}: {re}', 'error')
        code = 503 if str(re) in ('not-connected','no-websocket-info') else 500
        return jsonify({'error': str(re)}), code
    except Exception as e:
        log_action(f'Exception getDataDirectory {obj_ref}: {e}', 'error')
        return jsonify({'error': str(e)}), 500

@app.route('/api/model')
def api_model():
    # Non-blocking: if model not ready, ensure build started and return status
    try:
        _ensure_connection()  # may raise runtime errors
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 503
    with runtime['model_lock']:
        status = runtime['model_status']
        data = runtime['model_data']
        error = runtime['model_error']
    if status == 'ready' and data:
        return jsonify({'status': 'ready', 'model': data})
    if status == 'error':
        return jsonify({'status': 'error', 'error': error}), 500
    # status idle/building => trigger if idle
    if status == 'idle':
        _start_model_build_if_needed()
    with runtime['model_lock']:
        progress = runtime.get('model_progress')
    return jsonify({'status': 'building', 'progress': progress})


@app.route('/api/ld/<ld_inst>')
def api_ld(ld_inst):
    try:
        _, client, ws_info = _list_logical_devices()
        ln_list = _list_logical_nodes(ld_inst, client, ws_info)
        return jsonify({'ld': {'logicalNodes': ln_list}, 'source': 'live'})
    except RuntimeError as re:
        code = 503 if str(re) in ('not-connected','no-websocket-info') else 500
        return jsonify({'error': str(re)}), code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/model/rebuild', methods=['POST'])
def api_model_rebuild():
    try:
        _ensure_connection()
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 503
    with runtime['model_lock']:
        runtime['model_status'] = 'idle'
        runtime['model_data'] = None
        runtime['model_error'] = None
        runtime['model_task'] = None
        runtime['model_started_at'] = None
    status = _start_model_build_if_needed()
    return jsonify({'status': status})


## Removed /api/mock/model endpoint.


@app.route('/api/connect', methods=['POST'])
def api_connect():
    data = request.get_json() or {}
    url = data.get('url')
    port = data.get('port')
    cp = data.get('cp')
    is_direct = data.get('is_direct', False)
    is_server = data.get('is_server', False)  # New parameter to indicate server mode
    security = data.get('security') # Security settings dict

    # In server mode, url is not required
    if is_server:
        if not port or not cp:
            return jsonify({'error': 'port and cp are required for server mode'}), 400
        mode = 'passive'
        url = '0.0.0.0'  # Listen on all interfaces
    else:
        if not url or not port or not cp:
            return jsonify({'error': 'url, port and cp are required for client mode'}), 400
        mode = 'active'

    try:
        if is_server:
            log_action(f'Server mode: listening on port {port} cp={cp}')
        else:
            sec_msg = ""
            if security:
                if security.get('enableTLS'): sec_msg += " [TLS]"
                if security.get('enableOAuth'): sec_msg += " [OAuth]"
            log_action(f'Client mode: connecting to {url}:{port} cp={cp} direct={is_direct}{sec_msg}')
        # Reset manual disconnect suppression on explicit connect request
        runtime['manual_disconnect'] = False
        runtime['cancel_connect'] = False
        start_connection_in_background(url, port, cp, is_direct=is_direct, mode=mode, security=security)
        return jsonify({'status': 'listening' if is_server else 'connecting'})
    except Exception as e:
        log_action(f'Connect error: {e}', 'error')
        return jsonify({'error': str(e)}), 500


@app.route('/api/disconnect', methods=['POST'])
def api_disconnect():
    try:
        client = runtime.get('client')
        endpoint = runtime.get('endpoint')
        loop = runtime.get('loop')
        if not client or not endpoint or not loop:
            return jsonify({'status': 'no-active-connection'})
        mode = runtime.get('mode', 'active')
        # Mark manual disconnect & cancel any in-flight connection
        runtime['manual_disconnect'] = True
        runtime['cancel_connect'] = True
        # Passive mode: stop listening server and disconnect any clients
        if mode == 'passive':
            async def _stop_passive():
                await endpoint.stop_passive()
            asyncio.run_coroutine_threadsafe(_stop_passive(), loop).result(timeout=10)
            client.is_connected = False
            log_action('Passive server stopped', 'warn')
        else:
            ws_info = endpoint.get_websocket_info(client)
            if ws_info and not getattr(ws_info.websocket, 'closed', False):
                def _close():
                    return ws_info.websocket.close()
                asyncio.run_coroutine_threadsafe(_close(), loop)
            client.is_connected = False
            log_action('Disconnected from server', 'warn')
        with runtime['model_lock']:
            runtime['model_status'] = 'idle'
            runtime['model_data'] = None
            runtime['model_error'] = None
            runtime['model_task'] = None
            runtime['model_started_at'] = None
        runtime['status'] = 'not-connected'
        # Drop references so status endpoint doesn't infer a pseudo connecting state
        runtime['endpoint'] = None
        runtime['client'] = None
        runtime['loop'] = None
        return jsonify({'status': 'disconnected'})
    except Exception as e:
        log_action(f'Disconnect error: {e}', 'error')
        return jsonify({'error': str(e)}), 500


@app.route('/api/status')
def api_status():
    try:
        client = runtime.get('client')
        endpoint = runtime.get('endpoint')
        loop = runtime.get('loop')
        mode = runtime.get('mode', 'active')
        state = 'not-connected'
        detail = {}

        # If user manually disconnected, force not-connected regardless of remnants
        if runtime.get('manual_disconnect'):
            return jsonify({'state': state, 'detail': detail})

        if client and endpoint and loop:
            ws_info = endpoint.get_websocket_info(client)

            # In passive mode, check if we're listening or connected
            if mode == 'passive':
                if client.is_connected and ws_info is not None:
                    # Check if websocket is still open
                    if not getattr(ws_info.websocket, 'closed', False):
                        state = 'connected'
                    else:
                        # Websocket closed, reset state
                        client.is_connected = False
                        runtime['status'] = 'listening'
                        state = 'listening'
                        # Clear model when client disconnects
                        with runtime['model_lock']:
                            runtime['model_data'] = None
                            runtime['model_status'] = 'idle'
                else:
                    # Not connected but listening
                    state = 'listening'
            else:
                # Active mode (client)
                if client.is_connected:
                    state = 'connected'
                else:
                    if ws_info is not None:
                        state = 'connecting'
                    else:
                        state = 'starting'
                # Detect closed websockets in list -> disconnected override
                if ws_info and getattr(ws_info.websocket, 'closed', False):
                    state = 'not-connected'

            if ws_info:
                detail = {
                    'invokeId': ws_info.invoke_id,
                    'associateId': ws_info.associate_id,
                    'cp': client.cp
                }

        return jsonify({'state': state, 'detail': detail})
    except Exception as e:
        log_action(f'Status error: {e}', 'error')
        return jsonify({'state': 'error', 'error': str(e)}), 500

@app.route('/api/actions')
def api_actions():
    # Return recent actions (latest last)
    return jsonify({'actions': list(runtime['actions'])})

@app.route('/api/messages')
def api_messages():
    """Return recent protocol messages (sent/received)."""
    return jsonify({'messages': list(runtime['messages'])})

@app.route('/api/messages/clear', methods=['POST'])
def api_messages_clear():
    """Clear all stored protocol messages.
    Returns JSON status so frontend can confirm purge.
    """
    try:
        with runtime['messages_lock']:
            runtime['messages'].clear()
            runtime['message_seq'] = 0  # optional reset of sequence counter
        return jsonify({'status': 'cleared'})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/messages/settings', methods=['GET', 'POST'])
def api_messages_settings():
    """Get or update message retention settings.
    GET: returns current max retention.
    POST: expects JSON {"max": <int>} and updates retention, truncating if needed.
    """
    try:
        if request.method == 'GET':
            return jsonify({'max': runtime['messages_max']})
        data = request.get_json() or {}
        new_max = int(data.get('max', runtime['messages_max']))
        # Validation bounds
        if new_max < 50 or new_max > 5000:
            return jsonify({'error': 'max out of allowed range (50-5000)'}), 400
        with runtime['messages_lock']:
            # Rebuild deque preserving newest messages (truncate if shrinking)
            existing = list(runtime['messages'])
            if len(existing) > new_max:
                existing = existing[-new_max:]
            runtime['messages'] = deque(existing, maxlen=new_max)
            runtime['messages_max'] = new_max
        return jsonify({'status': 'updated', 'max': new_max})
    except ValueError:
        return jsonify({'error': 'invalid max value'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/report-updates')
def api_report_updates():
    """Return and clear pending report updates for the frontend."""
    updates = runtime.get('report_updates', [])
    runtime['report_updates'] = []  # Clear after reading
    return jsonify({'updates': updates})

@app.route('/api/ln/<ld_inst>/<ln_inst>')
def api_ln(ld_inst, ln_inst):
    try:
        _, client, ws_info = _list_logical_devices()
        details = _get_ln_details(ld_inst, ln_inst, client, ws_info)
        return jsonify({'ln': details, 'source': 'live'})
    except RuntimeError as re:
        code = 503 if str(re) in ('not-connected','no-websocket-info') else 500
        return jsonify({'error': str(re)}), code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/rcb/values', methods=['POST'])
def api_get_rcb_values():
    """Get RCB values without calling getServerDirectory."""
    try:
        data = request.get_json() or {}
        rcb_ref = data.get('rcbRef')
        rcb_type = data.get('rcbType')

        if not rcb_ref or not rcb_type:
            return jsonify({'error': 'rcbRef and rcbType required'}), 400

        client, _, ws_info = _ensure_connection()

        # Call appropriate method based on type
        if rcb_type == 'BRCB':
            result = _invoke_async(client.get_BRCB_values(rcb_ref, ws_info, None, None), timeout=10)
        elif rcb_type == 'URCB':
            result = _invoke_async(client.get_URCB_values(rcb_ref, ws_info, None, None), timeout=10)
        else:
            return jsonify({'error': f'Invalid rcbType: {rcb_type}'}), 400

        # Extract RptEna and convert bytes to hex
        rpt_ena = False
        if isinstance(result, dict):
            # Check both 'RptEna' and 'rptEna' for case-insensitive matching
            rpt_ena = result.get('RptEna', result.get('rptEna', False))
            result = _convert_bytes_to_hex(result)

        return jsonify({'values': result, 'enabled': rpt_ena})

    except RuntimeError as re:
        code = 503 if str(re) in ('not-connected','no-websocket-info') else 500
        return jsonify({'error': str(re)}), code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/rcb/set', methods=['POST'])
def api_set_rcb_values():
    """Set RCB values using set_BRCB_values or set_URCB_values."""
    try:
        data = request.get_json() or {}
        rcb_ref = data.get('rcbRef')
        rcb_type = data.get('rcbType')
        values = data.get('values', {})

        print(f"[RCB Set] Received request for {rcb_ref} ({rcb_type})")
        print(f"[RCB Set] Values received: {values}")

        if not rcb_ref or not rcb_type:
            return jsonify({'error': 'rcbRef and rcbType required'}), 400

        client, _, ws_info = _ensure_connection()

        # Create a ClientReportControlBlock object
        from IEC61850.client.IEC61850Client import IEC61850Client
        is_buffered = (rcb_type == 'BRCB')
        rcb_block = IEC61850Client.ClientReportControlBlock(rcb_ref, is_buffered)

        # Map frontend field names to ClientReportControlBlock attribute names
        # Allow multiple casing / naming variants coming from the UI (DatSet, dataSet, DataSet, datSet)
        field_mapping = {
            'RptEna': 'rptEna',
            'DatSet': 'dataSet',
            'dataSet': 'dataSet',
            'DataSet': 'dataSet',
            'datSet': 'dataSet',
            'IntgPd': 'intgPd',
            'GI': 'gi',
            'PurgeBuf': 'purgeBuf',
            'OptFlds': 'optFlds',
            'TrgOps': 'trgOps'
        }

        # Set attributes on the RCB block object (normalize dataset variants)
        for frontend_name, backend_name in field_mapping.items():
            if frontend_name in values:
                value = values[frontend_name]
                setattr(rcb_block, backend_name, value)

        # If none of the explicit dataset keys matched but a generic key is present (case-insensitive), set it
        if getattr(rcb_block, 'dataSet', None) is None:
            for k, v in values.items():
                if isinstance(k, str) and k.lower() == 'dataset':  # catch stray lowercase variant
                    setattr(rcb_block, 'dataSet', v)
                    print(f"[RCB Set] Applied dataSet via fallback key variant '{k}': {v}")
                    break

        # Log what's set on the RCB block
        print(f"[RCB Set] RCB block attributes:")
        for attr in ['rptEna', 'dataSet', 'intgPd', 'gi', 'purgeBuf', 'optFlds', 'trgOps']:
            val = getattr(rcb_block, attr, None)
            if val is not None:
                print(f"  {attr}: {val}")

        # Call appropriate method based on type
        if rcb_type == 'BRCB':
            _invoke_async(client.set_BRCB_values(rcb_block, ws_info, None, None), timeout=10)
            # Read back the values
            result = _invoke_async(client.get_BRCB_values(rcb_ref, ws_info, None, None), timeout=10)
        elif rcb_type == 'URCB':
            _invoke_async(client.set_URCB_values(rcb_block, ws_info, None, None), timeout=10)
            # Read back the values
            result = _invoke_async(client.get_URCB_values(rcb_ref, ws_info, None, None), timeout=10)
        else:
            return jsonify({'error': f'Invalid rcbType: {rcb_type}'}), 400

        # Extract RptEna and convert bytes to hex
        rpt_ena = False
        if isinstance(result, dict):
            # Check both 'RptEna' and 'rptEna' for case-insensitive matching
            rpt_ena = result.get('RptEna', result.get('rptEna', False))
            result = _convert_bytes_to_hex(result)

        # Include the dataSet we attempted to set for easier frontend validation
        attempted_dataset = getattr(rcb_block, 'dataSet', None)
        return jsonify({'values': result, 'enabled': rpt_ena, 'dataSetApplied': attempted_dataset})

    except RuntimeError as re:
        code = 503 if str(re) in ('not-connected','no-websocket-info') else 500
        return jsonify({'error': str(re)}), code
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/control/select', methods=['POST'])
def control_select():
    """Select control operation (reserve control point)"""
    try:
        client = runtime.get('client')
        endpoint = runtime.get('endpoint')
        if not client or not endpoint:
            return jsonify({'error': 'not-connected'}), 503
        
        data = request.get_json()
        obj_ref = data.get('objRef')
        
        if not obj_ref:
            return jsonify({'error': 'objRef is required'}), 400
        
        print(f"[Control Select] objRef={obj_ref}")
        
        # Get websocket info and event loop
        websocket_info = endpoint.get_websocket_info(client)
        if not websocket_info:
            return jsonify({'error': 'no-websocket-info'}), 503
        
        loop = runtime.get('loop')
        if not loop:
            return jsonify({'error': 'event-loop-not-available'}), 503
        
        # Call select on the client using the existing event loop
        fut = asyncio.run_coroutine_threadsafe(
            client.select(obj_ref, websocket_info, None, None),
            loop
        )
        result = fut.result(timeout=30)
        
        print(f"[Control Select Result] {result}")
        
        return jsonify({'success': True, 'ctlNum': result if isinstance(result, int) else 0})
        
    except RuntimeError as re:
        return jsonify({'error': str(re)}), 503
    except Exception as e:
        print(f"[Control Select Error] {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/control/operate', methods=['POST'])
def control_operate():
    """Operate control operation (execute control)"""
    try:
        client = runtime.get('client')
        endpoint = runtime.get('endpoint')
        if not client or not endpoint:
            return jsonify({'error': 'not-connected'}), 503
        
        data = request.get_json()
        obj_ref = data.get('objRef')
        ctl_val = data.get('ctlVal')
        ctl_num = data.get('ctlNum', 0)
        origin = data.get('origin', {'orCat': 1, 'orIdent': '0'})
        test = data.get('test', False)
        
        if not obj_ref:
            return jsonify({'error': 'objRef is required'}), 400
        if ctl_val is None:
            return jsonify({'error': 'ctlVal is required'}), 400
        
        print(f"[Control Operate] objRef={obj_ref}, ctlVal={ctl_val}, ctlNum={ctl_num}")
        
        # Get websocket info
        websocket_info = endpoint.get_websocket_info(client)
        if not websocket_info:
            return jsonify({'error': 'no-websocket-info'}), 503
        
        # Format control value based on type
        if isinstance(ctl_val, bool):
            formatted_ctlVal = ('boolean', ctl_val)
        elif isinstance(ctl_val, int):
            formatted_ctlVal = ('int32', ctl_val)
        elif isinstance(ctl_val, float):
            formatted_ctlVal = ('float32', ctl_val)
        elif isinstance(ctl_val, str):
            # Handle enumerated values
            formatted_ctlVal = ('enumerated', ctl_val)
        else:
            formatted_ctlVal = ctl_val
        
        # Get current timestamp
        import time
        current_time = int(time.time())
        
        # Map origin category value to proper enum format (camelCase without hyphens)
        origin_category_map = {
            0: 'notSupported',
            1: 'bayControl',
            2: 'stationControl',
            3: 'remoteControl',
            4: 'automaticBay',
            5: 'automaticStation',
            6: 'automaticRemote',
            7: 'maintenance',
            8: 'process'
        }
        
        # Build operate request dictionary
        oper_val = {
            "ref": obj_ref,
            "ctlVal": formatted_ctlVal,
            "origin": {
                "orCat": origin['orCat'] if isinstance(origin['orCat'], str) else origin_category_map.get(origin['orCat'], 'bayControl'),
                "orIdent": origin['orIdent'].encode() if isinstance(origin['orIdent'], str) else origin['orIdent']
            },
            "ctlNum": ctl_num,
            "t": {
                "secondSinceEpoch": current_time,
                "fractionOfSecond": 0,
                "timeQuality": {
                    "leapSecondKnown": False,
                    "clockFailure": False,
                    "clockNotSynchronized": False,
                    "timeAccuracy": 0
                }
            },
            "test": test,
            "check": {
                "synchroCheck": False,
                "interlockCheck": False
            }
        }
        
        print(f"[Control Operate Request] {oper_val}")
        
        # Get event loop
        loop = runtime.get('loop')
        if not loop:
            return jsonify({'error': 'event-loop-not-available'}), 503
        
        # Call operate on the client using the existing event loop
        fut = asyncio.run_coroutine_threadsafe(
            client.operate(oper_val, websocket_info, None, None),
            loop
        )
        result = fut.result(timeout=30)
        
        print(f"[Control Operate Result] {result}")
        
        return jsonify({'success': True, 'result': str(result)})
        
    except RuntimeError as re:
        return jsonify({'error': str(re)}), 503
    except Exception as e:
        print(f"[Control Operate Error] {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/control/cancel', methods=['POST'])
def control_cancel():
    """Cancel control operation (release reservation)"""
    try:
        client = runtime.get('client')
        endpoint = runtime.get('endpoint')
        if not client or not endpoint:
            return jsonify({'error': 'not-connected'}), 503
        
        data = request.get_json()
        obj_ref = data.get('objRef')
        
        if not obj_ref:
            return jsonify({'error': 'objRef is required'}), 400
        
        print(f"[Control Cancel] objRef={obj_ref}")
        
        # Check if client has a cancel method
        if not hasattr(client, 'cancel'):
            # Cancel is not implemented yet in the client
            # For now, we return a not-implemented error
            return jsonify({'error': 'Cancel operation not yet implemented'}), 501
        
        # Get websocket info and event loop
        websocket_info = endpoint.get_websocket_info(client)
        if not websocket_info:
            return jsonify({'error': 'no-websocket-info'}), 503
        
        loop = runtime.get('loop')
        if not loop:
            return jsonify({'error': 'event-loop-not-available'}), 503
        
        # Call cancel on the client using the existing event loop
        fut = asyncio.run_coroutine_threadsafe(
            client.cancel(obj_ref, websocket_info, None, None),
            loop
        )
        result = fut.result(timeout=30)
        
        print(f"[Control Cancel Result] {result}")
        
        return jsonify({'success': True})
        
    except RuntimeError as re:
        return jsonify({'error': str(re)}), 503
    except Exception as e:
        print(f"[Control Cancel Error] {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting Flask app on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=True)