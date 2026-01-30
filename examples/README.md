# Overview

This folder contains some example code using the Python reference implementation of the WebSocket/JSON based IEC 61850
SCSM
that has been developed as part of the RTI 2.0 project's PoC.

Also included are the test scripts and other materials (certificates, scripts, ...) required to execute the test cases.

For demonstration there is also a web based GUI client tool.

Notes

- Examples pairing: run matching client/server scripts from `examples/ws61850_mode` depending on the mode:
    - “reversed” mode: IEC61850Server in client, IEC61850Client in server
    - “direct” mode: IEC61850Server in server, IEC61850Client in client
