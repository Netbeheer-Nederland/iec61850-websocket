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

from ws61850.iec61850.server.server_report_control import ServerReportControl


def create_tpaa_associate_response(max_message_size, associate_id, service_error=None, max_outstanding_calls=None):
    """
    Creates a Two-Party Application Association response between two applications to acknowledge and establish communication.
    """
    service_dict = {
        "maxMessageSize": max_message_size,
        "associateId": associate_id
    }
    if max_outstanding_calls is not None:
        service_dict["maxOutstandingCalls"] = max_outstanding_calls
    if service_error is not None:
        service_dict["serviceError"] = service_error

    return_item = (
        "associate",
        (
            "service",
            (
                "associateResponse",
                service_dict
            )
        )
    )
    return return_item


def create_tpaa_response_getServerDirectory(invoke_id, associate_id, ld_refs):
    """
    Creates a Two-Party Application Association response to retrieve information about the server's directory structure.
    """
    return (
        "response",
        {
            "invokeId": invoke_id,
            "associateId": associate_id,
            "service": (
                "getServerDirectory",
                {
                    "result": ld_refs  # expected to be a list of strings
                }
            )
        }
    )


def create_tpaa_response_getLDDirectory(invoke_id, associate_id, ln_refs):
    """
    Creates a Two-Party Application Association response to retrieve the list of logical nodes contained within a specific logical device.
    """
    return (
        "response",
        {
            "invokeId": invoke_id,
            "associateId": associate_id,
            "service": (
                "getLogicalDeviceDirectory",
                {
                    "lnRef": ln_refs  # expected to be a list of strings
                }
            )
        }
    )


def build_ds_refs_from_dataset(ds_list):
    """
    Builds a list of data set references from a given data set lists into a structured dictionary format.
    """
    ds_refs = []
    for entry in ds_list:
        ds_refs.append({
            "ref": entry.variable_name,
            "fc": entry.fc.name
        })
    return ds_refs


def create_tpaa_response_getDataSetDirectoryRequest(invoke_id, associate_id, ds_refs):
    """
    Creates a Two-Party Application Association response to retrieve the list of data attributes contained within a specific data set.
    """
    ref_list = build_ds_refs_from_dataset(ds_refs)
    return (
        "response",
        {
            "invokeId": invoke_id,
            "associateId": associate_id,
            "service": (
                "getDataSetDirectory",
                {
                    "dsMemberRef": ref_list  # expected to be a list of strings
                }
            )
        }
    )


def create_tpaa_response_getLogicalNodeDirectory(invoke_id, associate_id, ref_list):
    """
    Creates a Two-Party Application Association response to retrieve the list of objects within a specific logical node.
    """
    return (
        "response",
        {
            "invokeId": invoke_id,
            "associateId": associate_id,
            "service": (
                "getLogicalNodeDirectory",
                {
                    "instanceNames": ref_list  # expected to be a list of strings
                }
            )
        }
    )


def create_tpaa_response_getDataDirectory(invoke_id, associate_id, sdo_list, da_list):
    """
    Creates a Two-Party Application Association response to retrieve the list of components within an object.
    """
    return (
        "response",
        {
            "invokeId": invoke_id,
            "associateId": associate_id,
            "service": (
                "getDataDirectory",
                {
                    "subDataObjectName": sdo_list,
                    "dataAttrName": da_list
                }
            )
        }
    )


def create_tpaa_response_getBRCBValues(invoke_id, associate_id, server_brcb: ServerReportControl):
    """
    Response Function for getBRCBValues
    """
    brcb = server_brcb.rcb
    service_data = {
        "rptID": brcb.rptId,
        "rptEna": server_brcb.rptEna,
        "dataSet": brcb.datasetName,
        "confRev": brcb.confRev,
        "optFlds": brcb.options,
        "bufTm": brcb.bufferedTime,
        "sqNum": server_brcb.seq_num,
        "trgOp": brcb.trgOps,
        "intgPd": brcb.intPeriod,
        "gi": brcb.gi,
        "purgeBuf": server_brcb.purge_buff,
        "entryID": server_brcb.entry_id,
        "timeOfEntry": server_brcb.time_of_entry,
        "rsvdTimeSec": server_brcb.rsvdTimeSec,
    }

    if server_brcb.owner is not None:
        service_data["owner"] = server_brcb.owner

    return (
        "response",
        {
            "invokeId": invoke_id,
            "associateId": associate_id,
            "service": (
                "getBRCBValues",
                service_data
            )
        }
    )


def create_tpaa_response_getURCBValues(invoke_id, associate_id, server_urcb: ServerReportControl):
    """
    Response Function for getURCBValues
    """
    urcb = server_urcb.rcb
    service_data = {
        "rptID": urcb.rptId,
        "rptEna": server_urcb.rptEna,
        "dataSet": urcb.datasetName,
        "confRev": urcb.confRev,
        "optFlds": urcb.options,
        "bufTm": urcb.bufferedTime,
        "sqNum": server_urcb.seq_num,
        "trgOp": urcb.trgOps,
        "intgPd": urcb.intPeriod,
        "gi": urcb.gi,
        "entryID": server_urcb.entry_id,
        "timeOfEntry": server_urcb.time_of_entry,
        "resv": server_urcb.resv,
    }

    if hasattr(server_urcb, "owner") and server_urcb.owner is not None:
        service_data["owner"] = server_urcb.owner

    return (
        "response",
        {
            "invokeId": invoke_id,
            "associateId": associate_id,
            "service": (
                "getURCBValues",
                service_data
            )
        }
    )


def create_tpaa_response_setBRCBValues(invoke_id, associate_id, service_data):
    """
    Response function for setBRCBValues
    """
    return (
        "response",
        {
            "invokeId": invoke_id,
            "associateId": associate_id,
            "service": (
                "setBRCBValues",
                {
                    "result": service_data
                }
            )
        }
    )


def create_tpaa_response_setURCBValues(invoke_id, associate_id, service_data):
    """
    Response function for setURCBValues
    """
    return (
        "response",
        {
            "invokeId": invoke_id,
            "associateId": associate_id,
            "service": (
                "setURCBValues",
                {
                    "result": service_data
                }
            )
        }
    )


def create_tpaa_response_getDataDefinition(invoke_id, associate_id, sdo_list, da_list, data_object):
    """
    Creates a Two-Party Application Association response to retrieve the data type definition of a specific object.
    """
    return (
        "response",
        {
            "invokeId": invoke_id,
            "associateId": associate_id,
            "service": (
                "getDataDefinition",
                {
                    "cdc": data_object.cdc,
                    "count": data_object.elementCount,
                    "subDataDefinition": sdo_list,
                    "dataAttributeDefinition": da_list
                }
            )
        }
    )


def create_tpaa_response_getDataValues(invoke_id, associate_id, service_data):
    """
    Creates a Two-Party Application Association response to retrieve the current values of a specific object.
    """
    return (
        "response",
        {
            "invokeId": invoke_id,
            "associateId": associate_id,
            "service": (
                "getDataValues",
                {
                    "dataAttrVal": service_data,
                }
            )
        }
    )


def create_tpaa_response_setDataValues(invoke_id, associate_id, service_data):
    """
    Creates a Two-Party Application Association response to set or update the values of a specific data attribute.
    """
    return (
        "response",
        {
            "invokeId": invoke_id,
            "associateId": associate_id,
            "service": (
                "setDataValues",
                {
                    "result": service_data
                }
            )
        }
    )


def create_tpaa_service_error_response(invoke_id, associate_id, service_data):
    """
    Creates a Two-Party Application Association response to set or update the values of a specific data attribute.
    """
    return (
        "response",
        {
            "invokeId": invoke_id,
            "associateId": associate_id,
            "service": (
                ("serviceError", service_data)

            )
        }
    )


def create_tpaa_response_getDataSetValues(invoke_id, associate_id, service_data):
    """
    Create a Two-Party Application Association response to retrieve the current values of a specific data set.
    """
    return (
        "response",
        {
            "invokeId": invoke_id,
            "associateId": associate_id,
            "service": (
                "getDatasetValues",
                {
                    "dsMemberValue": service_data,
                }
            )
        }
    )


def create_tpaa_release_response(invoke_id, associate_id):
    """
    Creates a Two-Party Application Association release response between two applications to acknowledge the termination of an existing association.
    """
    return (
        "associate",  # TpaaPdu CHOICE
        (
            "service",  # AssociateType CHOICE
            (
                "releaseResponse",  # AssociateServiceType CHOICE
                {
                    "invokeId": invoke_id,
                    "associateId": associate_id
                }
            )
        )
    )


def create_tpaa_abort_response(invoke_id, associate_id):
    """
    Aborts the connection
    """
    return (
        "associate",  # TpaaPdu CHOICE
        (
            "service",
            (
                "abortResponse",
                {
                    "invokeId": invoke_id,
                    "associateId": associate_id
                }
            )
        )
    )


def create_tpaa_report(server_report_control: ServerReportControl, da_entry_list, associate_id):
    """
    Create a Two-Party Application Association for report
    """
    report_control = server_report_control.rcb
    report_instance = {
        "rptID": report_control.rptId,
        "sqNum": server_report_control.seq_num,
        "moreSegmentsFollow": False,
        "dataSet": report_control.datasetName,
        "bufOvfl": report_control.options["bufOvfl"],
        "confRev": report_control.confRev,
        "entry": {
            "timeOfEntry": server_report_control.time_of_entry,
            "entryID": server_report_control.entry_id,
            "entryData": da_entry_list

        }
    }

    tpaa_pdu = (
        "unconfirmed",
        {
            "associateId": associate_id,
            "service":
                (
                    "report",
                    report_instance
                )

        }

    )

    return tpaa_pdu


def create_tpaa_response_select(invoke_id, associate_id, success, add_cause, service_error):
    """
    Create a Two-Party Application Association response to select.
    """
    service_dict = {
        "success": success
    }
    if add_cause is not None:
        service_dict["addCause"] = add_cause
    if service_error is not None:
        service_dict["serviceError"] = service_error

    return_object = (
        "response",
        {
            "invokeId": invoke_id,
            "associateId": associate_id,
            "service": (
                "select",
                service_dict
            )
        }
    )

    return return_object


def create_tpaa_response_operate(invoke_id, associate_id, success, add_cause, service_error):
    """
    Create a Two-Party Application Association response to operate.
    """

    service_dict = {
        "success": success
    }
    if add_cause is not None:
        service_dict["addCause"] = add_cause
    if service_error is not None:
        service_dict["serviceError"] = service_error

    return_object = (
        "response",
        {
            "invokeId": invoke_id,
            "associateId": associate_id,
            "service": (
                "operate",
                service_dict
            )
        }
    )

    return return_object
