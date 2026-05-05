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
import logging
import re

from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

from ws61850.asn1.encode_decode import decode_tpaa_message, encode_tpaa_message
from ws61850.iec61850.data_model.helper import get_now_time
from ws61850.iec61850.data_model.ied_model import (
    DataAttribute,
    DataAttributeType,
    DataObject,
)
from ws61850.iec61850.server.request_handling import (
    create_data_attribute_list_from_dataset,
    create_signle_entry_for_report,
    create_tpaa_abort_request,
    create_tpaa_release_request,
    extract_associate_request_type,
    extract_invoke_id,
    extract_max_message_size,
    extract_service_name,
    find_object_in_tree,
)
from ws61850.iec61850.server.response_handling import (
    create_tpaa_abort_response,
    create_tpaa_associate_response,
    create_tpaa_release_response,
    create_tpaa_report,
    create_tpaa_service_error_response,
)
from ws61850.iec61850.server.server_control_object import (
    create_server_control_objects_list,
)
from ws61850.iec61850.server.server_report_control import (
    ReasonForInclusionInLog,
    create_server_report_controls_list,
)
from ws61850.iec61850.services.control_service import ControlService
from ws61850.iec61850.services.data_access_service import DataAccessService
from ws61850.iec61850.services.directory_service import DirectoryService
from ws61850.iec61850.services.report_service import ReportService

logger = logging.getLogger(__name__)


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

        self._directory_service = DirectoryService(ied_model)
        self._data_access_service = DataAccessService(ied_model)
        self._report_service = ReportService(self.server_report_controls)
        self._control_service = ControlService(
            ied_model, self.server_control_objects, lambda: self.control_handler
        )

        quality_item = self.find_object_in_tree("LD0/DWMX1.WMaxSpt.q")
        if quality_item is not None:
            quality_item.mmsValue["validity"] = "questionable"

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
            value["validity"] = "questionable"
        else:
            quality_item = self.find_object_in_tree(obj_ref)
            value = quality_item.mmsValue
            value["validity"] = "questionable"

    async def set_quality_to_good(self, control_do):
        quality_item = next((da for da in control_do.get_da_from_do_or_da_list() if da.name == "q"), None)
        value = quality_item.mmsValue.copy()
        value["validity"] = "good"
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

    def find_object_in_tree(self, data_ref):
        """
        Find a DataObject or DataAttribute in the IED tree
        """
        return_do = None
        ld_name, ln_name, first_do, *seg_ref = re.split(r"[/ .]", data_ref)
        foundLD = next((ld for ld in self.ied_model.logical_devices if ld.name == ld_name), None)
        if foundLD:
            foundLN = next((ln for ln in foundLD.logical_nodes if ln.name == ln_name), None)
            if foundLN:
                foundDO = next((do for do in foundLN.data_objects if do.name == first_do), None)
                if len(seg_ref) != 0:
                    return_do = self.look_in_da_or_do_list(seg_ref, foundDO)

                else:
                    return_do = foundDO

        return return_do

    def find_ds_in_tree(self, data_ref):
        """
        Find a Dataset in the IED tree
        """
        ld_name, ln_name, ds_name = re.split(r"[/ .]", data_ref)
        foundLN = next(
            (
                ln
                for ld in self.ied_model.logical_devices
                if ld.name == ld_name
                for ln in ld.logical_nodes
                if ln.name == ln_name
            ),
            None,
        )
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
        current_item = item
        while current_item is not None:
            if isinstance(current_item, DataObject):
                return current_item
            current_item = current_item.parent
        return None

    def get_control_data_object(self, data_ref, ied):
        """
        Resolve control service refs to the owning DataObject.
        """
        control_item = find_object_in_tree(data_ref, ied)
        if isinstance(control_item, DataObject):
            return control_item
        if isinstance(control_item, DataAttribute):
            return self.get_do_parent(control_item)
        return None

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
                                (
                                    entry
                                    for entry in dataset.fcdas
                                    if entry.variable_name in data_attribute.get_objRef()
                                ),
                                None,
                            )
                            if is_in_dataset is not None:
                                da_list = None
                                if data_attribute.type == DataAttributeType.quality:
                                    da_list = [
                                        create_signle_entry_for_report(
                                            data_attribute, ReasonForInclusionInLog(qualityChange=True)
                                        )
                                    ]
                                else:
                                    da_list = [
                                        create_signle_entry_for_report(
                                            data_attribute, ReasonForInclusionInLog(dataChange=True)
                                        )
                                    ]
                                if server_report_control.rcb.client_connection is not None:
                                    server_report_control.time_of_entry = get_now_time()
                                    tpaa_report = create_tpaa_report(
                                        server_report_control,
                                        da_list,
                                        server_report_control.rcb.client_connection.associate_id,
                                    )
                                    encoded_report = encode_tpaa_message(
                                        tpaa_report, server_report_control.rcb.client_connection.is_ber_protocol
                                    )
                                    await server_report_control.rcb.client_connection.websocket.send(encoded_report)
                                    if self.send_msg_callback is not None:
                                        self.send_msg_callback(encoded_report, datetime.datetime.now())
                                    server_report_control.seq_num += 1
                                else:
                                    logger.info("Client connection is null!")
                    except Exception as e:
                        logger.error("Error in send_event_based_report:", e)

        except asyncio.CancelledError:
            logger.info("Report sending task cancelled.")

    async def periodic_report_task(self, server_report_control):
        """Send a report every `interval` second without blocking receive loop."""
        try:
            while True:

                if server_report_control.rptEna and server_report_control.rcb.trgOps["integrity"]:
                    obj_ref = server_report_control.rcb.datasetName
                    dataset = self.find_ds_in_tree(obj_ref)
                    if dataset is not None:
                        da_list = create_data_attribute_list_from_dataset(
                            dataset, self.ied_model, ReasonForInclusionInLog(integrity=True)
                        )
                        server_report_control.time_of_entry = get_now_time()

                        tpaa_report = create_tpaa_report(
                            server_report_control, da_list, server_report_control.rcb.client_connection.associate_id
                        )
                        encoded_report = encode_tpaa_message(
                            tpaa_report, server_report_control.rcb.client_connection.is_ber_protocol
                        )
                        await server_report_control.rcb.client_connection.websocket.send(encoded_report)

                        if self.send_msg_callback is not None:
                            self.send_msg_callback(encoded_report, datetime.datetime.now())

                        server_report_control.seq_num += 1
                await asyncio.sleep(server_report_control.rcb.intPeriod / 1000)  # Convert milliseconds to seconds

        except ConnectionClosedOK:
            current_task = asyncio.current_task()
            current_task.cancel()
            logger.info("[Report task] connection closed normally.")
        except ConnectionClosedError as e:
            current_task = asyncio.current_task()
            current_task.cancel()
            logger.error("[Report task]: connection closed:", e)
        except Exception as e:
            current_task = asyncio.current_task()
            current_task.cancel()
            logger.error("Error in send_report_periodically:", e)

    async def periodic_report(self):
        """Send a report every `interval` second without blocking receive loop."""
        tasks = []
        for server_report_control in self.server_report_controls:
            tasks.append(
                asyncio.create_task(
                    self.periodic_report_task(server_report_control), name=server_report_control.rcb.get_objRef()
                )
            )

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
            logger.debug("Association message cp=%r type=%r", cp, associate_type)
            if associate_type == "associateRequest":
                maxMessageSize_server = extract_max_message_size(decoded_message)
                maxMessageSize = min(maxMessageSize_client, maxMessageSize_server)
                websocket_info.associate_id = associate_id
                tpaa_response = create_tpaa_associate_response(
                    maxMessageSize, associate_id, max_outstanding_calls=self.max_outstanding_calls
                )
                response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)
                await websocket.send(response)
                if self.send_msg_callback is not None:
                    self.send_msg_callback(response, datetime.datetime.now())
                self.ready_event.set()
                logger.info(
                    "Association accepted cp=%r associate_id=%r max_msg_size=%s",
                    cp,
                    associate_id,
                    maxMessageSize,
                )

            elif associate_type == "releaseRequest":
                invoke_id = decoded_message[1][1][1]["invokeId"]
                logger.info("Release request cp=%r associate_id=%r", cp, associate_id)
                tpaa_response = create_tpaa_release_response(invoke_id, associate_id)
                response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)
                await websocket.send(response)
                if self.send_msg_callback is not None:
                    self.send_msg_callback(response, datetime.datetime.now())
                await websocket.close()
            elif associate_type == "abortRequest":
                invoke_id = decoded_message[1][1][1]["invokeId"]
                logger.info("Abort request cp=%r associate_id=%r", cp, associate_id)
                tpaa_response = create_tpaa_abort_response(invoke_id, associate_id)
                response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)
                await websocket.send(response)
                websocket.transport.abort()
            elif associate_type == "abortResponse":
                logger.info("Connection aborted by client cp=%r", cp)
            else:
                logger.warning("Unsupported association type=%r cp=%r", associate_type, cp)
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
            logger.debug("Service request cp=%r service=%r invoke_id=%s", cp, service_name, invoke_id)

            if service_name == "getServerDirectory":
                tpaa_response = self._directory_service.get_server_directory(invoke_id, associate_id)
                response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

            elif service_name == "getLogicalDeviceDirectory":
                tpaa_response = self._directory_service.get_logical_device_directory(invoke_id, associate_id, decoded_message)
                response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

            elif service_name == "getLogicalNodeDirectory":
                tpaa_response = self._directory_service.get_logical_node_directory(invoke_id, associate_id, decoded_message)
                response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

            elif service_name == "getDataSetDirectory":
                tpaa_response = self._directory_service.get_data_set_directory(invoke_id, associate_id, decoded_message)
                response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

            elif service_name == "getDataDirectory":
                tpaa_response = self._directory_service.get_data_directory(invoke_id, associate_id, decoded_message)
                response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

            elif service_name == "getDataDefinition":
                tpaa_response = self._directory_service.get_data_definition(invoke_id, associate_id, decoded_message)
                response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

            elif service_name == "getDataValues":
                tpaa_response = self._data_access_service.get_data_values(invoke_id, associate_id, decoded_message)
                response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

            elif service_name == "setDataValues":
                tpaa_response = self._data_access_service.set_data_values(invoke_id, associate_id, decoded_message)
                response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

            elif service_name == "getDatasetValues":
                tpaa_response = self._data_access_service.get_dataset_values(
                    invoke_id, associate_id, decoded_message, self.find_ds_in_tree
                )
                response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

            elif service_name == "getBRCBValues":
                tpaa_response, _ = self._report_service.get_brcb_values(invoke_id, associate_id, decoded_message)
                response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

            elif service_name == "getURCBValues":
                tpaa_response, _ = self._report_service.get_urcb_values(invoke_id, associate_id, decoded_message)
                response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

            elif service_name == "setBRCBValues":
                tpaa_response, gi_brcb = self._report_service.set_brcb_values(
                    invoke_id, associate_id, decoded_message, websocket_info, self
                )
                response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)
                if gi_brcb is not None:
                    logger.info("value set, sending the one time gi")
                    dataset = self.find_ds_in_tree(gi_brcb.rcb.datasetName)
                    if dataset is not None:
                        da_list = create_data_attribute_list_from_dataset(
                            dataset, self.ied_model, ReasonForInclusionInLog(generalInterrogation=True)
                        )
                        gi_brcb.time_of_entry = get_now_time()
                        tpaa_report = create_tpaa_report(gi_brcb, da_list, gi_brcb.rcb.client_connection.associate_id)
                        encoded_report = encode_tpaa_message(tpaa_report, websocket_info.is_ber_protocol)
                        await gi_brcb.rcb.client_connection.websocket.send(encoded_report)
                        if self.send_msg_callback is not None:
                            self.send_msg_callback(response, datetime.datetime.now())
                        gi_brcb.rcb.gi = False

            elif service_name == "setURCBValues":
                tpaa_response, gi_urcb = self._report_service.set_urcb_values(
                    invoke_id, associate_id, decoded_message, websocket_info, self
                )
                response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)
                if gi_urcb is not None:
                    logger.info("value set, sending the one time gi")
                    dataset = self.find_ds_in_tree(gi_urcb.rcb.datasetName)
                    if dataset is not None:
                        da_list = create_data_attribute_list_from_dataset(
                            dataset, self.ied_model, ReasonForInclusionInLog(generalInterrogation=True)
                        )
                        gi_urcb.time_of_entry = get_now_time()
                        tpaa_report = create_tpaa_report(gi_urcb, da_list, gi_urcb.rcb.client_connection.associate_id)
                        encoded_report = encode_tpaa_message(tpaa_report, websocket_info.is_ber_protocol)
                        await gi_urcb.rcb.client_connection.websocket.send(encoded_report)
                        if self.send_msg_callback is not None:
                            self.send_msg_callback(response, datetime.datetime.now())
                        gi_urcb.rcb.gi = False

            elif service_name == "operate":
                tpaa_response, quality_do = self._control_service.operate(invoke_id, associate_id, decoded_message)
                if quality_do is not None:
                    await self.set_quality_to_good(quality_do)
                response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

            elif service_name == "select":
                tpaa_response, _ = self._control_service.select(invoke_id, associate_id, decoded_message)
                response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

            else:
                logger.warning("Unsupported service cp=%r service=%r invoke_id=%s", cp, service_name, invoke_id)
                tpaa_response = create_tpaa_service_error_response(invoke_id, associate_id, "classNotSupported")
                response = encode_tpaa_message(tpaa_response, websocket_info.is_ber_protocol)

            await websocket.send(response)
            if self.send_msg_callback is not None:
                self.send_msg_callback(response, datetime.datetime.now())
