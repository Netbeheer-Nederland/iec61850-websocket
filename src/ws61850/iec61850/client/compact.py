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

from ws61850.asn1.encode_decode import encode_tpaa_message
from ws61850.iec61850.client.reconstruct_tree_client import build_fcd_ref
from ws61850.iec61850.client.request_handling import create_tpaa_request_getServerDirectory, create_tpaa_request_getLDDirectory, \
    create_tpaa_request_getLogicalNodeDirectory, create_tpaa_request_getDataSetDirectoryRequest, \
    create_tpaa_request_getDataDefinition, create_tpaa_request_getDataValues, create_tpaa_request_setDataValues, \
    create_tpaa_request_getBRCBValuesRequest, \
    create_tpaa_request_setBRCBValuesRequest, create_tpaa_request_setURCBValuesRequest, \
    create_tpaa_request_getURCBValuesRequest, create_tpaa_release_request, create_tpaa_associate_request


async def association_req_response(websocket, ap, maxMessageSize):
    """
    Function used for sending association request and returning the response and increased invoke_id
    """
    tpaa_request = create_tpaa_associate_request(ap, maxMessageSize)
    request = encode_tpaa_message(tpaa_request)

    await websocket.send(request)
    response = await websocket.recv()

    return response


async def getServerDirectory_req_response(websocket, invoke_id, associate_id):
    """
    Function used for sending getServerDirectory request and returning the response and increased invoke_id
    """
    tpaa_request = create_tpaa_request_getServerDirectory(invoke_id, associate_id, "logicalDevice")

    request = encode_tpaa_message(tpaa_request)
    await websocket.send(request)

    response = await websocket.recv()

    invoke_id += 1

    return response, invoke_id


async def getLDDirectory_req_response(websocket, invoke_id, associate_id, ld_inst):
    """
    Function used for sending getLogicalDeviceDirectory request and returning the response and increased invoke_id
    """
    tpaa_request = create_tpaa_request_getLDDirectory(invoke_id, associate_id, ld_inst)

    request = encode_tpaa_message(tpaa_request)
    await websocket.send(request)

    response = await websocket.recv()
    invoke_id += 1

    return response, invoke_id


async def getLNDirectory_req_response(websocket, invoke_id, associate_id, ld_inst, ln_inst, mode):
    """
    Function used for sending getLogicalNodeDirectory request and returning the response and increased invoke_id
    """
    tpaa_request = create_tpaa_request_getLogicalNodeDirectory(invoke_id, associate_id,
                                                               ld_inst + "/" + ln_inst,
                                                               aCSIClass=mode)
    request = encode_tpaa_message(tpaa_request)
    await websocket.send(request)

    response = await websocket.recv()

    invoke_id += 1
    return response, invoke_id


async def getDSDirectory_req_response(websocket, invoke_id, associate_id, ld_inst, ln_inst, ds_inst):
    """
    Function used for sending getDataSetDirectory request and returning the response and increased invoke_id
    """
    tpaa_request = create_tpaa_request_getDataSetDirectoryRequest(invoke_id, associate_id,
                                                                  ld_inst + "/" + ln_inst + "." + ds_inst)

    request = encode_tpaa_message(tpaa_request)
    await websocket.send(request)

    response = await websocket.recv()

    invoke_id += 1
    return response, invoke_id


async def getDataDefinition_req_response(websocket, invoke_id, associate_id, obj_ref):
    """
    Function used for sending getDataDefinition request and returning the response and increased invoke_id
    """
    tpaa_request = create_tpaa_request_getDataDefinition(invoke_id, associate_id,
                                                         obj_ref)
    request = encode_tpaa_message(tpaa_request)
    await websocket.send(request)

    response = await websocket.recv()

    invoke_id += 1
    return response, invoke_id


async def getDataValues_req_response(websocket, invoke_id, associate_id, obj_ref, fc, includeElementName):
    """
    Function used for sending getDataValues request and returning the response and increased invoke_id
    """
    tpaa_request = create_tpaa_request_getDataValues(invoke_id, associate_id,
                                                     build_fcd_ref(obj_ref, fc), includeElementName)
    request = encode_tpaa_message(tpaa_request)

    await websocket.send(request)
    # print(f"Sent: {request}")

    response = await websocket.recv()

    invoke_id += 1
    return response, invoke_id


async def getBRCBValues_req_response(websocket, invoke_id, associate_id, obj_ref):
    """
    Function used for sending getBRCBValues request and returning the response and increased invoke_id
    """
    tpaa_request = create_tpaa_request_getBRCBValuesRequest(invoke_id, associate_id, obj_ref)
    request = encode_tpaa_message(tpaa_request)

    await websocket.send(request)
    # print(f"Sent: {request}")

    response = await websocket.recv()

    invoke_id += 1
    return response, invoke_id


async def getURCBValues_req_response(websocket, invoke_id, associate_id, obj_ref):
    """
    Function used for sending getBRCBValues request and returning the response and increased invoke_id
    """
    tpaa_request = create_tpaa_request_getURCBValuesRequest(invoke_id, associate_id, obj_ref)
    request = encode_tpaa_message(tpaa_request)

    await websocket.send(request)
    # print(f"Sent: {request}")

    response = await websocket.recv()

    invoke_id += 1
    return response, invoke_id


async def setBRCBValues_req_response(websocket, invoke_id, associate_id, service_data):
    """
    Function used for sending setBRCBValues request and returning the response and increased invoke_id
    """
    tpaa_request = create_tpaa_request_setBRCBValuesRequest(invoke_id, associate_id, service_data)
    request = encode_tpaa_message(tpaa_request)

    await websocket.send(request)
    # print(f"Sent: {request}")

    response = await websocket.recv()

    invoke_id += 1
    return response, invoke_id


async def setURCBValues_req_response(websocket, invoke_id, associate_id, service_data):
    """
    Function used for sending setBRCBValues request and returning the response and increased invoke_id
    """
    tpaa_request = create_tpaa_request_setURCBValuesRequest(invoke_id, associate_id, service_data)
    request = encode_tpaa_message(tpaa_request)

    await websocket.send(request)

    response = await websocket.recv()

    invoke_id += 1
    return response, invoke_id


async def setDataValuse_req_response(websocket, invoke_id, associate_id, obj_ref, fc, value):
    """
    Function used for sending setDataValues request and returning the response and increased invoke_id
    """
    tpaa_request = create_tpaa_request_setDataValues(invoke_id, associate_id, build_fcd_ref(obj_ref, fc), value)

    request = encode_tpaa_message(tpaa_request)
    await websocket.send(request)

    response = await websocket.recv()

    invoke_id += 1

    return response, invoke_id


async def release_function(websocket, invoke_id, associate_id):
    """
    Function used for sending release request and returning the response and increased invoke_id
    """
    tpaa_request = create_tpaa_release_request(invoke_id, associate_id)
    request = encode_tpaa_message(tpaa_request)

    await websocket.send(request)
    response = await websocket.recv()
    print("release response: ", response)
    await websocket.close()
