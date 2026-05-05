# Logging Reference

## Logger names

Every module in `ws61850` uses `logging.getLogger(__name__)`, so logger names map directly to Python module paths.

| Logger name | Module |
|---|---|
| `ws61850.endpoint.passive_endpoint` | WebSocket server lifecycle, OAuth, per-connection handling |
| `ws61850.endpoint.active_endpoint` | WebSocket client lifecycle, session handling |
| `ws61850.endpoint.association_handler` | TPAA abort / release / refreshToken dispatch |
| `ws61850.endpoint.connection_router` | `cp` → IEC 61850 object lookup, `instanceNotAvailable` responses |
| `ws61850.transport.reconnect` | Reconnect policy — attempt counts, delays, give-up decisions |
| `ws61850.transport.websocket_transport` | Low-level WebSocket send / receive |
| `ws61850.iec61850.server.iec61850_server` | IEC 61850 server — association and service dispatch |
| `ws61850.iec61850.server.request_handling` | Server-side service request handling |
| `ws61850.iec61850.client.iec61850_client` | IEC 61850 client — association, select/operate, directory |
| `ws61850.iec61850.client.compact` | Compact client helpers |
| `ws61850.iec61850.client.reconstruct_tree_client` | Data-model tree reconstruction |
| `ws61850.security.oauth2.jwks` | JWKS endpoint fetch and key cache |
| `ws61850.security.oauth2.validator` | JWT decode and claim validation |
| `ws61850.asn1.encode_decode` | BER encoding / decoding |
| `ws61850.shared.tree_render` | ASCII tree rendering |

The third-party `websockets` library emits its own log records under `websockets.server`. `PassiveEndpoint` suppresses its `INFO`-level "connection opened/closed" records by default (a `logging.Filter` is installed on that logger during `start()`).

---

## Log levels by layer

### `DEBUG`

Emitted for per-message and per-request detail that is noisy in normal operation. Enable only when tracing a specific handshake or data exchange.

| Logger | What triggers it |
|---|---|
| `ws61850.endpoint.passive_endpoint` | Dispatching to server/client (`cp=`), BER encoding selected, token expiry task scheduled, association control message type |
| `ws61850.endpoint.active_endpoint` | Same events in active session |
| `ws61850.endpoint.association_handler` | Raw decoded association message; token claims after refresh |
| `ws61850.transport.reconnect` | Retry counter reset after successful connection |
| `ws61850.iec61850.client.iec61850_client` | Response queued (invoke_id, msg_type), select/operate call entry, directory call entry, per-service response detail |
| `ws61850.iec61850.server.iec61850_server` | Association message type, service request dispatch (service name, invoke_id) |
| `ws61850.security.oauth2.jwks` | JWKS fetch initiated, keys cached, cache miss (kid) |
| `ws61850.security.oauth2.validator` | Token accepted (kid, alg, sub, exp) |

### `INFO`

Normal operational events. Suitable for production with `INFO` level.

| Logger | What triggers it |
|---|---|
| `ws61850.endpoint.passive_endpoint` | Server started (`host:port`), server stopped, OAuth token accepted/rejected, client connected/disconnected, client flags cleared |
| `ws61850.endpoint.active_endpoint` | URI being connected, connection established, connection closed (gracefully or unexpectedly with code/reason), client flags cleared |
| `ws61850.endpoint.association_handler` | Association aborted (`associate_id`), association released (`associate_id`) |
| `ws61850.endpoint.connection_router` | Connection failed — access point not available |
| `ws61850.transport.reconnect` | Reconnect attempt number and delay |
| `ws61850.iec61850.client.iec61850_client` | Association established (`associate_id`), connection closed while awaiting response |
| `ws61850.iec61850.server.iec61850_server` | Association request received, release/abort received, GI sent after value set, report task stopped |

### `WARNING`

Unexpected-but-recoverable events: bad protocol state, rejected tokens, timed-out calls, unsupported message types.

| Logger | What triggers it |
|---|---|
| `ws61850.endpoint.passive_endpoint` | Missing/malformed `Authorization` header, token rejected |
| `ws61850.endpoint.active_endpoint` | Unexpected message type in association loop |
| `ws61850.endpoint.association_handler` | Unrecognised token refresh response code |
| `ws61850.endpoint.connection_router` | `cp` not found in registered objects |
| `ws61850.transport.reconnect` | Max retries reached — giving up |
| `ws61850.iec61850.client.iec61850_client` | Response timeout, select/operate service error, no response received |
| `ws61850.iec61850.server.iec61850_server` | Unsupported association type, unsupported service name |
| `ws61850.security.oauth2.validator` | Token expired, token invalid (signature, claims) |

### `ERROR`

Conditions that broke a connection or prevented normal operation.

| Logger | What triggers it |
|---|---|
| `ws61850.endpoint.passive_endpoint` | Error stopping server, JWKS fetch or decode error, JWT validator not configured when `oauth_enable=True`, unhandled exception in connection handler |
| `ws61850.endpoint.active_endpoint` | Connection refused / OS error (logged as WARNING during retries), unexpected error in active session |
| `ws61850.security.oauth2.jwks` | No JWKS key found for `kid` after refresh |
| `ws61850.iec61850.client.iec61850_client` | Error scanning outstanding calls |
| `ws61850.iec61850.server.iec61850_server` | Error in report send or periodic report task |

---

## Configuring log output

### Minimal setup (scripts and integration tests)

```python
import logging, sys

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    stream=sys.stdout,
)
```

This is the pattern used in all integration test scripts. It enables all `ws61850` loggers at `DEBUG` and writes to stdout.

### Production / library use

`ws61850` follows the standard library convention: it never configures any handlers or levels itself. Applications are responsible for configuring the root logger or the `ws61850` logger tree.

To get `INFO`-level output from `ws61850` without touching the rest of your application's logging:

```python
logging.getLogger("ws61850").setLevel(logging.INFO)
```

To silence the endpoint layer entirely while keeping application-level logs:

```python
logging.getLogger("ws61850.endpoint").setLevel(logging.WARNING)
```

### Suppressing `websockets` server noise

`PassiveEndpoint` automatically installs a filter on the `websockets.server` logger during `start()` to suppress `INFO`-level connection-open/close messages from the `websockets` library. No application-side configuration is needed. If you do want those records, set the `websockets.server` logger level explicitly:

```python
logging.getLogger("websockets.server").setLevel(logging.DEBUG)
```

### Example: INFO for ws61850, DEBUG for endpoint only

```python
logging.basicConfig(level=logging.WARNING)                       # quiet everything else
logging.getLogger("ws61850").setLevel(logging.INFO)              # normal ws61850 events
logging.getLogger("ws61850.endpoint").setLevel(logging.DEBUG)    # full endpoint trace
```
