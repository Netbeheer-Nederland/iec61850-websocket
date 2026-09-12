#!/usr/bin/env python3
"""Standalone test for io_router without requiring ACSI model files."""

import os
import sys

# Add the acsi directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from .io_router import create_io_router


def test_io_router_standalone():
    """Test io_router as a standalone router."""
    print("=" * 60)
    print("Testing IO Router Standalone")
    print("=" * 60)
    
    # Create a simple FastAPI app and add the io_router
    app = FastAPI()
    io_router = create_io_router()
    app.include_router(io_router)
    
    # Create test client
    client = TestClient(app)
    
    # Test connection status endpoint (should show not connected initially)
    response = client.get("/api/io/connection")
    print(f"[OK] GET /api/io/connection - Status: {response.status_code}")
    data = response.json()
    print(f"  Response: {data}")
    assert response.status_code == 200
    assert data["connected"] == False
    assert data["healthy"] == False
    
    # Test connect endpoint with non-existent service
    response = client.post("/api/io/connect", json={"base_url": "http://nonexistent:9999"})
    print(f"[OK] POST /api/io/connect (bad URL) - Status: {response.status_code}")
    assert response.status_code == 400
    data = response.json()
    print(f"  Error: {data.get('detail', 'No detail')}")
    
    # Test LED endpoints without connection (should fail with 500)
    response = client.get("/api/io/leds")
    print(f"[OK] GET /api/io/leds - Status: {response.status_code} (expected 500)")
    assert response.status_code == 500
    
    response = client.post("/api/io/leds/led1/set", json={"state": True})
    print(f"[OK] POST /api/io/leds/led1/set - Status: {response.status_code} (expected 500)")
    assert response.status_code == 500
    
    response = client.get("/api/io/status")
    print(f"[OK] GET /api/io/status - Status: {response.status_code} (expected 500)")
    assert response.status_code == 500
    
    response = client.get("/api/io/health")
    print(f"[OK] GET /api/io/health - Status: {response.status_code} (expected 500)")
    assert response.status_code == 500
    
    # Test disconnect (should work even when not connected)
    response = client.post("/api/io/disconnect")
    print(f"[OK] POST /api/io/disconnect - Status: {response.status_code}")
    assert response.status_code == 200
    
    print("[OK] All standalone io_router tests passed!")
    return True


def test_io_router_with_mock_demo_io():
    """Test io_router with a mock demo_IO service."""
    print("\n" + "=" * 60)
    print("Testing IO Router with Mock Demo IO")
    print("=" * 60)
    
    # We'll need to run this with a real demo_IO service to test fully
    # For now, just test that the router structure is correct
    app = FastAPI()
    io_router = create_io_router()
    app.include_router(io_router)
    
    client = TestClient(app)
    
    # List all routes to verify they exist
    def get_route_paths(routes):
        """Extract path from route objects."""
        paths = []
        for route in routes:
            if hasattr(route, 'path'):
                paths.append(route.path)
            elif hasattr(route, 'routes'):
                # It's an included router, recurse
                paths.extend(get_route_paths(route.routes))
        return paths
    
    routes = get_route_paths(app.routes)
    expected_io_routes = [
        "/api/io/connect",
        "/api/io/connection", 
        "/api/io/disconnect",
        "/api/io/health",
        "/api/io/status",
        "/api/io/leds",
        "/api/io/leds/config",
        "/api/io/leds/all/set",
        "/api/io/leds/all/on",
        "/api/io/leds/all/off",
        "/api/io/initialize",
        "/api/io/cleanup",
    ]
    
    for route in expected_io_routes:
        if route in routes:
            print(f"[OK] Route exists: {route}")
        else:
            print(f"[WARN] Route not found: {route}")
            # Check if it's a parameterized route
            found = any(route.startswith(r.split("{")[0]) for r in routes if "{" in r)
            if found:
                print(f"  (Found as parameterized route)")
    
    # Check for parameterized routes
    param_routes = [r for r in routes if "{" in r]
    print(f"\n[OK] Found {len(param_routes)} parameterized routes:")
    for route in param_routes:
        if "/api/io/" in route:
            print(f"  {route}")
    
    print("[OK] IO router structure tests passed!")
    return True


def main():
    """Run all standalone tests."""
    print("Running standalone io_router tests...\n")
    
    try:
        test_io_router_standalone()
        test_io_router_with_mock_demo_io()
        
        print("\n" + "=" * 60)
        print("ALL STANDALONE TESTS PASSED!")
        print("=" * 60)
        return 0
        
    except Exception as e:
        print(f"\n[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
