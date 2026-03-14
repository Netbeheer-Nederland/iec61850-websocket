# FT31: Using OAuth 2.0 for Connected Party Endpoint Authentication

## Scope

This document describes how to run the FT31 security scenario that verifies OAuth 2.0 authentication for a Connected
Party (CP) WebSocket session. The WebSocket server accepts or rejects CP connections based on access tokens issued by a
Keycloak authorization server.

The current FT31 flow is implemented by:

- `tests/security/FT31/ws_server.py`
- `tests/security/FT31/ws_client.py`
- `tests/security/FT31/ws_client_n1.py`
- `tests/security/FT31/ws_client_n2.py`

## What the test starts

`ws_server.py`:

- starts a passive endpoint on `localhost:8765`
- enables OAuth token validation for Connected Party connections
- validates tokens against the Keycloak certs endpoint for realm `iec61850-test`
- registers IEC 61850 client `cp1`
- runs IEC 61850 service calls after a client is authenticated and connected

`ws_client.py`:

- requests an OAuth access token from Keycloak over HTTPS
- starts an active endpoint for `cp1`
- connects with that access token
- refreshes the token shortly before expiry while the WebSocket session remains active

`ws_client_n1.py`:

- starts an active endpoint for `cp1`
- connects with a hardcoded token instead of requesting one from the FT31 Keycloak setup
- is used as a negative authentication variant

`ws_client_n2.py`:

- requests an OAuth access token from Keycloak over HTTPS
- starts an active endpoint for `cp1`
- connects with that token
- disables reconnection and does not send token refresh messages
- is used as the token-expiry negative variant

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

3. Make sure Docker is available for Keycloak.

## Required configuration

The FT31 scripts currently use these fixed values:

| Setting               | Value                                                                       |
|-----------------------|-----------------------------------------------------------------------------|
| Keycloak base URL     | `https://localhost:8443`                                                    |
| Keycloak realm        | `iec61850-test`                                                             |
| WebSocket server host | `localhost`                                                                 |
| WebSocket server port | `8765`                                                                      |
| OAuth client id       | `ws-client`                                                                 |
| OAuth client secret   | `K4Nrd14seXG52J3xpnIqfMyILTJJu3VI`                                          |
| CA trust for HTTPS    | `testing/certs/ca.pem`                                                      |
| JWKS endpoint         | `https://localhost:8443/realms/iec61850-test/protocol/openid-connect/certs` |

The current FT31 scripts do not expose command-line options or environment variables for these values.

## Start Keycloak

The FT31 test expects the Keycloak container defined in `scripts/keycloak/docker-compose.yaml`.

From the repository root:

```bash
docker compose -f scripts/keycloak/docker-compose.yaml up
```

The docker-compose file provides:

- starts Keycloak 26.0
- exposes HTTP on `8080`
- exposes HTTPS on `8443`
- bootstraps the admin user as `admin` / `admin`
- imports the realm from `scripts/keycloak/data/realm-test.json`
- mounts `testing/certs/server.pem` and `testing/certs/server-key.pem` into Keycloak

After startup, verify that the realm is reachable:

```bash
curl --cacert testing/certs/ca.pem \
  https://localhost:8443/realms/iec61850-test
```

## Run the FT31 server

Open a terminal in the repository root and start the passive endpoint:

```bash
uv run python tests/security/FT31/ws_server.py
```

Current server behavior:

- listens on `ws://localhost:8765`
- validates OAuth bearer tokens against the FT31 Keycloak realm
- accepts `cp1` only after token validation succeeds
- issues IEC 61850 directory, dataset, data definition, data read, data write, and BRCB configuration requests after
  authentication

## Run the positive FT31 client

In another terminal, start the positive client flow:

```bash
uv run python tests/security/FT31/ws_client.py
```

Current positive-client behavior:

- requests an access token from Keycloak using the configured client credentials
- connects as `cp1` to the FT31 server
- monitors token expiry locally
- sends an OAuth token refresh associate message before expiry

## Run the negative FT31 variants

Negative variant 1 uses the hardcoded-token client:

```bash
uv run python tests/security/FT31/ws_client_n1.py
```

Current behavior to be aware of:

- the script does not request a token from the active FT31 Keycloak setup
- the server is expected to reject the session if that token is invalid for the configured realm or issuer

Negative variant 2 uses the no-refresh client:

```bash
uv run python tests/security/FT31/ws_client_n2.py
```

Current behavior to be aware of:

- the script requests an initial valid token from Keycloak
- the script does not refresh the token after connection setup
- the server is expected to close the session when the token expires

## Expected result

When FT31 is configured correctly:

- `ws_client.py` obtains a valid OAuth token and establishes the CP connection successfully
- the FT31 server accepts the authenticated `cp1` session and processes IEC 61850 requests
- `ws_client_n1.py` is rejected if the supplied token is not valid for the FT31 Keycloak realm
- `ws_client_n2.py` connects initially but the session is closed after token expiry because no valid refresh arrives

Useful log indicators:

- server logs show token validation and connection handling for `cp1`
- positive-client logs show access token retrieval and refresh activity
- negative-case logs show either authentication rejection or connection closure on expiry

## Troubleshooting

If Keycloak token requests fail:

- verify Keycloak is running on `https://localhost:8443`
- verify `testing/certs/ca.pem` trusts the Keycloak HTTPS certificate
- verify the `iec61850-test` realm is available

If the positive client is rejected:

- verify the client id and secret in `ws_client.py` still match the imported Keycloak realm
- verify the FT31 server still points at the same issuer and JWKS endpoint

If the negative case does not behave as expected:

- note that `ws_client_n1.py` uses a hardcoded token and depends on that token being invalid for the active FT31 setup
- note that `ws_client_n2.py` is designed to succeed first and fail only after token expiry

If the WebSocket connection fails:

- verify `ws_server.py` is running before any FT31 client
- verify all FT31 scripts still use `localhost:8765`

## Minimal run sequence

From the repository root:

```bash
uv sync
docker compose -f scripts/keycloak/docker-compose.yaml up
```

In another terminal:

```bash
uv run python tests/security/FT31/ws_server.py
```

In another terminal:

```bash
uv run python tests/security/FT31/ws_client.py
```
