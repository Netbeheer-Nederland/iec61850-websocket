# Migration Guide: WebSocketEndpoint → PassiveEndpoint / ActiveEndpoint

## Summary

The original `WebSocketEndpoint` class has been split into two focused classes:

- `PassiveEndpoint` — WebSocket **server** role (listens for connections)
- `ActiveEndpoint` — WebSocket **client** role (connects outward)

`WebSocketEndpoint` still works unchanged as a backward-compatible shim. Migration is optional but recommended for new code.

---

## Before / After comparison

### WebSocket server (passive role)

**Before**

```python
from ws61850.endpoint.endpoint import WebSocketEndpoint
from ws61850.iec61850.client.iec61850_client import IEC61850Client

endpoint = WebSocketEndpoint()
client = IEC61850Client("cp1")
endpoint.add_iec61850_client(client)
await endpoint.start("passive", "localhost", 8765)
```

**After**

```python
from ws61850.endpoint.passive_endpoint import PassiveEndpoint
from ws61850.iec61850.client.iec61850_client import IEC61850Client

endpoint = PassiveEndpoint()
client = IEC61850Client("cp1")
endpoint.add_iec61850_client(client)
await endpoint.start("localhost", 8765)
```

Changes: import path, class name, `start()` drops the `"passive"` mode string.

---

### WebSocket client (active role)

**Before**

```python
from ws61850.endpoint.endpoint import WebSocketEndpoint
from ws61850.iec61850.server.iec61850_server import IEC61850Server

endpoint = WebSocketEndpoint()
server = IEC61850Server(ied_model, "cp1")
endpoint.add_iec61850_server(server)
await endpoint.start("active", "localhost", 8765, "cp1")
```

**After**

```python
from ws61850.endpoint.active_endpoint import ActiveEndpoint
from ws61850.iec61850.server.iec61850_server import IEC61850Server

endpoint = ActiveEndpoint()
server = IEC61850Server(ied_model, "cp1")
endpoint.add_iec61850_server(server)
await endpoint.start("localhost", 8765, "cp1")
```

Changes: import path, class name, `start()` drops the `"active"` mode string.

---

### Constructor arguments

All constructor arguments are the same keyword-only parameters. The only split is `try_reconnect` (and its siblings) which now live exclusively on `ActiveEndpoint` because reconnection is only meaningful for the client role.

| Argument | `PassiveEndpoint` | `ActiveEndpoint` |
|---|---|---|
| `tls_config` | yes | yes |
| `oauth_enable` | yes | yes |
| `is_direct` | yes | yes |
| `kc_cert` | yes | yes |
| `own_cert` | yes | yes |
| `cert_endpoint` | yes | yes |
| `token_issuer` | yes | yes |
| `try_reconnect` | — | yes (default `True`) |
| `max_retries` | — | yes (default `None`) |
| `retry_connection_delay` | — | yes (default `5.0`) |

---

### `access_token` is now keyword-only

In the old shim, `access_token` was the fifth positional argument to `start()`:

```python
# old — positional
await endpoint.start("active", "localhost", 8765, "cp1", access_token_value)
```

In `ActiveEndpoint.start()` it is keyword-only:

```python
# new — keyword
await endpoint.start("localhost", 8765, "cp1", access_token=access_token_value)
```

---

### Reconnect behaviour

The old `WebSocketEndpoint` contained an inline retry loop. `ActiveEndpoint` delegates to `ReconnectPolicy`. The behaviour is equivalent:

| Old pattern | New equivalent |
|---|---|
| `WebSocketEndpoint(try_reconnect=True)` | `ActiveEndpoint(try_reconnect=True)` (default) |
| `WebSocketEndpoint(try_reconnect=False)` | `ActiveEndpoint(try_reconnect=False)` |
| Manual `connect_with_retry()` helper | Remove it; `ActiveEndpoint` handles retries internally |

To limit retries:

```python
endpoint = ActiveEndpoint(try_reconnect=True, max_retries=5, retry_connection_delay=10.0)
```

---

### Reading `client_list` / `server_list` after construction

Both concrete classes expose `client_list` and `server_list` as plain lists. The pattern previously used with the shim still works:

```python
# old
ep_ws_server.client_list[0].ready_event.wait()
websocket_info = ep_ws_server.get_websocket_info(ep_ws_server.client_list[0])

# new — capture the object at registration time (preferred)
client = IEC61850Client("cp1")
endpoint.add_iec61850_client(client)
await client.ready_event.wait()
websocket_info = endpoint.get_websocket_info(client)
```

Capturing the object at registration time avoids index-based access and is clearer about which object you intend to use.

---

### Type annotations

If your code annotated variables as `WebSocketEndpoint`, update to `EndpointProtocol` for the widest compatibility:

```python
# old
from ws61850.endpoint.endpoint import WebSocketEndpoint
def configure(ep: WebSocketEndpoint) -> None: ...

# new
from ws61850.endpoint import EndpointProtocol
def configure(ep: EndpointProtocol) -> None: ...
```

`EndpointProtocol` is a `@runtime_checkable Protocol`, so `isinstance(endpoint, EndpointProtocol)` works at runtime.

---

## What does not change

- `add_iec61850_client()` / `add_iec61850_server()` — identical
- `get_websocket_info()` / `get_websocket_info_iec61850_server()` — identical
- `websocket_info_list` — identical
- `send_msg_callback` / `recv_msg_callback` — identical
- `WebSocketInfo` fields — identical
- `stop_passive()` — identical on `PassiveEndpoint`; no-op stub on `ActiveEndpoint`

---

## Keeping the shim

If you cannot migrate immediately, `WebSocketEndpoint` continues to work:

```python
from ws61850.endpoint.endpoint import WebSocketEndpoint  # deprecated, but functional
```

The shim simply forwards all calls to the appropriate concrete class after `start()` is called. There is no functional difference from the caller's perspective.
