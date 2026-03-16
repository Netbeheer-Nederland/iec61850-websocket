# Interactive WebSocket IEC 61850 Example

## Scope

This document describes how to run the interactive example in `examples/ws61850_interactive`. The example starts:

- one passive WebSocket endpoint that exposes an interactive console
- one active WebSocket endpoint hosting an IEC 61850 server model

The current interactive flow is implemented by:

- `examples/ws61850_interactive/ws_server.py`
- `examples/ws61850_interactive/ws_client.py`

## What the example starts

`ws_server.py`:

- starts a passive endpoint on `localhost:8765`
- registers IEC 61850 clients `cp1` and `cp2`
- waits for `cp1` to connect
- enables an interactive console only while the client is connected
- lets you trigger IEC 61850 service calls manually from the terminal

`ws_client.py`:

- starts an active endpoint for `cp1`
- connects to `localhost:8765`
- hosts an IEC 61850 server model created by `build_model1()`
- installs a control handler for float control values

## Prerequisites

Install the project dependencies from the repository root:

```bash
uv sync
```

No Keycloak setup is required for this example.

No TLS certificate setup is required for this example.

## Supported configuration

The current interactive scripts use these fixed values:

| Setting               | Value         |
|-----------------------|---------------|
| WebSocket server host | `localhost`   |
| WebSocket server port | `8765`        |
| Passive-side clients  | `cp1`, `cp2`  |
| Active-side server    | `cp1`         |
| WebSocket transport   | plain `ws://` |

The current scripts do not expose command-line options or environment variables for these values.

## Run the passive side

Open a terminal in the repository root and start the passive endpoint:

```bash
uv run python examples/ws61850_interactive/ws_server.py
```

Current passive-side behavior:

- listens on `ws://localhost:8765`
- waits for `cp1` to become ready
- enables the console prompt after the client is connected
- disables the console prompt again when the client disconnects

The interactive server accepts commands such as:

```text
get_server_directory()
get_logical_device_directory("IED1")
get_data_definition("IED1/XCBRGenericIO/XCBR1.Pos")
get_data_values("IED1/XCBRGenericIO/XCBR1.Pos", None, None)
select("IED1/DSCH1.CSWI1.Pos")
operate("IED1/DSCH1.CSWI1.Pos", "stVal", 1)
set_data_values("IED1/XCBRGenericIO/XCBR1.Pos.stVal", None, "boolean", True)
```

Current command coverage in `ws_server.py` includes:

- server, logical device, and logical node directory reads
- data definition and data value reads
- dataset directory and dataset value reads
- `select` and `operate`
- `set_data_values`
- `get_BRCB_values`, `set_BRCB_values`
- `get_URCB_values`, `set_URCB_values`

## Run the active side

In another terminal, start the active endpoint:

```bash
uv run python examples/ws61850_interactive/ws_client.py
```

Current active-side behavior:

- connects as `cp1` to `localhost:8765`
- exposes the sample IEC 61850 model returned by `build_model1()`
- accepts float control values below `50`
- keeps the WebSocket connection active so the passive-side console can issue requests

## Expected result

When the example is configured correctly:

- the passive endpoint starts on `ws://localhost:8765`
- the active endpoint connects successfully as `cp1`
- the server logs show the client reaching the ready state
- the command prompt appears only after the client is connected
- entered IEC 61850 commands return responses in the passive-side logs

Useful log indicators:

- passive-side logs show the client connection and console enablement
- active-side logs show the `cp1` connection startup
- passive-side logs show results for the IEC 61850 service calls you enter

## Troubleshooting

If the peers do not connect:

- verify `ws_server.py` is running before `ws_client.py`
- verify both scripts still use `localhost:8765`
- verify no other process is already bound to port `8765`

If the prompt does not appear:

- verify the client reached the connected state
- verify you started `ws_server.py` directly
- note that the prompt is intentionally hidden until ws_client `cp1` is connected

If a control operation fails:

- verify the referenced control object exists in the sample model
- verify the float control value is below `50`

If a command returns an error:

- verify the object reference exists in `build_model1()`
- verify the command syntax matches the examples expected by `ws_server.py`

## Minimal run sequence

From the repository root:

```bash
uv sync
uv run python examples/ws61850_interactive/ws_server.py
```

In another terminal:

```bash
uv run python examples/ws61850_interactive/ws_client.py
```

## Supported services

* get_server_directory():<br>
  example: get_server_directory()


* get_logical_device_directory(ld_name:str)<br>
  example: get_logical_device_directory("LD0")


* get_logical_node_directory(ld_name:str, ln_name:str, mode:str=dataset/dataObject)<br>
  example: get_logical_node_directory("LD0", "LLN0", "dataObject")


* get_data_definition(object_reference:str)<br>
  example: get_data_definition("LD0/LLN0.Mod")


* get_data_values(object_reference:str, fc:str, includeElementName:bool)<br>
  example: get_data_values("LD0/DWMX1.WMaxSpt.Oper", "co", False)


* select(object_reference:str)<br>
  example: select("LD0/DWMX1.WMaxSpt")


* operate(object_reference:str, type:str, value)<br>
  example: operate("LD0/DWMX1.WMaxSpt", "float32", 43.1)


* get_dataset_directory(ld_name:str, ln_name:str, ds_name:str)<br>
  example: get_dataset_directory("LD0", "LLN0", "DataSetSetpoints")


* set_data_values(object_reference, fc, type, value)<br>
  example: set_data_values("LD0/MMXU1.MaxWPhs.mag.f", "mx", "float32", 13.0)

Note: In this mode, only value of a single non-structured data attribute value can be set; i.e. only the value of a
single Boolean, int, float, ... can be set with a single command.
It is necessary to import the type of the data attribute to be set, e.g. "float32", "int16", ....

* get_dataset_values(ld_name:str, ln_name:str, ds_name:str)<br>
  example:get_dataset_values("LD0", "LLN0", "DataSetSetpoints")


* get_BRCB_values(object_reference:str)<br>
  example: get_BRCB_values("LD0/LLN0.rcbMinMaxAvg")


* get_URCB_values(object_reference:str)<br>
  example: get_URCB_values("LD0/LLN0.rcbActualValues")


* set_BRCB_values(object_reference:str, object=value)<br>
  example: set_BRCB_values("LD0/LLN0.rcbMinMaxAvg", rptId="new_id_7")

Note: it is important to correctly input the expected value of the object that is being set, for example, if entryID
which is of type octet string is to be set, the value should be of form
octetString: b"value"
Note: Only and only one value can be set with one command, so it is important to only add one "object=value" to the
command.

* set_URCB_values(object_reference:str, object=value)<br>
  example: set_URCB_values("LD0/LLN0.rcbSetpoints", rptEna=True)

Note: it is important to correctly input the expected value of the object that is being set, for example, if entryID
which is of type octet string is to be set, the value should be of form
octetString: b"value"
Note: Only and only one value can be set with one command, so it is important to only add one "object=value" to the
command.