## FT22: Multiple clients performance test

This test validates endpoint behavior when a large number of Connected Parties (CPs) connect to one passive endpoint.

## Test design

- `ws_server.py` starts a passive endpoint on `localhost:8765`.
- The server registers IEC 61850 clients for `EAN001` through `EAN100` (100 PoCCs total).
- first `multiple_clients.py` starts active endpoints for `EAN001..EAN050` (50 clients), with a 1 second delay between
  client
  startups.
- second `multiple_clients.py` starts active endpoints for `EAN051..EAN100` (50 clients), without delay.
- Together, `b1 + b2` provide the full `EAN001..EAN100` range expected by `ws_server.py`.

## How to run

1. Start `ws_server.py`. (default 100 PoCC)
2. In separate terminals, start:
    - `multiple_clients.py --start 1 --stop 50`
    - `multiple_clients.py --start 51 --stop 100 --delay 0`

## Report-enabled variant

- `multiple_clients.py` has a report capability and by default disabled, to enable periodic reporting per client.
- `multiple_clients.py --report` enables reporting for all clients, contains a IED model and calls
  `periodic_report_start()` for each simulated IEC61850 controller.

## Important configuration note

- `multiple_clients.py` connects to `localhost`on port `8765`, this is the default for `ws_server.py`.
- The server is configured to accept 100 simultaneous connections.
- The hostname and port are configurable by command line parameters `--host` and `--port` or the `WS_SERVER_HOST` and
  `WS_SERVER_PORT` environment variables.

