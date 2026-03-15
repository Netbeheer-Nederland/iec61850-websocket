# Overview

This folder contains some example code using the Python reference implementation of the WebSocket/JSON based IEC 61850
SCSM that has been developed as part of the RTI 2.0 project's PoC.

Also included are the test scripts and other materials (certificates, scripts, ...) required to execute the test cases.

Notes

## The examples

The getting started guide describes how to build and install the Python reference implementation of the WebSocket/
JSON-based IEC 61850 SCSM. The reference data-models are also included in the distribution.

Run the setup instructions and run the examples from the project root directory:

## IEC61850 mode

Examples pairing: run matching client/server scripts from `examples/ws61850_mode` depending on the mode.

### “reversed” mode

The ws_client runs the IEC61850Server, and the ws_service runs the IEC61850Client in server

### “direct” mode:

The ws_server runs the IEC61850Server, and the ws_client runs the IEC61850Client

### Execute

Run from the project root directory

The websocket server and client run separately.

```bash
# start the websocket server
python examples/ws61850_mode/<mode>/ws_server.py
```

```bash
# start the websocket client
python examples/ws61850_mode/<mode>/ws_client.py
```

The mode is equal to the directory name.

## IEC61850 interactive

The interactive command line mode interface is also available.

See `examples/ws61850_interactive/README.md` for a dedicated runbook covering the interactive server, client, launcher,
supported commands, and troubleshooting:

- `examples/ws61850_interactive/README.md`: interactive IEC 61850 WebSocket example with a console prompt on the
  passive side that is enabled only while a client is connected

Running this example will establish a websocket connection between IEC61850 Server(WS Client) and IEC61850 Client(WS
Server). It is also possible to run ws_server.py and ws_client.py separately for more comprehensible logs.  
For the requests to be sent correctly and without error, it is important to follow the exact template of each command. A
list of supported services and an example of their usage is mentioned in this document.

### Supported services

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

## IEC61850 UI

For demonstration there is also a web-based GUI client tool and this takes two steps: first, the websocket server and
client is started,
second, the UI is started.

### Execute

First, start the websocket server and client together.

```bash
python examples/ws61850_interactive/console_app.py
```

Second, start the UI.

```bash
export PORT=5000   # optional; defaults to 5000
python examples/ws61850_interactive/app.py
```

Open `http://localhost:5000` in your browser.

### Connect from UI

Use the connection form:

- Host: IEC 61850 WebSocket server host
- Port: IEC 61850 WebSocket server port
- CP: CP path (e.g., `cp`)

Click "Connect" to start a client connection. The backend manages the endpoint/client lifecycle and logs recent actions
and messages.

Features:

- Build and browse the IED model tree (LD/LN).
- Monitor sent/received TPAA protocol messages.
- Optional TLS and OAuth support when configured on the server side.

Troubleshooting:

- Connection issues: verify server host/port and reachability;
- Check TLS/OAuth settings if enabled. (not yet in this example)
- Port conflicts: set `PORT` to a free port before starting the app.
