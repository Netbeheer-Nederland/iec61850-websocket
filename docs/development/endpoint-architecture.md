# Endpoint Architecture

## Overview

The `ws61850.endpoint` package is the WebSocket transport layer that sits between the raw WebSocket connection and the IEC 61850 application layer (`IEC61850Server` / `IEC61850Client`). It handles:

- WebSocket connection lifecycle (listen / connect / reconnect)
- TPAA association handshake (associateRequest / associateResponse)
- TPAA control messages (abort, release, token refresh)
- OAuth 2.0 bearer-token validation (passive role)
- TLS configuration
- Routing incoming connections to the correct registered IEC 61850 object

## Module layout

```
src/ws61850/endpoint/
  __init__.py              # public exports + create_endpoint() factory
  base.py                  # WebSocketInfo, EndpointProtocol
  association_handler.py   # TPAA abort / release / refreshToken (extracted once)
  connection_router.py     # cp → server/client lookup + instanceNotAvailable response
  passive_endpoint.py      # WebSocket server role  (listens for connections)
  active_endpoint.py       # WebSocket client role  (connects outward)
  endpoint.py              # WebSocketEndpoint — backward-compatible buffering shim
```

## Class responsibilities

### `WebSocketInfo` (`base.py`)

Per-connection session state passed between the endpoint and the IEC 61850 application layer.

| Field | Type | Description |
|---|---|---|
| `websocket` | `websockets.ServerConnection \| ClientConnection` | The live WebSocket |
| `associate_id` | `bytes` | TPAA association identifier negotiated at handshake |
| `invoke_id` | `int` | Monotonically increasing request counter for this session |
| `cp` | `str \| None` | Control-point path string (e.g. `"cp1"`) |
| `expiry_task` | `asyncio.Task \| None` | Token-expiry watchdog task, set by `PassiveEndpoint` |
| `access_token` | `str \| None` | Bearer token carried for refresh |
| `is_ber_protocol` | `bool` | `True` when the negotiated subprotocol is `iec61850-tpaa-ber-v1` |

### `EndpointProtocol` (`base.py`)

A `@runtime_checkable Protocol` that both concrete endpoint classes implement. Code that does not need to know whether the endpoint is a server or a client (bindings, transports, DI containers) should type-annotate against `EndpointProtocol`.

```python
from ws61850.endpoint import EndpointProtocol

def install(endpoint: EndpointProtocol) -> None: ...
```

Declared surface:

```python
websocket_info_list: list
send_msg_callback: Callable | None
recv_msg_callback: Callable | None
server: object                         # websockets Server object or None

def add_iec61850_client(self, client) -> None
def add_iec61850_server(self, server) -> None
def get_websocket_info(self, iec61850_client) -> WebSocketInfo | None
def get_websocket_info_iec61850_server(self, server) -> WebSocketInfo | None
async def start(self, *args, **kwargs) -> None
async def stop_passive(self) -> None
```

### `PassiveEndpoint` (`passive_endpoint.py`)

Listens for incoming WebSocket connections (`websockets.serve`). Registered IEC 61850 objects are added before calling `start()`.

**Constructor** (all keyword-only):

| Parameter | Default | Description |
|---|---|---|
| `tls_config` | `None` | `TLSConfiguration` for WSS |
| `oauth_enable` | `False` | Require and validate a Bearer token on each connection |
| `is_direct` | `False` | See [is_direct semantics](#is_direct-semantics) below |
| `kc_cert` | `None` | CA certificate PEM path for JWKS endpoint TLS verification |
| `own_cert` | `None` | Client certificate for mTLS to the JWKS endpoint |
| `cert_endpoint` | `None` | URL of the JWKS endpoint (e.g. Keycloak certs URL) |
| `token_issuer` | `None` | Expected `iss` claim in incoming tokens |

**Start signature:**

```python
await endpoint.start(hostname: str, port: int, protocol=None)
```

`protocol` is an optional list of accepted WebSocket subprotocol strings, e.g. `["iec61850-tpaa-ber-v1"]`. Omit to accept all.

**OAuth flow:** When `oauth_enable=True` and `cert_endpoint`/`token_issuer` are provided, a `JwksCache` + `JwtValidator` pair is constructed once in `__init__`. The `process_request` hook validates the `Authorization: Bearer <token>` header before the WebSocket handshake completes. Connections without a valid token receive HTTP 401 and are rejected.

### `ActiveEndpoint` (`active_endpoint.py`)

Connects outward to a remote WebSocket server (`websockets.connect`). Registered IEC 61850 objects are added before calling `start()`.

**Constructor** (all keyword-only):

| Parameter | Default | Description |
|---|---|---|
| `tls_config` | `None` | `TLSConfiguration` for WSS |
| `oauth_enable` | `False` | Attach a Bearer token to the connection request |
| `is_direct` | `False` | See [is_direct semantics](#is_direct-semantics) below |
| `try_reconnect` | `True` | Reconnect after a dropped connection |
| `max_retries` | `None` | Maximum reconnect attempts; `None` = unlimited |
| `retry_connection_delay` | `5.0` | Seconds to wait between reconnect attempts |
| `kc_cert` | `None` | CA certificate for token-refresh TLS |
| `own_cert` | `None` | Client certificate for token-refresh mTLS |
| `cert_endpoint` | `None` | JWKS endpoint URL |
| `token_issuer` | `None` | Expected `iss` claim |

**Start signature:**

```python
await endpoint.start(hostname: str, port: int, cp: str, *, access_token=None, protocol=None)
```

**Reconnect loop:** Implemented via `ReconnectPolicy` (`ws61850.transport.reconnect`). The loop retries on `ConnectionRefusedError` / `OSError`. After a successful connection it resets the retry counter. To disable reconnection pass `try_reconnect=False`.

### `AssociationHandler` (`association_handler.py`)

Handles the three TPAA association-control message types that appear inside every receive loop, returning one of three sentinel strings:

| Return value | Meaning |
|---|---|
| `ACTION_ABORT` (`"abort"`) | An `abortRequest` was received; abort response sent, transport aborted |
| `ACTION_RELEASE` (`"release"`) | A `releaseRequest` was received; release response sent, connection closed |
| `ACTION_CONTINUE` (`"continue"`) | A `refreshToken` or unrecognised type; loop should continue |

Before this class existed, the same ~40-line block was copy-pasted three times inside `WebSocketEndpoint` (once per receive path). Both `PassiveEndpoint` and `ActiveEndpoint` call `AssociationHandler.handle()` from their respective receive loops.

### `ConnectionRouter` (`connection_router.py`)

Resolves a control-point identifier (`cp` string) to a registered `IEC61850Server` or `IEC61850Client`, and sends the standard TPAA `instanceNotAvailable` response when no match is found.

Before this class existed, the same lookup-plus-not-found block was copy-pasted four times inside `WebSocketEndpoint`. Both endpoint classes share a single `ConnectionRouter` instance.

### `WebSocketEndpoint` (`endpoint.py`) — backward-compatible shim

Buffers `add_iec61850_client` / `add_iec61850_server` registrations and callbacks made before `start()`. On `start(mode, hostname, port, ...)` it constructs the correct concrete class (`PassiveEndpoint` or `ActiveEndpoint`), replays the buffered state, and awaits.

This shim exists so existing callers do not need to change. New code should use `PassiveEndpoint` or `ActiveEndpoint` directly.

## `is_direct` semantics

The `is_direct` flag controls which list is served and who initiates the TPAA association handshake.

| Endpoint | `is_direct=False` (default) | `is_direct=True` |
|---|---|---|
| `PassiveEndpoint` | Serves `client_list`. Incoming WS connections are from field devices acting as WS clients; the remote side sends `associateRequest`. | Serves `server_list`. The passive endpoint is actually the IED side; the remote client initiates as a WS client but is an IEC 61850 client. |
| `ActiveEndpoint` | Serves `server_list`. The active endpoint connects outward and waits for the remote passive side to send `associateRequest`. | Serves `client_list`. The active endpoint connects outward and immediately sends `associateRequest` itself. |

For the vast majority of deployments (`ws_server.py` / `ws_client.py` test pairs) `is_direct=False` is the right choice.

## Reused infrastructure

| Class | Module | Replaces |
|---|---|---|
| `ReconnectPolicy` | `ws61850.transport.reconnect` | Inline retry loop in `WebSocketEndpoint.__start_active()` |
| `JwksCache` | `ws61850.security.oauth2.jwks` | Inline `requests.Session().get(jwks_url)` in `process_request` |
| `JwtValidator` | `ws61850.security.oauth2.validator` | Inline `jwt.decode()` in `process_request` |

## Public API surface (`__init__.py`)

```python
from ws61850.endpoint import (
    PassiveEndpoint,     # concrete WebSocket server role
    ActiveEndpoint,      # concrete WebSocket client role
    WebSocketInfo,       # per-connection session state
    EndpointProtocol,    # structural Protocol for type annotations
    WebSocketEndpoint,   # deprecated shim — kept for backward compatibility
    create_endpoint,     # factory: create_endpoint('passive'/'active', **kwargs)
)
```

## Minimal usage examples

### PassiveEndpoint

```python
from ws61850.endpoint.passive_endpoint import PassiveEndpoint
from ws61850.iec61850.client.iec61850_client import IEC61850Client

endpoint = PassiveEndpoint()
client = IEC61850Client("cp1")
endpoint.add_iec61850_client(client)
await endpoint.start("localhost", 8765)
```

### ActiveEndpoint

```python
from ws61850.endpoint.active_endpoint import ActiveEndpoint
from ws61850.iec61850.server.iec61850_server import IEC61850Server

endpoint = ActiveEndpoint(try_reconnect=False)
server = IEC61850Server(ied_model, "cp1")
endpoint.add_iec61850_server(server)
await endpoint.start("localhost", 8765, "cp1")
```

### ActiveEndpoint with OAuth + TLS

```python
from ws61850.endpoint.active_endpoint import ActiveEndpoint
from ws61850.security.tls import TLSConfiguration

tls_config = TLSConfiguration(cafile, None, is_ws_server=False)
endpoint = ActiveEndpoint(oauth_enable=True, tls_config=tls_config)
endpoint.add_iec61850_server(server)
await endpoint.start("example.com", 8765, "cp1", access_token=token)
```

### PassiveEndpoint with OAuth + TLS

```python
from ws61850.endpoint.passive_endpoint import PassiveEndpoint
from ws61850.security.tls import TLSConfiguration

tls_config = TLSConfiguration(cert_path, key_path, is_ws_server=True)
endpoint = PassiveEndpoint(
    oauth_enable=True,
    tls_config=tls_config,
    cert_endpoint="https://auth.example.com/realms/r1/protocol/openid-connect/certs",
    token_issuer="https://auth.example.com/realms/r1",
    kc_cert=cafile,
)
endpoint.add_iec61850_client(IEC61850Client("cp1"))
await endpoint.start("0.0.0.0", 8765)
```
