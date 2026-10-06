# Examples

Example code for the `ws61850` library, the Python reference implementation of the WebSocket/JSON-based IEC 61850
SCSM developed for the RTI 2.0 proof of concept. Set up the project first (see
[docs/getting-started.md](../docs/getting-started.md)), then run the examples from the
repository root.

| Example | What it shows |
|---|---|
| [`ws61850_mode/`](#iec61850-mode) | The smallest complete exchange: one WebSocket server and one client script, in `direct` and `reverse` mode |
| [`ws61850_interactive/`](ws61850_interactive/README.md) | An interactive console on the passive side: type ACSI service calls and see the responses |
| [`rti-demo/`](rti-demo/README.md) | The full RTI demo: RTI-FSP, RTI-SO, BFF, React HMI and Raspberry Pi IO, locally or in Docker |

The example IED models are JSON files: `ws61850_mode/ied_model1.json`, `ws61850_mode/ied_model2.json` and
`ws61850_interactive/ied_model1.json`.

## IEC61850 mode

Matching client/server script pairs live in `examples/ws61850_mode/<mode>/`, where `<mode>` is the directory name:

| Mode      | `ws_server.py` (WebSocket server) | `ws_client.py` (WebSocket client) |
|-----------|-----------------------------------|-----------------------------------|
| `direct`  | runs the `IEC61850Server`         | runs the `IEC61850Client`         |
| `reverse` | runs the `IEC61850Client`         | runs the `IEC61850Server`         |

Run from the project root directory. The WebSocket server and client run in separate terminals; start the server
first.

```bash
# start the websocket server
uv run python examples/ws61850_mode/<mode>/ws_server.py
```

```bash
# start the websocket client
uv run python examples/ws61850_mode/<mode>/ws_client.py
```

## IEC61850 interactive

`ws61850_interactive` connects an IEC 61850 server (on the WebSocket client side) to an IEC 61850 client (on the
WebSocket server side) and opens a console on the passive side while the client is connected. Its
[README](ws61850_interactive/README.md) covers how to run it, the supported service commands with examples, and
troubleshooting.
