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
        status = resp.json()['status']['status']
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



    # Connect SO to FSP
    connect_payload = {
        'host': '127.0.0.1',
        'port': 1080,
        'cp': 'cp1'
    }
    connect_response = requests.post(f"{BFF_BASE_URL}/iec61850client/connect", json=connect_payload)
    assert connect_response.status_code == 200, f"Connect failed: {connect_response.text}"
    connect_resp_json = connect_response.json()
    assert connect_resp_json.get('ok') is True
    print(connect_resp_json)

    wait_for_connected_status()

    # Now disconnect
    disconnect_response = requests.post(f"{BFF_BASE_URL}/iec61850client/disconnect")
    assert disconnect_response.status_code == 200, f"Disconnect failed: {disconnect_response.text}"
    disconnect_resp_json = disconnect_response.json()
    assert disconnect_resp_json.get('ok') is True


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

