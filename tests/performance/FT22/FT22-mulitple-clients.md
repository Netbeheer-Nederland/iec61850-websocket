# FT22: Multiple-Clients Performance Test

## Scope

This document describes how to run the FT22 is a multiple-clients performance scenario that combines:

- one passive WebSocket server
- a configurable number of active WebSocket clients
- optional IEC 61850 periodic reporting from each client

The current FT22 flow is implemented by:

- `tests/performance/FT22/ws_server.py`
- `tests/performance/FT22/multiple_clients.py`

## What the test starts

`ws_server.py`:

- starts a passive endpoint on `localhost:8765`
- registers IEC 61850 clients with PoCC identifiers `EAN001` upward
- supports a configurable total number of registered PoCCs

`multiple_clients.py`:

- starts active endpoints for a configurable PoCC range
- connects those clients to the FT22 server
- optionally enables periodic IEC 61850 reports

## Prerequisites

Install the project dependencies from the repository root:

```bash
uv sync
```

No Keycloak setup is required for FT22.

No TLS certificate setup is required for FT22.

## Supported configuration

The FT22 scripts use these defaults:

| Setting               | Default     |
|-----------------------|-------------|
| WebSocket server host | `localhost` |
| WebSocket server port | `8765`      |
| Server PoCC capacity  | `100`       |
| Client start PoCC     | `1`         |
| Client stop PoCC      | `50`        |
| Client startup delay  | `2` seconds |
| Periodic reporting    | disabled    |

The environment variables supported by the scripts are:

```bash
export WS_SERVER_HOST=localhost
export WS_SERVER_PORT=8765
```

These only need to be set when you want values different from the defaults.

## Run the FT22 server

Open a terminal in the repository root and start the passive endpoint:

```bash
uv run python tests/performance/FT22/ws_server.py
```

To change the number of registered PoCCs or the bind address:

```bash
uv run python tests/performance/FT22/ws_server.py \
  --pocc 100 \
  --host localhost \
  --port 8765
```

Current server behavior:

- registers `EAN001` through `EAN100` when `--pocc 100` is used
- listens in passive mode on the configured host and port
- serves plain `ws://` traffic, not `wss://`

## Run the FT22 clients

In another terminal, start one client batch:

```bash
uv run python tests/performance/FT22/multiple_clients.py
```

Useful options:

```bash
uv run python tests/performance/FT22/multiple_clients.py \
  --start 1 \
  --stop 50 \
  --delay 2 \
  --host localhost \
  --port 8765
```

Current client behavior:

- each client uses a PoCC identifier in the selected range
- clients connect to the configured FT22 server host and port
- connections are plain WebSocket connections without TLS
- no OAuth token exchange is performed

## Full 100-client run

The existing FT22 note describes a two-batch run that fills the server's default `100` registered PoCCs.

Terminal 1:

```bash
uv run python tests/performance/FT22/ws_server.py --pocc 100
```

Terminal 2:

```bash
uv run python tests/performance/FT22/multiple_clients.py \
  --start 1 \
  --stop 50 \
  --delay 1
```

Terminal 3:

```bash
uv run python tests/performance/FT22/multiple_clients.py \
  --start 51 \
  --stop 100 \
  --delay 0
```

## Report-enabled variant

The FT22 client runner has a `--report` argument and defaults it to `False`.

To start a batch with periodic reporting enabled:

```bash
uv run python tests/performance/FT22/multiple_clients.py \
  --start 1 \
  --stop 50 \
  --report True
```

## Expected result

When FT22 is configured correctly:

- the passive endpoint starts on `ws://localhost:8765`
- the client batches connect successfully within the requested PoCC range
- the server accepts those PoCCs if they were pre-registered by `--pocc`
- IEC 61850 requests and responses are logged after client readiness

## Troubleshooting

If clients fail to connect:

- verify the FT22 server is running first
- verify `WS_SERVER_HOST` and `WS_SERVER_PORT` match on both sides
- verify the requested client range fits inside the server `--pocc` capacity

## Minimal run sequence

From the repository root:

```bash
uv sync
uv run python tests/performance/FT22/ws_server.py --pocc 100
```

In another terminal:

```bash
uv run python tests/performance/FT22/multiple_clients.py --start 1 --stop 50
```
