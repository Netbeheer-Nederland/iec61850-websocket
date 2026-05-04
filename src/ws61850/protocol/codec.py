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

from ws61850.asn1.encode_decode import decode_tpaa_message, encode_tpaa_message


class TpaaCodec:
    """Thin wrapper around ASN.1 encode/decode so callers depend on this interface, not the asn1 module."""

    def encode(self, message) -> bytes:
        return encode_tpaa_message(message)

    def decode(self, raw: bytes):
        return decode_tpaa_message(raw)
