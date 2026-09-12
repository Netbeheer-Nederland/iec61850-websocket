#!/usr/bin/env python3
"""Check syntax of bff_endpoint.py"""
import ast
import sys

try:
    with open('/c/Users/MaxsonRamonDosAnjosM/workspace/tools/Clients/RTI_DEMO/rti_2_0_demo/iec61850-websocket/examples/rti-demo/fsp/bff_endpoint.py', 'r') as f:
        code = f.read()
    ast.parse(code)
    print("Syntax is valid!")
    sys.exit(0)
except SyntaxError as e:
    print(f"Syntax error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
