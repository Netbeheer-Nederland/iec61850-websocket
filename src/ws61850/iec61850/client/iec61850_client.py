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
from collections import deque

from ws61850.asn1.encode_decode import decode_tpaa_message, encode_tpaa_message
from ws61850.endpoint.endpoint import WebSocketInfo
from ws61850.iec61850.client.reconstruct_tree_client import (
    build_fcd_ref,
    extract_associate_request_type,
    extract_invoke_id,
    retrieve_associate_id,
    retrieve_data_definition,
    retrieve_data_val,
    retrieve_ds_items,
    retrieve_ds_values,
    retrieve_lds,
    retrieve_ln_items,
    retrieve_lns,
    retrieve_rcb_val,
    retrieve_service_name,
    retrieve_set_result,
    retrieve_success,
)
from ws61850.iec61850.client.request_handling import (
    create_tpaa_abort_request,
    create_tpaa_release_request,
    create_tpaa_request_getBRCBValuesRequest,
    create_tpaa_request_getDataDefinition,
    create_tpaa_request_getDataDirectory,
    create_tpaa_request_getDataSetDirectoryRequest,
    create_tpaa_request_getDataSetValues,
    create_tpaa_request_getDataValues,
    create_tpaa_request_getLDDirectory,
    create_tpaa_request_getLogicalNodeDirectory,
    create_tpaa_request_getServerDirectory,
    create_tpaa_request_getURCBValuesRequest,
    create_tpaa_request_operate,
    create_tpaa_request_select,
    create_tpaa_request_setBRCBValuesRequest,
    create_tpaa_request_setDataValues,
    create_tpaa_request_setURCBValuesRequest,
)

logger = logging.getLogger(__name__)


class IEC61850Client:
    """
    Class used to represent IEC61850Client
    """

    def __init__(self, cp, max_outstanding_call=12):
        """
        Initializing function
        :param cp:
        """
        self.cp = cp
        self.request_list = []
        self.is_connected = False
        self.ready_event = asyncio.Event()
        self.max_outstanding_call = max_outstanding_call
        self.outstanding_calls = deque(maxlen=max_outstanding_call)
        self.response_received = asyncio.Event()  # Event-driven response notification
        self.send_msg_callback = None
        self.recv_msg_callback = None
        self.disconnect_event = asyncio.Event()

    def install_send_msg_callback(self, callback):
        self.send_msg_callback = callback

    def install_recv_msg_callback(self, callback):
        self.recv_msg_callback = callback

    def add_to_outstanding_calls(self, decoded_message, is_ber_protocol):
        """
        Function to decode a message and add it the list of outstanding calls
        """
        if decoded_message[0] != "unconfirmed" and decoded_message[0] != "associate":
            self.outstanding_calls.append(decoded_message)
            self.response_received.set()  # Notify waiters that a response arrived
            if decoded_message[0] != "associate":
                invoke_id = extract_invoke_id(decoded_message)
                return invoke_id

        elif decoded_message[0] != "unconfirmed" and decoded_message[0] == "associate":
            if decoded_message[0][1] == "abortRequest" or decoded_message[0][1] == "releaseRequest":
                invoke_id = extract_invoke_id(decoded_message)
                return invoke_id
        return None

    def find_outstanding_call(self, message, outstanding_calls, websocket_info):
        decoded_message = decode_tpaa_message(message, websocket_info.is_ber_protocol)
        if decoded_message[0] == "associate":
            if decoded_message[0] == "associate":
                associate_type = extract_associate_request_type(decoded_message)
                if associate_type == "associateResponse":
                    asc_id = retrieve_associate_id(message)
                    websocket_info.associate_id = asc_id
                    self.is_connected = True
                    self.ready_event.set()
        elif decoded_message[0] == "response":
            invoke_id = extract_invoke_id(decoded_message)
            outstanding_call = next((call for call in outstanding_calls if call[1]["service"][0] == invoke_id), None)
            callback = outstanding_call["callback"]
            parameter = outstanding_call["parameter"]
            callback(parameter)

    async def await_response(self, invoke_id):
        """
        Function used for extracting the corresponding message from the list of outstanding calls using invoke_id.
        Event-driven: waits for response_received event instead of polling with sleep.
        """
        timeout = 12  # Total timeout in seconds
        start_time = asyncio.get_event_loop().time()

        while (asyncio.get_event_loop().time() - start_time) < timeout:

            if self.disconnect_event.is_set():
                logger.info(f"Connection closed while waiting for invoke_id={invoke_id}")
                await asyncio.sleep(0.2)
                self.response_received.clear()
                return None

            try:
                # Check if response already arrived
                for call in self.outstanding_calls:
                    if call[0] not in ("associate", "unconfirmed"):
                        if call[1].get("invokeId") == invoke_id:
                            return call
                    if call[0] == "associate":
                        if call[1][1][1].get("invokeId") is not None:
                            if call[1][1][1].get("invokeId") == invoke_id:
                                return call
            except Exception as e:
                logger.info("error in await_response: ", e)

            # Wait for next response notification (with short timeout to allow periodic checks)
            try:
                await asyncio.wait_for(self.response_received.wait(), timeout=0.2)
                self.response_received.clear()  # Reset for next wait
            except asyncio.TimeoutError:
                continue  # Check again
        self.response_received.clear()
        logger.info(f"response not found for invoke_id={invoke_id}!")
        return None

    async def select(self, data, websocket_info: WebSocketInfo, callback, parameter):
        """
        Function used for sending select request and awaiting its response
        """
        tpaa_request = create_tpaa_request_select(websocket_info.invoke_id, websocket_info.associate_id, data)

        request = encode_tpaa_message(tpaa_request, websocket_info.is_ber_protocol)
        await websocket_info.websocket.send(request)
        if self.send_msg_callback is not None:
            self.send_msg_callback(request, datetime.datetime.now())
        response = await self.await_response(websocket_info.invoke_id)

        if response is not None:
            self.outstanding_calls.remove(response)
            service_name = retrieve_service_name(response)
            if service_name[0] != "serviceError":
                success = retrieve_success(response)
                if callback is not None:
                    callback(success, parameter)
                websocket_info.invoke_id += 1
                return success
            else:
                websocket_info.invoke_id += 1
                return service_name[1]

        else:
            websocket_info.invoke_id += 1
            return None

    async def operate(self, data, websocket_info: WebSocketInfo, callback, parameter):
        """
        Function used for sending operate request and awaiting its response
        """
        tpaa_request = create_tpaa_request_operate(websocket_info.invoke_id, websocket_info.associate_id, data)

        request = encode_tpaa_message(tpaa_request, websocket_info.is_ber_protocol)
        await websocket_info.websocket.send(request)
        if self.send_msg_callback is not None:
            self.send_msg_callback(request, datetime.datetime.now())
        response = await self.await_response(websocket_info.invoke_id)

        if response is not None:
            self.outstanding_calls.remove(response)
            service_name = retrieve_service_name(response)
            if service_name[0] != "serviceError":
                success = retrieve_success(response)
                if success == True:
                    if callback is not None:
                        callback(success, parameter)
                    websocket_info.invoke_id += 1
                    return success
                else:
                    websocket_info.invoke_id += 1
                    return service_name[1]
            else:
                websocket_info.invoke_id += 1
                return service_name[1]

        else:
            websocket_info.invoke_id += 1
            return None

    async def get_server_directory(self, websocket_info: WebSocketInfo, callback, parameter):
        """
        Function used for sending getServerDirectory request and awaiting its response
        """

        tpaa_request = create_tpaa_request_getServerDirectory(
            websocket_info.invoke_id, websocket_info.associate_id, "logicalDevice"
        )

        request = encode_tpaa_message(tpaa_request, websocket_info.is_ber_protocol)
        await websocket_info.websocket.send(request)
        if self.send_msg_callback is not None:
            self.send_msg_callback(request, datetime.datetime.now())
        response = await self.await_response(websocket_info.invoke_id)

        if response is not None:
            self.outstanding_calls.remove(response)
            service_name = retrieve_service_name(response)
            if service_name[0] != "serviceError":
                ld_list = retrieve_lds(response)
                if callback is not None:
                    callback(ld_list, parameter)
                websocket_info.invoke_id += 1
                return ld_list
            else:
                websocket_info.invoke_id += 1
                return service_name[1]

        else:
            websocket_info.invoke_id += 1
            return None

    async def get_logical_device_directory(self, ld_inst, websocket_info: WebSocketInfo, callback, parameter):
        """
        Function used for sending getLogicalDeviceDirectory request and awaiting its response
        """

        tpaa_request = create_tpaa_request_getLDDirectory(
            websocket_info.invoke_id, websocket_info.associate_id, ld_inst
        )

        request = encode_tpaa_message(tpaa_request, websocket_info.is_ber_protocol)
        await websocket_info.websocket.send(request)
        if self.send_msg_callback is not None:
            self.send_msg_callback(request, datetime.datetime.now())

        response = await self.await_response(websocket_info.invoke_id)
        if response is not None:
            self.outstanding_calls.remove(response)
            service_name = retrieve_service_name(response)
            if service_name[0] != "serviceError":
                ln_list = retrieve_lns(response)
                websocket_info.invoke_id += 1

                if callback is not None:
                    callback(ln_list, parameter)

                return ln_list

            else:
                websocket_info.invoke_id += 1
                return service_name[1]
        else:
            websocket_info.invoke_id += 1
            return None

    async def get_logical_node_directory(
        self, ld_inst, ln_inst, mode, websocket_info: WebSocketInfo, callback, parameter
    ):
        """
        Function used for sending getLogicalNodeDirectory request and awaiting its response
        """

        tpaa_request = create_tpaa_request_getLogicalNodeDirectory(
            websocket_info.invoke_id, websocket_info.associate_id, ld_inst + "/" + ln_inst, aCSIClass=mode
        )
        request = encode_tpaa_message(tpaa_request, websocket_info.is_ber_protocol)
        await websocket_info.websocket.send(request)
        if self.send_msg_callback is not None:
            self.send_msg_callback(request, datetime.datetime.now())
        response = await self.await_response(websocket_info.invoke_id)

        if response is not None:
            self.outstanding_calls.remove(response)
            service_name = retrieve_service_name(response)
            if service_name[0] != "serviceError":
                ln_items = retrieve_ln_items(response)
                if callback is not None:
                    callback(ln_items, parameter)
                websocket_info.invoke_id += 1
                return ln_items
            else:
                websocket_info.invoke_id += 1
                return service_name[1]
        else:
            websocket_info.invoke_id += 1
            return None

    async def get_dataset_directory(self, ld_inst, ln_inst, ds_inst, websocket_info, callback, parameter):
        """
        Function used for sending getDatasetDirectory request and awaiting its response
        """

        tpaa_request = create_tpaa_request_getDataSetDirectoryRequest(
            websocket_info.invoke_id, websocket_info.associate_id, ld_inst + "/" + ln_inst + "." + ds_inst
        )

        request = encode_tpaa_message(tpaa_request, websocket_info.is_ber_protocol)
        await websocket_info.websocket.send(request)
        if self.send_msg_callback is not None:
            self.send_msg_callback(request, datetime.datetime.now())
        response = await self.await_response(websocket_info.invoke_id)
        if response is not None:
            self.outstanding_calls.remove(response)
            service_name = retrieve_service_name(response)
            if service_name[0] != "serviceError":
                ds_items = retrieve_ds_items(response)
                if callback is not None:
                    callback(ds_items, parameter)
                websocket_info.invoke_id += 1
                return ds_items
            else:
                websocket_info.invoke_id += 1
                return service_name[1]
        else:
            websocket_info.invoke_id += 1
            return None

    async def get_dataset_values(self, ld_inst, ln_inst, ds_inst, websocket_info, callback, parameter):
        """
        Function used for sending getDatasetDirectory request and awaiting its response
        """

        tpaa_request = create_tpaa_request_getDataSetValues(
            websocket_info.invoke_id, websocket_info.associate_id, ld_inst + "/" + ln_inst + "." + ds_inst
        )

        request = encode_tpaa_message(tpaa_request, websocket_info.is_ber_protocol)
        await websocket_info.websocket.send(request)
        if self.send_msg_callback is not None:
            self.send_msg_callback(request, datetime.datetime.now())

        response = await self.await_response(websocket_info.invoke_id)
        if response is not None:
            self.outstanding_calls.remove(response)
            service_name = retrieve_service_name(response)
            if service_name[0] != "serviceError":
                ds_items = retrieve_ds_values(response)
                if callback is not None:
                    callback(ds_items, parameter)
                websocket_info.invoke_id += 1
                return ds_items
            else:
                websocket_info.invoke_id += 1
                return service_name[1]
        else:
            websocket_info.invoke_id += 1
            return None

    async def get_data_definition(self, obj_ref, websocket_info, callback, parameter):
        """
        Function used for sending getDataDefinition request and awaiting its response
        """

        tpaa_request = create_tpaa_request_getDataDefinition(
            websocket_info.invoke_id, websocket_info.associate_id, obj_ref
        )
        request = encode_tpaa_message(tpaa_request, websocket_info.is_ber_protocol)
        await websocket_info.websocket.send(request)
        if self.send_msg_callback is not None:
            self.send_msg_callback(request, datetime.datetime.now())

        response = await self.await_response(websocket_info.invoke_id)
        if response is not None:
            self.outstanding_calls.remove(response)
            service_name = retrieve_service_name(response)
            if service_name[0] != "serviceError":
                data_def = retrieve_data_definition(response)
                if callback is not None:
                    callback(data_def, parameter)

                websocket_info.invoke_id += 1
                return data_def
            else:
                websocket_info.invoke_id += 1
                return service_name[1]
        else:
            websocket_info.invoke_id += 1
            return None

    async def get_data_directory(self, obj_ref, websocket_info, callback, parameter):
        """
        Function used for sending getDataDefinition request and awaiting its response
        """

        tpaa_request = create_tpaa_request_getDataDirectory(
            websocket_info.invoke_id, websocket_info.associate_id, obj_ref
        )
        request = encode_tpaa_message(tpaa_request, websocket_info.is_ber_protocol)
        await websocket_info.websocket.send(request)
        if self.send_msg_callback is not None:
            self.send_msg_callback(request, datetime.datetime.now())

        response = await self.await_response(websocket_info.invoke_id)
        if response is not None:
            self.outstanding_calls.remove(response)
            service_name = retrieve_service_name(response)
            if service_name[0] != "serviceError":
                data_def = retrieve_data_definition(response)
                if callback is not None:
                    callback(data_def, parameter)

                websocket_info.invoke_id += 1
                return data_def
            else:
                websocket_info.invoke_id += 1
                return service_name[1]
        else:
            websocket_info.invoke_id += 1
            return None

    async def get_data_values(self, obj_ref, fc, include_element_name, websocket_info, callback, parameter):
        """
        Function used for sending getDataValues request and awaiting its response
        """

        tpaa_request = create_tpaa_request_getDataValues(
            websocket_info.invoke_id, websocket_info.associate_id, build_fcd_ref(obj_ref, fc), include_element_name
        )

        request = encode_tpaa_message(tpaa_request, websocket_info.is_ber_protocol)
        await websocket_info.websocket.send(request)
        if self.send_msg_callback is not None:
            self.send_msg_callback(request, datetime.datetime.now())

        response = await self.await_response(websocket_info.invoke_id)
        if response is not None:
            self.outstanding_calls.remove(response)
            service_name = retrieve_service_name(response)
            if service_name[0] != "serviceError":
                data_val = retrieve_data_val(response)
                if callback is not None:
                    callback(data_val, parameter)
                websocket_info.invoke_id += 1
                return data_val
            else:
                websocket_info.invoke_id += 1
                return service_name[1]
        else:
            websocket_info.invoke_id += 1
            return None

    async def set_data_values(self, obj_ref, fc, value, websocket_info, callback, parameter):
        """
        Function used for sending setDataValues request and awaiting its response
        """

        tpaa_request = create_tpaa_request_setDataValues(
            websocket_info.invoke_id, websocket_info.associate_id, build_fcd_ref(obj_ref, fc), value
        )

        request = encode_tpaa_message(tpaa_request, websocket_info.is_ber_protocol)
        await websocket_info.websocket.send(request)
        if self.send_msg_callback is not None:
            self.send_msg_callback(request, datetime.datetime.now())
        response = await self.await_response(websocket_info.invoke_id)
        if response is not None:
            self.outstanding_calls.remove(response)
            service_name = retrieve_service_name(response)
            if service_name[0] != "serviceError":
                set_val = retrieve_set_result(response)

                result = False
                if set_val == "ok":
                    result = True
                if callback is not None:
                    callback(result, parameter)
                websocket_info.invoke_id += 1
                return result
            else:
                websocket_info.invoke_id += 1
                return service_name[1]
        else:
            websocket_info.invoke_id += 1
            return None

    async def get_BRCB_values(self, obj_ref, websocket_info, callback, parameter):
        """
        Function used for sending getBRCBValues request and awaiting its response
        """

        tpaa_request = create_tpaa_request_getBRCBValuesRequest(
            websocket_info.invoke_id, websocket_info.associate_id, obj_ref
        )
        request = encode_tpaa_message(tpaa_request, websocket_info.is_ber_protocol)

        await websocket_info.websocket.send(request)
        if self.send_msg_callback is not None:
            self.send_msg_callback(request, datetime.datetime.now())

        response = await self.await_response(websocket_info.invoke_id)
        if response is not None:
            self.outstanding_calls.remove(response)
            service_name = retrieve_service_name(response)
            if service_name[0] != "serviceError":
                data_val = retrieve_rcb_val(response)
                if callback is not None:
                    callback(data_val, parameter)
                websocket_info.invoke_id += 1
                return data_val
            else:
                websocket_info.invoke_id += 1
                return service_name[1]

        else:
            websocket_info.invoke_id += 1
            return None

    async def set_BRCB_values(self, client_report_control, websocket_info, callback, parameter):
        """
        Function used for sending setBRCBValues request and awaiting its response
        """

        tpaa_request = create_tpaa_request_setBRCBValuesRequest(
            websocket_info.invoke_id, websocket_info.associate_id, client_report_control
        )
        request = encode_tpaa_message(tpaa_request, websocket_info.is_ber_protocol)
        await websocket_info.websocket.send(request)
        if self.send_msg_callback is not None:
            self.send_msg_callback(request, datetime.datetime.now())

        response = await self.await_response(websocket_info.invoke_id)
        if response is not None:
            self.outstanding_calls.remove(response)
            service_name = retrieve_service_name(response)
            if service_name[0] != "serviceError":
                set_val = retrieve_set_result(response)

                result = False
                if set_val == "ok":
                    result = True

                if callback is not None:
                    callback(result, parameter)
                websocket_info.invoke_id += 1
                return result
            else:
                websocket_info.invoke_id += 1
                return service_name[1]
        else:
            websocket_info.invoke_id += 1
            return None

    async def set_URCB_values(self, client_report_control, websocket_info, callback, parameter):
        """
        Function used for sending setURCBValues request and awaiting its response
        """

        tpaa_request = create_tpaa_request_setURCBValuesRequest(
            websocket_info.invoke_id, websocket_info.associate_id, client_report_control
        )

        request = encode_tpaa_message(tpaa_request, websocket_info.is_ber_protocol)

        await websocket_info.websocket.send(request)
        if self.send_msg_callback is not None:
            self.send_msg_callback(request, datetime.datetime.now())

        response = await self.await_response(websocket_info.invoke_id)
        if response is not None:
            self.outstanding_calls.remove(response)
            service_name = retrieve_service_name(response)
            if service_name[0] != "serviceError":
                set_val = retrieve_set_result(response)

                result = False
                if set_val == "ok":
                    result = True
                if callback is not None:
                    callback(result, parameter)

                websocket_info.invoke_id += 1
                return result
            else:
                websocket_info.invoke_id += 1
                return service_name[1]

        else:
            websocket_info.invoke_id += 1
            return None

    async def get_URCB_values(self, obj_ref, websocket_info, callback, parameter):
        """
        Function used for sending getURCBValues request and awaiting its response
        """

        tpaa_request = create_tpaa_request_getURCBValuesRequest(
            websocket_info.invoke_id, websocket_info.associate_id, obj_ref
        )
        request = encode_tpaa_message(tpaa_request, websocket_info.is_ber_protocol)

        await websocket_info.websocket.send(request)
        if self.send_msg_callback is not None:
            self.send_msg_callback(request, datetime.datetime.now())

        response = await self.await_response(websocket_info.invoke_id)
        if response is not None:
            self.outstanding_calls.remove(response)
            service_name = retrieve_service_name(response)
            if service_name[0] != "serviceError":
                data_val = retrieve_rcb_val(response)
                if callback is not None:
                    callback(data_val, parameter)
                websocket_info.invoke_id += 1
                return data_val
            else:
                websocket_info.invoke_id += 1
                return service_name[1]
        else:
            websocket_info.invoke_id += 1
            return None

    async def abort(self, websocket_info, callback, parameter):
        """
        Function used for sending getURCBValues request and awaiting its response
        """

        tpaa_request = create_tpaa_abort_request(websocket_info.invoke_id, websocket_info.associate_id)
        request = encode_tpaa_message(tpaa_request, websocket_info.is_ber_protocol)

        await websocket_info.websocket.send(request)

        response = await self.await_response(websocket_info.invoke_id)
        if response is not None:
            return response
        else:
            return None

    async def release(self, websocket_info, callback, parameter):
        """
        Function used for sending getURCBValues request and awaiting its response
        """

        tpaa_request = create_tpaa_release_request(websocket_info.invoke_id, websocket_info.associate_id)
        request = encode_tpaa_message(tpaa_request, websocket_info.is_ber_protocol)

        await websocket_info.websocket.send(request)

        response = await self.await_response(websocket_info.invoke_id)
        if response is not None:
            return response
        else:
            return None

    class ClientReportControlBlock:
        def __init__(self, objectReference, isBuffered):
            self.objectReference = objectReference
            self.isBuffered = isBuffered
            self.rptId = None
            self.rptEna = None
            self.resv = None
            self.dataSet = None
            self.confRev = None
            self.optFlds = None
            self.bufTm = None
            self.sqNum = None
            self.trgOps = None
            self.intgPd = None
            self.gi = None
            self.purgeBuf = None
            self.entryId = None
            self.timeOfEntry = None
            self.resvTms = None
            self.owner = None


def get_now_time():
    """
    Function used for getting the time of now in the format appropriate for timestamp
    """
    now = datetime.datetime.now()

    timestamp = {
        "secondSinceEpoch": int(now.timestamp()),  # UTC seconds since Unix epoch
        "fractionOfSecond": now.microsecond * 10,  # microseconds × 10
        "timeQuality": {
            "leapSecondsKown": False,
            "clockFailure": False,
            "clockNotSynchronized": False,
            "timeAccuracy": 3,  # Example value: ±1 ms
        },
    }
    return timestamp
