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
import re

from ws61850.iec61850.data_model.ied_model import IedModel, LogicalDevice, LogicalNode


# ---------------------------------------------------------------------------
# Association-level extractors (work on raw JSON strings)
# ---------------------------------------------------------------------------

def retrieve_associate_id(response_raw):
    """Extracts association id from an associateResponse JSON string."""
    response = json.loads(response_raw)
    try:
        return response["associate"]["service"]["associateResponse"]["associateId"]
    except (KeyError, TypeError) as e:
        raise ValueError("Invalid structure for associateId extraction") from e


def retrieve_max_message_size(response_raw):
    """Extracts maxMessageSize from an associateResponse JSON string."""
    response = json.loads(response_raw)
    try:
        return response["associate"]["service"]["associateResponse"]["maxMessageSize"]
    except (IndexError, KeyError, TypeError):
        raise ValueError("Invalid TPAA structure for maxMessageSize")


# ---------------------------------------------------------------------------
# Association-level extractors (work on decoded TPAA tuples)
# ---------------------------------------------------------------------------

def retrieve_associate_id_from_decoded_msg(decoded_msg):
    """Extracts associateId from a decoded associateResponse TPAA tuple."""
    try:
        return decoded_msg[1][1][1]["associateId"]
    except (KeyError, TypeError) as e:
        raise ValueError("Invalid structure for associateId extraction") from e


def retrieve_max_outstanding_calls_from_decoded_msg(decoded_msg):
    """Extracts maxOutstandingCalls from a decoded associateResponse TPAA tuple."""
    try:
        return decoded_msg[1][1][1]["maxOutstandingCalls"]
    except (KeyError, TypeError):
        return 0


def extract_max_message_size(tpaa):
    """Extracts maxMessageSize from a TPAA associateRequest/Response tuple."""
    try:
        return tpaa[1][1][1]["maxMessageSize"]
    except (IndexError, KeyError, TypeError):
        raise ValueError("Invalid TPAA structure for maxMessageSize")


# ---------------------------------------------------------------------------
# TPAA PDU type extractors (work on decoded TPAA tuples)
# ---------------------------------------------------------------------------

def extract_associate_request_type(tpaa_tuple):
    """
    Extracts the request type from an associate TPAA tuple.
    Example input: ("associate", ("service", ("associateRequest", {...})))
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
    Extracts the service name from a request/response TPAA tuple.
    Example input: ("response", {"invokeId": ..., "service": ("serviceName", {...})})
    """
    try:
        return tpaa_tuple[1]["service"][0]
    except (IndexError, KeyError, TypeError) as e:
        raise ValueError("Invalid TPAA structure for service name") from e


def extract_invoke_id(tpaa_tuple):
    """Extracts the invokeId from a request/response TPAA tuple."""
    try:
        return tpaa_tuple[1]["invokeId"]
    except (IndexError, KeyError, TypeError) as e:
        raise ValueError("Invalid TPAA structure for invokeId") from e


# ---------------------------------------------------------------------------
# Service field extractors (work on decoded TPAA tuples)
# ---------------------------------------------------------------------------

def extract_ld_name(tpaa_tuple):
    """Extracts ldName from a getLogicalDeviceDirectory request tuple."""
    try:
        return tpaa_tuple[1]["service"][1]["ldName"]
    except (IndexError, KeyError, TypeError) as e:
        raise ValueError("Invalid TPAA structure for ldName") from e


def extract_ln_ref(tpaa_tuple):
    """Extracts lnRef from a getLogicalNodeDirectory request tuple."""
    try:
        return tpaa_tuple[1]["service"][1]["lnRef"]
    except (IndexError, KeyError, TypeError) as e:
        raise ValueError("Invalid TPAA structure for lnRef") from e


def extract_acsiType(tpaa_tuple):
    """Extracts aCSIClass from a getLogicalNodeDirectory request tuple."""
    try:
        return tpaa_tuple[1]["service"][1]["aCSIClass"]
    except (IndexError, KeyError, TypeError) as e:
        raise ValueError("Invalid TPAA structure for aCSIClass") from e


def extract_ds_ref(tpaa_tuple):
    """Extracts dsRef from a getDataSetDirectory request tuple."""
    try:
        return tpaa_tuple[1]["service"][1]["dsRef"]
    except (IndexError, KeyError, TypeError) as e:
        raise ValueError("Invalid TPAA structure for dsRef") from e


def extract_data_ref(tpaa_tuple):
    """Extracts dataRef from a getDataDirectory request tuple."""
    try:
        return tpaa_tuple[1]["service"][1]["dataRef"]
    except (IndexError, KeyError, TypeError) as e:
        raise ValueError("Invalid TPAA structure for dataRef") from e


def extract_ref(tpaa_tuple):
    """Extracts ref from a getDataValues request tuple."""
    try:
        return tpaa_tuple[1]["service"][1]["ref"]
    except (IndexError, KeyError, TypeError) as e:
        raise ValueError("Invalid TPAA structure for ref") from e


def extract_dataAttrVal(tpaa_tuple):
    """Extracts dataAttrVal from a setDataValues request tuple."""
    try:
        return tpaa_tuple[1]["service"][1]["dataAttrVal"]
    except (IndexError, KeyError, TypeError) as e:
        raise ValueError("Invalid TPAA structure for dataAttrVal") from e


def extract_includeElementName(tpaa_tuple):
    """Extracts includeElementName from a getDataValues request tuple."""
    try:
        return tpaa_tuple[1]["service"][1]["includeElementName"]
    except (IndexError, KeyError, TypeError) as e:
        raise ValueError("Invalid TPAA structure for includeElementName") from e


def extract_brcb_ref(tpaa_tuple):
    """Extracts brcbRef from a getBRCBValues request tuple."""
    try:
        return tpaa_tuple[1]["service"][1]["brcbRef"]
    except (IndexError, KeyError, TypeError) as e:
        raise ValueError("Invalid TPAA structure for brcbRef") from e


def extract_urcb_ref(tpaa_tuple):
    """Extracts urcbRef from a getURCBValues request tuple."""
    try:
        return tpaa_tuple[1]["service"][1]["urcbRef"]
    except (IndexError, KeyError, TypeError) as e:
        raise ValueError("Invalid TPAA structure for urcbRef") from e


# ---------------------------------------------------------------------------
# IED model navigation helpers (shared between client and server)
# ---------------------------------------------------------------------------

def get_list_of_items_ln(ln_ref, asci_service, ied: IedModel):
    """Returns items from the logical node for getLogicalNodeDirectory."""
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
