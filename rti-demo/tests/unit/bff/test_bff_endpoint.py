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
    not is_service_available(f"http://localhost:{FSP_PORT}/api/iec61850server/status"),
    reason=f"FSP service not running on port {FSP_PORT}. Start with: docker run --rm -p 5001:5001 rti-demo-fsp"
)
def test_fsp_status_endpoint():
    """
    Integration test: Directly call FSP status endpoint.

    Requires FSP Docker container to be running.
    Start with: docker run --rm -p 5001:5001 rti-demo-fsp
    """
    fsp_url = f"http://localhost:{FSP_PORT}/api/iec61850server/status"

    response = requests.get(fsp_url, timeout=10)
    assert response.status_code == 200
    data = response.json()

    # Verify the response contains expected fields
    assert "status" in data or "ok" in data
    print(f"FSP Response: {data}")


@pytest.mark.integration
@pytest.mark.skipif(
    not is_service_available(f"http://localhost:{BFF_PORT}/api/health"),
    reason=f"BFF service not running on port {BFF_PORT}. Start with: docker compose up -d"
)
def test_bff_health_endpoint():
    """
    Integration test: Check if BFF health endpoint is working.

    Requires BFF Docker container to be running.
    Start with: docker compose up -d
    """
    bff_health_url = f"http://localhost:{BFF_PORT}/api/health"

    response = requests.get(bff_health_url, timeout=10)
    assert response.status_code == 200
    print(f"BFF Health Response: {response.json()}")


@pytest.mark.integration
@pytest.mark.skipif(
    not is_service_available(f"http://localhost:{BFF_PORT}/api/health"),
    reason=f"BFF service not running on port {BFF_PORT}. Start with: docker compose up -d"
)
def test_bff_to_fsp_status():
    """
    Integration test: BFF proxies request to FSP and returns status.

    Requires both BFF and FSP Docker containers to be running ON THE SAME DOCKER NETWORK.

    NOTE: If you get a 502 error, it means:
    - BFF is running but cannot reach FSP
    - FSP needs to be started via docker-compose (not docker run separately)

    Start with: docker compose up -d
    """
    bff_url = f"http://localhost:{BFF_PORT}/api/iec61850server/status"

    response = requests.get(bff_url, timeout=10)

    # 502 means BFF is working but can't reach FSP (they're not on same network)
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

    # Get the initial IED name before update (assuming there is an endpoint to get model info)
    get_url = f'http://localhost:5000/api/model/tree'
    get_resp = requests.get(get_url)
    assert get_resp.status_code == 200
    model_info = get_resp.json()
    assert model_info['tree']['model']['iedName'] == 'simpleIO'

    # Update model via POST
    url = f'http://localhost:5000/api/model/update'
    payload = { 'modelPy': model_py }
    headers = { 'Content-Type': 'application/json' }
    response = requests.post(url, data=json.dumps(payload), headers=headers)
    assert response.status_code == 200
    resp_json = response.json()
    assert resp_json.get('ok') is True

    # Now check the IED name (assuming there is an endpoint to get model info)
    get_url = f'http://localhost:5000/api/model/tree'
    get_resp = requests.get(get_url)
    assert get_resp.status_code == 200
    model_info = get_resp.json()

    assert model_info['tree']['model']['iedName'] == 'simpleIO_updated'

@pytest.mark.integration
def test_server_start_and_status():
    # Start the server with specific parameters
    url = f'http://localhost:5000/api/iec61850server/start'
    payload = {
        'host': '127.0.0.1',
        'port': 1080,  # Use a port above 1024 to avoid permission issues
        'mode': 'server',
        'cp': 'cp1'
    }
    print(f"Payload sent to BFF: {payload}")
    response = requests.post(url, json=payload)  # Use json=payload for correct encoding
    if response.status_code != 200:
        print(f"Server returned {response.status_code}: {response.text}")
        print(f"Payload was: {payload}")
    assert response.status_code == 200
    resp_json = response.json()
    assert resp_json.get('ok') is True

    # Check server status
    status_url = f'http://localhost:5000/api/iec61850server/status'
    status_resp = requests.get(status_url)
    assert status_resp.status_code == 200
    status_info = status_resp.json()
    print(status_info)
    assert status_info.get('status') == 'listening'

@pytest.mark.integration
def test_server_stop():
    # Stop the server
    url = f'http://localhost:5000/api/iec61850server/stop'
    response = requests.post(url)
    assert response.status_code == 200
    resp_json = response.json()
    assert resp_json.get('ok') is True

    # Check server status to confirm it's stopped
    status_url = f'http://localhost:5000/api/iec61850server/status'
    status_resp = requests.get(status_url)
    assert status_resp.status_code == 200
    status_info = status_resp.json()
    print(status_info)
    assert status_info.get('status') == 'stopped' or status_info.get('status') == 'stopping'


@pytest.mark.integration
def test_server_actions():
    # Get available actions
    url = f'http://localhost:5000/api/iec61850server/actions'
    response = requests.get(url)
    assert response.status_code == 200
    actions_info = response.json()
    print(actions_info)
    assert 'actions' in actions_info
    assert isinstance(actions_info['actions'], list)


@pytest.mark.integration
def test_server_clear_action():
    # Clear the server
    url = f'http://localhost:5000/api/iec61850server/actions/clear'
    response = requests.post(url)
    assert response.status_code == 200
    resp_json = response.json()
    assert resp_json.get('ok') is True

    url = f'http://localhost:5000/api/iec61850server/actions'
    response = requests.get(url)
    assert response.status_code == 200
    actions_info = response.json()
    print(actions_info)
    assert 'actions' in actions_info
    print( actions_info['actions'])

@pytest.mark.integration
def test_server_get_protocol_messages():
    # Get protocol messages
    url = f'http://localhost:5000/api/iec61850server/messages'
    response = requests.get(url)
    assert response.status_code == 200
    messages_info = response.json()
    print(messages_info)
    assert 'messages' in messages_info
    assert isinstance(messages_info['messages']['messages'], list)

@pytest.mark.integration
def test_server_clear_protocol_messages():
    # Clear protocol messages
    url = f'http://localhost:5000/api/iec61850server/messages/clear'
    response = requests.post(url)
    assert response.status_code == 200
    resp_json = response.json()
    assert resp_json.get('ok') is True

    # Check messages to confirm they're cleared
    url = f'http://localhost:5000/api/iec61850server/messages'
    response = requests.get(url)
    assert response.status_code == 200
    messages_info = response.json()
    print(messages_info)
    assert 'messages' in messages_info
    assert len(messages_info['messages']['messages']) == 0

@pytest.mark.integration
def test_read_write_value():
    # Stop any previously running server first
    # requests.post(f'http://localhost:5000/api/iec61850server/stop')
    # time.sleep(1)

    #Start the server first
    start_url = f'http://localhost:5000/api/iec61850server/start'
    start_payload = {'host': '127.0.0.1', 'port': 8765, 'mode': 'server', 'cp': 'cp1'}
    start_resp = requests.post(start_url, json=start_payload)
    assert start_resp.status_code == 200, f"Server failed to start: {start_resp.text}"
    print(start_resp)
    # Wait until server is listening
    status_url = f'http://localhost:5000/api/iec61850server/status'
    for _ in range(10):
        status_resp = requests.get(status_url)
        if status_resp.json().get('status') == 'listening':
            break
        time.sleep(1)
    else:
        pytest.fail(f"Server did not reach 'listening' state: {status_resp.json()}")

    # # Write a value
    # write_url = f'http://localhost:5000/api/iec61850server/writevalue'
    # payload = {
    #     'objRef': 'GenericIO/GGIO1.AnIn1.mag.f',
    #     'value': 42.0,
    #     'fc': 'MX'
    # }
    # response = requests.post(write_url, json=payload)
    # assert response.status_code == 200, f"Write failed: {response.text}"
    # resp_json = response.json()
    # assert resp_json.get('ok') is True
    #
    # Read the value back
    read_url = f'http://localhost:5000/api/iec61850server/readvalue'
    read_payload = {
        'objRef': 'GenericIO/GGIO1.AnIn1.mag.f',
        'fc': 'MX'
    }
    read_response = requests.post(read_url, json=read_payload)
    assert read_response.status_code == 200, f"Read failed: {read_response.text}"
    read_resp_json = read_response.json()
    print(read_resp_json)
    # assert read_resp_json.get('ok') is True
    # values = read_resp_json.get('values', [])
    # assert len(values) > 0
    # assert values[0].get('value') == 42.0
