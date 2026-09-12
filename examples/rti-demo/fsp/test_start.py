#!/usr/bin/env python
import os
import sys

# Add the parent directory to path for demo_IO imports
sys.path.insert(0, 'C:/Users/MaxsonRamonDosAnjosM/workspace/tools/Clients/RTI_DEMO/rti_2_0_demo/iec61850-websocket/examples/rti-demo')

# Set PORT to 5002
os.environ['PORT'] = '5002'

# Import and run the bff_endpoint
try:
    from fsp.bff_endpoint import create_fastapi_app
    from pathlib import Path
    
    print("Creating FastAPI app...")
    factory_dir = Path('C:/Users/MaxsonRamonDosAnjosM/workspace/tools/Clients/RTI_DEMO/rti_2_0_demo/iec61850-websocket/examples/rti-demo/fsp')
    app = create_fastapi_app(factory_dir)
    print("FastAPI app created successfully!")
    
    print("Starting uvicorn server on port 5002...")
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=5002)
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
