"""Integration test for BFF to FSP API calls.

This test requires both BFF and FSP Docker containers to be running.
Run with: docker compose up -d && pytest test_bff_endpoint.py
"""

import pytest
import requests
import time
import json
import os

# Update these ports to match your docker-compose setup
BFF_PORT = 5000  # BFF is exposed on port 5000 (from docker-compose.yml)
FSP_PORT = 5001  # FSP is running on port 5001
SO_PORT = 5002  # SO is running on port 5002

# Base URLs - use these everywhere instead of hardcoding
BFF_BASE_URL = f"http://localhost:{BFF_PORT}/api"
FSP_BASE_URL = f"http://localhost:{FSP_PORT}/api"
SO_BASE_URL = f"http://localhost:{SO_PORT}/api"


def _extract_messages(resp_json):
    """Normalize messages response - handles both list and dict shapes."""
    msgs = resp_json.get('messages', [])
    if isinstance(msgs, dict):
        msgs = msgs.get('messages', [])
    return msgs if isinstance(msgs, list) else []


def _extract_actions(resp_json):
    """Normalize actions response - handles both list and dict shapes."""
    acts = resp_json.get('actions', [])
    if isinstance(acts, dict):
        acts = acts.get('actions', [])
    return acts if isinstance(acts, list) else []


def _print_msg(msg):
    """Safely print a protocol message regardless of its schema."""
    t = msg.get('time') or msg.get('ts') or '-'
    typ = msg.get('type') or msg.get('direction') or '-'
    svc = msg.get('service') or msg.get('serviceType') or msg.get('category') or '-'
    print(f"  [{t}] {typ}: {svc}")


def is_service_available(url, timeout=2):
    """Check if a service is available (quick check)."""
    try:
        r = requests.get(url, timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


def wait_for_service(url, timeout=30):
    """Wait for a service to be available."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                return True
        except Exception:
            time.sleep(1)
    raise RuntimeError(f"Service at {url} did not become available in {timeout} seconds.")


@pytest.mark.integration
@pytest.mark.skipif(
    not is_service_available(f"{FSP_BASE_URL}/iec61850server/status"),
    reason=f"FSP service not running on port {FSP_PORT}. Start with: docker run --rm -p 5001:5001 rti-demo-fsp"
)
def test_fsp_status_endpoint():
    """Integration test: Directly call FSP status endpoint."""
    response = requests.get(f"{FSP_BASE_URL}/iec61850server/status", timeout=10)
    assert response.status_code == 200
    data = response.json()
    assert "status" in data or "ok" in data
    print(f"FSP Response: {data}")


@pytest.mark.integration
@pytest.mark.skipif(
    not is_service_available(f"{BFF_BASE_URL}/health"),
    reason=f"BFF service not running on port {BFF_PORT}. Start with: docker compose up -d"
)
def test_bff_health_endpoint():
    """Integration test: Check if BFF health endpoint is working."""
    response = requests.get(f"{BFF_BASE_URL}/health", timeout=10)
    assert response.status_code == 200
    print(f"BFF Health Response: {response.json()}")


@pytest.mark.integration
@pytest.mark.skipif(
    not is_service_available(f"{BFF_BASE_URL}/health"),
    reason=f"BFF service not running on port {BFF_PORT}. Start with: docker compose up -d"
)
def test_bff_to_fsp_status():
    """Integration test: BFF proxies request to FSP and returns status."""
    response = requests.get(f"{BFF_BASE_URL}/iec61850server/status", timeout=10)

    if response.status_code == 502:
        pytest.skip(
            "BFF returned 502 (Bad Gateway). "
            "FSP is not reachable from BFF. "
            "Make sure both are started via 'docker compose up -d' on the same network."
        )

    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert "status" in data or "ok" in data
    print(f"BFF->FSP Response: {data}")


# A simple unit test that doesn't require Docker
def test_bff_endpoint_module_exists():
    """Basic unit test that doesn't require Docker services."""
    assert True


@pytest.mark.integration
def test_update_model_and_check_ied_name():
    # Path to your updated model file
    updated_model_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../fsp/updated_model.py'))
    with open(updated_model_path, 'r', encoding='utf-8') as f:
        model_py = f.read()

    # Get the initial IED name before update
    get_resp = requests.get(f"{BFF_BASE_URL}/model/tree")
    assert get_resp.status_code == 200
    model_info = get_resp.json()
    assert model_info['tree']['model']['iedName'] == 'simpleIO'

    # Update model via POST
    payload = {'modelPy': model_py}
    headers = {'Content-Type': 'application/json'}
    response = requests.post(f"{BFF_BASE_URL}/model/update", data=json.dumps(payload), headers=headers)
    assert response.status_code == 200
    resp_json = response.json()
    assert resp_json.get('ok') is True

    # Now check the IED name
    get_resp = requests.get(f"{BFF_BASE_URL}/model/tree")
    assert get_resp.status_code == 200
    model_info = get_resp.json()
    assert model_info['tree']['model']['iedName'] == 'simpleIO_updated'


@pytest.mark.integration
def test_server_start_stop_and_status():
    # Start the server with specific parameters
    payload = {
        'host': '127.0.0.1',
        'port': 1080,
        'mode': 'server',
        'cp': 'cp1'
    }
    print(f"Payload sent to BFF: {payload}")
    response = requests.post(f"{BFF_BASE_URL}/iec61850server/start", json=payload)
    if response.status_code != 200:
        print(f"Server returned {response.status_code}: {response.text}")
        print(f"Payload was: {payload}")
    assert response.status_code == 200
    resp_json = response.json()
    assert resp_json.get('ok') is True

    # Check server status
    status_resp = requests.get(f"{BFF_BASE_URL}/iec61850server/status")
    assert status_resp.status_code == 200
    status_info = status_resp.json()
    print(status_info)
    assert status_info.get('status') == 'listening'

    # Stop the server
    response = requests.post(f"{BFF_BASE_URL}/iec61850server/stop")
    assert response.status_code == 200
    resp_json = response.json()
    assert resp_json.get('ok') is True

    # Check server status to confirm it's stopped
    status_resp = requests.get(f"{BFF_BASE_URL}/iec61850server/status")
    assert status_resp.status_code == 200
    status_info = status_resp.json()
    print(status_info)
    assert status_info.get('status') in ('stopped', 'stopping')


@pytest.mark.integration
def test_server_actions():
    response = requests.get(f"{BFF_BASE_URL}/iec61850server/actions")
    assert response.status_code == 200
    actions_info = response.json()
    print(actions_info)
    assert 'actions' in actions_info
    assert isinstance(actions_info['actions'], list)


@pytest.mark.integration
def test_server_clear_action():
    response = requests.post(f"{BFF_BASE_URL}/iec61850server/actions/clear")
    assert response.status_code == 200
    resp_json = response.json()
    assert resp_json.get('ok') is True

    response = requests.get(f"{BFF_BASE_URL}/iec61850server/actions")
    assert response.status_code == 200
    actions_info = response.json()
    print(actions_info)
    assert 'actions' in actions_info
    print(actions_info['actions'])


@pytest.mark.integration
def test_server_get_protocol_messages():
    response = requests.get(f"{BFF_BASE_URL}/iec61850server/messages")
    assert response.status_code == 200
    messages_info = response.json()
    print(messages_info)
    assert 'messages' in messages_info
    assert isinstance(messages_info['messages']['messages'], list)


@pytest.mark.integration
def test_server_clear_protocol_messages():
    response = requests.post(f"{BFF_BASE_URL}/iec61850server/messages/clear")
    assert response.status_code == 200
    resp_json = response.json()
    assert resp_json.get('ok') is True

    response = requests.get(f"{BFF_BASE_URL}/iec61850server/messages")
    assert response.status_code == 200
    messages_info = response.json()
    print(messages_info)
    assert 'messages' in messages_info
    assert len(messages_info['messages']['messages']) == 0


@pytest.mark.integration
def test_read_write_value():
    # Start the server first
    start_payload = {'host': '127.0.0.1', 'port': 8765, 'mode': 'server', 'cp': 'cp1'}
    start_resp = requests.post(f"{BFF_BASE_URL}/iec61850server/start", json=start_payload)
    assert start_resp.status_code == 200, f"Server failed to start: {start_resp.text}"
    print(start_resp)

    # Wait until server is listening
    for _ in range(10):
        status_resp = requests.get(f"{BFF_BASE_URL}/iec61850server/status")
        if status_resp.json().get('status') == 'listening':
            break
        time.sleep(1)
    else:
        pytest.fail(f"Server did not reach 'listening' state: {status_resp.json()}")

    # Write a value
    payload = {
        'objRef': 'GenericIO/GGIO1.AnIn1.mag.f',
        'value': 42.0
    }
    response = requests.post(f"{BFF_BASE_URL}/iec61850server/writevalue", json=payload)
    assert response.status_code == 200, f"Write failed: {response.text}"
    resp_json = response.json()
    assert resp_json.get('ok') is True

    # Read the value back
    read_payload = {'objRef': 'GenericIO/GGIO1.AnIn1.mag.f'}
    read_response = requests.post(f"{BFF_BASE_URL}/iec61850server/readvalue", json=read_payload)
    assert read_response.status_code == 200, f"Read failed: {read_response.text}"
    read_resp_json = read_response.json()
    print(read_resp_json)
    assert read_resp_json.get('ok') is True
    values = read_resp_json.get('values', [])
    assert len(values) > 0
    assert values[0].get('value') == 42.0

    # Stop the server
    stop_resp = requests.post(f"{BFF_BASE_URL}/iec61850server/stop")
    assert stop_resp.status_code == 200, f"Server failed to stop: {stop_resp.text}"


@pytest.mark.integration
def test_so_status_from_bff():
    response = requests.get(f"{BFF_BASE_URL}/iec61850client/status")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert "status" in data or "ok" in data
    print(f"BFF->SO Response: {data}")

@pytest.mark.integration
def test_so_actions_from_bff():
    response = requests.get(f"{BFF_BASE_URL}/iec61850client/actions")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert "actions" in data
    print(f"BFF->SO Actions Response: {data}")

@pytest.mark.integration
def test_so_clear_actions_from_bff():
    response = requests.post(f"{BFF_BASE_URL}/iec61850client/actions/clear")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    resp_json = response.json()
    assert resp_json.get('ok') is True

    response = requests.get(f"{BFF_BASE_URL}/iec61850client/actions")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert "actions" in data
    print(f"BFF->SO Actions after clear: {data}")

@pytest.mark.integration
def test_so_protocol_messages_from_bff():
    response = requests.get(f"{BFF_BASE_URL}/iec61850client/messages")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert "messages" in data
    print(f"BFF->SO Messages Response: {data}")

@pytest.mark.integration
def test_so_clear_protocol_messages_from_bff():
    response = requests.post(f"{BFF_BASE_URL}/iec61850client/messages/clear")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    resp_json = response.json()
    assert resp_json.get('ok') is True

    response = requests.get(f"{BFF_BASE_URL}/iec61850client/messages")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert "messages" in data
    assert len(data['messages']['messages']) == 0
    print(f"BFF->SO Messages after clear: {data}")

@pytest.mark.integration
def test_so_connections_from_bff():
    response = requests.get(f"{BFF_BASE_URL}/iec61850client/connections")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert "connections" in data
    print(f"BFF->SO Connections Response: {data}")

import time

def wait_for_connected_status(timeout=10):
    """Polls the status endpoint until status is 'connected' or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = requests.get(f"{BFF_BASE_URL}/iec61850client/status")
        assert resp.status_code == 200
        status = resp.json()['status']
        if status == 'connected':
            return True
        time.sleep(0.5)
    raise RuntimeError("Timed out waiting for 'connected' status")


@pytest.mark.integration
def test_so_connect_and_disconnect_from_bff():
    connect_payload = {
        'host': '127.0.0.1',
        'port': 8765,
        'cp': 'cp1'
    }
    connect_response = requests.post(f"{BFF_BASE_URL}/iec61850client/connect", json=connect_payload)
    assert connect_response.status_code == 200, f"Connect failed: {connect_response.text}"
    connect_resp_json = connect_response.json()
    assert connect_resp_json.get('ok') is True
    print(connect_resp_json)
    assert connect_resp_json['result']['status'] in ('connected', 'connecting')

    disconnect_response = requests.post(f"{BFF_BASE_URL}/iec61850client/disconnect")
    assert disconnect_response.status_code == 200, f"Disconnect failed: {disconnect_response.text}"
    disconnect_resp_json = disconnect_response.json()
    assert disconnect_resp_json.get('ok') is True

    # Check status to confirm disconnected
    status_resp = requests.get(f"{BFF_BASE_URL}/iec61850client/status")
    assert status_resp.status_code == 200, f"Status check failed: {status_resp.text}"
    status_info = status_resp.json()
    print(status_info)
    assert status_info['status']['status'] in ('disconnected', 'disconnecting')

@pytest.mark.integration
def test_so_connect_to_fsp_and_check_status():
    """
    Test FSP server-mode connection to SO (passive) listening.
    Flow: SO listens -> FSP connects to SO -> verify connected -> disconnect
    """
    print("\n" + "="*70)
    print("TEST: SO connects to FSP over WebSocket")
    print("="*70)

    # Start SO listening on port 1080
    so_listen_payload = {
        'host': '0.0.0.0',
        'port': 1080,
        'cp': 'cp1'
    }
    print(f"\n[1] Starting SO to listen on port 1080...")
    so_start_resp = requests.post(f"{BFF_BASE_URL}/iec61850client/connect", json=so_listen_payload)
    assert so_start_resp.status_code == 200, f"SO listen failed: {so_start_resp.text}"
    assert so_start_resp.json().get('ok') is True
    print("✓ SO is now listening")

    # Print SO actions after starting to listen
    print("\n[SO Actions after starting to listen]")
    so_actions_resp = requests.get(f"{BFF_BASE_URL}/iec61850client/actions")
    if so_actions_resp.status_code == 200:
        so_actions = _extract_actions(so_actions_resp.json())
        for action in so_actions[-5:]:
            print(f"  [{action.get('time','-')}] {action.get('level','-')}: {action.get('message','-')}")

    # Print SO messages after starting to listen
    print("\n[SO Messages after starting to listen]")
    so_msgs_resp = requests.get(f"{BFF_BASE_URL}/iec61850client/messages")
    if so_msgs_resp.status_code == 200:
        so_msgs = _extract_messages(so_msgs_resp.json())
        for msg in so_msgs[-5:]:
            _print_msg(msg)

    # Give SO time to start listening
    time.sleep(1)

    # Start FSP server to connect to SO
    # Note: host='rti-client' resolves to the SO container inside docker network
    fsp_connect_payload = {
        'host': 'rti-client',  # SO hostname in docker network
        'port': 1080,          # SO's listening port
        'mode': 'server',
        'cp': 'cp1'
    }
    print(f"\n[2] Starting FSP to connect to SO at rti-client:1080...")
    fsp_start_resp = requests.post(f"{BFF_BASE_URL}/iec61850server/start", json=fsp_connect_payload)
    assert fsp_start_resp.status_code == 200, f"FSP connect failed: {fsp_start_resp.text}"
    assert fsp_start_resp.json().get('ok') is True
    print("✓ FSP started, attempting connection...")

    # Print FSP actions after start
    print("\n[FSP Actions after start]")
    fsp_actions_resp = requests.get(f"{BFF_BASE_URL}/iec61850server/actions")
    if fsp_actions_resp.status_code == 200:
        fsp_actions = _extract_actions(fsp_actions_resp.json())
        for action in fsp_actions[-5:]:
            print(f"  [{action.get('time','-')}] {action.get('level','-')}: {action.get('message','-')}")

    # Wait for FSP to reach 'listening' or 'connected' state
    print("\n[3] Waiting for FSP to establish connection...")
    deadline = time.time() + 15
    fsp_status = None
    while time.time() < deadline:
        status_resp = requests.get(f"{BFF_BASE_URL}/iec61850server/status")
        assert status_resp.status_code == 200
        fsp_status = status_resp.json().get('status')
        print(f"  FSP status: {fsp_status}")
        if fsp_status in ('listening', 'connected', 'ready'):
            break
        time.sleep(0.5)
    assert fsp_status in ('listening', 'connected', 'ready'), \
        f"FSP did not reach connected state. Last status: {fsp_status}"

    # Wait for SO to report 'connected' state
    print("\n[4] Waiting for SO to report connection...")
    deadline = time.time() + 15
    so_status_str = None
    while time.time() < deadline:
        status_resp = requests.get(f"{BFF_BASE_URL}/iec61850client/status")
        assert status_resp.status_code == 200
        so_status = status_resp.json().get('status')
        # BFF wraps SO status as a dict; FSP returns a flat string
        if isinstance(so_status, dict):
            so_status_str = so_status.get('status')
        else:
            so_status_str = so_status
        print(f"  SO status: {so_status_str}")
        if so_status_str in ('connected', 'associated', 'ready'):
            break
        time.sleep(0.5)
    assert so_status_str in ('connected', 'associated', 'ready'), \
        f"SO did not reach connected state. Last status: {so_status_str}"

    print("\n✓ Both FSP and SO are connected")

    # Print messages during connection
    print("\n[FSP Protocol Messages during connection]")
    fsp_msgs_resp = requests.get(f"{BFF_BASE_URL}/iec61850server/messages")
    if fsp_msgs_resp.status_code == 200:
        fsp_msgs = _extract_messages(fsp_msgs_resp.json())
        for msg in fsp_msgs[-10:]:
            _print_msg(msg)

    print("\n[SO Protocol Messages during connection]")
    so_msgs_resp = requests.get(f"{BFF_BASE_URL}/iec61850client/messages")
    if so_msgs_resp.status_code == 200:
        so_msgs = _extract_messages(so_msgs_resp.json())
        for msg in so_msgs[-10:]:
            _print_msg(msg)

    # Print final actions
    print("\n[FSP Actions during connection]")
    fsp_actions_resp = requests.get(f"{BFF_BASE_URL}/iec61850server/actions")
    if fsp_actions_resp.status_code == 200:
        fsp_actions = _extract_actions(fsp_actions_resp.json())
        for action in fsp_actions[-10:]:
            print(f"  [{action.get('time','-')}] {action.get('level','-')}: {action.get('message','-')}")

    print("\n[SO Actions during connection]")
    so_actions_resp = requests.get(f"{BFF_BASE_URL}/iec61850client/actions")
    if so_actions_resp.status_code == 200:
        so_actions = _extract_actions(so_actions_resp.json())
        for action in so_actions[-10:]:
            print(f"  [{action.get('time','-')}] {action.get('level','-')}: {action.get('message','-')}")

    # Disconnect FSP
    print("\n[5] Disconnecting FSP...")
    fsp_stop_resp = requests.post(f"{BFF_BASE_URL}/iec61850server/stop")
    assert fsp_stop_resp.status_code == 200, f"FSP stop failed: {fsp_stop_resp.text}"
    assert fsp_stop_resp.json().get('ok') is True

    # Disconnect SO
    print("[6] Disconnecting SO...")
    so_disconnect_resp = requests.post(f"{BFF_BASE_URL}/iec61850client/disconnect")
    assert so_disconnect_resp.status_code == 200, f"SO disconnect failed: {so_disconnect_resp.text}"
    assert so_disconnect_resp.json().get('ok') is True

    print("\n✓ Test completed successfully")
    print("="*70)


@pytest.mark.integration
def test_so_read_write_value_via_bff():
    """
    End-to-end read/write through BFF -> SO -> WebSocket -> FSP -> WebSocket -> SO -> BFF.
    Flow:
      1. SO listens on port 1080 (via BFF)
      2. FSP connects to SO over WebSocket (via BFF)
      3. SO writes a value to FSP over the live WebSocket (via BFF)
      4. SO reads the value back from FSP over the live WebSocket (via BFF)
      5. Verify the value matches what was written
      6. Cleanup
    All HTTP calls go through the BFF (port 5000).
    """
    print("\n" + "="*70)
    print("TEST: Read/Write via BFF -> SO -> WebSocket -> FSP")
    print("="*70)

    obj_ref = "GenericIO/GGIO1.AnIn1.mag.f"
    fc = "mx"
    write_value = 93.58

    # Cleanup any prior state
    try:
        requests.post(f"{BFF_BASE_URL}/iec61850client/disconnect", timeout=5)
    except Exception:
        pass
    try:
        requests.post(f"{BFF_BASE_URL}/iec61850server/stop", timeout=5)
    except Exception:
        pass
    time.sleep(1)

    # [1] Start SO listening on port 1080
    print("\n[1] Starting SO to listen on port 1080 (via BFF)...")
    so_listen_payload = {'host': '0.0.0.0', 'port': 1080, 'cp': 'cp1'}
    so_start_resp = requests.post(f"{BFF_BASE_URL}/iec61850client/connect", json=so_listen_payload)
    assert so_start_resp.status_code == 200, f"SO listen failed: {so_start_resp.text}"
    assert so_start_resp.json().get('ok') is True
    print("✓ SO is now listening")

    time.sleep(1)

    # [2] Start FSP to connect to SO
    print("\n[2] Starting FSP to connect to SO at rti-client:1080 (via BFF)...")
    fsp_payload = {'host': 'rti-client', 'port': 1080, 'mode': 'server', 'cp': 'cp1'}
    fsp_start_resp = requests.post(f"{BFF_BASE_URL}/iec61850server/start", json=fsp_payload)
    assert fsp_start_resp.status_code == 200, f"FSP start failed: {fsp_start_resp.text}"
    assert fsp_start_resp.json().get('ok') is True
    print("✓ FSP started")

    # [3] Wait for SO to report connected
    print("\n[3] Waiting for SO to reach 'connected' state...")
    deadline = time.time() + 20
    so_status_str = None
    while time.time() < deadline:
        status_resp = requests.get(f"{BFF_BASE_URL}/iec61850client/status")
        assert status_resp.status_code == 200
        so_status = status_resp.json().get('status')
        so_status_str = so_status.get('status') if isinstance(so_status, dict) else so_status
        print(f"  SO status: {so_status_str}")
        if so_status_str in ('connected', 'associated', 'ready'):
            break
        time.sleep(0.5)
    assert so_status_str in ('connected', 'associated', 'ready'), \
        f"SO did not reach connected state. Last: {so_status_str}"
    print("✓ SO connected to FSP over WebSocket")

    # [4] SO writes a value to FSP via BFF -> SO -> WebSocket -> FSP
    print(f"\n[4] Writing value {write_value} to {obj_ref} (BFF -> SO -> WS -> FSP)...")
    write_payload = {
        'objRef': obj_ref,
        'fc': fc,
        'value': write_value,
        'dataType': 'float32',  # BFF reads 'dataType' and forwards as 'value_type' to SO
    }
    write_resp = requests.post(
        f"{BFF_BASE_URL}/iec61850client/writevalue",
        json=write_payload,
        timeout=15,
    )
    if write_resp.status_code != 200:
        print(f"  ✗ Write failed. Status={write_resp.status_code}")
        try:
            print(f"  BFF error body: {json.dumps(write_resp.json(), indent=2)}")
        except Exception:
            print(f"  BFF error body (raw): {write_resp.text}")
    assert write_resp.status_code == 200, f"Write failed: {write_resp.text}"
    write_json = write_resp.json()
    print(f"  Write response: {write_json}")
    assert write_json.get('ok') is True, f"Write not ok: {write_json}"
    print("✓ Value written successfully")

    time.sleep(0.5)

    # [5] SO reads the value back via BFF -> SO -> WebSocket -> FSP
    print(f"\n[5] Reading value back from {obj_ref} (BFF -> SO -> WS -> FSP)...")
    read_payload = {'objRef': obj_ref, 'fc': fc}
    read_resp = requests.post(
        f"{BFF_BASE_URL}/iec61850client/readvalue",
        json=read_payload,
        timeout=15,
    )
    assert read_resp.status_code == 200, f"Read failed: {read_resp.text}"
    read_json = read_resp.json()
    print(f"  Read response: {read_json}")
    assert read_json.get('ok') is True, f"Read not ok: {read_json}"

    def _unwrap_value(v):
        """Recursively unwrap common ACSI value shapes to a scalar.
        Handles e.g. [{'data': ['float32', 77.5]}], {'data': ['float32', 77.5]},
        ['float32', 77.5], or a raw scalar.
        """
        # List: take first element and recurse
        if isinstance(v, list):
            if not v:
                return None
            # Type-tagged tuple/list: [type_str, scalar]
            if len(v) == 2 and isinstance(v[0], str):
                return _unwrap_value(v[1])
            return _unwrap_value(v[0])
        # Dict: try common keys
        if isinstance(v, dict):
            for key in ('value', 'data', 'val'):
                if key in v:
                    return _unwrap_value(v[key])
            return None
        return v

    # Extract value (try several common shapes)
    raw_value = None
    if 'value' in read_json:
        raw_value = read_json['value']
    elif 'values' in read_json and read_json['values']:
        raw_value = read_json['values']
    elif 'result' in read_json and isinstance(read_json['result'], dict):
        res = read_json['result']
        if 'value' in res:
            raw_value = res['value']
        elif 'values' in res and res['values']:
            raw_value = res['values']

    read_value = _unwrap_value(raw_value)

    assert read_value is not None, f"Could not extract value from read response: {read_json}"
    print(f"  Read value: {read_value}")
    assert float(read_value) == pytest.approx(write_value), \
        f"Read value {read_value} does not match written value {write_value}"
    print(f"✓ Value matches: written={write_value}, read={read_value}")

    # [6] Print SO protocol messages to confirm WebSocket traffic
    print("\n[6] SO Protocol Messages (last 10) — confirms WebSocket traffic:")
    so_msgs_resp = requests.get(f"{BFF_BASE_URL}/iec61850client/messages")
    if so_msgs_resp.status_code == 200:
        so_msgs = _extract_messages(so_msgs_resp.json())
        for msg in so_msgs[-10:]:
            _print_msg(msg)

    print("\n[FSP Protocol Messages (last 10)]")
    fsp_msgs_resp = requests.get(f"{BFF_BASE_URL}/iec61850server/messages")
    if fsp_msgs_resp.status_code == 200:
        fsp_msgs = _extract_messages(fsp_msgs_resp.json())
        for msg in fsp_msgs[-10:]:
            _print_msg(msg)

    # [7] Cleanup
    print("\n[7] Cleanup: stop FSP and disconnect SO...")
    requests.post(f"{BFF_BASE_URL}/iec61850server/stop", timeout=5)
    requests.post(f"{BFF_BASE_URL}/iec61850client/disconnect", timeout=5)

    print("\n✓ Test completed successfully")
    print("="*70)

@pytest.mark.integration
def test_server_properties_bff():
    response = requests.get(f"{BFF_BASE_URL}/iec61850server/properties")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert "properties" in data
    print(f"BFF->Server Properties Response: {data}")

@pytest.mark.integration
def test_client_properties_bff():
    response = requests.get(f"{BFF_BASE_URL}/iec61850client/properties")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert "properties" in data
    print(f"BFF->Client Properties Response: {data}")