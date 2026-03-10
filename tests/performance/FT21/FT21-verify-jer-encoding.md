## FT21: Verify JER encoding

This test verifies IEC 61850 communication over WebSocket using JER encoding (`iec61850-tpaa-jer-v1`).

## Test design

- `ws_server_jer.py` starts a passive endpoint on `localhost:8765` with JER protocol enabled.
- `ws_client_jer.py` starts an active endpoint for `cp1` with JER protocol enabled.
- The passive test script (`ws_server_jer.py`) runs service calls after connection:
  - directory and data model reads
  - data write (`set_data_values`)
  - control workflow (`select` and `operate`)
  - report control configuration (`set_URCB_values`)

## How to run

1. Start `ws_server_jer.py`.
2. Start `ws_client_jer.py`.

## Notes

- Both scripts must use the same JER protocol list: `["iec61850-tpaa-jer-v1"]`.
- The current FT21 client script only starts `cp1`; `cp2` is registered in `ws_server_jer.py` but not exercised by `ws_client_jer.py`.
