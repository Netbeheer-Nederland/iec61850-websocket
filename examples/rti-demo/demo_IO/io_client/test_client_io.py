#!/usr/bin/env python3
"""Test script for client_io and io_router functionality.

This script tests:
1. DemoIOClient direct usage
2. IO router endpoints (requires FastAPI test client)
"""

import asyncio
import os
import sys

# Add the acsi directory to the path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_demo_io_client():
    """Test the DemoIOClient class."""
    print("=" * 60)
    print("Testing DemoIOClient")
    print("=" * 60)
    
    from .client_io import DemoIOClient
    
    # Test client creation
    client = DemoIOClient(base_url="http://localhost:8080")
    print(f"[OK] Client created with base URL: {client.base_url}")
    print(f"[OK] IO base URL: {client.io_base}")
    
    # Test that methods exist
    assert hasattr(client, 'health_check'), "Missing health_check method"
    assert hasattr(client, 'is_healthy'), "Missing is_healthy method"
    assert hasattr(client, 'get_status'), "Missing get_status method"
    assert hasattr(client, 'config_led'), "Missing config_led method"
    assert hasattr(client, 'list_leds'), "Missing list_leds method"
    assert hasattr(client, 'get_led_state'), "Missing get_led_state method"
    assert hasattr(client, 'set_led'), "Missing set_led method"
    assert hasattr(client, 'toggle_led'), "Missing toggle_led method"
    assert hasattr(client, 'set_all_leds'), "Missing set_all_leds method"
    assert hasattr(client, 'all_leds_on'), "Missing all_leds_on method"
    assert hasattr(client, 'all_leds_off'), "Missing all_leds_off method"
    assert hasattr(client, 'initialize'), "Missing initialize method"
    assert hasattr(client, 'cleanup'), "Missing cleanup method"
    print("[OK] All required methods exist")
    
    # Test convenience methods
    assert hasattr(client, 'turn_on'), "Missing turn_on method"
    assert hasattr(client, 'turn_off'), "Missing turn_off method"
    assert hasattr(client, 'add_led'), "Missing add_led method"
    assert hasattr(client, 'get_all_states'), "Missing get_all_states method"
    assert hasattr(client, 'create_led'), "Missing create_led method"
    print("[OK] All convenience methods exist")
    
    # Note: We can't test actual HTTP calls without a running demo_IO service
    print("[OK] DemoIOClient tests passed (structural only)")
    return True


def test_io_router_imports():
    """Test that the io_router can be imported."""
    print("\n" + "=" * 60)
    print("Testing IO Router Imports")
    print("=" * 60)
    
    try:
        from .io_router import create_io_router, get_io_client, set_io_client
        print("[OK] IO router module imports successfully")
        
        # Test router creation
        router = create_io_router()
        print(f"[OK] Router created: {router}")
        print(f"[OK] Router prefix: {router.prefix}")
        print(f"[OK] Router tags: {router.tags}")
        
        return True
    except Exception as e:
        print(f"✗ Failed to import or create io_router: {e}")
        return False


async def test_io_router_endpoints():
    """Test IO router endpoints using FastAPI test client."""
    print("\n" + "=" * 60)
    print("Testing IO Router Endpoints")
    print("=" * 60)
    
    try:
        from fastapi.testclient import TestClient
        from bff_endpoint import create_fastapi_app
        
        # Create app with io_router
        app = create_fastapi_app()
        client = TestClient(app)
        
        # Test connection status endpoint (should show not connected initially)
        response = client.get("/api/io/connection")
        print(f"[OK] GET /api/io/connection - Status: {response.status_code}")
        data = response.json()
        print(f"  Response: {data}")
        assert response.status_code == 200
        assert data["connected"] == False
        
        # Test health endpoint (should fail without connection)
        response = client.get("/api/io/health")
        print(f"[OK] GET /api/io/health - Status: {response.status_code}")
        if response.status_code == 500:
            print("  Expected 500 error without demo_IO connection")
        
        # Test connect endpoint with non-existent service
        response = client.post("/api/io/connect", json={"base_url": "http://nonexistent:9999"})
        print(f"[OK] POST /api/io/connect (bad URL) - Status: {response.status_code}")
        assert response.status_code == 400
        
        # Test LED endpoints without connection (should fail)
        response = client.get("/api/io/leds")
        print(f"[OK] GET /api/io/leds - Status: {response.status_code} (expected 500)")
        
        response = client.post("/api/io/leds/led1/set", json={"state": True})
        print(f"[OK] POST /api/io/leds/led1/set - Status: {response.status_code} (expected 500)")
        
        print("[OK] IO router endpoint tests passed (structural only)")
        return True
        
    except Exception as e:
        print(f"[FAIL] Failed to test io_router endpoints: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("Running client_io and io_router tests...\n")
    
    results = []
    
    # Test DemoIOClient
    results.append(("DemoIOClient", test_demo_io_client()))
    
    # Test IO router imports
    results.append(("IO Router Imports", test_io_router_imports()))
    
    # Test IO router endpoints
    results.append(("IO Router Endpoints", asyncio.run(test_io_router_endpoints())))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    for name, passed in results:
        status = "[OK] PASSED" if passed else "[FAIL] FAILED"
        print(f"{name:30} {status}")
    
    all_passed = all(passed for _, passed in results)
    print("=" * 60)
    if all_passed:
        print("All tests passed!")
        return 0
    else:
        print("Some tests failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
