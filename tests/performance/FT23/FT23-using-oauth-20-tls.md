# FT23: Running the OAuth 2.0 + TLS Performance Test

## Scope

This document describes OAuth 2.0 authentication for a Connected Party (CP) WebSocket session. The WebSocket server
accepts or rejects CP connections based on access tokens issued by a Keycloak authorization server. The Keycloak realm
and
client configuration used by this test are imported from the local `keycloak` directory in this test folder.

This document describes how to run the FT23 performance scenario that combines:

- OAuth 2.0 client-credentials authentication against Keycloak
- TLS for both Keycloak HTTPS access and the WebSocket server
- Multiple IEC61850 WebSocket clients started from one runner

The current FT23 flow is implemented by:

- `tests/performance/FT23/ws_server.py`
- `tests/performance/FT23/multiple_clients_oauth_tls.py`

## What the test starts

`ws_server.py`:

- starts a WebSocket server on `localhost:8765`
- enables TLS with `testing/certs/server.pem` and `testing/certs/server-key.pem`
- enables OAuth token validation
- validates tokens against the Keycloak realm certificate endpoint
- registers one IEC 61850 client per configured PoCC credential

`multiple_clients_oauth_tls.py`:

- loads OAuth client credentials from `tests/performance/FT23/data/client_credentials.json`
- requests access tokens from Keycloak over HTTPS
- opens secure WebSocket connections to the FT23 server
- refreshes tokens before expiry while clients remain connected

## Prerequisites

1. Install the project dependencies:

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

The FT23 scripts use these defaults:

| Setting               | Default                                               |
|-----------------------|-------------------------------------------------------|
| Keycloak base URL     | `https://localhost:8443`                              |
| Keycloak realm        | `iec61850-test`                                       |
| WebSocket server host | `localhost`                                           |
| WebSocket server port | `8765`                                                |
| Credentials file      | `tests/performance/FT23/data/client_credentials.json` |

The environment variables supported by the scripts are:

```bash
export KEYCLOAK_URL=https://localhost:8443
export IEC61850_REALM=iec61850-test
export WS_SERVER_HOST=localhost
export WS_SERVER_PORT=8765
```

These only need to be set when you want values different from the defaults.

## Start Keycloak

The FT23 test expects the Keycloak container defined in `scripts/keycloak/docker-compose.yaml`.

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

## Prepare FT23 client credentials

The FT23 scripts read credentials from:

```text
tests/performance/FT23/data/client_credentials.json
```

That file does not come packed with this repository, so you need to recreate the Keycloak clients or change the client
count, run:

```bash
uv run python tests/performance/FT23/client_credentials/create_keycloak_clients.py \
  --num-clients-in-batch 15
```

Notes:

- The script writes the credentials back to `tests/performance/FT23/data/client_credentials.json`.
- The provisioning script talks to the Keycloak admin API on `http://localhost:8080`.
- It uses the admin account from the compose file by default: `admin` / `admin`.

If your Keycloak admin settings are different, set:

```bash
export KEYCLOAK_ADMIN_USER=admin
export KEYCLOAK_ADMIN_PASSWORD=admin
export KEYCLOAK_REALM=master
```

## Run the FT23 server

Open a terminal in the repository root and start the passive endpoint:

```bash
uv run python tests/performance/FT23/ws_server.py
```

What this process uses:

- server certificate: `testing/certs/server.pem`
- server private key: `testing/certs/server-key.pem`
- Keycloak CA trust: `testing/certs/ca.pem`
- OAuth JWKS endpoint:
  `https://localhost:8443/realms/iec61850-test/protocol/openid-connect/certs`

The server listens on:

```text
wss://localhost:8765
```

## Run the FT23 clients

In a second terminal, start the multi-client runner:

```bash
uv run python tests/performance/FT23/multiple_clients_oauth_tls.py
```

Useful options:

```bash
uv run python tests/performance/FT23/multiple_clients_oauth_tls.py \
  --start 1 \
  --stop 15 \
  --delay 2 \
  --host localhost \
  --port 8765
```

Current behavior to be aware of:

- the runner loads all entries from `data/client_credentials.json`, or from `start` to `stop` based on the pocc_id in
  the file.
- `--delay` is applied between client startups
- `--host` and `--port` control the WebSocket target
- OAuth tokens are requested from Keycloak using the configured realm
- token refresh is scheduled before expiry

## Expected result

When the setup is correct:

- Keycloak issues access tokens for each FT23 client
- each client establishes a secure WebSocket connection to `wss://localhost:8765`
- the FT23 server accepts the OAuth-authenticated clients
- the connections remain active while refresh tokens continue to be exchanged successfully

Useful log indicators:

- server logs show client registration and connection handling
- client logs show access token retrieval and connection startup per `pocc_id`

## Troubleshooting

If Keycloak token requests fail:

- verify `KEYCLOAK_URL` matches the active Keycloak listener
- verify `testing/certs/ca.pem` trusts the Keycloak HTTPS certificate
- verify the `iec61850-test` realm was imported successfully

If the WebSocket connection fails during TLS setup:

- confirm `testing/certs/server.pem` and `testing/certs/server-key.pem` exist
- confirm the client is connecting to the same host and port used by `ws_server.py`

If the clients fail authentication:

- stop the Keycloak container and restart it with the realm definition, this removes defined the client credentials
- verify the Keycloak realm is still available at `https://localhost:8443/realms/iec61850-test`
- recreate the FT23 clients with `create_keycloak_clients.py` and verify the clients are registered
- verify `tests/performance/FT23/data/client_credentials.json` contains the expected `client_id`, `client_secret`, and
  `pocc_id` values
- verify the FT23 server and client processes use the same realm value

## Minimal run sequence

From the repository root:

```bash
uv sync
docker compose -f scripts/keycloak/docker-compose.yaml up
```

In another terminal:

```bash
uv run python tests/performance/FT23/ws_server.py
```

In another terminal:

```bash
uv run python tests/performance/FT23/multiple_clients_oauth_tls.py
```
