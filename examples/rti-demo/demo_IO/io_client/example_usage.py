#!/usr/bin/env python3
"""
Example usage of async_client_io and io_router for connecting ACSI to demo_IO.

This example demonstrates how to:
1. Use DemoIOClient directly to control LEDs from ACSI
2. Use the IO router to expose LED control endpoints through ACSI's BFF
3. Connect ACSI to demo_IO for integrated LED control
"""

import os
import sys
import time

# Add the acsi directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def example_direct_client_usage():
    """Example 1: Using DemoIOClient directly from ACSI code."""
    print("=" * 70)
    print("Example 1: Direct DemoIOClient Usage")
    print("=" * 70)
    
    from .async_client_io import DemoIOClient
    
    # Create client pointing to demo_IO service
    # demo_IO typically runs on port 8080
    client = DemoIOClient(base_url="http://localhost:8080")
    
    print("Connecting to demo_IO service...")
    
    # Check if service is healthy
    try:
        health = client.health_check()
        print(f"demo_IO health: {health}")
        
        # Get current status
        status = client.get_status()
        print(f"GPIO status: {status}")
        
        # Configure a new LED (if not already configured)
        print("\nConfiguring LED...")
        result = client.config_led(
            name="my_led",
            gpio_pin=17,
            description="LED controlled from FSP",
            initial_state=False
        )
        print(f"LED configuration result: {result}")
        
        # Turn device on
        print("\nTurning device ON...")
        result = client.set_device("my_led", state=True)
        print(f"Set device result: {result}")
        
        # Get LED state
        print("\nGetting LED state...")
        state = client.get_led_state("my_led")
        print(f"LED state: {state}")
        
        # Toggle LED
        print("\nToggling LED...")
        result = client.toggle_led("my_led")
        print(f"Toggle result: {result}")
        
        # Turn LED off
        print("\nTurning LED OFF...")
        result = client.turn_off("my_led")
        print(f"Turn off result: {result}")
        
        # Use convenience methods
        print("\nUsing convenience methods...")
        client.turn_on("my_led")
        print("LED turned on using turn_on()")
        
        client.turn_off("my_led")
        print("LED turned off using turn_off()")
        
        # List all LEDs
        print("\nListing all LEDs...")
        leds = client.list_leds()
        print(f"All LEDs: {leds}")
        
        # Bulk operations
        print("\nTurning all LEDs ON...")
        result = client.all_leds_on()
        print(f"All LEDs ON result: {result}")
        
        print("\nTurning all LEDs OFF...")
        result = client.all_leds_off()
        print(f"All LEDs OFF result: {result}")
        
        print("\n[OK] Example 1 completed successfully!")
        
    except Exception as e:
        print(f"[ERROR] Example 1 failed: {e}")
        print("Make sure demo_IO service is running on http://localhost:8080")
        return False
    
    return True


def example_environment_config():
    """Example 2: Using environment variable for automatic configuration."""
    print("\n" + "=" * 70)
    print("Example 2: Environment Variable Configuration")
    print("=" * 70)
    
    # Set environment variable to auto-configure the client
    os.environ["DEMO_IO_URL"] = "http://localhost:8080"
    
    # Now when we import and create the router, it will auto-connect
    from .io_router import create_io_router, get_io_client
    
    # Create router (will auto-configure client from DEMO_IO_URL)
    router = create_io_router()
    
    # Check client
    client = get_io_client()
    if client:
        print(f"Client auto-configured with URL: {client.base_url}")
        if client.is_healthy():
            print("Client is healthy and ready to use")
        else:
            print("Client configured but demo_IO is not responding")
    else:
        print("Client not configured (DEMO_IO_URL not set or empty)")
    
    print("[OK] Example 2 completed!")
    
    # Clean up
    del os.environ["DEMO_IO_URL"]
    return True


def example_router_integration():
    """Example 3: Integrating IO router with ACSI's BFF."""
    print("\n" + "=" * 70)
    print("Example 3: IO Router Integration with ACSI BFF")
    print("=" * 70)
    
    from fastapi import FastAPI
    from .io_router import create_io_router
    
    # Create FastAPI app
    app = FastAPI(
        title="ACSI with IO Control",
        description="ACSI service with integrated IO/LED control via demo_IO",
        version="1.0.0"
    )
    
    # Add IO router
    io_router = create_io_router()
    app.include_router(io_router)
    
    # Now ACSI has additional endpoints:
    print("ACSI now has the following IO endpoints:")
    print("  POST /api/io/connect - Connect to demo_IO service")
    print("  GET  /api/io/connection - Get connection status")
    print("  POST /api/io/disconnect - Disconnect from demo_IO")
    print("  GET  /api/io/health - Check demo_IO health")
    print("  GET  /api/io/status - Get GPIO controller status")
    print("  POST /api/io/leds/config - Configure an LED")
    print("  GET  /api/io/leds - List all LEDs and states")
    print("  GET  /api/io/leds/{name} - Get LED state")
    print("  POST /api/io/leds/{name}/set - Set LED state")
    print("  POST /api/io/leds/{name}/toggle - Toggle LED state")
    print("  POST /api/io/leds/{name}/on - Turn LED on")
    print("  POST /api/io/leds/{name}/off - Turn LED off")
    print("  POST /api/io/leds/all/set - Set all LEDs state")
    print("  POST /api/io/leds/all/on - Turn all LEDs on")
    print("  POST /api/io/leds/all/off - Turn all LEDs off")
    print("  POST /api/io/initialize - Initialize GPIO controller")
    print("  POST /api/io/cleanup - Clean up GPIO resources")
    
    print("\nTo use these endpoints:")
    print("1. First connect to demo_IO:")
    print('   POST /api/io/connect with body {"base_url": "http://demo-io:8080"}')
    print("2. Then use any of the LED control endpoints")
    
    print("[OK] Example 3 completed!")
    return True


def example_programmatic_connection():
    """Example 4: Programmatically connecting to demo_IO in ACSI."""
    print("\n" + "=" * 70)
    print("Example 4: Programmatic Connection Management")
    print("=" * 70)
    
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from .io_router import create_io_router, set_io_client, get_io_client
    from .async_client_io import DemoIOClient
    
    # Create app with IO router
    app = FastAPI()
    io_router = create_io_router()
    app.include_router(io_router)
    
    # Create test client
    test_client = TestClient(app)
    
    # Check initial connection status
    response = test_client.get("/api/io/connection")
    print(f"Initial connection status: {response.json()}")
    
    # Connect to demo_IO programmatically
    demo_io_url = "http://localhost:8080"
    client = DemoIOClient(base_url=demo_io_url)
    set_io_client(client)
    
    response = test_client.get("/api/io/connection")
    print(f"After setting client: {response.json()}")
    
    # Try to use LED endpoints (will fail if demo_IO is not running)
    try:
        response = test_client.get("/api/io/leds")
        if response.status_code == 200:
            print(f"LEDs list: {response.json()}")
        else:
            print(f"Failed to get LEDs: {response.json()}")
    except Exception as e:
        print(f"Expected error without running demo_IO: {e}")
    
    # Disconnect
    response = test_client.post("/api/io/disconnect")
    print(f"Disconnect result: {response.json()}")
    
    print("[OK] Example 4 completed!")
    return True


def main():
    """Run all examples."""
    print("Running async_client_io usage examples...\n")
    
    examples = [
        ("Direct Client Usage", example_direct_client_usage),
        ("Environment Configuration", example_environment_config),
        ("Router Integration", example_router_integration),
        ("Programmatic Connection", example_programmatic_connection),
    ]
    
    results = []
    for name, example_func in examples:
        try:
            result = example_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n[ERROR] {name} failed: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 70)
    print("EXAMPLE SUMMARY")
    print("=" * 70)
    for name, passed in results:
        status = "[OK] PASSED" if passed else "[FAIL] FAILED"
        print(f"{name:30} {status}")
    
    print("=" * 70)
    
    if all(passed for _, passed in results):
        print("All examples completed successfully!")
        return 0
    else:
        print("Some examples may have failed (likely due to demo_IO not running).")
        print("\nTo run the examples with a real demo_IO service:")
        print("1. Start demo_IO: python examples/rti-demo/demo_IO/main.py")
        print("2. Then run this example script")
        return 0


if __name__ == "__main__":
    sys.exit(main())
