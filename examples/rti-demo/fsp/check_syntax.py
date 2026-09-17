# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
#
# Copyright 2025 Netbeheer Nederland
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
