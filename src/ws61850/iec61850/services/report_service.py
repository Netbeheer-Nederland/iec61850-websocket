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

from ws61850.iec61850.server.request_handling import assign_brcb_value, assign_urcb_value
from ws61850.iec61850.server.response_handling import (
    create_tpaa_response_getBRCBValues,
    create_tpaa_response_getURCBValues,
    create_tpaa_response_setBRCBValues,
    create_tpaa_response_setURCBValues,
    create_tpaa_service_error_response,
)
from ws61850.shared.extractors import extract_brcb_ref, extract_urcb_ref


class ReportService:
    """
    Handles IEC 61850 Report Control Block service requests.

    Extracted from IEC61850Server.handle_request:
      - getBRCBValues, setBRCBValues
      - getURCBValues, setURCBValues

    Note: setBRCBValues / setURCBValues may trigger an async general-interrogation
    report; those are handled by the server after calling these methods.
    """

    def __init__(self, server_report_controls):
        self._report_controls = server_report_controls

    def get_brcb_values(self, invoke_id, associate_id, decoded_message):
        brcb_ref = extract_brcb_ref(decoded_message)
        brcb = next(
            (rc for rc in self._report_controls if rc.rcb.get_objRef() == brcb_ref),
            None,
        )
        if brcb is not None and brcb.rcb.buffered is True:
            return create_tpaa_response_getBRCBValues(invoke_id, associate_id, brcb), None
        return create_tpaa_service_error_response(invoke_id, associate_id, "instanceNotAvailable"), None

    def set_brcb_values(self, invoke_id, associate_id, decoded_message, websocket_info, iec61850_server):
        brcb_ref = extract_brcb_ref(decoded_message)
        brcb = next(
            (rc for rc in self._report_controls if rc.rcb.get_objRef() == brcb_ref),
            None,
        )
        if brcb is not None and brcb.rcb.buffered is True:
            brcb.rcb.client_connection = websocket_info
            service = decoded_message[1]["service"]
            result = assign_brcb_value(brcb, service[1], iec61850_server)
            response = create_tpaa_response_setBRCBValues(invoke_id, associate_id, result)
            return response, brcb if (brcb.rptEna and brcb.rcb.trg_ops.get("gi") and brcb.rcb.gi) else None
        return create_tpaa_service_error_response(invoke_id, associate_id, "instanceNotAvailable"), None

    def get_urcb_values(self, invoke_id, associate_id, decoded_message):
        urcb_ref = extract_urcb_ref(decoded_message)
        urcb = next(
            (rc for rc in self._report_controls if rc.rcb.get_objRef() == urcb_ref),
            None,
        )
        if urcb is not None and urcb.rcb.buffered is False:
            return create_tpaa_response_getURCBValues(invoke_id, associate_id, urcb), None
        return create_tpaa_service_error_response(invoke_id, associate_id, "instanceNotAvailable"), None

    def set_urcb_values(self, invoke_id, associate_id, decoded_message, websocket_info, iec61850_server):
        urcb_ref = extract_urcb_ref(decoded_message)
        urcb = next(
            (rc for rc in self._report_controls if rc.rcb.get_objRef() == urcb_ref),
            None,
        )
        if urcb is not None and urcb.rcb.buffered is False:
            service = decoded_message[1]["service"]
            result = assign_urcb_value(urcb, service[1], iec61850_server)
            urcb.rcb.client_connection = websocket_info
            response = create_tpaa_response_setURCBValues(invoke_id, associate_id, result)
            return response, urcb if (urcb.rptEna and urcb.rcb.trg_ops.get("gi") and urcb.rcb.gi) else None
        return create_tpaa_service_error_response(invoke_id, associate_id, "instanceNotAvailable"), None
