#!/usr/bin/env python3
"""
Test script to verify the demo_IO module can be imported correctly.

Run this script to check that all modules are properly structured.
"""

import sys
import os

# Add the demo_IO directory to the path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

print("Testing imports from demo_IO module...")
print(f"Script directory: {script_dir}")
print()

# Test 1: Import __init__
try:
    import demo_IO
    print("✓ Successfully imported demo_IO package")
except Exception as e:
    print(f"✗ Failed to import demo_IO: {e}")
    sys.exit(1)

# Test 2: Import io_controller
try:
    from io_controller import IOController
    print("✓ Successfully imported from io_controller")
    print(f"  - IOController: {IOController}")
except Exception as e:
    print(f"✗ Failed to import from io_controller: {e}")
    sys.exit(1)

# Test 3: Import api_endpoint
try:
    from api_endpoint import create_fastapi_app, create_io_router
    print("✓ Successfully imported from api_endpoint")
    print(f"  - create_fastapi_app: {create_fastapi_app}")
    print(f"  - create_io_router: {create_io_router}")
except Exception as e:
    print(f"✗ Failed to import from api_endpoint: {e}")
    sys.exit(1)

# Test 4: Import main
try:
    from main import create_app, main
    print("✓ Successfully imported from main")
    print(f"  - create_app: {create_app}")
    print(f"  - main: {main}")
except Exception as e:
    print(f"✗ Failed to import from main: {e}")
    sys.exit(1)

# Test 5: Create a IOController and test basic functionality
try:
    from devices import LEDConfig
    
    controller = IOController()
    print("✓ Created IOController instance")
    
    # Add an LED device
    controller.add_device(LEDConfig(
        name="test_led",
        gpio_pin=17,
        description="Test LED",
        initial_state=False
    ))
    print("✓ Added test LED device configuration")
    
    # Initialize (should work in mock mode)
    if controller.initialize():
        print("✓ IOController initialized (mock mode)")
    else:
        print("✗ IOController initialization failed")
        sys.exit(1)
    
    # Get status
    status = controller.get_status()
    print(f"✓ Got controller status: {status}")
    
    # Cleanup
    controller.cleanup()
    print("✓ IOController cleaned up")
    
except Exception as e:
    print(f"✗ Failed IOController test: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 6: Create FastAPI app
try:
    app = create_fastapi_app()
    print(f"✓ Created FastAPI app: {app}")
    print(f"  - App title: {app.title}")
    print(f"  - App version: {app.version}")
    
    # Check if the router is included
    routes = [route.path for route in app.routes]
    print(f"  - Number of routes: {len(routes)}")
    print(f"  - API routes: {[r for r in routes if '/api/io' in r]}")
    
except Exception as e:
    print(f"✗ Failed to create FastAPI app: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()
print("=" * 60)
print("All tests passed! The demo_IO module is working correctly.")
print("=" * 60)
print()
print("To run the API server:")
print("  python main.py")
print()
print("Then access the API at (default port 8080):")
print("  http://localhost:8080/api/io/docs")
print()
print("To use a different port:")
print("  PORT=8001 python main.py")
print("  Then access at: http://localhost:8001/api/io/docs")
