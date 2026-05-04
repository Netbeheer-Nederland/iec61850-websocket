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

import re

from ws61850.iec61850.data_model.ied_model import DataAttribute, DataAttributeType, DataObject, FunctionalConstraint
from ws61850.iec61850.server.request_handling import (
    assign_da_item,
    assign_do_item,
    build_data_value,
    find_object_in_tree,
    flatten_nested_data_attributes_with_fc,
)
from ws61850.iec61850.server.response_handling import (
    create_tpaa_response_getDataSetValues,
    create_tpaa_response_getDataValues,
    create_tpaa_response_setDataValues,
    create_tpaa_service_error_response,
)
from ws61850.shared.extractors import extract_dataAttrVal, extract_ds_ref, extract_includeElementName, extract_ref


class DataAccessService:
    """
    Handles IEC 61850 data access service requests.

    Extracted from IEC61850Server.handle_request:
      - getDataValues
      - setDataValues
      - getDatasetValues
    """

    def __init__(self, ied_model):
        self._ied = ied_model

    def get_data_values(self, invoke_id, associate_id, decoded_message):
        ied = self._ied
        data_ref = extract_ref(decoded_message)
        include_element_name = extract_includeElementName(decoded_message)
        item = find_object_in_tree(data_ref["ref"], ied)
        if item is None:
            return create_tpaa_service_error_response(invoke_id, associate_id, "instanceNotAvailable")
        if isinstance(item, DataObject):
            da_list = flatten_nested_data_attributes_with_fc(item, data_ref["fc"])
            da_fc = [build_data_value(da, da.type.name, da.mmsValue, include_element_name) for da in da_list]
        else:
            da_fc = [build_data_value(item, item.type.name, item.mmsValue, include_element_name)]
        return create_tpaa_response_getDataValues(invoke_id, associate_id, da_fc)

    def set_data_values(self, invoke_id, associate_id, decoded_message):
        ied = self._ied
        data_ref = extract_ref(decoded_message)
        dataAttr_val = extract_dataAttrVal(decoded_message)
        item = find_object_in_tree(data_ref["ref"], ied)
        if item is None:
            return create_tpaa_service_error_response(invoke_id, associate_id, "instanceNotAvailable")

        fc = data_ref["fc"]
        if fc == FunctionalConstraint.co.name:
            return create_tpaa_service_error_response(invoke_id, associate_id, "accessViolation")

        if isinstance(item, DataObject):
            for da_do_index, da_do_item in enumerate(item.do_or_da):
                if da_do_index < len(dataAttr_val):
                    value = dataAttr_val[da_do_index]
                    if isinstance(da_do_item, DataAttribute):
                        assign_da_item(item.do_or_da[da_do_index], value["data"], fc)
                    else:
                        assign_do_item(item.do_or_da[da_do_index], value["data"], fc)
            return create_tpaa_response_setDataValues(invoke_id, associate_id, "ok")
        else:
            if fc == item.fc.name:
                result = assign_da_item(item, dataAttr_val[0]["data"], fc)
                if result is False:
                    return create_tpaa_service_error_response(invoke_id, associate_id, "typeConflict")
                return create_tpaa_response_setDataValues(invoke_id, associate_id, "ok")
            return create_tpaa_service_error_response(invoke_id, associate_id, "instanceNotAvailable")

    def get_dataset_values(self, invoke_id, associate_id, decoded_message, find_ds_in_tree):
        ied = self._ied
        ds_ref = extract_ds_ref(decoded_message)
        ldName, lnName, dsName = re.split(r"[/.]", ds_ref)
        foundLN = next(
            (ln for ld in ied.logical_devices if ld.name == ldName
             for ln in ld.logical_nodes if ln.name == lnName),
            None,
        )
        if foundLN is None:
            return create_tpaa_service_error_response(invoke_id, associate_id, "instanceNotAvailable")
        foundDS = next(
            (ds for ds in foundLN.data_sets
             if ds.logical_device_name == ldName and ds.parent.name == lnName and ds.name == dsName),
            None,
        )
        if not foundDS:
            return create_tpaa_service_error_response(invoke_id, associate_id, "instanceNotAvailable")

        value_list = []
        for ds_entry in foundDS.fcdas:
            item = find_object_in_tree(ds_entry.variable_name, ied)
            if item is not None:
                if isinstance(item, DataObject):
                    da_list = flatten_nested_data_attributes_with_fc(item, ds_entry.fc.name)
                    for da in da_list:
                        value_list.append(build_data_value(da, da.type.name, da.mmsValue, True))
                else:
                    value_list.append(build_data_value(item, item.type.name, item.mmsValue, True))
        return create_tpaa_response_getDataSetValues(invoke_id, associate_id, value_list)
