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
import logging

from ws61850.protocol.codec import TpaaCodec
from ws61850.protocol.message_factory import TpaaMessageFactory
from ws61850.protocol.operations import OperationExecutor
from ws61850.shared.refs import build_fcd_ref

logger = logging.getLogger(__name__)

_factory = TpaaMessageFactory()
_codec = TpaaCodec()


def _executor(websocket) -> OperationExecutor:
    return OperationExecutor(_codec, websocket)


async def association_req_response(websocket, ap, maxMessageSize):
    """Sends an associateRequest and returns the raw response bytes."""
    msg = _factory.associate_request(ap, maxMessageSize)
    result = await _executor(websocket).call(msg, expects_response=True)
    return result.raw


async def getServerDirectory_req_response(websocket, invoke_id, associate_id):
    msg = _factory.get_server_directory(invoke_id, associate_id, "logicalDevice")
    result = await _executor(websocket).call(msg, invoke_id=invoke_id)
    return result.raw, invoke_id + 1


async def getLDDirectory_req_response(websocket, invoke_id, associate_id, ld_inst):
    msg = _factory.get_logical_device_directory(invoke_id, associate_id, ld_inst)
    result = await _executor(websocket).call(msg, invoke_id=invoke_id)
    return result.raw, invoke_id + 1


async def getLNDirectory_req_response(websocket, invoke_id, associate_id, ld_inst, ln_inst, mode):
    msg = _factory.get_logical_node_directory(
        invoke_id, associate_id, ld_inst + "/" + ln_inst, mode
    )
    result = await _executor(websocket).call(msg, invoke_id=invoke_id)
    return result.raw, invoke_id + 1


async def getDSDirectory_req_response(websocket, invoke_id, associate_id, ld_inst, ln_inst, ds_inst):
    msg = _factory.get_data_set_directory(
        invoke_id, associate_id, ld_inst + "/" + ln_inst + "." + ds_inst
    )
    result = await _executor(websocket).call(msg, invoke_id=invoke_id)
    return result.raw, invoke_id + 1


async def getDataDefinition_req_response(websocket, invoke_id, associate_id, obj_ref):
    msg = _factory.get_data_definition(invoke_id, associate_id, obj_ref)
    result = await _executor(websocket).call(msg, invoke_id=invoke_id)
    return result.raw, invoke_id + 1


async def getDataValues_req_response(websocket, invoke_id, associate_id, obj_ref, fc, includeElementName):
    msg = _factory.get_data_values(invoke_id, associate_id, build_fcd_ref(obj_ref, fc), includeElementName)
    result = await _executor(websocket).call(msg, invoke_id=invoke_id)
    return result.raw, invoke_id + 1


async def getBRCBValues_req_response(websocket, invoke_id, associate_id, obj_ref):
    msg = _factory.get_brcb_values(invoke_id, associate_id, obj_ref)
    result = await _executor(websocket).call(msg, invoke_id=invoke_id)
    return result.raw, invoke_id + 1


async def getURCBValues_req_response(websocket, invoke_id, associate_id, obj_ref):
    msg = _factory.get_urcb_values(invoke_id, associate_id, obj_ref)
    result = await _executor(websocket).call(msg, invoke_id=invoke_id)
    return result.raw, invoke_id + 1


async def setBRCBValues_req_response(websocket, invoke_id, associate_id, service_data):
    from ws61850.iec61850.client.request_handling import create_tpaa_request_setBRCBValuesRequest
    msg = create_tpaa_request_setBRCBValuesRequest(invoke_id, associate_id, service_data)
    result = await _executor(websocket).call(msg, invoke_id=invoke_id)
    return result.raw, invoke_id + 1


async def setURCBValues_req_response(websocket, invoke_id, associate_id, service_data):
    from ws61850.iec61850.client.request_handling import create_tpaa_request_setURCBValuesRequest
    msg = create_tpaa_request_setURCBValuesRequest(invoke_id, associate_id, service_data)
    result = await _executor(websocket).call(msg, invoke_id=invoke_id)
    return result.raw, invoke_id + 1


async def setDataValuse_req_response(websocket, invoke_id, associate_id, obj_ref, fc, value):
    msg = _factory.set_data_values(invoke_id, associate_id, build_fcd_ref(obj_ref, fc), value)
    result = await _executor(websocket).call(msg, invoke_id=invoke_id)
    return result.raw, invoke_id + 1


async def release_function(websocket, invoke_id, associate_id):
    msg = _factory.release_request(invoke_id, associate_id)
    result = await _executor(websocket).call(msg, invoke_id=invoke_id)
    logger.info("release response: ", result.raw)
    await websocket.close()
