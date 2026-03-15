# FT20: Verify BER Encoding

## Scope

This document describes how to run the FT20 scenario that verifies IEC 61850 communication over WebSocket using BER
encoding with the `iec61850-tpaa-ber-v1` subprotocol.

The current FT20 flow is implemented by:

- `tests/performance/FT20/ws_server.py`
- `tests/performance/FT20/ws_client.py`

## What the test starts

`ws_server.py`:

- starts a passive endpoint on `localhost:8765`
- enables the BER WebSocket subprotocol
- registers IEC 61850 clients `cp1` and `cp2`
- runs IEC 61850 service calls against `cp1` after the connection is ready

`ws_client.py`:

- starts an active endpoint for `cp1`
- enables the same BER WebSocket subprotocol
- hosts an IEC 61850 server model built from `testing.ieds.high_level_model.make_ied_model1()`
- starts periodic reporting for the connected server instance

## Prerequisites

Install the project dependencies from the repository root:

```bash
uv sync
```

No Keycloak setup is required for FT20.

No TLS certificate setup is required for FT20.

## Supported configuration

The FT20 scripts currently use these fixed values:

| Setting               | Value                    |
|-----------------------|--------------------------|
| WebSocket server host | `localhost`              |
| WebSocket server port | `8765`                   |
| WebSocket subprotocol | `iec61850-tpaa-ber-v1`   |
| Passive-side clients  | `cp1`, `cp2`             |
| Active-side server    | `cp1`                    |

The current FT20 scripts do not expose command-line options or environment variables for these values.

## Run the FT20 passive side

Open a terminal in the repository root and start the passive endpoint:

```bash
uv run python tests/performance/FT20/ws_server.py
```

Current passive-side behavior:

- listens on `ws://localhost:8765`
- waits for `cp1` to become ready
- issues these IEC 61850 operations after the connection is established:
  - server directory read
  - logical device, logical node, dataset, and data definition reads
  - data write with `set_data_values`
  - control sequence with `select` and `operate`
  - data readback with `get_data_values`
  - report control configuration with `set_URCB_values`

## Run the FT20 active side

In another terminal, start the active endpoint:

```bash
uv run python tests/performance/FT20/ws_client.py
```

Current active-side behavior:

- connects as `cp1` to `localhost:8765`
- exposes the sample IEC 61850 server data model
- uses a control handler that accepts float control values below `50`
- starts periodic report generation while connected

## Expected result

When FT20 is configured correctly:

- the passive endpoint starts on `ws://localhost:8765`
- the active endpoint connects successfully using `iec61850-tpaa-ber-v1`
- the passive script completes the BER-encoded IEC 61850 request flow against `cp1`
- the control operation and URCB configuration requests are handled without protocol mismatch errors

Useful log indicators:

- passive-side logs show the connection reaching the ready state
- passive-side logs show the service calls progressing after connection setup
- active-side logs show the `cp1` connection and periodic reporting activity

## Troubleshooting

If the peers do not connect:

- verify `ws_server.py` is running before `ws_client.py`
- verify both scripts still use `localhost:8765`
- verify both sides still use `iec61850-tpaa-ber-v1`

If the control operation fails:

- verify the control handler in `ws_client.py` still accepts the requested float value
- verify the sample data model from `make_ied_model1()` still exposes the referenced control objects

If you expect `cp2` traffic:

- note that `cp2` is registered by `ws_server.py` but the current FT20 client script only starts `cp1`

## Minimal run sequence

From the repository root:

```bash
uv sync
uv run python tests/performance/FT20/ws_server.py
```

In another terminal:

```bash
uv run python tests/performance/FT20/ws_client.py
```
