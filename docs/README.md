# Overview

This folder contains the souce code of the Python reference implementation of the WebSocket/JSON based IEC 61850 SCSM that has
been developed as part of the RTI 2.0 project's PoC.

In addition it also contains the ASN.1 schema that is used by the version of the protocol specification that has been developed during the PoC and has been used for the PoC tests.

The ASN.1 schema together with the PoC version of the RTI 2.0 protocol specification document is the base for the reference implementation.

Also included are the test scripts and other materials (certificates, scripts, ...) required to execute the test cases.

For demonstration there is also a web based GUI client tool.

# Directory Structure

Below is a concise map of the repository with short descriptions of key folders.

```
rti2_protocol_spec/
├─ certs/                    # TLS certs and helper scripts for tests
├─ client_credentials/       # OAuth client IDs/secrets for perf tests
├─ doxygen/                  # Doxygen config and generated HTML docs
├─ example_messages/         # Sample JSON requests/responses
├─ Examples/                 # Example clients/servers and interactive demos
│  ├─ WS_Client/             # WebSocket clients (endpoint variants)
│  ├─ WS_Server/             # Matching WebSocket servers
│  ├─ interactive_examples/  # Simple console/websocket demos
│  └─ ieds/                  # Example IED models
├─ extra_files/              # Additional example scripts (TLS/OAuth variants)
├─ iec61850-gui/             # Web GUI Client Tool
├─ scl/                      # SCL files (e.g., `rti_v1.0.scd`)
├─ src/                      # Reference implementation (Python)
│  ├─ asn1/                  # ASN.1 schema, encode/decode, formatters, tests
│  ├─ Endpoint/              # WebSocket endpoint implementation
│  ├─ IEC61850/              # Client/server logic and data model helpers
│  ├─ oauth/                 # OAuth utilities for client identification
│  └─ TLSConfig/             # TLS configuration container
├─ Tests/                    # Functional and performance test suites (FT1..FT10)
├─ README.md                 # Project overview and usage notes
├─ pyproject.toml            # Python project metadata
├─ requirements.txt          # Python dependencies
└─ setup.sh                  # Helper to set `PYTHONPATH`
```

Notes
- Examples pairing: run matching client/server scripts from `Examples/WS_Client` and `Examples/WS_Server` depending on the mode:
	- `endpoint_ws_client_1.py` ↔ `endpoint_ws_server_1.py` (“reversed” mode: IEC61850Server in client, IEC61850Client in server)
	- `endpoint_ws_client_2.py` ↔ `endpoint_ws_server_2.py` (“direct” mode: IEC61850Server in server, IEC61850Client in client)
- `src/IEC61850` contains request/response helpers and IEC 61850 abstractions (e.g., DataObject, LogicalNode) plus utilities to inspect messages.
- `src/asn1` includes the protocol ASN.1 schema and Python helpers to encode/decode messages; formatters assist with readable tagging.


Environment setup
- Ensure `PYTHONPATH` includes the project roots. Run `./setup.sh` from the repo root to set:
	- `path_to/rti2_protocol_spec`
	- `path_to/rti2_protocol_spec/certs`
	- `path_to/rti2_protocol_spec/src`
	- `path_to/rti2_protocol_spec/client_credentials`
	- `path_to/rti2_protocol_spec/Examples`
- If this step is skipped, tests and examples may fail to import. After setup, you can run example and test scripts normally.
