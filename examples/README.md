# Overview

This folder contains some example code using the Python reference implementation of the WebSocket/JSON based IEC 61850
SCSM
that has been developed as part of the RTI 2.0 project's PoC.

Also included are the test scripts and other materials (certificates, scripts, ...) required to execute the test cases.

For demonstration there is also a web based GUI client tool.

Notes

- Examples pairing: run matching client/server scripts from `Examples/WS_Client` and `Examples/WS_Server` depending on
  the mode:
    - `endpoint_ws_client_1.py` ↔ `endpoint_ws_server_1.py` (“reversed” mode: IEC61850Server in client, IEC61850Client
      in server)
    - `endpoint_ws_client_2.py` ↔ `endpoint_ws_server_2.py` (“direct” mode: IEC61850Server in server, IEC61850Client in
      client)
