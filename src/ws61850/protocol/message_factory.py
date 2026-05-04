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


class TpaaMessageFactory:
    """Single builder API for all TPAA messages, both client-originated and server-originated."""

    # ------------------------------------------------------------------
    # Association lifecycle
    # ------------------------------------------------------------------

    def associate_request(self, called_ap, max_message_size):
        return (
            "associate",
            ("service", ("associateRequest", {"calledAP": called_ap, "maxMessageSize": max_message_size})),
        )

    def associate_response(self, max_message_size, associate_id, *, max_outstanding_calls=None, service_error=None):
        payload = {"maxMessageSize": max_message_size, "associateId": associate_id}
        if max_outstanding_calls is not None:
            payload["maxOutstandingCalls"] = max_outstanding_calls
        if service_error is not None:
            payload["serviceError"] = service_error
        return ("associate", ("service", ("associateResponse", payload)))

    def release_request(self, invoke_id, associate_id):
        return (
            "associate",
            ("service", ("releaseRequest", {"invokeId": invoke_id, "associateId": associate_id})),
        )

    def release_response(self, invoke_id, associate_id):
        return (
            "associate",
            ("service", ("releaseResponse", {"invokeId": invoke_id, "associateId": associate_id})),
        )

    def abort_request(self, invoke_id, associate_id):
        return (
            "associate",
            ("service", ("abortRequest", {"invokeId": invoke_id, "associateId": associate_id})),
        )

    def abort_response(self, invoke_id, associate_id):
        return (
            "associate",
            ("service", ("abortResponse", {"invokeId": invoke_id, "associateId": associate_id})),
        )

    def token_refresh(self, associate_id, token):
        return ("associate", ("service", ("refreshToken", {"associateId": associate_id, "token": token})))

    # ------------------------------------------------------------------
    # Generic request / response builders
    # ------------------------------------------------------------------

    def request(self, service_name, *, invoke_id, associate_id, **payload):
        return (
            "request",
            {"invokeId": invoke_id, "associateId": associate_id, "service": (service_name, payload)},
        )

    def response(self, service_name, *, invoke_id, associate_id, **payload):
        return (
            "response",
            {"invokeId": invoke_id, "associateId": associate_id, "service": (service_name, payload)},
        )

    def service_error(self, *, invoke_id, associate_id, error):
        return (
            "response",
            {"invokeId": invoke_id, "associateId": associate_id, "serviceError": error},
        )

    # ------------------------------------------------------------------
    # Named request builders (thin wrappers over self.request)
    # ------------------------------------------------------------------

    def get_server_directory(self, invoke_id, associate_id, object_class="logicalDevice"):
        return self.request("getServerDirectory", invoke_id=invoke_id, associate_id=associate_id,
                            objectClass=object_class)

    def get_logical_device_directory(self, invoke_id, associate_id, ld_name):
        return self.request("getLogicalDeviceDirectory", invoke_id=invoke_id, associate_id=associate_id,
                            ldName=ld_name)

    def get_logical_node_directory(self, invoke_id, associate_id, ln_ref, acsi_class):
        return self.request("getLogicalNodeDirectory", invoke_id=invoke_id, associate_id=associate_id,
                            lnRef=ln_ref, aCSIClass=acsi_class)

    def get_data_set_directory(self, invoke_id, associate_id, ds_ref):
        return self.request("getDataSetDirectory", invoke_id=invoke_id, associate_id=associate_id,
                            dsRef=ds_ref)

    def get_data_directory(self, invoke_id, associate_id, data_ref):
        return self.request("getDataDirectory", invoke_id=invoke_id, associate_id=associate_id,
                            dataRef=data_ref)

    def get_data_definition(self, invoke_id, associate_id, data_ref):
        return self.request("getDataDefinition", invoke_id=invoke_id, associate_id=associate_id,
                            dataRef=data_ref)

    def get_data_values(self, invoke_id, associate_id, ref, include_element_name):
        return self.request("getDataValues", invoke_id=invoke_id, associate_id=associate_id,
                            ref=ref, includeElementName=include_element_name)

    def set_data_values(self, invoke_id, associate_id, ref, data_attr_val):
        return self.request("setDataValues", invoke_id=invoke_id, associate_id=associate_id,
                            ref=ref, dataAttrVal=data_attr_val)

    def get_dataset_values(self, invoke_id, associate_id, ds_ref):
        return self.request("getDatasetValues", invoke_id=invoke_id, associate_id=associate_id,
                            dsRef=ds_ref)

    def get_brcb_values(self, invoke_id, associate_id, brcb_ref):
        return self.request("getBRCBValues", invoke_id=invoke_id, associate_id=associate_id,
                            brcbRef=brcb_ref)

    def set_brcb_values(self, invoke_id, associate_id, service_data: dict):
        return ("request", {"invokeId": invoke_id, "associateId": associate_id,
                             "service": ("setBRCBValues", service_data)})

    def get_urcb_values(self, invoke_id, associate_id, urcb_ref):
        return self.request("getURCBValues", invoke_id=invoke_id, associate_id=associate_id,
                            urcbRef=urcb_ref)

    def set_urcb_values(self, invoke_id, associate_id, service_data: dict):
        return ("request", {"invokeId": invoke_id, "associateId": associate_id,
                             "service": ("setURCBValues", service_data)})

    def select(self, invoke_id, associate_id, ref):
        return self.request("select", invoke_id=invoke_id, associate_id=associate_id, ref=ref)

    def operate(self, invoke_id, associate_id, service_data: dict):
        return ("request", {"invokeId": invoke_id, "associateId": associate_id,
                             "service": ("operate", service_data)})
