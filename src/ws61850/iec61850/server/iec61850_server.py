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
import datetime
import re

from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError

from ws61850.asn1.encode_decode import encode_tpaa_message, decode_tpaa_message
from ws61850.iec61850.data_model.helper import get_now_time
from ws61850.iec61850.data_model.ied_model import DataObject, DataAttributeType, FunctionalConstraint, DataAttribute
from ws61850.iec61850.server.control_handling import ControlServiceStatusKind, ControlHandlerResult
from ws61850.iec61850.server.request_handling import create_tpaa_abort_request, create_tpaa_release_request, \
    create_signle_entry_for_report, create_data_attribute_list_from_dataset, extract_associate_request_type, \
    extract_max_message_size, extract_service_name, extract_invoke_id, extract_ld_name, extract_ds_ref, extract_ln_ref, \
    extract_acsiType, get_list_of_items_ln, extract_data_ref, find_do_with_ref, create_subDataDefinition_list, \
    create_DataAttributeDefinition_list, extract_ref, extract_includeElementName, find_object_in_tree, \
    flatten_nested_data_attributes_with_fc, build_data_value, extract_dataAttrVal, assign_da_item, assign_do_item, \
    extract_brcb_ref, extract_urcb_ref, assign_brcb_value, assign_urcb_value, extract_operate_or_select_ref, \
    extract_ctlVal_from_operate_request
from ws61850.iec61850.server.response_handling import create_tpaa_report, create_tpaa_associate_response, \
    create_tpaa_release_response, create_tpaa_abort_response, create_tpaa_service_error_response, \
    create_tpaa_response_getServerDirectory, create_tpaa_response_getLDDirectory, \
    create_tpaa_response_getDataSetDirectoryRequest, create_tpaa_response_getLogicalNodeDirectory, \
    create_tpaa_response_getDataDirectory, create_tpaa_response_getDataDefinition, create_tpaa_response_getDataValues, \
    create_tpaa_response_setDataValues, create_tpaa_response_getDataSetValues, create_tpaa_response_getBRCBValues, \
    create_tpaa_response_getURCBValues, create_tpaa_response_setBRCBValues, create_tpaa_response_setURCBValues, \
    create_tpaa_response_operate, create_tpaa_response_select
from ws61850.iec61850.server.server_control_object import create_server_control_objects_list
from ws61850.iec61850.server.server_report_control import create_server_report_controls_list, ReasonForInclusionInLog
from ws61850.iec61850.server.service_error import ServiceStatusKind


class IEC61850Server:
    """
    Class representing IEC61850Server
    """

    def __init__(self, ied_model, cp, max_outstanding_calls=10):
        """
        Initializer function
        :param ied_model:
        :param cp:
        """
        self.ied_model = ied_model
        self.cp = cp
        self.server_report_controls = create_server_report_controls_list(ied_model)
        self.ready_event = asyncio.Event()
        self.control_handler = None
        self.server_control_objects = create_server_control_objects_list(ied_model)
        self.send_msg_callback = None
        self.recv_msg_callback = None
        self.max_outstanding_calls = max_outstanding_calls

        quality_item = self.find_object_in_tree("LD0/DWMX1.WMaxSpt.q")
        if quality_item is not None:
            quality_item.mmsValue['validity'] = "questionable"

    def install_send_msg_callback(self, callback):
        self.send_msg_callback = callback

    def install_recv_msg_callback(self, callback):
        self.recv_msg_callback = callback

    def set_control_handler(self, handler, parameter):
        """
        Function used for setting control handler
        """
        self.control_handler = (handler, parameter)

    def set_quality_to_questionable(self, obj_ref=None):
        if obj_ref is None:
            quality_item = self.find_object_in_tree("LD0/DWMX1.WMaxSpt.q")
            value = quality_item.mmsValue
            value['validity'] = "questionable"
        else:
            quality_item = self.find_object_in_tree(obj_ref)
            value = quality_item.mmsValue
            value['validity'] = "questionable"

    async def set_quality_to_good(self, control_do):
        quality_item = next((da for da in control_do.get_da_from_do_or_da_list() if
                             da.name == "q"), None)
        value = quality_item.mmsValue.copy()
        value['validity'] = "good"
        await self.update_value(quality_item.get_objRef(), value)

    def get_ctlVal_value(self, obj_ref):
        """
        Function used for getting ctlVal from a control object
        """
        oper_item = self.find_object_in_tree(obj_ref)
        if oper_item is not None:
            da = oper_item.data_attributes[0]
            return {"type": da.type.name, "value": da.mmsValue}
        return None

    def set_ctlVal_value(self, tree_item, value, type):
        """
        Function used for setting values to ctlVal in a control object
        """
        da = tree_item.data_attributes[0]
        if da.type.name == type:
            da.mmsValue = value
            return True
        return False

    def look_in_da_or_do_list(self, seg_ref, foundDO):
        """
        Find an item in a Data Object do_or_da_list
        """
        found_obj = foundDO
        for ref_index, ref_item in enumerate(seg_ref):
            if isinstance(found_obj, DataObject):
                found_item = next(
                    (item for item in found_obj.get_do_from_do_or_da_list() + found_obj.get_da_from_do_or_da_list() if
                     item.name == ref_item), None)
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

    def find_object_in_tree(self, data_ref):
        """
        Find a DataObject or DataAttribute in the IED tree
        """
        return_do = None
        ld_name, ln_name, first_do, *seg_ref = re.split(r'[/ .]', data_ref)
        foundLD = next((ld for ld in self.ied_model.logical_devices if ld.name == ld_name), None)
        if (foundLD):
            foundLN = next((ln for ln in foundLD.logical_nodes if ln.name == ln_name), None)
            if (foundLN):
                foundDO = next((do for do in foundLN.data_objects if do.name == first_do), None)
                if (len(seg_ref) != 0):
                    return_do = self.look_in_da_or_do_list(seg_ref, foundDO)

                else:
                    return_do = foundDO

        return return_do

    def find_ds_in_tree(self, data_ref):
        """
        Find a Dataset in the IED tree
        """
        ld_name, ln_name, ds_name = re.split(r'[/ .]', data_ref)
        foundLN = next((ln for ld in self.ied_model.logical_devices if ld.name == ld_name for ln in ld.logical_nodes if
                        ln.name == ln_name), None)
        if not foundLN:
            return None
        foundDS = next((ds for ds in foundLN.data_sets if ds.name == ds_name), None)

        return foundDS

    async def abort_function(self, websocket_info):
        """
        Function used for aborting the connection
        """
        await self.ready_event.wait()
        if websocket_info.websocket is not None:
            tpaa_request = create_tpaa_abort_request(websocket_info.invoke_id, websocket_info.associate_id)
            request = encode_tpaa_message(tpaa_request, websocket_info.is_ber_protocol)

            await websocket_info.websocket.send(request)

    async def release_function(self, websocket_info):
        """
        Function used for releasing the connection
        """
        await self.ready_event.wait()

        if websocket_info.websocket is not None:
            tpaa_request = create_tpaa_release_request(websocket_info.invoke_id, websocket_info.associate_id)
            request = encode_tpaa_message(tpaa_request, websocket_info.is_ber_protocol)

            await websocket_info.websocket.send(request)

    def get_do_parent(self, item):
        """
        Function used for getting the parent DataObject of an element
        """
        return_item = None
        parent_item = item.parent
        if isinstance(parent_item, DataObject) is True:
            return_item = parent_item
        else:
            return_item = self.get_do_parent(parent_item)
        return return_item

    def update_timestamp(self, item):
        """
        Function used for updating the timestamp of an element
        """
        parent_item = self.get_do_parent(item)
        if isinstance(parent_item, DataObject) is True:
            da_time = next((da for da in parent_item.do_or_da if da.name == "t" and da.fc.name == item.fc.name), None)
            current_time = get_now_time()
            if da_time is not None:
                da_time.mmsValue = current_time

    async def update_value(self, obj_ref, value):
        """
        Function used for updating the value of an element
        """
        await self.ready_event.wait()
        item = self.find_object_in_tree(obj_ref)
        if item.mmsValue != value:
            item.mmsValue = value
            self.update_timestamp(item)
            await self.check_for_changed_trigger(item)

    async def periodic_report_start(self):
        """
        Function used to start periodic reports
        """
        await self.ready_event.wait()
        await self.periodic_report()

    async def check_for_changed_trigger(self, data_attribute):
        """
        Function checks if a report needs to be sent following a value change
        """
        try:
            ied = self.ied_model
            for server_report_control in self.server_report_controls:
                if server_report_control.rptEna:
                    try:
                        if server_report_control.rcb.trgOps["dchg"] is True or server_report_control.rcb.trgOps["qchg"]:
                            obj_ref = server_report_control.rcb.datasetName
                            dataset = self.find_ds_in_tree(obj_ref)
                            is_in_dataset = next(
                                (entry for entry in dataset.fcdas if
                                 entry.variable_name in data_attribute.get_objRef()),
                                None)
                            if is_in_dataset is not None:
                                da_list = None
                                if data_attribute.type == DataAttributeType.quality:
                                    da_list = [create_signle_entry_for_report(data_attribute,
                                                                              ReasonForInclusionInLog(
                                                                                  qualityChange=True))]
                                else:
                                    da_list = [create_signle_entry_for_report(data_attribute,
                                                                              ReasonForInclusionInLog(dataChange=True))]
                                if server_report_control.rcb.client_connection is not None:
                                    server_report_control.time_of_entry = get_now_time()
                                    tpaa_report = create_tpaa_report(server_report_control, da_list,
                                                                     server_report_control.rcb.client_connection.associate_id)
                                    encoded_report = encode_tpaa_message(tpaa_report,
                                                                         server_report_control.rcb.client_connection.is_ber_protocol)
                                    await server_report_control.rcb.client_connection.websocket.send(encoded_report)
                                    if self.send_msg_callback is not None:
                                        self.send_msg_callback(encoded_report, datetime.datetime.now())
                                    server_report_control.seq_num += 1
                                else:
                                    print("client_connection null!")
                    except Exception as e:
                        print("Error in send_event_based_report:", e)

        except asyncio.CancelledError:
            print("Report sending task cancelled.")

    async def periodic_report_task(self, server_report_control):
        """Send a report every `interval` second without blocking receive loop."""
        try:
            while True:

                if server_report_control.rptEna and server_report_control.rcb.trgOps["integrity"]:
                    obj_ref = server_report_control.rcb.datasetName
                    dataset = self.find_ds_in_tree(obj_ref)
                    if dataset is not None:
                        da_list = create_data_attribute_list_from_dataset(dataset,
                                                                          self.ied_model,
                                                                          ReasonForInclusionInLog(
                                                                              integrity=True))
                        server_report_control.time_of_entry = get_now_time()

                        tpaa_report = create_tpaa_report(server_report_control, da_list,
                                                         server_report_control.rcb.client_connection.associate_id)
                        encoded_report = encode_tpaa_message(tpaa_report,
                                                             server_report_control.rcb.client_connection.is_ber_protocol)
                        await server_report_control.rcb.client_connection.websocket.send(encoded_report)

                        if self.send_msg_callback is not None:
                            self.send_msg_callback(encoded_report, datetime.datetime.now())

                        server_report_control.seq_num += 1
                await asyncio.sleep(server_report_control.rcb.intPeriod / 1000)  # Convert milliseconds to seconds

        except ConnectionClosedOK:
            current_task = asyncio.current_task()
            current_task.cancel()
            print("[Report task] connection closed normally.")
        except ConnectionClosedError as e:
            current_task = asyncio.current_task()
            current_task.cancel()
            print("[Report task]: connection closed:", e)
        except Exception as e:
            current_task = asyncio.current_task()
            current_task.cancel()
            print("Error in send_report_periodically:", e)

    async def periodic_report(self):
        """Send a report every `interval` second without blocking receive loop."""
        tasks = []
        for server_report_control in self.server_report_controls:
            tasks.append(asyncio.create_task(self.periodic_report_task(server_report_control),
                                             name=server_report_control.rcb.get_objRef()))

        await asyncio.gather(*tasks)

    async def handle_request(self, message, cp, websocket_info):
        """
        Function used for analyzing the request and sending the correct response accordingly
        """
        websocket = websocket_info.websocket
        ied = self.ied_model
        maxMessageSize_client = 65000
        decoded_message = decode_tpaa_message(message, websocket_info.is_ber_protocol)
        associate_id = "id_" + cp
        websocket_info.associate_id = associate_id

        if decoded_message[0] == "associate":
            associate_type = extract_associate_request_type(decoded_message)
            if associate_type == "associateRequest":
                maxMessageSize_server = extract_max_message_size(decoded_message)
                maxMessageSize = min(maxMessageSize_client, maxMessageSize_server)
                websocket_info.associate_id = associate_id
                tpaa_response = create_tpaa_associate_response(maxMessageSize, associate_id,
                                                               max_outstanding_calls=self.max_outstanding_calls)
                response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)
                await websocket.send(response)
                if self.send_msg_callback is not None:
                    self.send_msg_callback(response, datetime.datetime.now())
                self.ready_event.set()

            elif associate_type == "releaseRequest":
                invoke_id = decoded_message[1][1][1]["invokeId"]

                tpaa_response = create_tpaa_release_response(invoke_id, associate_id)
                response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)
                await websocket.send(response)
                if self.send_msg_callback is not None:
                    self.send_msg_callback(response, datetime.datetime.now())
                await websocket.close()
            elif associate_type == "abortRequest":
                invoke_id = decoded_message[1][1][1]["invokeId"]

                tpaa_response = create_tpaa_abort_response(invoke_id, associate_id)
                response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)
                await websocket.send(response)
                websocket.transport.abort()
            elif associate_type == "abortResponse":
                print("Connection aborted by client")
            else:
                try:
                    invoke_id = decoded_message[1][1][1]["invokeId"]
                    tpaa_response = create_tpaa_service_error_response(invoke_id, associate_id, "classNotSupported")
                    response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)
                    await websocket.send(response)
                except (KeyError, TypeError, IndexError):
                    return  # nothing to do if it doesn't exist

        else:
            service_name = extract_service_name(decoded_message)
            invoke_id = extract_invoke_id(decoded_message)
            websocket_info.invoke_id = invoke_id + 1

            if service_name == "getServerDirectory":
                ld_refs = [ld.name for ld in ied.logical_devices]
                tpaa_response = create_tpaa_response_getServerDirectory(invoke_id, associate_id, ld_refs)
                response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

            elif service_name == "getLogicalDeviceDirectory":
                ld_name = extract_ld_name(decoded_message)
                foundLD = next((ld for ld in ied.logical_devices if ld.name == ld_name), None)

                if foundLD:
                    ln_names = [ln.name for ln in foundLD.logical_nodes]
                    tpaa_response = create_tpaa_response_getLDDirectory(invoke_id, associate_id, ln_names)
                    response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)
                else:
                    tpaa_response = create_tpaa_service_error_response(invoke_id, associate_id, "instanceNotAvailable")
                    response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

            elif service_name == "getDataSetDirectory":
                ds_ref = extract_ds_ref(decoded_message)
                ldName, lnName, dsName = re.split(r'[/.]', ds_ref)
                foundLN = next((ln for ld in ied.logical_devices if ld.name == ldName for ln in ld.logical_nodes if
                                ln.name == lnName), None)
                foundDS = next(
                    (ds for ds in foundLN.data_sets if
                     (ds.logical_device_name == ldName and ds.parent.name == lnName and ds.name == dsName)), None)
                if (foundDS):
                    tpaa_response = create_tpaa_response_getDataSetDirectoryRequest(invoke_id, associate_id,
                                                                                    foundDS.fcdas)
                    response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)
                else:
                    tpaa_response = create_tpaa_service_error_response(invoke_id, associate_id, "instanceNotAvailable")
                    response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

            ##TODO: complete the getLogicalNodeDirectory function
            elif service_name == "getLogicalNodeDirectory":
                ln_ref = extract_ln_ref(decoded_message)
                acsi_service = extract_acsiType(decoded_message)
                refs = get_list_of_items_ln(ln_ref, acsi_service, ied)
                if refs is not None:
                    tpaa_response = create_tpaa_response_getLogicalNodeDirectory(invoke_id, associate_id, refs)
                    response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)
                else:
                    tpaa_response = create_tpaa_service_error_response(invoke_id, associate_id, "instanceNotAvailable")
                    response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

            elif service_name == "getDataDirectory":
                data_ref = extract_data_ref(decoded_message)
                dataObject, seg_ref = find_do_with_ref(data_ref, ied)
                if dataObject is not None:
                    sdo_list = [sdo.name for sdo in dataObject.get_do_from_do_or_da_list()]
                    da_list = [da.name for da in dataObject.get_da_from_do_or_da_list()]
                    tpaa_response = create_tpaa_response_getDataDirectory(invoke_id, associate_id, sdo_list, da_list)
                    response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)
                else:
                    tpaa_response = create_tpaa_service_error_response(invoke_id, associate_id, "instanceNotAvailable")
                    response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

            elif service_name == "getDataDefinition":
                data_ref = extract_data_ref(decoded_message)
                dataObject, seg_ref = find_do_with_ref(data_ref, ied)
                if dataObject is not None:
                    sdo_list, primary_da = create_subDataDefinition_list(dataObject.get_do_from_do_or_da_list())
                    da_list = create_DataAttributeDefinition_list(dataObject.get_da_from_do_or_da_list())
                    tpaa_response = create_tpaa_response_getDataDefinition(invoke_id, associate_id, sdo_list, da_list,
                                                                           dataObject)
                    response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)
                else:
                    tpaa_response = create_tpaa_service_error_response(invoke_id, associate_id, "instanceNotAvailable")
                    response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

            elif service_name == "getDataValues":
                data_ref = extract_ref(decoded_message)
                include_element_name = extract_includeElementName(decoded_message)
                item = find_object_in_tree(data_ref["ref"], ied)
                if item is not None:
                    if isinstance(item, DataObject):
                        da_list = flatten_nested_data_attributes_with_fc(item, data_ref["fc"])
                        da_fc = [build_data_value(da, da.type.name, da.mmsValue, include_element_name) for da in
                                 da_list]

                        tpaa_response = create_tpaa_response_getDataValues(invoke_id, associate_id, da_fc)
                        response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)
                    else:
                        da_fc = [build_data_value(item, item.type.name, item.mmsValue, include_element_name)]
                        tpaa_response = create_tpaa_response_getDataValues(invoke_id, associate_id, da_fc)
                        response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)
                else:
                    tpaa_response = create_tpaa_service_error_response(invoke_id, associate_id, "instanceNotAvailable")
                    response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

            elif service_name == "setDataValues":
                value = None
                data_ref = extract_ref(decoded_message)
                dataAttr_val = extract_dataAttrVal(decoded_message)

                item = find_object_in_tree(data_ref["ref"], ied)
                if item is not None:
                    fc = data_ref["fc"]
                    if fc == FunctionalConstraint.co.name:

                        tpaa_response = create_tpaa_service_error_response(invoke_id, associate_id,
                                                                           "accessViolation")
                        response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)
                    else:
                        if isinstance(item, DataObject):

                            for da_do_index, da_do_item in enumerate(item.do_or_da):

                                if da_do_index < len(dataAttr_val):
                                    value = dataAttr_val[da_do_index]
                                    if isinstance(da_do_item, DataAttribute):

                                        assign_result = assign_da_item(item.do_or_da[da_do_index], value["data"], fc)

                                    else:
                                        assign_result = assign_do_item(item.do_or_da[da_do_index], value["data"], fc)

                            tpaa_response = create_tpaa_response_setDataValues(invoke_id, associate_id, "ok")
                            response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)
                        else:
                            if fc == item.fc.name:
                                result = assign_da_item(item, dataAttr_val[0]["data"], fc)
                                if result is False:
                                    tpaa_response = create_tpaa_service_error_response(invoke_id, associate_id,
                                                                                       "typeConflict")
                                    response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)
                                else:
                                    tpaa_response = create_tpaa_response_setDataValues(invoke_id, associate_id, "ok")
                                    response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)
                            else:
                                tpaa_response = create_tpaa_service_error_response(invoke_id, associate_id,
                                                                                   "instanceNotAvailable")
                                response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

                    # tpaa_response = create_tpaa_response_setDataValues(invoke_id, associate_id, "ok")
                    # response = encode_tpaa_message(tpaa_response)
                else:
                    tpaa_response = create_tpaa_service_error_response(invoke_id, associate_id, "instanceNotAvailable")
                    response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

            elif service_name == "getDatasetValues":
                ds_ref = extract_ds_ref(decoded_message)
                ldName, lnName, dsName = re.split(r'[/.]', ds_ref)
                foundLN = next((ln for ld in ied.logical_devices if ld.name == ldName for ln in ld.logical_nodes if
                                ln.name == lnName), None)
                foundDS = next(
                    (ds for ds in foundLN.data_sets if
                     (ds.logical_device_name == ldName and ds.parent.name == lnName and ds.name == dsName)), None)
                if (foundDS):
                    value_list = []
                    for ds_entry in foundDS.fcdas:
                        item = find_object_in_tree(ds_entry.variable_name, ied)
                        if item is not None:
                            if isinstance(item, DataObject):
                                da_list = flatten_nested_data_attributes_with_fc(item, ds_entry.fc.name)
                                da_fc = [build_data_value(da, da.type.name, da.mmsValue, True) for da in
                                         da_list]
                                for iterable_item in da_fc:
                                    value_list.append(iterable_item)

                            else:
                                da_fc = build_data_value(item, item.type.name, item.mmsValue, True)
                                value_list.append(da_fc)

                    tpaa_response = create_tpaa_response_getDataSetValues(invoke_id, associate_id, value_list)
                    response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)
                else:
                    tpaa_response = create_tpaa_service_error_response(invoke_id, associate_id, "instanceNotAvailable")
                    response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

            elif service_name == "getBRCBValues":
                brcb_ref = extract_brcb_ref(decoded_message)
                brcb = next((server_brcb for server_brcb in self.server_report_controls if (
                        server_brcb.rcb.get_objRef() == brcb_ref)),
                            None)
                if brcb is not None and brcb.rcb.buffered is True:
                    tpaa_response = create_tpaa_response_getBRCBValues(invoke_id, associate_id, brcb)
                    response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)
                else:
                    tpaa_response = create_tpaa_service_error_response(invoke_id, associate_id, "instanceNotAvailable")
                    response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

            elif service_name == "getURCBValues":
                urcb_ref = extract_urcb_ref(decoded_message)
                urcb = next((server_urcb for server_urcb in self.server_report_controls if (
                        server_urcb.rcb.get_objRef() == urcb_ref)),
                            None)
                if urcb is not None and urcb.rcb.buffered is False:
                    tpaa_response = create_tpaa_response_getURCBValues(invoke_id, associate_id, urcb)
                    response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)
                else:
                    tpaa_response = create_tpaa_service_error_response(invoke_id, associate_id, "instanceNotAvailable")
                    response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

            elif service_name == "setBRCBValues":
                brcb_ref = extract_brcb_ref(decoded_message)
                brcb = next((server_brcb for server_brcb in self.server_report_controls if (
                        server_brcb.rcb.get_objRef() == brcb_ref)),
                            None)
                if brcb is not None and brcb.rcb.buffered is True:
                    brcb.rcb.client_connection = websocket_info
                    service = decoded_message[1]["service"]
                    result = assign_brcb_value(brcb, service[1], self)

                    tpaa_response = create_tpaa_response_setBRCBValues(invoke_id, associate_id, result)
                    response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

                    if brcb.rptEna is True and brcb.rcb.trgOps["gi"] is True and brcb.rcb.gi is True:
                        print("value set, sending the one time gi")

                        dataset = self.find_ds_in_tree(brcb.rcb.datasetName)
                        if dataset is not None:
                            da_list = create_data_attribute_list_from_dataset(dataset,
                                                                              self.ied_model,
                                                                              ReasonForInclusionInLog(
                                                                                  generalInterrogation=True))
                            brcb.time_of_entry = get_now_time()
                            tpaa_report = create_tpaa_report(brcb, da_list,
                                                             brcb.rcb.client_connection.associate_id)
                            encoded_report = encode_tpaa_message(tpaa_report, websocket_info.is_ber_protocol)
                            await brcb.rcb.client_connection.websocket.send(encoded_report)
                            if self.send_msg_callback is not None:
                                self.send_msg_callback(response, datetime.datetime.now())
                            brcb.rcb.gi = False

                else:
                    tpaa_response = create_tpaa_service_error_response(invoke_id, associate_id, "instanceNotAvailable")
                    response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

            elif service_name == "setURCBValues":
                urcb_ref = extract_urcb_ref(decoded_message)

                urcb = next((server_urcb for server_urcb in self.server_report_controls if (
                        server_urcb.rcb.get_objRef() == urcb_ref)),
                            None)
                if urcb is not None and urcb.rcb.buffered is False:
                    service = decoded_message[1]["service"]
                    result = assign_urcb_value(urcb, service[1], self)
                    urcb.rcb.client_connection = websocket_info

                    tpaa_response = create_tpaa_response_setURCBValues(invoke_id, associate_id, result)
                    response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

                    if urcb.rptEna is True and urcb.rcb.trgOps["gi"] is True and urcb.rcb.gi is True:
                        print("value set, sending the one time gi")

                        dataset = self.find_ds_in_tree(urcb.rcb.datasetName)
                        if dataset is not None:
                            da_list = create_data_attribute_list_from_dataset(dataset,
                                                                              self.ied_model,
                                                                              ReasonForInclusionInLog(
                                                                                  generalInterrogation=True))
                            urcb.time_of_entry = get_now_time()
                            tpaa_report = create_tpaa_report(urcb, da_list,
                                                             urcb.rcb.client_connection.associate_id)
                            encoded_report = encode_tpaa_message(tpaa_report, websocket_info.is_ber_protocol)
                            await urcb.rcb.client_connection.websocket.send(encoded_report)
                            if self.send_msg_callback is not None:
                                self.send_msg_callback(response, datetime.datetime.now())
                            urcb.rcb.gi = False


                else:
                    tpaa_response = create_tpaa_service_error_response(invoke_id, associate_id, "instanceNotAvailable")
                    response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

            elif service_name == "operate":
                ref = extract_operate_or_select_ref(decoded_message)
                control_do = find_object_in_tree(ref, ied)
                operate_item = next((da for da in control_do.get_da_from_do_or_da_list() if
                                     da.fc == FunctionalConstraint.co and da.name == "Oper"), None)
                if operate_item is None:
                    tpaa_response = create_tpaa_response_operate(invoke_id, associate_id, False,
                                                                 ControlServiceStatusKind.inconsistentParameters.name,
                                                                 None)
                    response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)
                else:
                    server_control_obj = next((control_obj for control_obj in self.server_control_objects
                                               if control_obj.data_object.get_objRef() == control_do.get_objRef()),
                                              None)
                    control_da = next((da for da in operate_item.data_attributes if da.name == "ctlVal"), None)
                    if control_da is not None:
                        ctl_num = next((da for da in operate_item.data_attributes if da.name == "ctlNum"), None)
                        ctlVal_tree_item = next((da for da in operate_item.data_attributes if da.name == "ctlVal"),
                                                None)
                        tpaa_response = None

                        if self.control_handler is not None:
                            ctlVal_request = extract_ctlVal_from_operate_request(decoded_message)
                            assign_result = assign_da_item(control_da, ctlVal_request, control_da.fc.name)

                            if assign_result:

                                if control_do.get_objRef() == "LD0/DWMX1.WMaxSpt":
                                    await self.set_quality_to_good(control_do)

                                ctl_val = self.get_ctlVal_value(control_da.get_objRef())

                                result, error = self.control_handler[0](control_da.get_objRef(), ctl_val,
                                                                        self.control_handler[1])

                                if not server_control_obj.is_selected:
                                    tpaa_response = create_tpaa_response_operate(invoke_id, associate_id, False, None,
                                                                                 ServiceStatusKind.controlMustBeSelected.name)
                                    response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)
                                else:
                                    if result == ControlHandlerResult.OK:
                                        ctl_num.mmsValue += 1
                                        tpaa_response = create_tpaa_response_operate(invoke_id, associate_id, True,
                                                                                     None, None)
                                        response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

                                    else:
                                        if isinstance(error, ControlServiceStatusKind):
                                            ctl_num.mmsValue += 1
                                            tpaa_response = create_tpaa_response_operate(invoke_id, associate_id, False,
                                                                                         error.name, None)

                                            response = encode_tpaa_message(tpaa_response,
                                                                           websocket_info.is_ber_protocol)
                            else:
                                tpaa_response = create_tpaa_response_operate(invoke_id, associate_id, False, None,
                                                                             ServiceStatusKind.typeConflict.name)
                                response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)
                        else:
                            tpaa_response = create_tpaa_response_operate(invoke_id, associate_id, False, None,
                                                                         ServiceStatusKind.failedDueToServerConstraint.name)

                            response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)
                    else:
                        tpaa_response = create_tpaa_response_operate(invoke_id, associate_id, False, None,
                                                                     ServiceStatusKind.instanceNotAvailable.name)
                        response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

            elif service_name == "select":
                ref = extract_operate_or_select_ref(decoded_message)
                control_do = find_object_in_tree(ref, ied)
                server_control_obj = next((control_obj for control_obj in self.server_control_objects
                                           if control_obj.data_object.get_objRef() == control_do.get_objRef()), None)
                if server_control_obj is not None:

                    if not server_control_obj.is_selected:
                        server_control_obj.is_selected = True
                        tpaa_response = create_tpaa_response_select(invoke_id, associate_id, True, None, None)
                        response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)
                    else:
                        tpaa_response = create_tpaa_response_select(invoke_id, associate_id, False,
                                                                    ControlServiceStatusKind.objectAlreadySelected.name,
                                                                    None)
                        response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

                else:
                    tpaa_response = create_tpaa_response_select(invoke_id, associate_id, False, None,
                                                                ServiceStatusKind.instanceNotAvailable.name)
                    response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

            else:
                tpaa_response = create_tpaa_service_error_response(invoke_id, associate_id, "classNotSupported")
                response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

            await websocket.send(response)
            if self.send_msg_callback is not None:
                self.send_msg_callback(response, datetime.datetime.now())
