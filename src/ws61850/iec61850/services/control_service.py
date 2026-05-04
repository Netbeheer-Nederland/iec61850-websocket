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

from ws61850.iec61850.data_model.ied_model import DataAttribute, FunctionalConstraint
from ws61850.iec61850.server.control_handling import ControlHandlerResult, ControlServiceStatusKind
from ws61850.iec61850.server.request_handling import (
    assign_da_item,
    extract_ctlVal_from_operate_request,
    extract_operate_or_select_ref,
    find_object_in_tree,
)
from ws61850.iec61850.server.response_handling import (
    create_tpaa_response_operate,
    create_tpaa_response_select,
    create_tpaa_service_error_response,
)
from ws61850.iec61850.server.service_error import ServiceStatusKind


class ControlService:
    """
    Handles IEC 61850 control service requests.

    Extracted from IEC61850Server.handle_request:
      - select
      - operate  (sync part — the caller handles any async post-operate work)

    Returns a (tpaa_response, needs_quality_update) tuple so the caller can
    await set_quality_to_good() without ControlService needing an async context.
    """

    def __init__(self, ied_model, server_control_objects, control_handler_ref):
        """
        :param control_handler_ref: callable returning the server's current (handler, param) tuple,
                                    so ControlService sees handler changes without rebinding.
        """
        self._ied = ied_model
        self._control_objects = server_control_objects
        self._control_handler_ref = control_handler_ref

    def _get_control_data_object(self, ref):
        from ws61850.iec61850.data_model.ied_model import DataObject
        control_item = find_object_in_tree(ref, self._ied)
        if isinstance(control_item, DataObject):
            return control_item
        if isinstance(control_item, DataAttribute):
            current = control_item
            while current is not None:
                if isinstance(current, DataObject):
                    return current
                current = getattr(current, "parent", None)
        return None

    def select(self, invoke_id, associate_id, decoded_message):
        ref = extract_operate_or_select_ref(decoded_message)
        control_do = self._get_control_data_object(ref)
        server_control_obj = next(
            (co for co in self._control_objects
             if control_do is not None and co.data_object.get_objRef() == control_do.get_objRef()),
            None,
        )
        if server_control_obj is None:
            return create_tpaa_response_select(
                invoke_id, associate_id, False, None, ServiceStatusKind.instanceNotAvailable.name
            ), False

        if not server_control_obj.is_selected:
            server_control_obj.is_selected = True
            return create_tpaa_response_select(invoke_id, associate_id, True, None, None), False
        return create_tpaa_response_select(
            invoke_id, associate_id, False, ControlServiceStatusKind.objectAlreadySelected.name, None
        ), False

    def operate(self, invoke_id, associate_id, decoded_message):
        """
        Returns (tpaa_response, control_do_or_None).
        If control_do_or_None is not None, the caller should call set_quality_to_good(control_do).
        """
        ref = extract_operate_or_select_ref(decoded_message)
        control_do = self._get_control_data_object(ref)
        if control_do is None:
            return create_tpaa_response_operate(
                invoke_id, associate_id, False, None, ServiceStatusKind.instanceNotAvailable.name
            ), None

        operate_item = next(
            (da for da in control_do.get_da_from_do_or_da_list()
             if da.fc == FunctionalConstraint.co and da.name == "Oper"),
            None,
        )
        if operate_item is None:
            return create_tpaa_response_operate(
                invoke_id, associate_id, False, ControlServiceStatusKind.inconsistentParameters.name, None
            ), None

        server_control_obj = next(
            (co for co in self._control_objects
             if co.data_object.get_objRef() == control_do.get_objRef()),
            None,
        )
        control_da = next((da for da in operate_item.data_attributes if da.name == "ctlVal"), None)
        if control_da is None:
            return create_tpaa_response_operate(
                invoke_id, associate_id, False, None, ServiceStatusKind.instanceNotAvailable.name
            ), None

        control_handler = self._control_handler_ref()
        if control_handler is None:
            return create_tpaa_response_operate(
                invoke_id, associate_id, False, None, ServiceStatusKind.failedDueToServerConstraint.name
            ), None

        ctlVal_request = extract_ctlVal_from_operate_request(decoded_message)
        assign_result = assign_da_item(control_da, ctlVal_request, control_da.fc.name)
        if not assign_result:
            return create_tpaa_response_operate(
                invoke_id, associate_id, False, None, ServiceStatusKind.typeConflict.name
            ), None

        needs_quality_update = (control_do.get_objRef() == "LD0/DWMX1.WMaxSpt")

        ctl_num = next((da for da in operate_item.data_attributes if da.name == "ctlNum"), None)

        if not server_control_obj.is_selected:
            return create_tpaa_response_operate(
                invoke_id, associate_id, False, None, ServiceStatusKind.controlMustBeSelected.name
            ), None

        handler_fn, handler_param = control_handler
        from ws61850.iec61850.server.iec61850_server import IEC61850Server
        ctl_val = {"type": control_da.type.name, "value": control_da.mmsValue}
        result, error = handler_fn(control_da.get_objRef(), ctl_val, handler_param)

        if result == ControlHandlerResult.OK:
            if ctl_num:
                ctl_num.mmsValue += 1
            return create_tpaa_response_operate(invoke_id, associate_id, True, None, None), \
                   control_do if needs_quality_update else None

        if isinstance(error, ControlServiceStatusKind):
            if ctl_num:
                ctl_num.mmsValue += 1
            return create_tpaa_response_operate(invoke_id, associate_id, False, error.name, None), None

        return create_tpaa_response_operate(
            invoke_id, associate_id, False, None, ServiceStatusKind.failedDueToServerConstraint.name
        ), None
