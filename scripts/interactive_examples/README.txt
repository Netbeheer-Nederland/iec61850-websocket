By running the console_app.py, the user can use a terminal to send requests and receive the respective responses. Running this example will establish a websocket connection between IEC61850 Server(WS Client) and IEC61850 Client(WS Server). It is also possible to run ws_server.py and ws_client.py separately for more comprehensible logs.  
For the requests to be sent correctly and without error, it is important to follow the exact template of each command. A list of supported services and an example of their usage is mentioned in this document.

*get_server_directory():
example: get_server_directory()

*get_logical_device_directory(ld_name:str)
example: get_logical_device_directory("LD0")

*get_logical_node_directory(ld_name:str, ln_name:str, mode:str=dataset/dataObject)
example: get_logical_node_directory("LD0", "LLN0", "dataObject")

*get_data_definition(object_reference:str)
example: get_data_definition("LD0/LLN0.Mod")

*get_data_values(object_reference:str, fc:str, includeElementName:bool)
example: get_data_values("LD0/DWMX1.WMaxSpt.Oper", "co", False)

*select(object_reference:str)
example: select("LD0/DWMX1.WMaxSpt")

*operate(object_reference:str, type:str, value)
example: operate("LD0/DWMX1.WMaxSpt", "float32", 43.1)

*get_dataset_directory(ld_name:str, ln_name:str, ds_name:str)
example: get_dataset_directory("LD0", "LLN0", "DataSetSetpoints")

*set_data_values(object_reference, fc, type, value)
example: set_data_values("LD0/MMXU1.MaxWPhs.mag.f", "mx", "float32", 13.0)
Note: In this mode, only value of a single non-structured data attribute value can be set; i.e. only the value of a single Boolean, int, float, ... can be set with a single command. 
It is necessary to import the type of the data attribute to be set, e.g. "float32", "int16", ....

*get_dataset_values(ld_name:str, ln_name:str, ds_name:str)
example:get_dataset_values("LD0", "LLN0", "DataSetSetpoints")

*get_BRCB_values(object_reference:str)
example: get_BRCB_values("LD0/LLN0.rcbMinMaxAvg")

*get_URCB_values(object_reference:str)
example: get_URCB_values("LD0/LLN0.rcbActualValues")

*set_BRCB_valuse(object_reference:str, object=value)
example: set_BRCB_values("LD0/LLN0.rcbMinMaxAvg", rptId="new_id_7")
Note: it is important to correctly input the expected value of the object that is being set, for example, if entryID which is of type octet string is to be set, the value should be of form 
octetString: b"value"
Note: Only and only one value can be set with one command, so it is important to only add one "object=value" to the command.

*set_URCB_values(object_reference:str, object=value)
example: set_URCB_values("LD0/LLN0.rcbSetpoints", rptEna=True)
Note: it is important to correctly input the expected value of the object that is being set, for example, if entryID which is of type octet string is to be set, the value should be of form 
octetString: b"value"
Note: Only and only one value can be set with one command, so it is important to only add one "object=value" to the command.

