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

import json
import logging
import re

from ws61850.iec61850.data_model.ied_model import (
    DataAttribute,
    DataAttributeType,
    DataObject,
    IedModel,
    LogicalDevice,
    LogicalNode,
)

logger = logging.getLogger(__name__)


def retrieve_success(response):
    """
    Extracts the success from select/operate response
    """
    success = response[1]["service"][1]["success"]
    return success


def retrieve_lns(response):
    """
    Extracts the name of the logical node in a getLogicalDeviceDirectory response
    """
    ln_refs = response[1]["service"][1]["lnRef"]
    return ln_refs


def retrieve_lds(response):
    """
    Extracts the name of logical devices from getServerDirectory response
    """
    ld_refs = response[1]["service"][1]["result"]
    return ld_refs


def retrieve_ln_items(response):
    """
    Extracts the name of the items in a logical node from getLogicalNodeDirectory response
    """
    ln_items = response[1]["service"][1]["instanceNames"]
    return ln_items


def retrieve_service_name(response):
    """
    Extracts the name of the items in a logical node from getLogicalNodeDirectory response
    """
    service_name = response[1]["service"]
    return service_name


def retrieve_ds_items(response):
    """
    Extracts the name of the datasets in a logical node from getDataSetDirectory response
    """
    ds_refs = response[1]["service"][1]["dsMemberRef"]
    return ds_refs


def retrieve_ds_values(response):
    """
    Extracts the name of the datasets in a logical node from getDataSetDirectory response
    """
    ds_vals = response[1]["service"][1]["dsMemberValue"]
    return ds_vals


def retrieve_data_definition(response):
    """
    Extracts the data definition from a getDataDefinition response
    """
    da_def = response[1]["service"][1]
    return da_def


def retrieve_data_directory(response):
    """
    Extracts the data definition from a getDataDefinition response
    """
    da_dir = response[1]["service"][1]
    return da_dir


def retrieve_data_val(response):
    """
    Extracts the data value from getDataValues response
    """
    # response = json.loads(response_raw)
    da_def = response[1]["service"][1]["dataAttrVal"]
    return da_def


def retrieve_rcb_val(response):
    """
    Extracts rcb values from a getURCB/URCBValues response
    """
    rcb_val = response[1]["service"][1]
    return rcb_val


def retrieve_set_result(response):
    """
    Extracts the result of a set value from a response
    """
    val = response[1]["service"][1]["result"]
    return val


def retrieve_associate_id(response_raw):
    """
    Extracts association id from associateResponse
    """
    response = json.loads(response_raw)

    try:
        return response["associate"]["service"]["associateResponse"]["associateId"]
    except (KeyError, TypeError) as e:
        raise ValueError("Invalid structure for associateId extraction") from e


def retrieve_associate_id_from_decoded_msg(decoded_msg):
    """
    Extracts association id from associateResponse from a decoded message
    """
    try:
        return decoded_msg[1][1][1]["associateId"]
    except (KeyError, TypeError) as e:
        raise ValueError("Invalid structure for associateId extraction") from e


def retrieve_max_outstanding_calls_from_decoded_msg(decoded_msg):
    """
    Extracts association id from associateResponse from a decoded message
    """
    try:
        return decoded_msg[1][1][1]["maxOutstandingCalls"]
    except (KeyError, TypeError) as e:
        return 0
        # raise ValueError("Invalid structure for max outstanding calls extraction") from e


def retrieve_max_message_size(response_raw):
    """
    Extracts the max message size from associateResponse
    """
    response = json.loads(response_raw)
    try:
        return response["associate"]["service"]["associateResponse"]["maxMessageSize"]
    except (IndexError, KeyError, TypeError):
        raise ValueError("Invalid TPAA structure for maxMessageSize")


def retrieve_sdos(da_def):
    """
    Extracts the name of sub data attributes from getDataDefinition response
    """
    # response = json.loads(response_raw)
    sdos = da_def["subDataDefinition"]
    sdo_names = [sdo["name"] for sdo in sdos]
    return sdo_names


def retrieve_das(da_def):
    """
    Extracts the name of the dataAttribute definitions from getDataDefinition response
    """
    # response = json.loads(response_raw)
    das = da_def["dataAttributeDefinition"]
    return das


def retrieve_attributes_sdo(da_def, sdo_name):
    """
    Extracts the dataAttributeDefinition for each sub data object from getDataDefinition response
    """
    da_refs = []
    sdos = da_def["subDataDefinition"]
    for sub in sdos:
        if sub["name"] == sdo_name:
            da_def = sub["dataAttributeDefinition"]
            for da_index, da in enumerate(da_def):
                print_node_da(da_index, da["daRef"], len(da_refs), 0, True)
                # da_refs.append(da['daRef'])
                if next(iter(da["daType"])) == "structure":
                    structure_list = da["daType"][1]
                    print_structure(structure_list, da_index, len(da_refs), 1)


def print_node(index, item, last_index):
    """
    prints sdos in the reconstructed tree in the console
    """
    sdo_prefix = "          ├── " if index != last_index - 1 else "          └── "
    logger.info(f"{sdo_prefix}{item}")


def print_node_da(index, item, last_index, go_to_next_level, is_structure):
    """
    prints the data attributes in the reconstructed tree in the console
    """
    if is_structure:
        sdo_prefix = "               └── "
    else:
        sdo_prefix = "               ├── " if index != last_index - 1 else "               └── "
    if go_to_next_level > 0:
        logger.info(go_to_next_level * "     " + f"{sdo_prefix}{item}")
    else:
        logger.info(f"{sdo_prefix}{item}")


def print_structure(structure_list, item_index, list_len, go_to_next_level):
    """
    Prints structured items in the reconstructed tree in the console
    """
    for index, struct_item in enumerate(structure_list):
        if next(iter(struct_item["cmpType"])) != "structure":
            print_node_da(index, struct_item["cmpName"], len(structure_list), go_to_next_level, False)
        else:
            print_node_da(item_index, struct_item["cmpName"], len(structure_list), go_to_next_level, True)
            struct_item = struct_item["cmpType"][1]
            print_structure(struct_item, index, len(struct_item), 2)


def print_direct_da(da_list):
    """
    logger.info data attributes that are directly added to a direct Data Object (not a sub data object)
    """
    for da_index, da in enumerate(da_list):
        print_node_da(da_index, da["daRef"], len(da_list), 0, True)
        if next(iter(da["daType"])) == "structure":
            structure_list = da["daType"][1]
            print_structure(structure_list, da_index, len(da_list), 1)


def extract_associate_request_type(tpaa_tuple):
    """
    Extracts the request type from an associate TPAA tuple.
    Example input:
    ("associate", ("service", ("associateRequest", {...})))
    Returns: "associateRequest"
    """
    try:
        if tpaa_tuple[0] != "associate":
            raise ValueError("Not an 'associate' TPAA PDU")
        return tpaa_tuple[1][1][0]
    except (IndexError, TypeError) as e:
        raise ValueError("Invalid TPAA structure for associateRequest") from e


def extract_service_name(tpaa_tuple):
    """
    Extracts the service name from a TPAA tuple.
    Example input:
    ("response", { "invokeId": ..., "associateId": ..., "service": ("serviceName", {...}) })
    """
    try:
        return tpaa_tuple[1]["service"][0]
    except (IndexError, KeyError, TypeError) as e:
        raise ValueError("Invalid TPAA structure for service name") from e


def extract_invoke_id(tpaa_tuple):
    """
    Extracts the invoke id a TPAA tuple.
    Example input:
    ("response", { "invokeId": ..., "associateId": ..., "service": ("..., {...}) })
    """
    try:
        return tpaa_tuple[1]["invokeId"]
    except (IndexError, KeyError, TypeError) as e:
        raise ValueError("Invalid TPAA structure for service name") from e


def extract_ld_name(tpaa_tuple):
    """
    Extracts the ldName from a TPAA request tuple.
    Assumes structure:
    ("request", { ..., "service": ("getLogicalDeviceDirectory", {"ldName": "LD1"}) })
    """
    try:
        service = tpaa_tuple[1]["service"]
        return service[1]["ldName"]
    except (IndexError, KeyError, TypeError) as e:
        raise ValueError("Invalid TPAA structure for ldName") from e


def extract_ln_ref(tpaa_tuple):
    """
    Extracts the lnName from a TPAA request tuple.
    Assumes structure:
    ("request", { ..., "service": ("getLogicalNodeDirectory", {"lnRef": "LLN0"}) })
    """
    try:
        service = tpaa_tuple[1]["service"]
        return service[1]["lnRef"]
    except (IndexError, KeyError, TypeError) as e:
        raise ValueError("Invalid TPAA structure for ldName") from e


def extract_acsiType(tpaa_tuple):
    """
    Extracts the acsiType from a TPAA request tuple.
    Assumes structure:
    ("request", { ..., "service": ("getLogicalNodeDirectory", {"acsiType": "dataObject"}) })
    """
    try:
        service = tpaa_tuple[1]["service"]
        return service[1]["aCSIClass"]
    except (IndexError, KeyError, TypeError) as e:
        raise ValueError("Invalid TPAA structure for ldName") from e


def extract_ds_ref(tpaa_tuple):
    """
    Extracts the dataset reference from a TPAA request tuple.
    Assumes structure:
    ("request", { ..., "service": ("getDataSetDirectory", {"dsRef": "@Dataset1"}) })
    """
    try:
        service = tpaa_tuple[1]["service"]
        return service[1]["dsRef"]
    except (IndexError, KeyError, TypeError) as e:
        raise ValueError("Invalid TPAA structure for ldName") from e


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
                return_list = [ds.name for ds in ied.data_sets]
    return return_list


def extract_data_ref(tpaa_tuple):
    """
    Extracts the dataRef from a TPAA request tuple.
    Assumes structure:
    ("request", { ..., "service": ("getDataDirectory", {"dataRef": "LD0/LLN0.Mod"}) })
    """
    try:
        service = tpaa_tuple[1]["service"]
        return service[1]["dataRef"]
    except (IndexError, KeyError, TypeError) as e:
        raise ValueError("Invalid TPAA structure for dataRef") from e


def extract_ref(tpaa_tuple):
    """
    Extracts the ref from a TPAA request tuple.
    Assumes structure:
    ("request", { ..., "service": ("getDataValues", {"ref": "LD0/LLN0.Mod"}) })
    """
    try:
        service = tpaa_tuple[1]["service"]
        return service[1]["ref"]
    except (IndexError, KeyError, TypeError) as e:
        raise ValueError("Invalid TPAA structure for dataRef") from e


def extract_dataAttrVal(tpaa_tuple):
    """
    Extracts the dataAttrVal from a TPAA request tuple.
    Assumes structure:
    ("request", { ..., "service": ("setDataValues", {"dataAttrVal": ...}) })
    """
    try:
        service = tpaa_tuple[1]["service"]
        return service[1]["dataAttrVal"]
    except (IndexError, KeyError, TypeError) as e:
        raise ValueError("Invalid TPAA structure for dataRef") from e


def extract_includeElementName(tpaa_tuple):
    """
    Extracts the includeElementName from a TPAA request tuple of getDataValues.
    Assumes structure:
    ("request", { ..., "service": ("getDataValues", {"includeElementName": True}) })
    """
    try:
        service = tpaa_tuple[1]["service"]
        return service[1]["includeElementName"]
    except (IndexError, KeyError, TypeError) as e:
        raise ValueError("Invalid TPAA structure for dataRef") from e


def extract_max_message_size(tpaa):
    """
    Extracts the maxMessagesize from a TPAA request tuple
    """
    try:
        return tpaa[1][1][1]["maxMessageSize"]
    except (IndexError, KeyError, TypeError):
        raise ValueError("Invalid TPAA structure for maxMessageSize")


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
    Find a DataObject or DataAttribute in the IED tree
    """
    foundDS = None
    ld_name, ln_name, ds_name = re.split(r"[/ .]", data_ref)

    foundDS = next((ds for ds in ied.data_sets if ds.name == ds_name), None)
    return foundDS


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


def extract_brcb_ref(tpaa_tuple):
    """
    Extracts the brcbRef from a TPAA request tuple.
    Assumes structure:
    ("request", { ..., "service": ("getBRCBValues", {"brcbRef": "rcb1"}) })
    """
    try:
        service = tpaa_tuple[1]["service"]
        return service[1]["brcbRef"]
    except (IndexError, KeyError, TypeError) as e:
        raise ValueError("Invalid TPAA structure for dataRef") from e


def extract_urcb_ref(tpaa_tuple):
    """
    Extracts the urcbRef from a TPAA request tuple.
    Assumes structure:
    ("request", { ..., "service": ("getURCBValues", {"UrcbRef": "rcb1"}) })
    """
    try:
        service = tpaa_tuple[1]["service"]
        return service[1]["urcbRef"]
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
    return return_list, primary_da


def create_DataAttributeDefinition_list(da_list):
    """
    Create the list of data attribute definition to use inside getDataDefinition Response
    """

    return_list = []

    for da_item in da_list:
        value = None

        if da_item.type.name != "structure":
            value = None
        else:
            value = get_structure_value_def(da_item)

        input_data = {"daRef": da_item.name, "fc": da_item.fc.name, "daType": (da_item.type.name, value)}
        return_list.append(input_data)
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
            if da_interal.type.name != "structure" and da_interal.type.name != "octetString":
                value = None
            elif da_interal.type.name != "structure" and da_interal.type.name == "octetString":
                value = get_octetString_size(da_interal.mmsValue)
            else:
                value = get_structure_value_def(da_interal)
            input_data.append({"cmpName": da_interal.name, "cmpType": (da_interal.type.name, value)})

    return input_data


def get_structure_value(da_item: DataAttribute, include_element_name):
    """
    Create the list of data attribute value of structures to use inside getDataValues Response
    """

    value = None
    return_obj = None
    if len(da_item.data_attributes) != 0:
        for da_interal in da_item.data_attributes:
            if da_interal.type.name != "structure":
                value = da_interal.mmsValue
            else:
                value = get_structure_value(da_interal, include_element_name)
            if include_element_name:

                return_obj = {"name": da_interal.name, "data": [(da_interal.type.name, value)]}

            else:
                return_obj = {"data": [(da_interal.type.name, value)]}

    return return_obj


def set_structure_value(da_item: DataAttribute, structured_value):
    """
    Function used for setting values to structured values in setDataValues
    """
    data_field = structured_value[1]
    data = data_field["data"]
    if data[0][0] == "structure":
        set_structure_value(da_item.data_attributes[0], data[0])
    else:
        da_item.mmsValue = data[0][1]


def assign_da_item(item, value, fc):
    """
    Used to assign values to Data Attributes
    """
    if item.fc.name == fc:
        if value[0] != "structure":
            item.mmsValue = value[1]
        else:
            set_structure_value(item.data_attributes[0], value)


def assign_do_item(item, value, fc):
    """
    Used for assigning values to Data Objects
    """
    for da_do_index, da_do_item in enumerate(item.do_or_da):
        if isinstance(da_do_item, DataAttribute):
            assign_da_item(item.get_da_from_do_or_da_list()[da_do_index], value, fc)
        else:
            assign_do_item(item.data_attributes[da_do_index], value, fc)


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
                if attr_ not in flat_list and attr_.fc.name == fc:
                    logger.info(attr_.name)
                    flat_list.append(attr_)
        for attr in object.get_da_from_do_or_da_list():
            if attr not in flat_list and attr.fc.name == fc:
                flat_list.append(attr)

    else:
        logger.info("fdsgdghrgedg", type(object))
        for attr in object.data_attributes:
            if attr not in flat_list and attr.fc == fc:
                flat_list.append(attr)

    return flat_list


def build_fcd_ref(obj_ref, fc):
    """Building a fcda definition"""
    fcda_ref = {"ref": obj_ref, "fc": fc}
    return fcda_ref


def build_data_value(da: DataAttribute, type, value, include_element_name):
    """
    Creating the data values to use in getDataValues Response
    """
    if da.type == DataAttributeType.structure:
        value = get_structure_value(da, include_element_name)

    value = (type, value)
    if include_element_name:
        return_item = {"name": da.name, "data": value}
    else:
        return_item = {"data": value}
    return return_item


def build_data_obj_value(do: DataObject, value, include_element_name):
    """
    Creating the data values of structured values to use in getDataValues Response
    """
    if include_element_name:
        return_item = {"name": do.name, "data": ("structure", value)}
    else:
        return_item = {"data": ("structure", value)}
        return_item = ("structure", return_item)
    return return_item


def assign_brcb_value(server_brcb, values):
    brcb = server_brcb.rcb
    try:
        brcb.obj_ref = brcb.get_objRef()
        if "bufTm" in values:
            brcb.bufferedTime = values["bufTm"]

        if "dsRef" in values:
            brcb.datasetName = values["dsRef"]

        if "gi" in values:
            brcb.gi = values["gi"]

        if "intgPd" in values:
            brcb.intPeriod = values["intgPd"]

        if "optFlds" in values:
            brcb.options = values["optFlds"]

        if "rptEna" in values:
            server_brcb.rptEna = values["rptEna"]

        if "rptID" in values:
            brcb.rptId = values["rptID"]

        if "trgOp" in values:
            brcb.trgOps = values["trgOp"]

        if "entryID" in values:
            server_brcb.entry_id = values["entryID"]

        if "purgeBuf" in values:
            server_brcb.purge_buff = values["purgeBuf"]

        if "rsvdTimeSec" in values:
            server_brcb.rsvdTimeSec = values["rsvdTimeSec"]
        return "ok"
    except (AttributeError, TypeError, ValueError, KeyError):
        return "failure"


def assign_urcb_value(server_urcb, values):
    try:
        urcb = server_urcb.rcb
        urcb.obj_ref = values["urcbRef"]

        if "bufTm" in values:
            urcb.bufferedTime = values["bufTm"]

        if "dsRef" in values:
            urcb.datasetName = values["dsRef"]

        if "gi" in values:
            urcb.gi = values["gi"]

        if "intgPd" in values:
            urcb.intPeriod = values["intgPd"]

        if "optFlds" in values:
            urcb.options = values["optFlds"]

        if "rptEna" in values:
            server_urcb.rptEna = values["rptEna"]

        if "rptID" in values:
            urcb.rptId = values["rptID"]

        if "trgOp" in values:
            urcb.trgOps = values["trgOp"]

        if "resv" in values:
            server_urcb.resv = values["resv"]

        return "ok"
    except (AttributeError, TypeError, ValueError, KeyError) as e:
        logger.info("error in assign urcb values is: ", e)
        return "failure"
