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

def create_token_refresh(associate_id, token):
    """
    Creates a tokenRefresh message
    """
    return (
        "associate",
        (
            "service",
            (
                "refreshToken",
                {
                    "associateId": associate_id,
                    "token": token
                }
            )
        )
    )


def create_tpaa_associate_request(called_ap, max_message_size):
    """
    Creates a Two-Party Application Association request between two applications to initiate communication.
    """
    return (
        "associate",  # TpaaPdu CHOICE
        (
            "service",  # AssociateType CHOICE
            (
                "associateRequest",  # AssociateServiceType CHOICE
                {
                    "calledAP": called_ap,
                    "maxMessageSize": max_message_size
                }
            )
        )
    )


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
                    "associateId": associate_id
                    # Add more fields if required
                }
            )
        )
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
                    "associateId": associate_id
                    # Add more fields if required
                }
            )
        )
    )


def create_tpaa_request_getServerDirectory(invoke_id, associate_id, service_data):
    """
    Creates a Two-Party Application Association request to retrieve information about the server's directory structure.
    """
    return (
        "request",
        {
            "invokeId": invoke_id,
            "associateId": associate_id,
            "service": (
                "getServerDirectory",
                {
                    "objectClass": service_data
                }
            )
        }
    )


def create_tpaa_request_getLDDirectory(invoke_id, associate_id, service_data):
    """
    Creates a Two-Party Application Association request to retrieve the list of logical nodes contained within a specific logical device.
    """
    return (
        "request",
        {
            "invokeId": invoke_id,
            "associateId": associate_id,
            "service": (
                "getLogicalDeviceDirectory",
                {
                    "ldName": service_data
                }
            )
        }
    )


def create_tpaa_request_getDataSetDirectoryRequest(invoke_id, associate_id, service_data):
    """
    Creates a Two-Party Application Association request to retrieve the list of data attributes contained within a specific data set.
    """
    return (
        "request",
        {
            "invokeId": invoke_id,
            "associateId": associate_id,
            "service": (
                "getDataSetDirectory",
                {
                    "dsRef": service_data
                }
            )
        }
    )


def create_tpaa_request_getLogicalNodeDirectory(invoke_id, associate_id, service_data, aCSIClass):
    """
    Creates a Two-Party Application Association request to retrieve the list of objects within a specific logical node.
    """
    return (
        "request",
        {
            "invokeId": invoke_id,
            "associateId": associate_id,
            "service": (
                "getLogicalNodeDirectory",
                {
                    "lnRef": service_data,
                    "aCSIClass": aCSIClass
                }
            )
        }
    )


def create_tpaa_request_getDataDirectory(invoke_id, associate_id, service_data):
    """
    Creates a Two-Party Application Association request to retrieve the list of components within an object.
    """
    return (
        "request",
        {
            "invokeId": invoke_id,
            "associateId": associate_id,
            "service": (
                "getDataDirectory",
                {
                    "dataRef": service_data,
                }
            )
        }
    )


def create_tpaa_request_getBRCBValuesRequest(invoke_id, associate_id, service_data):
    """
    Creates a Two-Party Application Association request to retrieve the current values of a Buffered Report Control Block (BRCB).
    """
    return (
        "request",
        {
            "invokeId": invoke_id,
            "associateId": associate_id,
            "service": (
                "getBRCBValues",
                {
                    "brcbRef": service_data,
                }
            )
        }
    )


def create_tpaa_request_getURCBValuesRequest(invoke_id, associate_id, service_data):
    """
    Creates a Two-Party Application Association request to retrieve the current values of an Unbuffered Report Control Block (URCB).
    """
    return (
        "request",
        {
            "invokeId": invoke_id,
            "associateId": associate_id,
            "service": (
                "getURCBValues",
                {
                    "urcbRef": service_data,
                }
            )
        }
    )


def create_tpaa_request_setBRCBValuesRequest(invoke_id, associate_id, client_report_control):
    """
    Creates a Two-Party Application Association request to retrieve the current values of a Buffered Report Control Block (BRCB).
    """
    service_data = {
        "brcbRef": client_report_control.objectReference,
    }
    if client_report_control.bufTm is not None:
        service_data["bufTm"] = client_report_control.bufTm
    if client_report_control.dataSet is not None:
        service_data["dataSet"] = client_report_control.dataSet
    if client_report_control.entryId is not None:
        service_data["entryID"] = client_report_control.entryId
    if client_report_control.gi is not None:
        service_data["gi"] = client_report_control.gi
    if client_report_control.intgPd is not None:
        service_data["intgPd"] = client_report_control.intgPd
    if client_report_control.optFlds is not None:
        service_data["optFlds"] = client_report_control.optFlds
    if client_report_control.purgeBuf is not None:
        service_data["purgeBuf"] = client_report_control.purgeBuf
    if client_report_control.rptEna is not None:
        service_data["rptEna"] = client_report_control.rptEna
    if client_report_control.rptId is not None:
        service_data["rptID"] = client_report_control.rptId
    if client_report_control.resvTms is not None:
        service_data["rsvdTimeSec"] = client_report_control.resvTms
    if client_report_control.trgOps is not None:
        service_data["trgOp"] = client_report_control.trgOps

    return (
        "request",
        {
            "invokeId": invoke_id,
            "associateId": associate_id,
            "service": (
                "setBRCBValues",
                service_data
            )
        }
    )


def create_tpaa_request_setURCBValuesRequest(invoke_id, associate_id, client_report_control):
    """
    Creates a Two-Party Application Association request to retrieve the current values of a Unbuffered Report Control Block (URCB).
    """
    service_data = {
        "urcbRef": client_report_control.objectReference,
    }

    # Add only if not None
    if client_report_control.bufTm is not None:
        service_data["bufTm"] = client_report_control.bufTm
    if client_report_control.dataSet is not None:
        service_data["dataSet"] = client_report_control.dataSet
    if client_report_control.gi is not None:
        service_data["gi"] = client_report_control.gi
    if client_report_control.intgPd is not None:
        service_data["intgPd"] = client_report_control.intgPd
    if client_report_control.optFlds is not None:
        service_data["optFlds"] = client_report_control.optFlds
    if client_report_control.rptEna is not None:
        service_data["rptEna"] = client_report_control.rptEna
    if client_report_control.rptId is not None:
        service_data["rptID"] = client_report_control.rptId
    if client_report_control.resv is not None:
        service_data["resv"] = client_report_control.resv
    if client_report_control.trgOps is not None:
        service_data["trgOp"] = client_report_control.trgOps

    return (
        "request",
        {
            "invokeId": invoke_id,
            "associateId": associate_id,
            "service": (
                "setURCBValues",
                service_data
            )
        }
    )


def create_tpaa_request_getDataDefinition(invoke_id, associate_id, service_data):
    """
    Creates a Two-Party Application Association request to retrieve the data type definition of a specific object.
    """
    return (
        "request",
        {
            "invokeId": invoke_id,
            "associateId": associate_id,
            "service": (
                "getDataDefinition",
                {
                    "dataRef": service_data,
                }
            )
        }
    )


def create_tpaa_request_getDataValues(invoke_id, associate_id, service_data, includeElementName):
    """
    Creates a Two-Party Application Association request to retrieve the current values of a specific object.
    """
    return (
        "request",
        {
            "invokeId": invoke_id,
            "associateId": associate_id,
            "service": (
                "getDataValues",
                {
                    "ref": service_data,
                    "includeElementName": includeElementName
                }
            )
        }
    )


def create_tpaa_request_setDataValues(invoke_id, associate_id, ref, values):
    """
    Creates a Two-Party Application Association request  to set or update the values of a specific data attribute.
    """
    return (
        "request",
        {
            "invokeId": invoke_id,
            "associateId": associate_id,
            "service": (
                "setDataValues",
                {
                    "ref": ref,
                    "dataAttrVal": values
                }
            )
        }
    )


def create_tpaa_request_getDataSetValues(invoke_id, associate_id, service_data):
    """
    Create a Two-Party Application Association request to retrieve the current values of a specific data set.
    """
    return (
        "request",
        {
            "invokeId": invoke_id,
            "associateId": associate_id,
            "service": (
                "getDatasetValues",
                {
                    "dsRef": service_data,
                }
            )
        }
    )


def create_tpaa_request_select(invoke_id, associate_id, service_data):
    """
    Create a Two-Party Application Association response to select.
    """
    return (
        "request",
        {
            "invokeId": invoke_id,
            "associateId": associate_id,
            "service": (
                "select",
                {
                    "ref": service_data,
                }
            )
        }
    )


def create_tpaa_request_operate(invoke_id, associate_id, service_data):
    """
    Create a Two-Party Application Association request for operate.
    """
    return_object = (
        "request",
        {
            "invokeId": invoke_id,
            "associateId": associate_id,
            "service": (
                "operate",
                service_data
            )
        }
    )
    return return_object


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
                    # Add more fields if required
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
