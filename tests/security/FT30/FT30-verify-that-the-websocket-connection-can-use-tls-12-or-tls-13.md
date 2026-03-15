# FT30: Verify that the WebSocket Connection Can Use TLS 1.2 or TLS 1.3

## Scope

This document describes how to run the FT30 security scenario that verifies a secure WebSocket connection with TLS and
server certificate validation.

The current FT30 flow is implemented by:

- `tests/security/FT30/ws_server.py`
- `tests/security/FT30/ws_client.py`

## What the test starts

`ws_server.py`:

- starts a passive WebSocket endpoint on `localhost:8765`
- enables TLS with `testing/certs/server.pem` and `testing/certs/server-key.pem`
- currently pins the TLS version to `TLSv1_2`
- registers IEC 61850 client `cp1`
- runs IEC 61850 service calls after the connection is ready

`ws_client.py`:

- starts an active endpoint for `cp1`
- verifies the server certificate against `testing/certs/ca.pem`
- connects to the FT30 server over `wss://`
- hosts an IEC 61850 server model built from `testing.ieds.high_level_model.make_ied_model1()`
- starts periodic reporting for the connected server instance

## Prerequisites

1. Install the project dependencies from the repository root:

```bash
uv sync
```

2. Make sure local TLS material exists in `testing/certs/`.

The repository does not come packed with generated certificates. If you need to regenerate them:

```bash
cd testing/certs
./generate.sh
cd ../..
```

No Keycloak setup is required for FT30.

## Supported configuration

The FT30 scripts currently use these fixed values:

| Setting               | Value                          |
|-----------------------|--------------------------------|
| WebSocket server host | `localhost`                    |
| WebSocket server port | `8765`                         |
| Server certificate    | `testing/certs/server.pem`     |
| Server private key    | `testing/certs/server-key.pem` |
| Client CA trust       | `testing/certs/ca.pem`         |
| Passive-side client   | `cp1`                          |
| Active-side server    | `cp1`                          |
| TLS version in repo   | `TLS 1.2`                      |

The current FT30 scripts do not expose command-line options or environment variables for these values.

## Run the FT30 passive side

Open a terminal in the repository root and start the passive endpoint:

```bash
uv run python tests/security/FT30/ws_server.py
```

Current passive-side behavior:

- listens on `wss://localhost:8765`
- uses the server certificate and private key from `testing/certs/`
- writes TLS session keys to `tlskeys.log`
- waits for `cp1` to become ready
- issues IEC 61850 directory, dataset, data definition, data write, data read, and URCB configuration requests

## Run the FT30 active side

In another terminal, start the active endpoint:

```bash
uv run python tests/security/FT30/ws_client.py
```

Current active-side behavior:

- connects as `cp1` to `wss://localhost:8765`
- validates the server certificate using `testing/certs/ca.pem`
- exposes the sample IEC 61850 server data model
- uses a control handler that accepts float control values below `50`
- starts periodic report generation while connected

## TLS 1.3 variant

The checked-in FT30 server script currently forces TLS 1.2 with:

```python
tls_config.set_min_and_max_version(
    min_version=ssl.TLSVersion.TLSv1_2,
    max_version=ssl.TLSVersion.TLSv1_2,
)
```

To run the same FT30 scenario with TLS 1.3 instead, change that block in
`tests/security/FT30/ws_server.py` to `ssl.TLSVersion.TLSv1_3` for both the minimum and maximum version, then rerun the
same server and client commands.

## Expected result

When FT30 is configured correctly:

- the passive endpoint starts on `wss://localhost:8765`
- the client validates the presented server certificate against the local CA
- the TLS handshake completes successfully with the configured TLS version
- the secure WebSocket connection remains active while IEC 61850 requests and responses are exchanged

Useful log indicators:

- server logs show the secure listener starting on `wss://localhost:8765`
- client logs show the `cp1` connection being established
- the passive-side IEC 61850 requests complete after the TLS session is established

## Troubleshooting

If the TLS handshake fails:

- confirm `testing/certs/server.pem`, `testing/certs/server-key.pem`, and `testing/certs/ca.pem` exist
- confirm the client trusts the same CA that signed the server certificate
- confirm the server hostname matches the certificate expected by the client

If the connection is refused:

- verify `ws_server.py` is running before `ws_client.py`
- verify both scripts still use `localhost:8765`

If you want to test TLS 1.3:

- note that the checked-in FT30 server script currently runs TLS 1.2 only
- update the pinned TLS version in `tests/security/FT30/ws_server.py` before rerunning the test

## Minimal run sequence

From the repository root:

```bash
uv sync
uv run python tests/security/FT30/ws_server.py
```

In another terminal:

```bash
uv run python tests/security/FT30/ws_client.py
```
