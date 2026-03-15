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
from importlib.resources import files

import asn1tools

logger = logging.getLogger(__name__)

# asn1_file_path = join(schema_path, "ws_iec61850_tpaa_full.asn")
ASN1_SCHEMA = files("ws61850.asn1.schema") / "ws_iec61850_tpaa_full.asn"

foo = asn1tools.compile_files([str(ASN1_SCHEMA)], codec="jer")
foo_ber = asn1tools.compile_files([str(ASN1_SCHEMA)], codec="ber")


def encode_tpaa_message(tpaa_request, is_ber=False):
    if is_ber:
        encoded_request: bytes = foo_ber.encode("TpaaPdu", tpaa_request)
        # byte_length = len(encoded_request)
        # print("the tpaa_request is: ", tpaa_request)
        # print(f"Encoded message length (BER): {byte_length} bytes")
        return_val = encoded_request
    else:
        encoded_request: bytes = foo.encode("TpaaPdu", tpaa_request)
        # jer_bytes = encoded_request
        # already bytes from asn1 tools
        # byte_length = len(jer_bytes)
        # print("the tpaa_request is: ", tpaa_request)
        # print(f"Encoded message length (JER): {byte_length} bytes")
        return_val = encoded_request.decode("utf-8")

    return return_val


def decode_tpaa_message(tpaa_message, is_ber=False):
    if is_ber:
        received_bytes = tpaa_message
        decoded_request = foo_ber.decode("TpaaPdu", received_bytes)
    else:
        received_bytes = tpaa_message.encode("utf-8")
        decoded_request = foo.decode("TpaaPdu", received_bytes)

    return decoded_request
