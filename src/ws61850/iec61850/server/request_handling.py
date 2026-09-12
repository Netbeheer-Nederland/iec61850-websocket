# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
#
# Copyright 2025 Netbeheer Nederland
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import json
import logging
import re

from ws61850.iec61850.data_model.ied_model import (
    DataAttribute,
    DataAttributeType,
    DataObject,
    DataSet,
    IedModel,
    LogicalDevice,
    LogicalNode,
)
from ws61850.shared.refs import build_fcd_ref
from ws61850.shared.tree_render import print_direct_da, print_node, print_node_da, print_structure
from ws61850.shared.extractors import (
    extract_acsiType,
    extract_associate_request_type,
    extract_brcb_ref,
    extract_data_ref,
    extract_dataAttrVal,
    extract_ds_ref,
    extract_includeElementName,
    extract_invoke_id,
    extract_ld_name,
    extract_ln_ref,
    extract_max_message_size,
    extract_ref,
    extract_service_name,
    extract_urcb_ref,
    retrieve_associate_id,
    retrieve_associate_id_from_decoded_msg,
    retrieve_max_message_size,
    retrieve_max_outstanding_calls_from_decoded_msg,
)

logger = logging.getLogger(__name__)


def retrieve_lns(response_raw):
    """
    Extracts the name of the logical node in a getLogicalDeviceDirectory response
    """
    response = json.loads(response_raw)
    ln_refs = response["response"]["service"]["getLogicalDeviceDirectory"]["lnRef"]
    return ln_refs


def retrieve_ld_list(response_raw):
    """
    Extracts the name of logical devices from getServerDirectory response
    """
    response = json.loads(response_raw)
    ld_refs = response["response"]["service"]["getServerDirectory"]["response"]
    return ld_refs


def retrieve_ln_items(response_raw):
    """
    Extracts the name of the items in a logical node from getLogicalNodeDirectory response
    """
    response = json.loads(response_raw)
    ld_refs = response["response"]["service"]["getLogicalNodeDirectory"]["instanceNames"]
    return ld_refs


def retrieve_ds_items(response_raw):
    """
    Extracts the name of the datasets in a logical node from getDataSetDirectory response
    """
    response = json.loads(response_raw)
    ds_refs = response["response"]["service"]["getDataSetDirectory"]["dsMemberRef"]
    return ds_refs




def retrieve_sdos(response_raw):
    """
    Extracts the name of sub data attributes from getDataDefinition response
    """
    response = json.loads(response_raw)
    sdos = response["response"]["service"]["getDataDefinition"]["subDataDefinition"]
    sdo_names = [sdo["name"] for sdo in sdos]
    return sdo_names


def retrieve_das(response_raw):
    """
    Extracts the name of the dataAttribute definitions from getDataDefinition response
    """
    response = json.loads(response_raw)
    das = response["response"]["service"]["getDataDefinition"]["dataAttributeDefinition"]
    return das


def retrieve_attributes_sdo(response_raw, sdo_name):
    """
    Extracts the dataAttributeDefinition for each sub data object from getDataDefinition response
    """
    da_refs = []
    response = json.loads(response_raw)
    sdos = response["response"]["service"]["getDataDefinition"]["subDataDefinition"]
    for sub in sdos:
        if sub["name"] == sdo_name:
            da_def = sub["dataAttributeDefinition"]
            for da_index, da in enumerate(da_def):
                print_node_da(da_index, da["daRef"], len(da_refs), 0, True)
                if next(iter(da["daType"])) == "structure":
                    structure_list = next(iter(da["daType"].values()))
                    print_structure(structure_list, da_index, len(da_refs), 1)






def get_list_of_items_ln(ln_ref, asci_service, ied: IedModel):
    """
    Returns the list of requested items from the logical node in getLogicalNodeDirectory
    """
    return_list = []
    ld_name, ln_name = re.split(r"[/]", ln_ref)
    foundLD: LogicalDevice = next((ld for ld in ied.logical_devices if ld.name == ld_name), None)
    if foundLD:
        foundLN: LogicalNode = next((ln for ln in foundLD.logical_nodes if ln.name == ln_name), None)
        if foundLN:
            if asci_service == "dataObject":
                return_list = [do.name for do in foundLN.data_objects]
            elif asci_service == "dataset":
                return_list = [ds.name for ds in foundLN.data_sets]
            elif asci_service == "urcb":
                return_list = [
                    rcb.name
                    for rcb in foundLN.rcbs
                    if rcb.get_objRef().startswith(f"{ld_name}/{ln_name}.") and rcb.buffered == False
                ]
            elif asci_service == "brcb":
                return_list = [
                    rcb.name
                    for rcb in foundLN.rcbs
                    if rcb.get_objRef().startswith(f"{ld_name}/{ln_name}.") and rcb.buffered == True
                ]
            return return_list
    return None




def find_do_with_ref(data_ref, ied):
    """
    Finding a Data Object from IED tree using its object reference
    """
    return_do = None
    ld_name, ln_name, first_do, *seg_ref = re.split(r"[/ .]", data_ref)
    foundLD: LogicalDevice = next((ld for ld in ied.logical_devices if ld.name == ld_name), None)
    if foundLD:
        foundLN: LogicalNode = next((ln for ln in foundLD.logical_nodes if ln.name == ln_name), None)
        if foundLN:
            foundDO = next((do for do in foundLN.data_objects if do.name == first_do), None)
            if len(seg_ref) != 0:
                if foundDO:
                    inner_do: DataObject = foundDO
                    for i in range(0, len(seg_ref)):
                        inner_do = next(
                            (do for do in inner_do.get_do_from_do_or_da_list() if do.name == seg_ref[i]), None
                        )
                    return_do = inner_do

            else:
                return_do = foundDO

    return return_do, seg_ref


def look_in_da_or_do_list(seg_ref, foundDO):
    """
    Find an item in a Data Object do_or_da_list
    """
    found_obj = foundDO
    for ref_index, ref_item in enumerate(seg_ref):
        if isinstance(found_obj, DataObject):
            found_item = next(
                (
                    item
                    for item in found_obj.get_do_from_do_or_da_list() + found_obj.get_da_from_do_or_da_list()
                    if item.name == ref_item
                ),
                None,
            )
        else:
            found_item = next((item for item in found_obj.data_attributes if item.name == ref_item), None)
        if found_item is not None:
            found_obj = found_item
            if ref_index == len(seg_ref):
                return found_obj
            else:
                continue
        else:
            return None
    return found_obj


def find_ds_in_tree(data_ref, ied):
    """
    Find a DataSet in the IED tree
    """
    ld_name, ln_name, ds_name = re.split(r"[/ .]", data_ref)
    for ld in ied.logical_devices:
        if ld.name != ld_name:
            continue
        for ln in ld.logical_nodes:
            if ln.name != ln_name:
                continue
            return next((ds for ds in ln.data_sets if ds.name == ds_name), None)
    return None


def find_object_in_tree(data_ref, ied):
    """
    Find a DataObject or DataAttribute in the IED tree
    """
    return_do = None
    ld_name, ln_name, first_do, *seg_ref = re.split(r"[/ .]", data_ref)
    foundLD: LogicalDevice = next((ld for ld in ied.logical_devices if ld.name == ld_name), None)
    if foundLD:
        foundLN: LogicalNode = next((ln for ln in foundLD.logical_nodes if ln.name == ln_name), None)
        if foundLN:
            foundDO = next((do for do in foundLN.data_objects if do.name == first_do), None)
            if len(seg_ref) != 0:
                return_do = look_in_da_or_do_list(seg_ref, foundDO)

            else:
                return_do = foundDO

    return return_do




def extract_operate_or_select_ref(tpaa_tuple):
    """
    Extracts the ref from a TPAA request operate or select tuple.
    Assumes structure:
    ("request", { ..., "service": ("select/operate", {"UrcbRef": "rcb1"}) })
    """
    try:
        service = tpaa_tuple[1]["service"]
        return service[1]["ref"]
    except (IndexError, KeyError, TypeError) as e:
        raise ValueError("Invalid TPAA structure for dataRef") from e


def extract_ctlVal_from_operate_request(tpaa_tuple):
    """
    Extracts the ctlVal from a TPAA request tuple.
    Assumes structure:
    ("request", { ..., "service": ("operate", {"ctlVal": ...}) })
    """
    try:
        service = tpaa_tuple[1]["service"]
        return service[1]["ctlVal"]
    except (IndexError, KeyError, TypeError) as e:
        raise ValueError("Invalid TPAA structure for dataRef") from e


def create_subDataDefinition_list(subDo_list):
    """
    Create the list of sub data definition to use inside getDataDefinition Response
    """
    return_list = []
    primary_da = []
    for sdo_item in subDo_list:
        input_data = {
            "name": sdo_item.name,
            "cdc": sdo_item.cdc,
            "count": sdo_item.elementCount,
            "dataAttributeDefinition": create_DataAttributeDefinition_list(sdo_item.get_da_from_do_or_da_list()),
        }
        primary_da.extend(sdo_item.get_da_from_do_or_da_list())
        return_list.append(input_data)
        # return_list.append(create_DataAttributeDefinition_list(da_list))
    return return_list, primary_da


def create_DataAttributeDefinition_list(da_list):
    """
    Create the list of data attribute definition to use inside getDataDefinition Response
    """

    return_list = []
    # return_dict = {}

    for da_item in da_list:
        value = None

        if da_item.attr_type.name != "structure":
            value = None
        else:
            value = get_structure_value_def(da_item)

        input_data = {"daRef": da_item.name, "fc": da_item.fc.wire_name, "daType": (da_item.attr_type.name, value)}
        return_list.append(input_data)
    # return_dict['dataAttributeDefinition'] = return_list
    return return_list


def get_octetString_size(mmsValue):
    """
    Get the size of an Octet String
    """
    if mmsValue is None:
        return 0
    else:
        return len(mmsValue)


def get_structure_value_def(da_item: DataAttribute):
    """
    Create the list of data attribute definition of structures to use inside getDataDefinition Response
    """
    value = None
    input_data = []
    if len(da_item.data_attributes) != 0:
        for da_interal in da_item.data_attributes:
            if da_interal.attr_type.name != "structure" and da_interal.attr_type.name != "octetString":
                value = None
            elif da_interal.attr_type.name != "structure" and da_interal.attr_type.name == "octetString":
                value = get_octetString_size(da_interal.mms_value)
            else:
                value = get_structure_value_def(da_interal)
            input_data.append({"cmpName": da_interal.name, "cmpType": (da_interal.attr_type.name, value)})

    return input_data


def get_structure_value(da_item: DataAttribute, include_element_name):
    """
    Create the list of data attribute value of structures to use inside getDataValues Response
    """

    value = None
    # input_data = []
    value_list = []
    # return_obj = None
    if len(da_item.data_attributes) != 0:
        for da_interal in da_item.data_attributes:
            if da_interal.attr_type.name != "structure":
                value = da_interal.mms_value
            else:
                value = get_structure_value(da_interal, include_element_name)

            value_list.append((da_interal.attr_type.name, value))

    return_obj = {"data": value_list}
    return return_obj


def set_structure_value(da_item: DataAttribute, structured_value):
    """
    Function used for setting values to structured values in setDataValues
    """
    data_field = structured_value[1]
    data = data_field["data"]
    if data[0][0] == "structure":
        set_structure_value(da_item, data[0])
    else:
        da_item.mmsValue = data[0][1]


def set_struct_val(item, value):
    """
    Function used for setting values to more complex structs
    """
    if len(item.data_attributes) == 0:
        if value[0] != "structure" and value[0] != "check":
            item.mmsValue = value[1]
    else:
        for da_index, da_item in enumerate(item.data_attributes):
            if da_item.type != DataAttributeType.structure and da_item.type != DataAttributeType.check:
                da_item.mmsValue = value[1]["data"][da_index][1]
            else:
                logger.info("detected_structure or check : ", da_item.get_objRef())
                set_struct_val(da_item, value[1]["data"][da_index])


def set_check_val(item, value):
    """
    Function used for setting value to DataAttribute of type Check
    """
    for da_index, da_item in enumerate(item.data_attributes):
        da_item.mmsValue = value[1][da_item.name]

def convert_value(type_name, raw_str, TYPE_MAP):
    expected_type = TYPE_MAP.get(type_name)
    if expected_type is None:
        print(f"Unknown type: {type_name}")
        return False, None

    if expected_type is bool:
        if raw_str is str:
            if raw_str.lower() in ("true", "1"):
                return True, True
            elif raw_str.lower() in ("false", "0"):
                return True, False
            else:
                print(f"Cannot convert '{raw_str}' to bool")
                return False, None
        else:
            return True, bool(raw_str)

    if expected_type is int:
        try:
            return True, int(raw_str)
        except (ValueError, TypeError):
            print(f"Cannot convert '{raw_str}' to int")
            return False, None

    if expected_type is float:
        try:
            return True, float(raw_str)
        except (ValueError, TypeError):
            print(f"Cannot convert '{raw_str}' to float")
            return False, None

    if expected_type is bytes:
        try:
            return True, bytes.fromhex(raw_str)  # adjust if not hex-encoded
        except (ValueError, TypeError):
            print(f"Cannot convert '{raw_str}' to bytes")
            return False, None

    if expected_type is str:
        return True, raw_str  # already a string

    if expected_type is list:
        print(f"No defined conversion for {type_name} (list) from string '{raw_str}'")
        return False, None

    return False, None

def assign_da_item(item, value, fc):
    """
    Used to assign values to Data Attributes
    """
    if len(item.data_attributes) == 0:
        if value[0] != "structure" and value[0] != "check":
            print("checking item_attr_type: ", item.attr_type.name, " and value: ", value[0])
            if item.attr_type.name == value[0] and item.fc.wire_name == fc:

                TYPE_MAP = {
                    "boolean": bool,
                    "int8": int,
                    "int16": int,
                    "int24": int,
                    "int32": int,
                    "int64": int,
                    "int8u": int,
                    "int16u": int,
                    "int24u": int,
                    "int32u": int,
                    "float32": float,
                    "octetString": bytes,
                    "visString64": str,
                    "visString129": str,
                    "visString255": str,
                    "array": list,
                    "bitstring": list,  # or int/str depending on how you represent bits
                    "generalizedtime": str,  # or datetime, depending on how you parse it
                    "binarytime": str,  # or datetime/time
                    "quality": int,  # or a custom Quality class/bitmask
                    "timeStamp": str,  # or datetime
                    "enumerated": int,
                }

                converted, converted_val = convert_value(item.attr_type.name, value[1], TYPE_MAP)

                if converted is False:
                    print(f"Type mismatch: '{value[1]}' is not valid for {item.attr_type.name}")
                    return False
                else:
                    if item.attr_type.name == value[0] and item.fc.wire_name == fc:
                        item.mms_value = converted_val
                print("printing value type: ", type(value[1]), " and expected type: ", TYPE_MAP[value[0]])

            else:
                return False
        elif value[0] == "structure":
            set_structure_value(item.data_attributes[0], value)
        else:
            set_check_val(item, value)
    else:
        for da_index, da_item in enumerate(item.data_attributes):
            if da_item.fc.wire_name == fc:
                if da_item.attr_type != DataAttributeType.structure and da_item.attr_type != DataAttributeType.check:
                    if da_item.attr_type.name == value[0]:
                        da_item.mms_value = value[1]
                    else:
                        return False

                elif da_item.attr_type == DataAttributeType.structure:
                    set_struct_val(da_item, value[1]["data"][da_index])
                else:
                    set_check_val(da_item, value[1]["data"][da_index])
    return True


def assign_do_item(item, value, fc):
    """
    Used for assigning values to Data Objects
    """
    results = []
    for da_do_index, da_do_item in enumerate(item.do_or_da):
        assign_result = True
        if isinstance(da_do_item, DataAttribute):
            assign_result *= assign_da_item(item.get_da_from_do_or_da_list()[da_do_index], value, fc)
        else:
            assign_result *= assign_do_item(item.data_attributes[da_do_index], value, fc)

        results.append(assign_result)
    return all(results)


def flatten_nested_data_attributes(object):
    """
    Flatten the list of nested data attributes
    """
    flat_list = []
    if isinstance(object, DataObject):
        for sub_do in object.get_do_from_do_or_da_list():
            for attr_ in sub_do.get_da_from_do_or_da_list():
                if attr_ not in flat_list:
                    logger.info(attr_.name)
                    flat_list.append(attr_)
        for attr in object.get_da_from_do_or_da_list():
            if attr not in flat_list:
                flat_list.append(attr)

    else:
        for attr in object.data_attributes:
            if attr not in flat_list:
                flat_list.append(attr)
                logger.info(attr.name)

    return flat_list


def flatten_nested_data_attributes_with_fc(object, fc):
    """
    Flatten the list of nested data attributes that have a specific FC
    """
    flat_list = []

    if isinstance(object, DataObject):
        for sub_do in object.get_do_from_do_or_da_list():
            for attr_ in sub_do.get_da_from_do_or_da_list():
                if attr_ not in flat_list and attr_.fc.wire_name == fc:
                    flat_list.append(attr_)
        for attr in object.get_da_from_do_or_da_list():
            if attr not in flat_list and attr.fc.wire_name == fc:
                flat_list.append(attr)

    else:
        for attr in object.data_attributes:
            if attr not in flat_list and attr.fc == fc:
                flat_list.append(attr)

    return flat_list


def build_data_value(da: DataAttribute, type, value, include_element_name):
    """Creates a data value entry for getDataValues responses."""
    if da.attr_type == DataAttributeType.structure:
        value = get_structure_value(da, include_element_name)
    value = (type, value)
    if include_element_name:
        return {"name": da.name, "data": value}
    return {"data": value}


def build_data_obj_value(do: DataObject, value, include_element_name):
    """Creates a data value entry for structured Data Objects."""
    if include_element_name:
        return {"name": do.name, "data": ("structure", value)}
    return_item = {"data": ("structure", value)}
    return ("structure", return_item)


def assign_brcb_value(server_brcb, values, iec61850_server):
    """
    Function used for assigning values to brcb item
    """
    brcb = server_brcb.rcb
    try:
        brcb.obj_ref = brcb.get_objRef()
        if "bufTm" in values:
            brcb.buffered_time = values["bufTm"]

        if "dataSet" in values:
            brcb.dataset_name = values["dataSet"]

        if "gi" in values:
            brcb.gi = values["gi"]

        if "intgPd" in values:
            brcb.int_period = values["intgPd"]

        if "optFlds" in values:
            brcb.opt_flds = values["optFlds"]

        if "rptEna" in values:
            task, cancellation_check = check_for_task_cancellation(
                server_brcb.rptEna, values["rptEna"], server_brcb.rcb.get_objRef()
            )

            server_brcb.rptEna = values["rptEna"]
            if task is not None and cancellation_check == True:
                restart_report_task(task, server_brcb, iec61850_server)

        if "rptID" in values:
            brcb.rpt_id = values["rptID"]

        if "trgOp" in values:
            brcb.trg_ops = values["trgOp"]

        if "entryID" in values:
            server_brcb.entry_id = values["entryID"]

        if "purgeBuf" in values:
            server_brcb.purge_buff = values["purgeBuf"]

        if "rsvdTimeSec" in values:
            server_brcb.rsvdTimeSec = values["rsvdTimeSec"]
        return "ok"
    except (AttributeError, TypeError, ValueError, KeyError):
        return "failure"


def check_for_task_cancellation(old_value, new_value, obj_ref):
    """
    Function used for finding the task that has to be canceled when rptEna is changed from True to False
    """
    if new_value == False and old_value == True:
        for task in asyncio.all_tasks():
            if task.get_name() == obj_ref:
                return task, True
    return None, False


async def restart_report_task(task, server_rcb, iec61850_server):
    logger.info("canceling the task with this name:", task.get_name())
    task.cancel()
    try:
        await task  # <-- wait until it's really cancelled
    except asyncio.CancelledError:
        logger.info("Task cancelled successfully:", task.get_name())

    asyncio.create_task(iec61850_server.periodic_report_task(server_rcb), name=server_rcb.rcb.get_objRef())


def assign_urcb_value(server_urcb, values, iec61850_server):
    """
    Function used for assigning values to urcb item
    """
    try:
        urcb = server_urcb.rcb
        urcb.obj_ref = values["urcbRef"]

        if "bufTm" in values:
            urcb.buffered_time = values["bufTm"]

        if "dataSet" in values:
            urcb.dataset_name = values["dataSet"]

        if "gi" in values:
            urcb.gi = values["gi"]

        if "intgPd" in values:
            urcb.int_period = values["intgPd"]

        if "optFlds" in values:
            urcb.opt_flds = values["optFlds"]

        if "rptEna" in values:
            task, cancellation_check = check_for_task_cancellation(
                server_urcb.rptEna, values["rptEna"], server_urcb.rcb.get_objRef()
            )

            server_urcb.rptEna = values["rptEna"]
            if task is not None and cancellation_check == True:
                server_urcb.seq_num = 0
                server_urcb.resv = False
                restart_report_task(task, server_urcb, iec61850_server)
        if "rptID" in values:
            urcb.rpt_id = values["rptID"]

        if "trgOp" in values:
            urcb.trg_ops = values["trgOp"]

        if "resv" in values:
            server_urcb.resv = values["resv"]

        return "ok"
    except (AttributeError, TypeError, ValueError, KeyError) as e:
        logger.info("error in assign urcb values is: ", e)
        return "failure"


def create_data_attribute_list_from_dataset(dataset: DataSet, ied, reason_for_inclusion_in_log):
    """
    Creates a list of dataAttributes for when a report needs it
    """
    return_list = []
    for dataset_entry in dataset.fcdas:
        item = find_object_in_tree(dataset_entry.variable_name, ied)
        if isinstance(item, DataAttribute):
            if item.fc == dataset_entry.fc:
                if item.attr_type.name != "structure":
                    return_list.append(
                        {
                            "dataRef": item.get_objRef(),
                            "value": [{"data": (item.attr_type.name, item.mms_value)}],
                            "reasonCode": reason_for_inclusion_in_log.get_true_values_dict(),
                        }
                    )
                else:
                    struct_value = get_structure_value(item, False)
                    val = {"data": ("structure", struct_value)}

                    return_list.append(
                        {
                            "dataRef": item.get_objRef(),
                            "value": [val],
                            "reasonCode": reason_for_inclusion_in_log.get_true_values_dict(),
                        }
                    )

        else:
            for data_attribute in item.get_da_from_do_or_da_list():
                if data_attribute.fc == dataset_entry.fc:
                    if data_attribute.attr_type.name != "structure":
                        return_list.append(
                            {
                                "dataRef": data_attribute.get_objRef(),
                                "value": [{"data": (data_attribute.attr_type.name, data_attribute.mms_value)}],
                                "reasonCode": reason_for_inclusion_in_log.get_true_values_dict(),
                            }
                        )
                    else:
                        struct_value = get_structure_value(data_attribute, False)
                        val = {"data": ("structure", struct_value)}

                        return_list.append(
                            {
                                "dataRef": data_attribute.get_objRef(),
                                "value": [val],
                                "reasonCode": reason_for_inclusion_in_log.get_true_values_dict(),
                            }
                        )

    return return_list


def create_signle_entry_for_report(item, reason_for_inclusion_in_log):
    """
    Creates report appropriate single entry
    """
    if item.attr_type.name != "structure":
        return {
            "dataRef": item.get_objRef(),
            "value": [{"data": (item.attr_type.name, item.mms_value)}],
            "reasonCode": reason_for_inclusion_in_log.get_true_values_dict(),
        }
    else:
        struct_value = get_structure_value(item, False)
        val = {"data": ("structure", struct_value)}

        return {
            "dataRef": item.get_objRef(),
            "value": [val],
            "reasonCode": reason_for_inclusion_in_log.get_true_values_dict(),
        }


def get_structure_value_ds(da_item: DataAttribute):
    """
    Create the list of data attribute value of structures to use inside getDataValues Response
    """

    value = None
    return_obj = None
    if len(da_item.data_attributes) != 0:
        for da_interal in da_item.data_attributes:
            if da_interal.attr_type.name != "structure":
                value = da_interal.mms_value
            else:
                value = get_structure_value_ds(da_interal)

            return_obj = (da_interal.attr_type.name, value)

    return return_obj


def build_dataset_value(da: DataAttribute, type, value):
    """
    Creating the data values to use in getDataValues Response
    """
    if da.attr_type == DataAttributeType.structure:
        value = get_structure_value(da, True)

    return_value = (type, value)
    return return_value


def create_tpaa_release_request(invoke_id, associate_id):
    """
    Creates a Two-Party Application Association release request between two applications to initiate the termination of an existing association.
    """
    return (
        "associate",  # TpaaPdu CHOICE
        (
            "service",  # AssociateType CHOICE
            (
                "releaseRequest",  # AssociateServiceType CHOICE
                {
                    "invokeId": invoke_id,
                    "associateId": associate_id,
                    # Add more fields if required
                },
            ),
        ),
    )


def create_tpaa_abort_request(invoke_id, associate_id):
    """
    Creates a Two-Party Application Association release request between two applications to initiate the termination of an existing association.
    """
    return (
        "associate",  # TpaaPdu CHOICE
        (
            "service",  # AssociateType CHOICE
            (
                "abortRequest",  # AssociateServiceType CHOICE
                {
                    "invokeId": invoke_id,
                    "associateId": associate_id,
                    # Add more fields if required
                },
            ),
        ),
    )
