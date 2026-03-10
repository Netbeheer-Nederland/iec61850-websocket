## FT20: Verify BER encoding

This test verifies IEC 61850 communication over WebSocket using BER encoding (`iec61850-tpaa-ber-v1`).

## Test design

- `ws_server_ber.py` starts a passive endpoint on `localhost:8765` with BER protocol enabled.
- `ws_client_ber.py` starts an active endpoint for `cp1` with BER protocol enabled.
- The passive test script (`ws_server_ber.py`) runs service calls after connection:
  - directory and data model reads
  - data write (`set_data_values`)
  - control workflow (`select` and `operate`)
  - report control configuration (`set_URCB_values`)

## How to run

1. Start `ws_server_ber.py`.
2. Start `ws_client_ber.py`.

## Notes

- Both scripts must use the same BER protocol list: `["iec61850-tpaa-ber-v1"]`.
- The current FT20 client script only starts `cp1`; `cp2` is registered in `ws_server_ber.py` but not exercised by `ws_client_ber.py`.
