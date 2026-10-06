# SPDX-FileCopyrightText: 2025-2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
#
# Copyright 2025-2026 Netbeheer Nederland
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

import re

from ws61850.iec61850.server.request_handling import (
    create_data_attribute_definition_list,
    create_sub_data_definition_list,
    find_do_with_ref,
    get_list_of_items_ln,
)
from ws61850.iec61850.server.response_handling import (
    create_tpaa_response_get_data_definition,
    create_tpaa_response_get_data_directory,
    create_tpaa_response_get_data_set_directory_request,
    create_tpaa_response_get_ld_directory,
    create_tpaa_response_get_logical_node_directory,
    create_tpaa_response_get_server_directory,
    create_tpaa_service_error_response,
)
from ws61850.shared.extractors import (
    extract_acsi_type,
    extract_data_ref,
    extract_ds_ref,
    extract_ld_name,
    extract_ln_ref,
)


class DirectoryService:
    """
    Handles all IEC 61850 directory-browsing service requests.

    Extracts from IEC61850Server:
      - getServerDirectory
      - getLogicalDeviceDirectory
      - getLogicalNodeDirectory
      - getDataSetDirectory
      - getDataDirectory
      - getDataDefinition

    Each method returns a TPAA response tuple ready for encoding.
    """

    def __init__(self, ied_model):
        self._ied = ied_model

    def get_server_directory(self, invoke_id, associate_id):
        ld_refs = [ld.name for ld in self._ied.logical_devices]
        return create_tpaa_response_get_server_directory(
            invoke_id, associate_id, ld_refs
        )

    def get_logical_device_directory(self, invoke_id, associate_id, decoded_message):
        ied = self._ied
        ld_name = extract_ld_name(decoded_message)
        found_ld = next((ld for ld in ied.logical_devices if ld.name == ld_name), None)
        if found_ld:
            ln_names = [ln.name for ln in found_ld.logical_nodes]
            return create_tpaa_response_get_ld_directory(
                invoke_id, associate_id, ln_names
            )
        return create_tpaa_service_error_response(
            invoke_id, associate_id, "instanceNotAvailable"
        )

    def get_logical_node_directory(self, invoke_id, associate_id, decoded_message):
        ied = self._ied
        ln_ref = extract_ln_ref(decoded_message)
        acsi_service = extract_acsi_type(decoded_message)
        refs = get_list_of_items_ln(ln_ref, acsi_service, ied)
        if refs is not None:
            return create_tpaa_response_get_logical_node_directory(
                invoke_id, associate_id, refs
            )
        return create_tpaa_service_error_response(
            invoke_id, associate_id, "instanceNotAvailable"
        )

    def get_data_set_directory(self, invoke_id, associate_id, decoded_message):
        ied = self._ied
        ds_ref = extract_ds_ref(decoded_message)
        ld_name, ln_name, ds_name = re.split(r"[/.]", ds_ref)
        found_ln = next(
            (
                ln
                for ld in ied.logical_devices
                if ld.name == ld_name
                for ln in ld.logical_nodes
                if ln.name == ln_name
            ),
            None,
        )
        if found_ln is None:
            return create_tpaa_service_error_response(
                invoke_id, associate_id, "instanceNotAvailable"
            )
        found_ds = next(
            (
                ds
                for ds in found_ln.data_sets
                if ds.logical_device_name == ld_name
                and ds.parent.name == ln_name
                and ds.name == ds_name
            ),
            None,
        )
        if found_ds:
            return create_tpaa_response_get_data_set_directory_request(
                invoke_id, associate_id, found_ds.fcdas
            )
        return create_tpaa_service_error_response(
            invoke_id, associate_id, "instanceNotAvailable"
        )

    def get_data_directory(self, invoke_id, associate_id, decoded_message):
        ied = self._ied
        data_ref = extract_data_ref(decoded_message)
        data_object, _ = find_do_with_ref(data_ref, ied)
        if data_object is not None:
            sdo_list = [sdo.name for sdo in data_object.get_do_from_do_or_da_list()]
            da_list = [da.name for da in data_object.get_da_from_do_or_da_list()]
            return create_tpaa_response_get_data_directory(
                invoke_id, associate_id, sdo_list, da_list
            )
        return create_tpaa_service_error_response(
            invoke_id, associate_id, "instanceNotAvailable"
        )

    def get_data_definition(self, invoke_id, associate_id, decoded_message):
        ied = self._ied
        data_ref = extract_data_ref(decoded_message)
        data_object, _ = find_do_with_ref(data_ref, ied)
        if data_object is not None:
            sdo_list, _ = create_sub_data_definition_list(
                data_object.get_do_from_do_or_da_list()
            )
            da_list = create_data_attribute_definition_list(
                data_object.get_da_from_do_or_da_list()
            )
            return create_tpaa_response_get_data_definition(
                invoke_id, associate_id, sdo_list, da_list, data_object
            )
        return create_tpaa_service_error_response(
            invoke_id, associate_id, "instanceNotAvailable"
        )
